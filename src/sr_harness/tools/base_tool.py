# Copyright (c) 2026-present, Yumeow. Licensed under the MIT License.
"""Base tool abstraction, schema inference, and evaluation helpers for SRHarness tools."""
from __future__ import annotations
import re
import time
import warnings
from numbers import Real
import numpy as np
import sr_harness_engine as engine
from pathlib import Path
from logging import getLogger
from scipy import stats
from docstring_parser import DocstringStyle, parse
from abc import ABC, abstractmethod
from types import NoneType, UnionType
from inspect import Parameter, signature
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Literal, Union, get_args, get_origin, get_type_hints
from ..utils import FactoryMixin, log_exception
from ..core import AgentContext
from ..core.tool import ToolCallResult, ToolMetadata
from ..evaluator import utils as evaluator_utils
if TYPE_CHECKING:
    from ..skills import SkillManager

_logger = getLogger(f'sr_harness.{__name__}')

_ANSI_ESCAPE_RE = re.compile(
    r"(?:\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|(?:\x1b\[|\x9b)[0-?]*[ -/]*[@-~]|\x1b[@-_])"
)


class ToolRunAbort(RuntimeError):
    """Exception raised by a tool to abort execution and bypass ``BaseTool.__call__`` recovery."""


class BaseTool(ABC, FactoryMixin):
    """Abstract base class for all SRHarness tools.

    Subclasses register a tool name via ``@BaseTool.register(...)``, implement
    :meth:`execute` with simple JSON-serializable parameters, and optionally override
    :meth:`format_result_dict` to render concise text for the Agent. When
    ``metadata.description`` or ``metadata.parameters`` are omitted, ``BaseTool``
    infers them automatically from :meth:`execute`'s signature, type annotations,
    and Google-style docstring.
    """
    metadata: ToolMetadata = None
    MAX_FORMULA_LENGTH = 10000
    MAX_RESULT_STR_LENGTH = 64 * 1024
    FORMULA_DISPLAY_NUMBER_FORMAT = ".8g"

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Populate missing tool description and parameter schema when a subclass is defined.

        Args:
            **kwargs: Keyword arguments forwarded to ``super().__init_subclass__``.
        """
        super().__init_subclass__(**kwargs)
        if cls.metadata is None:
            cls.metadata = ToolMetadata()
        if cls.metadata.description is None:
            cls.metadata.description = cls.infer_tool_description()
        if cls.metadata.parameters is None:
            cls.metadata.parameters = cls.infer_tool_parameters()

    def __init__(self, context: AgentContext | None = None) -> None:
        """Initialize the tool with an execution context.

        Args:
            context: Runtime :class:`AgentContext` providing data splits, target, evaluator,
                and workspace. Defaults to an empty context when ``None``.

        Raises:
            TypeError: If ``context`` is neither an :class:`AgentContext` nor ``None``.
        """
        if context is not None and not isinstance(context, AgentContext):
            raise TypeError("context must be an AgentContext or None")
        self.context = context if context is not None else AgentContext()

    @classmethod
    def get_doc(cls) -> dict[str, str] | None:
        """Return optional skill documentation exposed by this tool at runtime.

        Returns:
            dict[str, str] | None: Skill mapping with ``name``, ``description``, and
            ``content``, or ``None`` if the tool does not expose a runtime skill.
        """
        return None

    @abstractmethod
    def execute(self) -> Dict[str, Any]:
        """Execute the tool logic on model-supplied arguments.

        Keep parameters simple and JSON-compatible; access dataset arrays, target metadata,
        and workspace state via ``self.context``. The summary before ``Args:`` becomes the
        default ``metadata.description``, and parameter descriptions under ``Args:`` populate
        the JSON Schema sent to the Agent.

        Returns:
            Dict[str, Any]: Structured execution output.
        """
        pass

    @classmethod
    def format_result_dict(cls, result: Dict[str, Any]) -> str:
        """Format the structured output of :meth:`execute` into concise text for the Agent.

        Args:
            result: Result dictionary returned by :meth:`execute`.

        Returns:
            str: Formatted text observation appended to the Agent conversation.
        """
        return str(result)

    def cancel(self) -> None:
        """Request cooperative cancellation of an in-flight tool invocation."""

    def __call__(self, *args, **kwargs) -> ToolCallResult:
        """Run :meth:`execute`, format the result, and capture timing and error metadata.

        Args:
            *args: Positional arguments forwarded to :meth:`execute`.
            **kwargs: Keyword arguments forwarded to :meth:`execute`.

        Returns:
            ToolCallResult: Wrapped execution status, raw dictionary, formatted text, and metadata.
        """
        start_time = time.time()
        try:
            cancellation_event = getattr(self, "cancel_event", None)
            if cancellation_event is not None and cancellation_event.is_set():
                raise InterruptedError("用户强制中止")
            result = self.execute(*args, **kwargs)
            if cancellation_event is not None and cancellation_event.is_set():
                raise InterruptedError("用户强制中止")
            if not isinstance(result, dict):
                _logger.critical(f"Tool {self.metadata.name} execute() should return a dict, but got {type(result)}, please check the implementation.")
            result_str = self.format_result_dict(result)
            result_str = self.truncate_result_str(_ANSI_ESCAPE_RE.sub("", str(result_str)))
            meta_data = {
                "timestamp": start_time,
                "execution_time": time.time() - start_time,
                "tool": self.metadata.name
            }
            return ToolCallResult(ok=True, result=result, result_str=result_str, meta_data=meta_data)
        except ToolRunAbort:
            raise
        except Exception as e:
            _logger.error(f"Error executing {self.metadata.name}: {log_exception(e)}")
            exception_message = str(e).strip() or repr(e)
            error_msg = (
                f"Error executing {self.metadata.name}:\n"
                f"    {type(e).__name__}: {exception_message}"
            )
            error_msg = self.truncate_result_str(_ANSI_ESCAPE_RE.sub("", error_msg))
            meta_data = {
                "timestamp": start_time,
                "execution_time": time.time() - start_time,
                "tool": self.metadata.name
            }
            return ToolCallResult(ok=False, result={'error': error_msg}, result_str=error_msg, meta_data=meta_data)

    @classmethod
    def normalize_formula(cls, eq: str, *, strip_modules: bool = True) -> str:
        """Validate and normalize an Agent-supplied formula string prior to parsing.

        Replaces ``^`` with ``**`` and optionally strips ``np.``, ``numpy.``, and ``math.`` prefixes.

        Args:
            eq: Raw formula string provided by the Agent.
            strip_modules: Whether to strip common Python math module prefixes.

        Returns:
            str: Normalized formula string ready for :mod:`sr_harness_engine`.
        """
        if not isinstance(eq, str):
            raise TypeError(f"Formula must be a string, got {type(eq).__name__}.")
        eq = eq.strip()
        if len(eq) > cls.MAX_FORMULA_LENGTH:
            raise ValueError(
                f"Formula is too long: {len(eq)} characters; "
                f"maximum allowed is {cls.MAX_FORMULA_LENGTH}."
            )
        eq = eq.replace("^", "**")
        if strip_modules:
            eq = eq.replace("np.", "").replace("numpy.", "").replace("math.", "")
        return eq

    @classmethod
    def parse_formula(cls, eq: str) -> engine.Expression:
        """Normalize and parse a formula string with built-in ``pi`` and ``e`` constants.

        Args:
            eq: Formula string to parse.

        Returns:
            engine.Expression: Parsed symbolic expression tree.
        """
        return engine.parse(
            cls.normalize_formula(eq),
            symbols={"pi": np.pi, "e": np.e},
        )

    @classmethod
    def truncate_result_str(cls, text: str) -> str:
        """Truncate formatted tool output to ``MAX_RESULT_STR_LENGTH`` characters.

        Args:
            text: Formatted tool output string.

        Returns:
            str: Original string or truncated prefix with an omitted-character count.
        """
        text = str(text)
        limit = cls.MAX_RESULT_STR_LENGTH
        if len(text) <= limit:
            return text
        suffix = "... (characters ignored)"
        keep = max(0, limit - len(suffix) - 32)
        ignored = len(text) - keep
        suffix = f"... ({ignored} characters ignored)"
        keep = max(0, limit - len(suffix))
        ignored = len(text) - keep
        suffix = f"... ({ignored} characters ignored)"
        return text[: max(0, limit - len(suffix))] + suffix

    @classmethod
    def to_tool_list(cls, tools_used: list[str] | None = None) -> list[dict]:
        """Build OpenAI-compatible function-tool definitions for selected registered tools.

        Args:
            tools_used: Optional list of tool names to include. Includes all registered tools when ``None``.

        Returns:
            list[dict]: OpenAI-format tool definitions.
        """
        tool_list = []
        for name, tool_cls in cls.REGISTRY_DICT.items():
            if tools_used is None or tool_cls.metadata.name in tools_used:
                tool_list.append(tool_cls.to_dict())
        return tool_list

    @classmethod
    def load_tool_list(cls, tools_used: list[str] | None = None) -> list[dict]:
        """Load flat tool metadata dictionaries for prompt-based tool parsers.

        Args:
            tools_used: Optional list of tool names to include. Includes all registered tools when ``None``.

        Returns:
            list[dict]: Dictionaries containing ``name``, ``description``, and ``parameters``.
        """
        tool_list = []
        for name, tool_cls in cls.REGISTRY_DICT.items():
            if tools_used is None or tool_cls.metadata.name in tools_used:
                tool_list.append({
                    "name": tool_cls.metadata.name,
                    "description": tool_cls.metadata.description,
                    "parameters": tool_cls.metadata.parameters,
                })
        return tool_list

    @classmethod
    def load_tool_classes(cls, tools_used: list[str] | None = None) -> list[type["BaseTool"]]:
        """Return registered :class:`BaseTool` subclasses matching ``tools_used``.

        Args:
            tools_used: Optional list of tool names to include. Includes all registered tools when ``None``.

        Returns:
            list[type[BaseTool]]: Selected tool classes.
        """
        tool_list = []
        for name, tool_cls in cls.REGISTRY_DICT.items():
            if tools_used is None or tool_cls.metadata.name in tools_used:
                tool_list.append(tool_cls)
        return tool_list

    @classmethod
    def load_custom_tool(cls, source: str, *, path: str | Path) -> dict:
        """Validate and register a sandboxed custom tool from Python source code.

        Args:
            source: Python source code defining a single :class:`BaseTool` subclass.
            path: Path to the ``tool.py`` file for diagnostics and reload tracking.

        Returns:
            dict: Registration details including ``tool_name``, ``path``, ``class_name``, and ``tool_class``.
        """
        path = Path(path).resolve()
        if path.suffix != ".py":
            raise ValueError(f"Custom tool source must be a Python file: {path}")
        from .sandboxed_custom_tool import create_sandboxed_custom_tool

        for registered_name, registered_cls in list(cls.REGISTRY_DICT.items()):
            if getattr(registered_cls, "source_path", None) == path:
                del cls.REGISTRY_DICT[registered_name]
        registry_before = dict(cls.REGISTRY_DICT)
        try:
            if len(source) > 50_000:
                raise ValueError("Custom tool source exceeds 50000 characters")
            # Parsing is side-effect free and preserves a useful SyntaxError for authors;
            # importing and inspecting the module still happens only in the sandbox.
            compile(source, str(path), "exec", dont_inherit=True)
            tool_cls = create_sandboxed_custom_tool(source, path)
            tool_name = tool_cls.metadata.name.strip()
            if tool_name in registry_before:
                raise ValueError(f"Tool name '{tool_name}' is already registered.")
            cls.register(tool_name)(tool_cls)
            return {
                "tool_name": tool_name,
                "path": str(path),
                "class_name": tool_cls.__name__,
                "tool_class": tool_cls,
            }
        except Exception:
            cls.REGISTRY_DICT.clear()
            cls.REGISTRY_DICT.update(registry_before)
            raise

    @classmethod
    def discover_custom_tools(cls, skill_manager: SkillManager) -> list[type["BaseTool"]]:
        # 将 skill_manager 中发现的自定义工具注册到 BaseTool，并返回 tool class list
        """Load and register all custom tools found in ``skill_manager``.

        Args:
            skill_manager: Skill manager used to scan ``tool.py`` files across skills.

        Returns:
            list[type[BaseTool]]: Registered sandbox-proxy tool classes.
        """
        custom_tool_cls_list = []
        for skill, source in skill_manager.load_tool_skills():
            tool_path = skill.skill_directory / "tool.py"
            try:
                loaded = cls.load_custom_tool(source, path=tool_path)
                custom_tool_cls_list.append(cls.REGISTRY_DICT[loaded["tool_name"]])
            except Exception as e:
                _logger.warning(f"Skipping custom tool {tool_path}: {log_exception(e)}")
        return custom_tool_cls_list

    @classmethod
    def to_dict(cls) -> dict:
        """Export this tool class as an OpenAI function-calling schema dictionary.

        Returns:
            dict: OpenAI ``{"type": "function", "function": ...}`` schema.
        """
        return {
            "type": "function",
            "function": {
                "name": cls.metadata.name,
                "description": cls.metadata.description,
                "parameters": cls.metadata.parameters
            },
        }

    @classmethod
    def infer_tool_description(cls) -> str:
        """Extract the tool description from the text preceding ``Args:`` in :meth:`execute`.

        Returns:
            str: Inferred tool description, or ``"(no description provided)"`` if empty.
        """
        doc = getattr(cls.execute, "__doc__", None) or ""
        description_lines = []
        for line in doc.splitlines():
            line = line.strip()
            if line == "Args:":
                break
            if line:
                description_lines.append(line)
        return "\n".join(description_lines) if description_lines else "(no description provided)"

    @classmethod
    def infer_tool_parameters(cls) -> Dict[str, Any]:
        """Infer a JSON Schema parameter object from :meth:`execute`'s signature and docstring.

        Returns:
            Dict[str, Any]: JSON Schema ``object`` definition with ``properties`` and ``required``.
        """
        properties = {}
        required = []

        try:
            sig = signature(cls.execute)
            type_hints = get_type_hints(cls.execute)
            descriptions = cls.parse_args_docstring(cls.execute)
        except Exception as e:
            _logger.warning(f"Failed to parse signature or type hints for {cls.__name__} since [{type(e).__name__}] {e}")
            return {}

        for param_name, param in sig.parameters.items():
            if param_name == 'self':
                continue
            if param.kind in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD):
                _logger.warning(
                    f"Parameter '{param_name}' in {cls.__name__}.execute is a variable positional or keyword parameter, "
                    f"which is not supported for automatic schema inference and will be ignored. "
                    f"Please specify its schema manually in ToolMetadata.parameters if needed."
                )
                continue

            schema = {}
            annotation = type_hints.get(param_name, param.annotation) # e.g., List[int], Optional[str], etc.
            schema |= cls.parse_args_typehints(annotation) # e.g., {"type": "array", "items": {"type": "integer"}} for List[int]
            schema |= {'description': descriptions[param_name]}
            if param.default is not Parameter.empty:
                schema |= {'default': param.default}
            else:
                required.append(param_name)
            properties[param_name] = schema

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    @staticmethod
    def parse_args_docstring(func: callable) -> dict[str, str]:
        """Parse parameter descriptions from a callable's Google-style docstring.

        Args:
            func: Callable whose docstring should be parsed.

        Returns:
            dict[str, str]: Mapping from parameter name to its description text.
        """
        docstring = getattr(func, "__doc__", None)
        parsed = parse(docstring, style=DocstringStyle.GOOGLE)
        description_dict = {}
        for param in parsed.params:
            if param.description is not None:
                description_dict[param.arg_name] = param.description
        set1 = set(description_dict.keys())
        set2 = set(signature(func).parameters.keys()) - {"self"}
        if set1 - set2:
            _logger.warning(
                f"Descriptions found for parameters {set1 - set2} in {func.__qualname__} docstring, "
                f"but these parameters are not in the function signature. Please check for typos or remove these descriptions."
            )
        if set2 - set1:
            _logger.warning(
                f"Parameters {set2 - set1} in {func.__qualname__} signature do not have descriptions in the docstring. "
                f"Please add descriptions for better LLM understanding."
            )
            description_dict = description_dict | {param: "(no description provided)" for param in set2 - set1}
        return description_dict

    @classmethod
    def parse_args_typehints(cls, annotation: Any) -> Dict[str, Any]:
        """Convert a Python type annotation into a JSON Schema fragment.

        Args:
            annotation: Type annotation from :meth:`execute`.

        Returns:
            Dict[str, Any]: Corresponding JSON Schema type definition.
        """
        if annotation is Parameter.empty or annotation is Any:
            return {}

        origin = get_origin(annotation) # e.g., list, dict, Union, etc.
        args = get_args(annotation) #  e.g., (int,) for List[int], (str, NoneType) for Optional[str], etc.

        if origin is Literal:
            values = list(args)
            schema = {"enum": values}
            if non_none_values := [v for v in values if v is not None]:
                schema["type"] = cls.parse_json_type(type(non_none_values[0]))
            return schema
        elif origin is list:
            return {"type": "array", "items": cls.parse_args_typehints(args[0] if args else Any)}
        elif origin is dict:
            return {"type": "object"}
        elif origin is tuple:
            # Tuple without type args
            if not args:
                return {"type": "array", "items": {}}
            # Variable-length tuple, e.g. Tuple[str, ...]
            elif args[-1] is Ellipsis:
                return {"type": "array", "items": cls.parse_args_typehints(args[0] if args else Any)}
            item_schemas = [cls.parse_args_typehints(arg) for arg in args]
            # Homogeneous fixed tuple, e.g. Tuple[str, str]
            if all(schema == item_schemas[0] for schema in item_schemas):
                return {"type": "array", "items": item_schemas[0], "minItems": len(args), "maxItems": len(args)}
            # Heterogeneous fixed tuple, e.g. Tuple[str, int]
            else:
                # This is less position-strict than prefixItems, but more compatible with OpenAI/Azure/OpenRouter tool schemas.
                # It means each item may match any of the tuple element schemas, while minItems/maxItems still enforce tuple length.
                _logger.warning(
                    f"Tuple parameter with heterogeneous types detected in {cls.__name__}.execute. "
                    f"This is not recommended since it may lead to less precise schema and LLM confusion. "
                    f"Please consider using a more specific schema or adding descriptions to clarify the expected format."
                )
                return {"type": "array", "items": {"anyOf": item_schemas}, "minItems": len(args), "maxItems": len(args)}
        elif origin in (Union, UnionType):
            schemas = [{"type": "null"} if arg is NoneType else cls.parse_args_typehints(arg) for arg in args]
            return {"anyOf": schemas}
        elif json_type := cls.parse_json_type(annotation):
            return {"type": json_type}
        else:
            _logger.warning(
                f"Unsupported type annotation '{annotation}' in {cls.__name__}.execute. "
                f"Automatic schema inference will not be able to parse this type, and it will be treated as an untyped parameter. "
                f"Please consider using basic types (int, float, str, bool) or common generics (List, Dict) for better compatibility, "
                f"or directly specify the parameter schema in ToolMetadata.parameters if a more complex structure is needed."
            )
            return {}

    @staticmethod
    def parse_json_type(value_type: Any) -> str:
        """Map a primitive Python type to its JSON Schema type name.

        Args:
            value_type: Python type object (e.g., ``int``, ``float``, ``str``, ``bool``).

        Returns:
            str: JSON Schema type name, or an empty string if unsupported.
        """
        if value_type is bool:
            return "boolean"
        if value_type is int:
            return "integer"
        if value_type is float:
            return "number"
        if value_type is str:
            return "string"
        if value_type is list:
            return "array"
        if value_type is dict:
            return "object"
        return ""

    @classmethod
    def calculate_metrics(cls, f: engine.Expression, y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, Any]:
        """Compute standard regression and complexity metrics from target and prediction arrays.

        Args:
            f: Symbolic expression used to compute structural complexity.
            y_true: Ground-truth target array.
            y_pred: Predicted target array.

        Returns:
            Dict[str, Any]: Regression metrics including MSE, RMSE, MAE, R2, AIC, BIC, correlations, and complexity.
        """
        return evaluator_utils.regression_metrics(f, y_true, y_pred)

    def evaluate(
        self,
        f: engine.Expression,
        y: engine.Expression,
        show_diagnostics: bool = True,
        fit: bool = False,
    ) -> Dict[str, Any]:
        """Evaluate a symbolic formula ``f`` against target expression ``y`` across data splits.

        Args:
            f: Candidate symbolic expression for the right-hand side.
            y: Target symbolic expression for the left-hand side.
            show_diagnostics: Whether to include worst-sample and residual-correlation diagnostics.
            fit: Whether to optimize scalar parameters on the training split before scoring.

        Returns:
            Dict[str, Any]: Evaluation dictionary with ``formula``, ``target_expression``,
            ``is_candidate``, ``candidate_ineligibility_reasons``, and ``data_split_results``.
        """
        if not isinstance(f, engine.Expression) or not isinstance(y, engine.Expression):
            raise TypeError("f and y must both be sr_harness_engine.Expression instances.")
        if self.context.target is None:
            raise ValueError("context.target must be configured before evaluating formulas")

        evaluator = self.context.evaluator

        target = self.context.target
        var_names = {var.name for var in f.iter_preorder() if isinstance(var, engine.Variable)}
        ineligibility_reasons = []
        if y.to_str() != target:
            ineligibility_reasons.append(f"the left-hand side of the equation is not {target}")
        if target in var_names:
            ineligibility_reasons.append(f"the right-hand side of the equation depends on {target}")
        is_candidate = not ineligibility_reasons

        isolated_evaluation = getattr(evaluator, "_evaluate_formula_isolated", None)
        isolated_metrics = None
        if isolated_evaluation is not None:
            fitted_f, isolated_metrics, isolated_splits = isolated_evaluation(
                f, y, self.context, fit=fit, candidate=is_candidate,
            )
            train_context = isolated_splits["train"]
            validation_context = isolated_splits["validation"]
            self.context._split_cache = isolated_splits
        else:
            train_context = self.context.train_split
            validation_context = self.context.validation_split

        fitted_f = fitted_f if isolated_metrics is not None else f
        if fit and isolated_metrics is None:
            fitted_f = (
                evaluator.fit_candidate(f, train_context)
                if is_candidate
                else evaluator.fit(f, y, train_context)
            )
            if not isinstance(fitted_f, engine.Expression):
                raise TypeError(f"{type(evaluator).__name__}.fit() must return an Expression")
        if missing := engine.unbound_parameters(fitted_f):
            raise ValueError(f"unbound parameters: {', '.join(missing)}")

        def evaluate_split(split_context: AgentContext, *, max_samples: int | None = None):
            result = isolated_metrics.get("train" if split_context is train_context else "validation") if isolated_metrics is not None else (
                evaluator.evaluate_candidate(fitted_f, split_context)
                if is_candidate
                else evaluator.evaluate(fitted_f, y, split_context)
            )
            if not isinstance(result, dict):
                raise TypeError(f"{type(evaluator).__name__}.evaluate() must return a dictionary")
            metrics = {}
            for name, value in result.items():
                if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
                    raise TypeError(f"Evaluator metric {name!r} must be a float or int")
                metrics[str(name)] = value.item() if isinstance(value, np.generic) else value
            split = {"metrics": metrics}
            if show_diagnostics:
                num_nodes = split_context.num_nodes
                split["diagnostics"] = self.residual_diagnostics(
                    y_true=np.asarray(y.eval(split_context.data, num_nodes=num_nodes)),
                    y_pred=np.asarray(fitted_f.evaluate(split_context.data, num_nodes=num_nodes)),
                    data=split_context.data,
                    target_expression=y.to_str(),
                    **({"max_samples": max_samples} if max_samples is not None else {}),
                )
            return split

        data_split_results = {"train": evaluate_split(train_context, max_samples=10)}
        if validation_context.data:
            data_split_results["validation"] = evaluate_split(validation_context)
        for split_name, split_result in data_split_results.items():
            metrics = split_result.get("metrics") or {}
            if not np.isfinite(metrics.get("mse", float("nan"))):
                ineligibility_reasons.append(
                    f"the formula does not produce a finite MSE on the {split_name} set"
                )
        evaluation = {
            "formula": fitted_f.to_str(number_format='.8g'),
            "target_expression": y.to_str(number_format='.8g'),
            "is_candidate": not ineligibility_reasons,
            "candidate_ineligibility_reasons": ineligibility_reasons,
            "data_split_results": data_split_results,
        }
        return evaluation

    def failed_evaluation(self, formula: str = "(None)") -> Dict[str, Any]:
        """Build a fallback evaluation result with infinite error metrics when fitting fails.

        Args:
            formula: Placeholder formula string to report.

        Returns:
            Dict[str, Any]: Non-candidate evaluation dictionary with ``inf``/``-inf`` metrics.
        """
        empty_metrics = {
            "mse": float("inf"),
            "rmse": float("inf"),
            "mae": float("inf"),
            "mape": float("inf"),
            "r2": -float("inf"),
            "aic": float("inf"),
            "bic": float("inf"),
            "pearson_r": -float("inf"),
            "spearman_r": -float("inf"),
            "complexity": float("inf"),
        }
        data_split_results = {
            'train': {'metrics': None},
            'validation': {'metrics': None},
        }
        if self.context.target is None:
            raise ValueError("context.target must be configured before reporting a failed evaluation")
        data_split_results['train']['metrics'] = empty_metrics
        if not self.context.validation_split.data:
            data_split_results.pop('validation')
        else:
            data_split_results['validation']['metrics'] = empty_metrics
        return {
            "formula": formula,
            "target_expression": self.context.target,
            "is_candidate": False,
            "candidate_ineligibility_reasons": ["no valid formula was produced"],
            "data_split_results": data_split_results,
        }

    @classmethod
    def format_evaluation_result(cls, result: Dict[str, Any], title: str = "Formula evaluation") -> str:
        """Render a standardized evaluation dictionary into a compact report for the Agent.

        Args:
            result: Evaluation dictionary returned by :meth:`evaluate`.
            title: Section title displayed at the top of the report.

        Returns:
            str: Formatted fit metrics, eligibility notes, worst samples, and residual correlations.
        """
        split_results = result["data_split_results"]
        train_result = split_results["train"]
        metrics = train_result["metrics"]
        lhs = result.get("target_expression", "LHS")
        formula = result["formula"]
        try:
            formula = engine.parse(formula).to_str(
                number_format=cls.FORMULA_DISPLAY_NUMBER_FORMAT
            )
        except Exception:
            # Some tools use a free-form model description instead of an
            # SRHarness Engine expression. Preserve those descriptions verbatim.
            pass
        lines = [
            f"{title}:",
            f"    {lhs} = {formula}",
        ]
        for reason in result.get("candidate_ineligibility_reasons", []):
            lines.append(f"    (Note: this formula is not eligible for submission since {reason}.)")
        validation_result = split_results.get("validation")
        validation_metrics = validation_result["metrics"] if validation_result else None

        def three_significant_digits(value: Any) -> str:
            if isinstance(value, (int, float, np.number)):
                return format(value, "#.3g").removesuffix(".")
            return str(value)

        def metric_pair(name: str) -> str:
            train_value = three_significant_digits(metrics.get(name, float("nan")))
            validation_value = (
                three_significant_digits(validation_metrics.get(name, float("nan")))
                if validation_metrics else "N/A"
            )
            return f"{train_value} | {validation_value}"

        lines.extend([
            "Fit quality (Train-set | Validation-set):",
            f"    RMSE={metric_pair('rmse')};",
            f"    MAE={metric_pair('mae')};",
            f"    R2={metric_pair('r2')};",
            f"    Formula Complexity={three_significant_digits(metrics.get('complexity', '?'))};",
        ])
        standard_metric_names = {
            "mse", "rmse", "mae", "mape", "r2", "aic", "bic",
            "pearson_r", "spearman_r", "complexity",
        }
        custom_metric_names = sorted(
            (set(metrics) | set(validation_metrics or {})) - standard_metric_names
        )
        if custom_metric_names:
            lines.append("Evaluator-specific metrics (Train-set | Validation-set):")
            lines.extend(
                f"    {name}={metric_pair(name)};" for name in custom_metric_names
            )
        if validation_metrics:
            train_rmse = metrics.get("rmse", float("nan"))
            validation_rmse = validation_metrics.get("rmse", float("nan"))
            if (np.isfinite(train_rmse) and np.isfinite(validation_rmse)
                    and validation_rmse > max(2.0 * train_rmse, train_rmse + 1e-12)):
                lines.append(
                    "Warning: validation error is substantially larger than training error; "
                    "the candidate may be overfitting or the validation domain may differ."
                )
        if diagnostics := train_result.get("diagnostics"):
            samples = diagnostics.get("worst_samples", [])[:10]
            if samples:
                input_names = result.get("analyzed_input_expressions") or [
                    name for name in samples[0]["row"] if name != lhs
                ]
                lines.extend([
                    "Error extremes (Top-10 sorted by |residual|):",
                    f"    ({' | '.join([*input_names, lhs, 'residual'])})",
                ])
                for sample in samples:
                    values = [sample["row"].get(name, float("nan")) for name in input_names]
                    values.extend([sample["y_true"], sample["y_pred"] - sample["y_true"]])
                    lines.append("    " + " | ".join(three_significant_digits(value) for value in values))
            if correlations := diagnostics.get("strongest_residual_correlations"):
                strongest = correlations[0]
                lines.extend([
                    "Largest residual correlation among other analyzed variables "
                    "(criterion=max(|Pearson|, |Spearman|)):",
                    f"    variable={strongest['variable']}",
                    f"    Pearson(residual, {strongest['variable']})={three_significant_digits(strongest['pearson'])};",
                    f"    Spearman(residual, {strongest['variable']})={three_significant_digits(strongest['spearman'])};",
                ])
        return "\n".join(lines)

    @classmethod
    def residual_diagnostics(
        cls,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        data: Dict[str, Any] = None,
        target_expression: str = None,
        max_samples: int = 3,
        max_correlations: int = 5,
    ) -> Dict[str, Any]:
        """Compute error quantiles, worst-predicted samples, and residual-feature correlations.

        Args:
            y_true: Ground-truth target values.
            y_pred: Model-predicted values.
            data: Optional dictionary of variables to correlate against residuals.
            target_expression: Optional target expression name to include in correlation checks.
            max_samples: Maximum number of high-error samples to return.
            max_correlations: Maximum number of residual correlations to return.

        Returns:
            Dict[str, Any]: Dictionary with ``error_profile``, ``worst_samples``, and ``strongest_residual_correlations``.
        """
        y_true, y_pred = np.broadcast_arrays(
            np.asarray(y_true, dtype=float),
            np.asarray(y_pred, dtype=float),
        )
        y_true = y_true.flatten()
        y_pred = y_pred.flatten()
        residual = y_pred - y_true
        absolute_error = np.abs(residual)
        finite_error = np.isfinite(residual)

        target_scale = float(np.median(np.abs(y_true[np.isfinite(y_true)]))) if np.any(np.isfinite(y_true)) else 0.0
        relative_floor = max(np.finfo(float).eps, target_scale * 1e-12)
        relative_valid = finite_error & np.isfinite(y_true) & (np.abs(y_true) > relative_floor)
        relative_error = np.full_like(absolute_error, np.nan, dtype=float)
        relative_error[relative_valid] = absolute_error[relative_valid] / np.abs(y_true[relative_valid])

        finite_absolute = absolute_error[finite_error]
        finite_relative = relative_error[np.isfinite(relative_error)]
        error_profile = {
            "median_signed_residual": float(np.median(residual[finite_error])) if np.any(finite_error) else float("nan"),
            "p95_absolute_error": float(np.quantile(finite_absolute, 0.95)) if finite_absolute.size else float("nan"),
            "max_absolute_error": float(np.max(finite_absolute)) if finite_absolute.size else float("nan"),
            "p95_relative_error": float(np.quantile(finite_relative, 0.95)) if finite_relative.size else float("nan"),
            "max_relative_error": float(np.max(finite_relative)) if finite_relative.size else float("nan"),
            "relative_error_defined_ratio": float(np.mean(relative_valid)),
        }

        numeric_data = {}
        for name, values in (data or {}).items():
            array = np.asarray(values)
            if array.size == y_true.size and np.issubdtype(array.dtype, np.number):
                numeric_data[name] = array.flatten()

        rank_score = np.where(finite_error, absolute_error, -np.inf)
        sample_limit = max(0, int(max_samples))
        worst_indices = (
            np.argsort(rank_score)[-sample_limit:][::-1]
            if sample_limit else np.array([], dtype=int)
        )
        worst_samples = []
        for index in worst_indices:
            if not np.isfinite(rank_score[index]):
                continue
            worst_samples.append({
                "index": int(index),
                "row": {name: float(values[index]) for name, values in numeric_data.items()},
                "y_true": float(y_true[index]),
                "y_pred": float(y_pred[index]),
                "absolute_error": float(absolute_error[index]),
                "relative_error": float(relative_error[index]),
            })

        correlation_arrays = dict(numeric_data)
        if target_expression and target_expression not in correlation_arrays:
            correlation_arrays[target_expression] = y_true
        correlations = []
        for name, values in correlation_arrays.items():
            pearson, spearman = cls.correlation_coefficients(values, residual)
            strength = max(abs(pearson), abs(spearman))
            if np.isfinite(strength):
                correlations.append({
                    "variable": name,
                    "pearson": pearson,
                    "spearman": spearman,
                    "strength": strength,
                })
        correlations.sort(key=lambda item: item["strength"], reverse=True)

        return {
            "error_profile": error_profile,
            "worst_samples": worst_samples,
            "strongest_residual_correlations": correlations[:max(0, int(max_correlations))],
        }

    @staticmethod
    def correlation_coefficients(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
        """Compute finite-sample Pearson linear and Spearman rank correlations.

        Args:
            x: First 1D numeric array.
            y: Second 1D numeric array.

        Returns:
            tuple[float, float]: ``(pearson_r, spearman_r)``, or ``(nan, nan)`` when undefined.
        """
        x = np.asarray(x, dtype=float).flatten()
        y = np.asarray(y, dtype=float).flatten()
        finite = np.isfinite(x) & np.isfinite(y)
        if np.count_nonzero(finite) < 2:
            return float("nan"), float("nan")
        x, y = x[finite], y[finite]
        with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore")
            pearson = float(np.corrcoef(x, y)[0, 1])
            spearman = float(stats.spearmanr(x, y).statistic)
        return pearson, spearman


def is_numeric_array(data: List[Any]) -> bool:
    """Check whether an array-like object has an integer or floating-point NumPy dtype.

    Args:
        data: Array-like object to inspect.

    Returns:
        bool: ``True`` if ``np.asarray(data)`` has an integer or floating-point dtype.
    """
    arr = np.asarray(data)
    return np.issubdtype(arr.dtype, np.integer) or np.issubdtype(arr.dtype, np.floating)
