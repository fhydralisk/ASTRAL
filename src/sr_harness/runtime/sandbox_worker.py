"""Private entry point executed inside the Landlock sandbox."""

from __future__ import annotations

import argparse
import contextlib
import inspect
import io
import json
import os
import resource
import sys
import traceback
import types
from pathlib import Path
from typing import Any

import numpy as np

_SOURCE_ROOT = Path(__file__).resolve().parents[2]
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))

# The public package initializer imports model-provider SDKs that are irrelevant
# inside the evaluator sandbox. Register a normal package shell so importing
# trusted evaluator submodules does not execute that broad initializer.
if "sr_harness" not in sys.modules:
    package = types.ModuleType("sr_harness")
    package.__package__ = "sr_harness"
    package.__path__ = [str(_SOURCE_ROOT / "sr_harness")]
    sys.modules["sr_harness"] = package


class LimitedWriter(io.StringIO):
    """In-memory text stream writer that truncates output once a character limit is reached."""

    SUFFIX = "...[truncated]"

    def __init__(self, limit: int) -> None:
        """Initialize the bounded writer with a maximum character capacity.

        Args:
            limit: Maximum number of characters to retain.
        """
        super().__init__()
        self.limit = limit

    def write(self, text: str) -> int:
        """Append text up to the remaining character budget.

        Args:
            text: String chunk to write.

        Returns:
            int: Length of ``text`` passed by the caller.
        """
        remaining = self.limit - self.tell() - len(self.SUFFIX)
        if remaining <= 0:
            return len(text)
        if len(text) > remaining:
            super().write(text[:remaining])
            super().write(self.SUFFIX)
            return len(text)
        return super().write(text)


def load_array_groups(root: Path) -> dict[str, dict[str, np.ndarray]]:
    """Load serialized NumPy array groups prepared by the parent process.

    Args:
        root: Directory containing ``manifest.json`` and ``.npy`` files for each group.

    Returns:
        dict[str, dict[str, np.ndarray]]: Nested mapping of group names to variable arrays.
    """
    manifest = json.loads((root / "arrays.json").read_text(encoding="utf-8"))
    return {
        group_name: {
            name: np.load(root / "arrays" / filename, mmap_mode="c", allow_pickle=False)
            for name, filename in values.items()
        }
        for group_name, values in manifest.items()
    }


def save_array_groups(root: Path, groups: dict[str, dict[str, Any]]) -> None:
    """Write named groups of NumPy arrays to ``root`` for safe reading by the parent process.

    Args:
        root: Destination directory where ``manifest.json`` and ``.npy`` files are written.
        groups: Mapping of group names to dictionaries of NumPy arrays.
    """
    array_root = root / "arrays"
    array_root.mkdir(exist_ok=True)
    manifest: dict[str, dict[str, str]] = {}
    index = 0
    for group_name, values in groups.items():
        manifest[group_name] = {}
        for name, value in values.items():
            array = np.asarray(value)
            if array.dtype.hasobject:
                raise TypeError(f"Sandbox result array {name!r} must not use object dtype")
            filename = f"array-{index}.npy"
            np.save(array_root / filename, array, allow_pickle=False)
            manifest[group_name][str(name)] = filename
            index += 1
    (root / "arrays.json").write_text(json.dumps(manifest), encoding="utf-8")


def apply_resource_limits(request: dict[str, Any]) -> None:
    """Enforce RLIMIT CPU time, address space, file size, and open-descriptor caps in the worker process.

    Args:
        request: Sandbox request dictionary specifying resource limits.
    """
    timeout_seconds = max(1, int(request["timeout_seconds"]))
    memory_limit_mb = max(64, int(request["memory_limit_mb"]))
    try:
        pages = int(Path("/proc/self/statm").read_text().split()[0])
        current_address_space = pages * os.sysconf("SC_PAGE_SIZE")
    except Exception:
        current_address_space = 0
    memory_bytes = max(memory_limit_mb * 1024 * 1024, current_address_space + 256 * 1024 * 1024)
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    resource.setrlimit(resource.RLIMIT_DATA, (memory_bytes, memory_bytes))
    resource.setrlimit(resource.RLIMIT_CPU, (timeout_seconds, timeout_seconds + 1))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    file_size_limit = min(memory_limit_mb, 1024) * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_FSIZE, (file_size_limit, file_size_limit))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))


def execute_program(request: dict[str, Any]) -> dict[str, Any]:
    """Run a standalone Python snippet under Landlock and seccomp confinement and capture stdout/stderr.

    Args:
        request: Sandbox request dictionary containing ``code``, ``stdin``, and limits.

    Returns:
        dict[str, Any]: Execution result containing ``exit_code``, ``stdout``, and ``stderr``.
    """
    stdout = LimitedWriter(int(request["output_limit_bytes"]))
    stderr = LimitedWriter(int(request["output_limit_bytes"]))
    stdin = io.StringIO(str(request.get("stdin_text", "")))
    namespace = {"__name__": "__sandbox__", "__package__": None}
    original_stdin = sys.stdin
    exit_code = 0
    try:
        sys.stdin = stdin
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                exec(
                    compile(str(request["program"]), "<sandbox-program>", "exec"),
                    namespace,
                    namespace,
                )
            except BaseException:
                exit_code = 1
                traceback.print_exc(limit=8, file=stderr)
    finally:
        sys.stdin = original_stdin
    return {
        "exit_code": exit_code,
        "stdout": stdout.getvalue(),
        "stderr": stderr.getvalue(),
    }


def _execute_function(
    source: str,
    arguments: tuple[Any, ...],
    expected_parameters: tuple[str, ...],
    namespace: dict[str, Any],
    filename: str,
) -> Any:
    before = set(namespace)
    exec(compile(source, filename, "exec"), namespace, namespace)
    functions = [
        value
        for name, value in namespace.items()
        if name not in before and inspect.isfunction(value) and value.__module__ == "__sandbox__"
    ]
    matching = [
        function
        for function in functions
        if tuple(inspect.signature(function).parameters) == expected_parameters
    ]
    if len(matching) != 1:
        expected = ", ".join(expected_parameters)
        raise ValueError(f"{filename} must define exactly one function with signature ({expected})")
    return matching[0](*arguments)


def _format_model(model: Any) -> str:
    try:
        return str(model["description"])
    except Exception:
        try:
            return (
                f"{str(model)} (`description` is not provided in model dict, "
                "fallback to `str(model)`)"
            )
        except Exception:
            return (
                f"{repr(model)} (`description` is not provided in model dict, "
                "fallback to `repr(model)`)"
            )


def evaluate_code(
    request: dict[str, Any], arrays: dict[str, dict[str, np.ndarray]], output: Path
) -> dict[str, Any]:
    """Fit and score a Python-defined model inside the sandbox against train and validation splits.

    Args:
        request: Sandbox request dictionary with user code and evaluation settings.
        arrays: Loaded train/validation NumPy array groups.
        output: Scratch directory for any output artifacts.

    Returns:
        dict[str, Any]: Evaluation metrics and captured output streams.
    """
    data = arrays["train"]
    validation = arrays.get("validation", {})
    namespace: dict[str, Any] = {
        "__name__": "__sandbox__",
        "__package__": None,
        "np": np,
        "numpy": np,
    }
    model = _execute_function(
        str(request["model_code"]), (data,), ("data",), namespace, "<evaluate-code-model>"
    )
    predictions: dict[str, np.ndarray] = {}
    prediction_groups = {"train": data, **({"validation": validation} if validation else {})}
    predict_source = str(request["predict_code"])
    before = set(namespace)
    exec(compile(predict_source, "<evaluate-code-predict>", "exec"), namespace, namespace)
    functions = [
        value
        for name, value in namespace.items()
        if name not in before
        and inspect.isfunction(value)
        and value.__module__ == "__sandbox__"
        and tuple(inspect.signature(value).parameters) == ("data", "model")
    ]
    if len(functions) != 1:
        raise ValueError(
            "predict_code must define exactly one function with signature (data, model)"
        )
    predict = functions[0]
    for split_name, split_data in prediction_groups.items():
        predictions[split_name] = np.asarray(predict(split_data, model))
    candidate_data = dict(data)
    candidate_data.pop(str(request["target"]), None)
    try:
        np.asarray(predict(candidate_data, model))
        is_candidate = True
    except Exception:
        is_candidate = False
    save_array_groups(output, {"predictions": predictions})
    return {"model_str": _format_model(model), "is_candidate": is_candidate}


def _load_evaluator(source: str, filename: str):
    """Load exactly one custom evaluator subclass inside the sandbox."""
    from sr_harness.evaluator.default_evaluator import DefaultEvaluator
    from sr_harness.evaluator.graph_evaluator import GraphEvaluator
    import sr_harness_engine as engine

    package = sys.modules["sr_harness"]
    package.DefaultEvaluator = DefaultEvaluator
    package.GraphEvaluator = GraphEvaluator

    module_name = f"sr_harness.evaluator.{Path(filename).stem}"
    namespace: dict[str, Any] = {
        "__name__": module_name,
        "__package__": "sr_harness.evaluator",
        "__file__": f"/app/sr_harness/evaluator/{Path(filename).name}",
        "DefaultEvaluator": DefaultEvaluator,
        "GraphEvaluator": GraphEvaluator,
        "engine": engine,
        "np": np,
        "numpy": np,
    }
    exec(compile(source, namespace["__file__"], "exec", dont_inherit=True), namespace)
    classes = [
        value
        for value in namespace.values()
        if isinstance(value, type)
        and value not in {DefaultEvaluator, GraphEvaluator}
        and issubclass(value, DefaultEvaluator)
        and value.__module__ == module_name
    ]
    if len(classes) != 1:
        raise ValueError("Define exactly one DefaultEvaluator subclass")
    return classes[0]()


def _load_custom_tool(source: str, filename: str):
    """Load exactly one user-authored BaseTool subclass inside the sandbox."""
    from sr_harness.tools.base_tool import BaseTool

    module_name = f"sr_harness.custom_tools.{Path(filename).stem}"
    namespace: dict[str, Any] = {
        "__name__": module_name,
        "__package__": "sr_harness.custom_tools",
        "__file__": f"/workspace/skills/{Path(filename).name}",
    }
    registry_before = dict(BaseTool.REGISTRY_DICT)
    try:
        exec(compile(source, namespace["__file__"], "exec", dont_inherit=True), namespace)
        classes = [
            value
            for value in namespace.values()
            if isinstance(value, type)
            and value is not BaseTool
            and issubclass(value, BaseTool)
            and value.__module__ == module_name
        ]
        if len(classes) != 1:
            raise ValueError(
                f"Custom tool must define exactly one BaseTool subclass, found {len(classes)}."
            )
        tool_class = classes[0]
        if any(registered is tool_class for registered in BaseTool.REGISTRY_DICT.values()):
            raise ValueError(
                "Custom tools must not use @BaseTool.register(...); set metadata.name "
                "and let the loader register the sandbox proxy."
            )
        metadata = tool_class.metadata
        if not isinstance(metadata.name, str) or not metadata.name.strip():
            raise ValueError("Custom tool metadata.name must be a non-empty string.")
        if not isinstance(metadata.description, str):
            raise ValueError("Custom tool metadata.description must be a string.")
        if not isinstance(metadata.parameters, dict):
            raise ValueError("Custom tool metadata.parameters must be a dictionary.")
        return tool_class
    finally:
        BaseTool.REGISTRY_DICT.clear()
        BaseTool.REGISTRY_DICT.update(registry_before)


def _tool_evaluator(metadata: dict[str, Any]):
    """Reconstruct the evaluator available to a sandboxed custom tool."""
    from sr_harness.evaluator.default_evaluator import DefaultEvaluator
    from sr_harness.evaluator.graph_evaluator import GraphEvaluator

    kind = metadata.get("kind", "default")
    if kind == "default":
        return DefaultEvaluator()
    if kind == "graph":
        return GraphEvaluator()
    if kind == "custom":
        return _load_evaluator(str(metadata["source"]), str(metadata["filename"]))
    raise ValueError(f"Unknown sandbox evaluator kind: {kind!r}")


def _build_tool_context(request: dict[str, Any], data: dict[str, np.ndarray], evaluator):
    """Reconstruct the explicitly shared portion of AgentContext."""
    from sr_harness.core import AgentContext

    metadata = request["context"]
    args = argparse.Namespace(**metadata.get("args", {}))
    return AgentContext(
        args=args,
        data=data,
        target=metadata.get("target"),
        variable_descriptions=metadata.get("variable_descriptions"),
        variable_axes={
            name: tuple(axes) for name, axes in metadata.get("variable_axes", {}).items()
        },
        variable_structures=metadata.get("variable_structures"),
        relation_names=set(metadata.get("relation_names", [])),
        num_nodes=metadata.get("num_nodes"),
        evaluator=evaluator,
        workspace=None,
    )


def execute_custom_tool(
    request: dict[str, Any], arrays: dict[str, dict[str, np.ndarray]]
) -> dict[str, Any]:
    """Load or execute a custom ``BaseTool`` subclass inside the isolated sandbox worker.

    Args:
        request: Sandbox request dictionary specifying ``mode``, ``source``, and ``params``.
        arrays: Loaded context arrays exposed to the custom tool.

    Returns:
        dict[str, Any]: Tool metadata or execution result dictionary.
    """
    from sr_harness.core import json_value

    tool_class = _load_custom_tool(str(request["source"]), str(request["filename"]))
    action = str(request["action"])
    if action == "inspect":
        return {
            "class_name": tool_class.__name__,
            "tool_name": tool_class.metadata.name.strip(),
            "description": tool_class.metadata.description,
            "parameters": tool_class.metadata.parameters,
        }
    if action != "execute":
        raise ValueError(f"Unknown custom-tool action: {action}")
    evaluator = _tool_evaluator(dict(request["context"].get("evaluator", {})))
    context = _build_tool_context(request, arrays["context"], evaluator)
    tool = tool_class(context=context)
    params = request.get("params", {})
    if not isinstance(params, dict):
        raise TypeError("Custom tool parameters must be a dictionary")
    result = tool.execute(**params)
    if not isinstance(result, dict):
        raise TypeError("Custom tool execute() must return a dictionary")
    return {
        "result": json_value(result),
        "result_str": str(tool.format_result_dict(result)),
    }


def _build_evaluator_context(request: dict[str, Any], data: dict[str, np.ndarray], evaluator):
    """Reconstruct the minimal AgentContext visible to a custom evaluator."""
    from sr_harness.core import AgentContext

    metadata = request["context"]
    args = argparse.Namespace(**metadata.get("args", {}))
    return AgentContext(
        args=args,
        data=data,
        target=metadata.get("target"),
        variable_descriptions=metadata.get("variable_descriptions"),
        variable_axes={
            name: tuple(axes) for name, axes in metadata.get("variable_axes", {}).items()
        },
        variable_structures=metadata.get("variable_structures"),
        relation_names=set(metadata.get("relation_names", [])),
        num_nodes=metadata.get("num_nodes"),
        evaluator=evaluator,
        workspace=None,
    )


def execute_evaluator(
    request: dict[str, Any], arrays: dict[str, dict[str, np.ndarray]], output: Path
) -> dict[str, Any]:
    """Load a custom ``DefaultEvaluator`` subclass in the sandbox and run one protocol method.

    Args:
        request: Sandbox request dictionary specifying ``operation``, ``source``, and expressions.
        arrays: Loaded context arrays for splitting, fitting, or evaluation.
        output: Directory where split array groups are written when ``operation == "split"``.

    Returns:
        dict[str, Any]: Serialized result of the requested evaluator operation.
    """
    import sr_harness_engine as engine

    evaluator = _load_evaluator(str(request["source"]), str(request["filename"]))
    action = str(request["action"])
    if action == "inspect":
        class_attributes = {
            name: value
            for name, value in vars(type(evaluator)).items()
            if not name.startswith("_") and isinstance(value, (str, int, float, bool, type(None)))
        }
        return {
            "class_name": type(evaluator).__name__,
            "class_attributes": class_attributes,
        }
    context = _build_evaluator_context(request, arrays["context"], evaluator)
    if action == "split":
        splits = evaluator.split(context)
        if set(splits) != {"train", "validation"}:
            raise ValueError("Custom evaluator split() must return train and validation contexts")
        save_array_groups(output, {name: split.data for name, split in splits.items()})
        return {}
    expression = engine.parse(str(request["f"]))
    target_expression = engine.parse(str(request["y"])) if request.get("y") is not None else None
    candidate = bool(request.get("candidate"))
    if action == "evaluate-formula":
        splits = evaluator.split(context)
        if set(splits) != {"train", "validation"}:
            raise ValueError("Custom evaluator split() must return train and validation contexts")
        fitted = expression
        if request.get("fit"):
            fitted = (
                evaluator.fit_candidate(expression, splits["train"])
                if candidate
                else evaluator.fit(expression, target_expression, splits["train"])
            )
        metrics: dict[str, dict[str, float | int]] = {}
        for split_name, split_context in splits.items():
            values = (
                evaluator.evaluate_candidate(fitted, split_context)
                if candidate
                else evaluator.evaluate(fitted, target_expression, split_context)
            )
            if not isinstance(values, dict):
                raise TypeError("Custom evaluator evaluate operation must return a dictionary")
            normalized: dict[str, float | int] = {}
            for name, value in values.items():
                if isinstance(value, (bool, np.bool_)) or not isinstance(
                    value, (int, float, np.integer, np.floating)
                ):
                    raise TypeError(f"Evaluator metric {name!r} must be a float or int")
                normalized[str(name)] = value.item() if isinstance(value, np.generic) else value
            metrics[split_name] = normalized
        save_array_groups(output, {name: split.data for name, split in splits.items()})
        return {
            "expression": fitted.to_str(number_format=".17g"),
            "metrics": metrics,
        }
    if action == "fit":
        fitted = (
            evaluator.fit_candidate(expression, context)
            if candidate
            else evaluator.fit(expression, target_expression, context)
        )
        if not isinstance(fitted, engine.Expression):
            raise TypeError("Custom evaluator fit operation must return an Expression")
        return {"expression": fitted.to_str(number_format=".17g")}
    if action == "evaluate":
        metrics = (
            evaluator.evaluate_candidate(expression, context)
            if candidate
            else evaluator.evaluate(expression, target_expression, context)
        )
        if not isinstance(metrics, dict):
            raise TypeError("Custom evaluator evaluate operation must return a dictionary")
        normalized: dict[str, float | int] = {}
        for name, value in metrics.items():
            if isinstance(value, (bool, np.bool_)) or not isinstance(
                value, (int, float, np.integer, np.floating)
            ):
                raise TypeError(f"Evaluator metric {name!r} must be a float or int")
            normalized[str(name)] = value.item() if isinstance(value, np.generic) else value
        return {"metrics": normalized}
    raise ValueError(f"Unknown evaluator action: {action}")


def _configure_sandbox() -> tuple[Path, Path, Path]:
    """Consume launcher metadata and confine this worker before user imports."""
    input_root = Path(os.environ.pop("SRH_SANDBOX_INPUT"))
    array_root = Path(os.environ.pop("SRH_SANDBOX_ARRAYS"))
    output_root = Path(os.environ.pop("SRH_SANDBOX_OUTPUT"))
    readable = json.loads(os.environ.pop("SRH_SANDBOX_READABLE"))
    writable = json.loads(os.environ.pop("SRH_SANDBOX_WRITABLE"))
    nonremovable_writable = json.loads(os.environ.pop("SRH_SANDBOX_NONREMOVABLE_WRITABLE"))
    executable = json.loads(os.environ.pop("SRH_SANDBOX_EXECUTABLE"))
    working_directory = Path(os.environ.pop("SRH_SANDBOX_CWD"))
    from sr_harness.runtime.landlock import restrict_filesystem, restrict_system_calls

    restrict_filesystem(
        readable=readable,
        writable=writable,
        nonremovable_writable=nonremovable_writable,
        executable=executable,
    )
    restrict_system_calls()
    os.chdir(working_directory)
    return input_root, output_root, array_root


def _sandbox_paths() -> tuple[Path, Path, Path]:
    """Return protocol paths before the syscall filter is installed."""
    return (
        Path(os.environ["SRH_SANDBOX_INPUT"]),
        Path(os.environ["SRH_SANDBOX_OUTPUT"]),
        Path(os.environ["SRH_SANDBOX_ARRAYS"]),
    )


def main() -> None:
    """Entry point for the isolated sandbox worker child process."""
    input_root, output_root, _ = _sandbox_paths()
    result_file = output_root / "result.json"
    try:
        request = json.loads((input_root / "request.json").read_text(encoding="utf-8"))
        apply_resource_limits(request)
        _, _, array_root = _configure_sandbox()
        arrays = load_array_groups(array_root)
        operation = request["operation"]
        if operation in {"code", "workspace-code"}:
            result = execute_program(request)
        elif operation == "evaluate-code":
            result = evaluate_code(request, arrays, output_root)
        elif operation == "evaluator":
            result = execute_evaluator(request, arrays, output_root)
        elif operation == "custom-tool":
            result = execute_custom_tool(request, arrays)
        else:
            raise ValueError(f"Unknown sandbox operation: {operation}")
        usage = resource.getrusage(resource.RUSAGE_SELF)
        result["_sandbox_usage"] = {
            "cpu_seconds": usage.ru_utime + usage.ru_stime,
            "peak_memory_bytes": int(usage.ru_maxrss) * 1024,
        }
        result_file.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    except BaseException as exc:
        error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=8)}"
        result_file.write_text(json.dumps({"error": error}, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
