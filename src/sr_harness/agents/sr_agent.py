# Copyright (c) 2026-present, Yumeow. Licensed under the MIT License.
"""Core R-C-L-K symbolic-regression agent implementation."""
from __future__ import annotations
import json
import logging
import numpy as np
from pathlib import Path
from copy import deepcopy
from itertools import islice
from collections import defaultdict
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple, TypeAlias
from ..api import BaseAPI
from ..tools import BaseTool
from ..parser import BaseParser
from ..skills import SkillManager
from ..runtime import ModelRouter
from ..utils import ParallelTimer, NamedTimer, Timer
from ..utils import format_pareto_front, render_markdown, tag2ansi, setup_logging
from ..core import APICallSample, AgentContext, CandidateRecord, ParentLink, SearchRunState, ToolCall, ToolCallResult
from .agent import Agent

_logger = logging.getLogger(f'sr_harness.{__name__}')

Message: TypeAlias = dict[str, Any]
Usage: TypeAlias = dict[str, Any]


class SRAgent(Agent):
    """Symbolic-regression agent that coordinates an R-C-L-K search tree.

    Drives language models and scientific tools across restarts (``R``),
    independent parallel conversation branches (``C``), iterative refinement
    steps (``L``), and local response samples (``K``), tracking all evaluated
    formulas and maintaining a global Pareto front.
    """

    DEFAULT_TOOLS = (
        "statistics_analysis",
        "relationship_analysis",
        "evaluate_formula",
        "submit_formula",
        "evaluate_code",
        "polynomial_fit",
        "power_law_fit",
        "rational_fit",
        "constant_fit",
        "read_skill",
        "create_skill",
        "edit_skill",
        "edit_tool",
        "call_sindy",
        "call_pysr",
        "web_search",
        "web_fetch",
        "read_pdf",
    )

    # Construction and public lifecycle

    def __init__(
        self,
        llm_provider: str,
        llm_model: str,
        tools: list[str] | None = None,
        skills: List[str] | None = None,
        verbose: bool = False,
        tool_parser: str | BaseParser = 'openai',
        save_path: Optional[str] = None,
        run_id: str | None = None,
        local_sample_size: int = 1,
        max_refinement_depth: int = 20,
        global_width: int = 1,
        max_restart_loop: int = 1,
        restart_top_k: int = 1,
        llm_max_tokens: int | None = None,
        max_workers: int = 0,
        validation_fraction: float = 0.2,
        split_by: str = "random",
        split_ood_variable: str | None = None,
        split_random_state: int = 42,
        ranking_metric: str = "mse",
        larger_is_better: bool = False,
        force_initial_diagnostics: bool = False,
        auto_routing: bool = True,
        strong_llm_provider: str | None = None,
        strong_llm_model: str | None = None,
        context: AgentContext | None = None,
        skill_manager: SkillManager | None = None,
    ) -> None:
        """Initialize the symbolic-regression agent and its R-C-L-K search configuration.

        Args:
            llm_provider: Base LLM provider name (e.g., ``"openrouter"``, ``"deepseek"``).
            llm_model: Base model identifier (e.g., ``"deepseek/deepseek-v4-flash-0731"``).
            tools: Enabled tool names, or ``None`` to use ``DEFAULT_TOOLS``.
            skills: Enabled skill names, or ``None`` to expose all available skills.
            verbose: Whether to emit debug-level runtime logs.
            tool_parser: Tool-call parser mode (``"openai"``, ``"text"``, ``"json"``,
                ``"xml"``) or a :class:`~sr_harness.parser.BaseParser` instance.
            save_path: Directory where run logs and search records are written, or
                ``None`` to disable file persistence.
            run_id: Explicit unique run identifier, or ``None`` to generate one.
            local_sample_size: Number of model responses sampled per step (``K``).
            max_refinement_depth: Maximum iterative steps per conversation branch (``L``).
            global_width: Number of parallel conversation branches per restart (``C``).
            max_restart_loop: Number of outer restart loops (``R``).
            restart_top_k: Number of top historical formulas injected into each new restart.
            llm_max_tokens: Optional maximum output tokens per model response.
            max_workers: Worker processes for parallel tool calls (``0`` runs serially).
            validation_fraction: Fraction of samples reserved for validation (``0`` disables splitting).
            split_by: Validation split strategy (``"random"`` or ``"ood"``).
            split_ood_variable: Variable name used to sort samples when ``split_by="ood"``.
            split_random_state: Random seed for reproducible train/validation splitting.
            ranking_metric: Metric name used to rank candidate formulas (defaults to ``"mse"``).
            larger_is_better: Whether higher values of ``ranking_metric`` rank better.
            force_initial_diagnostics: Whether to automatically run statistical and
                relationship diagnostics before the first model call of each branch.
            auto_routing: Whether to dynamically route between base and strong models.
            strong_llm_provider: Provider for the strong model (defaults to ``llm_provider``).
            strong_llm_model: Optional stronger model identifier for complex steps.
            context: Optional shared :class:`~sr_harness.core.AgentContext` instance.
            skill_manager: Optional :class:`~sr_harness.skills.SkillManager` instance.
        """
        # 配置日志：如果用户尚未配置，则根据 verbose 和 save_path 自动配置
        log_path = Path(save_path) / "info.log" if save_path is not None else None
        setup_logging(
            info_level='debug' if verbose else 'info',
            save_path=log_path,
            force=False,
        )

        tool_cls_list = []
        for tool_cls in BaseTool.load_tool_classes():
            # Custom tools are rediscovered and reloaded from this Agent's
            # SkillManager below. Exclude stale process-global class objects.
            if getattr(tool_cls, "source_path", None) is not None:
                continue
            tool_cls_list.append(tool_cls)

        # 参数
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.tool_parser = tool_parser
        self.local_sample_size = local_sample_size
        self.max_refinement_depth = max_refinement_depth
        self.global_width = global_width
        self.max_restart_loop = max_restart_loop
        self.restart_top_k = restart_top_k
        self.llm_max_tokens = llm_max_tokens
        self.max_workers = max_workers
        if not 0 <= validation_fraction < 1:
            raise ValueError("validation_fraction must be in [0, 1).")
        if split_by not in {"random", "ood"}:
            raise ValueError("split_by must be either 'random' or 'ood'.")
        if split_ood_variable is not None and (
            not isinstance(split_ood_variable, str) or not split_ood_variable.strip()
        ):
            raise ValueError("split_ood_variable must be None or a non-empty string.")
        self.validation_fraction = validation_fraction
        self.split_by = split_by
        self.split_ood_variable = split_ood_variable
        self.split_random_state = split_random_state
        self.ranking_metric = ranking_metric
        self.larger_is_better = larger_is_better
        self.force_initial_diagnostics = force_initial_diagnostics
        self.auto_routing = auto_routing
        self.strong_llm_provider = (
            llm_provider if strong_llm_provider is None else strong_llm_provider
        )
        self.strong_llm_model = strong_llm_model
        self.model_router = ModelRouter(
            enabled=auto_routing,
            base_provider=llm_provider,
            base_model=llm_model,
            strong_provider=self.strong_llm_provider,
            strong_model=strong_llm_model,
        )
        self._task_route_score = 0
        self._task_route_reasons: list[str] = []
        self._strong_api = None
        self._last_model_route = None

        # 关键组件
        self.context = context if context is not None else AgentContext()
        self.skill_manager = skill_manager or SkillManager(workspace=self.context.workspace)
        requested_tool_names = tuple(self.DEFAULT_TOOLS if tools is None else tools)
        requested_tools = set(requested_tool_names)
        initially_selected = [
            tool_cls for tool_cls in tool_cls_list
            if tool_cls.metadata.name in requested_tools
        ]
        self.skill_manager.register_tool_docs(initially_selected)
        tool_cls_list += BaseTool.discover_custom_tools(self.skill_manager)
        self.available_tool_classes = {
            tool_cls.metadata.name: tool_cls for tool_cls in tool_cls_list
        }
        if unknown_tools := requested_tools - self.available_tool_classes.keys():
            raise ValueError(f"Unknown tools: {', '.join(sorted(unknown_tools))}")
        self.tool_cls_list = [
            self.available_tool_classes[name] for name in requested_tool_names
        ]
        registered_skills = self.skill_manager.load_skills()
        self.skill_manager.register_tool_docs([
            tool_cls for tool_cls in self.tool_cls_list
            if (doc := tool_cls.get_doc()) is not None and doc["name"] not in registered_skills
        ])
        available_skills = self.skill_manager.load_skills()
        tool_skill_names = {
            doc["name"]
            for tool_cls in self.tool_cls_list
            if (doc := tool_cls.get_doc()) is not None
        }
        requested_skills = (
            set(skills) | tool_skill_names
            if skills is not None
            else set(available_skills)
        )
        if unknown_skills := requested_skills - available_skills.keys():
            raise ValueError(f"Unknown skills: {', '.join(sorted(unknown_skills))}")
        self.enabled_skills = requested_skills
        if self.force_initial_diagnostics:
            required_tools = {"statistics_analysis", "relationship_analysis", "read_skill"}
            enabled_tools = {tool_cls.metadata.name for tool_cls in self.tool_cls_list}
            if missing_tools := required_tools - enabled_tools:
                raise ValueError(
                    "force_initial_diagnostics requires these enabled tools: "
                    + ", ".join(sorted(missing_tools))
                )
            if "discover-symbolic-laws" not in self.enabled_skills:
                raise ValueError(
                    "force_initial_diagnostics requires the 'discover-symbolic-laws' skill."
                )
        self.tool_box = None  # 延迟实例化，因为需要 context 上下文
        self.api = None # 延迟实例化, 因为需要 tools 工具列表

        # 附属组件
        self.total_timer = Timer() # 总用时统计
        self.named_timer = NamedTimer() # 细粒度用时统计
        self.token_counter = ParallelTimer(unit='token') # token 统计
        self.money_counter = ParallelTimer(unit='$') # 费用统计
        self.tools_counter = ParallelTimer(unit='call') # 工具调用统计
        self.save_path = save_path
        self.context.args.validation_fraction = validation_fraction
        self.context.args.split_by = split_by
        self.context.args.split_ood_variable = split_ood_variable
        self.context.args.split_random_state = split_random_state
        self.context.invalidate_splits()
        self.run_state = SearchRunState(
            save_path=save_path,
            ranking_metric=ranking_metric,
            larger_is_better=larger_is_better,
            agent_metadata={
                "class": self.__class__.__name__,
                "llm_provider": llm_provider,
                "llm_model": llm_model,
                "tool_parser": str(tool_parser),
                "local_sample_size": local_sample_size,
                "max_refinement_depth": max_refinement_depth,
                "global_width": global_width,
                "max_restart_loop": max_restart_loop,
                "restart_top_k": restart_top_k,
                "max_workers": max_workers,
            },
            run_id=run_id,
        )

        _logger.info(f"Initialized {self.__class__.__name__}")

    def run(self, X: Dict[str, np.ndarray], y: Dict[str, np.ndarray] | np.ndarray, problem_description: str) -> Dict[str, Any]:
        """Initialize the runtime context and execute a complete symbolic-regression search.

        Args:
            X: Input feature arrays keyed by variable name.
            y: Target variable array or single-entry mapping ``{target_name: array}``.
            problem_description: Natural-language description of the scientific discovery problem.

        Returns:
            Dict[str, Any]: Serializable search summary containing the best formula,
                Pareto front, all evaluated candidates, and resource usage statistics.
        """
        if not isinstance(y, dict):
            y = {"target": y}

        target = next(iter(y))
        supplied_data = X | y

        def existing_value(name: str):
            if name in self.context.data:
                return self.context.data[name]
            return None

        data_changed = not self.context.data or any(
            (current := existing_value(name)) is None
            or not np.array_equal(current, value)
            for name, value in supplied_data.items()
        )
        if data_changed:
            self.context.commit_data(
                supplied_data,
                target=target,
                features=list(X),
                variable_descriptions=self.context.variable_descriptions,
            )
        else:
            self.context.target = target
        self.context.invalidate_splits()
        self._active_X = X
        self._active_y = y
        self._data_revision = int(self.context.args.data_revision)
        self.context.args.llm_provider = self.llm_provider
        self.context.args.llm_model = self.llm_model
        self.context.args.llm_max_tokens = self.llm_max_tokens
        self.context.args.skill_manager = self.skill_manager
        self.context.args.enabled_skills = sorted(self.enabled_skills)
        with self.prepare_tool_context(self.context) as tool_context:
            self.initialize_with_context(tool_context)
            description = self.tool_box.format_tools()
            if isinstance(description, list):
                description = json.dumps(description, indent=2)
            _logger.debug(
                f"Using {self.tool_parser} as tool parser. "
                f"Tools will be described as follows:\n{description}"
            )
            try:
                return self.search(X, y, problem_description)
            except KeyboardInterrupt as error:
                coordinate = self.run_state.latest_coordinate
                error.partial_result = self.build_search_result(
                    "interrupted",
                    R=coordinate.R if coordinate else None,
                    C=coordinate.C if coordinate else None,
                    L=coordinate.L if coordinate else None,
                )
                raise
            except Exception as error:
                coordinate = self.run_state.latest_coordinate
                error.partial_result = self.build_search_result(
                    "failed",
                    R=coordinate.R if coordinate else None,
                    C=coordinate.C if coordinate else None,
                    L=coordinate.L if coordinate else None,
                )
                raise

    @contextmanager
    def prepare_tool_context(self, tool_context: AgentContext) -> Iterator[AgentContext]:
        """Context manager that binds per-run resources to the shared tool context.

        Args:
            tool_context: Shared context passed to initialized tools.

        Yields:
            AgentContext: The active context ready for tool initialization.
        """
        yield tool_context

    # Search orchestration

    def search(self, X: Dict[str, np.ndarray], y: Dict[str, np.ndarray], problem_description: str) -> Dict[str, Any]:
        """Execute the R-C-L-K search loop over an already initialized context.

        At each refinement step, builds the prompt, queries the language model for
        ``K`` samples, executes tool calls, records search-tree nodes, extracts
        candidate formulas, updates the branch conversation buffer, and checks
        termination conditions.

        Args:
            X: Input feature arrays keyed by variable name.
            y: Target variable mapping ``{target_name: array}``.
            problem_description: Natural-language description of the discovery task.

        Returns:
            Dict[str, Any]: Final search result dictionary for the completed or stopped run.
        """
        ## 开始迭代
        self.total_timer.clear(reset_last_add_time=True)
        self.named_timer.clear(reset_last_add_time=True)
        R = 1
        while R <= self.max_restart_loop:  # R 次 best-solution restart
            _logger.info(f"Start Restart Loop (R={R}/{self.max_restart_loop})")

            # 用平凡结果或者历史最佳结果构建新的分支 buffer
            restart_records = self.run_state.ranked_candidates()[:self.restart_top_k]
            initial_buffer = self.create_initial_buffer(problem_description, X, y, restart_records)
            initial_node_parents = {record.node_id: "restart_seed" for record in restart_records}
            self.named_timer.add("create_initial_buffer")
            C = 1
            next_restart = False
            while C <= self.global_width:  # C 次独立重复对话
                _logger.info(
                    f"(R={R}/{self.max_restart_loop}) × "
                    f"Global Branch (C={C}/{self.global_width})"
                )

                # 用 initial prompt 初始化 buffer，node_parents 记录当前 buffer 的父节点
                buffer = deepcopy(initial_buffer)
                node_parents = deepcopy(initial_node_parents)
                self.named_timer.add("init_buffer")

                L = 1
                while L <= self.max_refinement_depth:  # L 轮对话迭代
                    _logger.info(
                        f"(R={R}/{self.max_restart_loop}) × "
                        f"(C={C}/{self.global_width}) × "
                        f"Refinement Step (L={L}/{self.max_refinement_depth})"
                    )

                    # Step 1: 根据 Buffer 创建 Prompt
                    transition = self.prepare_iteration(buffer, R=R, L=L, C=C)
                    if transition == "next_r":
                        next_restart = True
                        break
                    if transition == "next_c":
                        break
                    prompt = self.prepare_model_messages(buffer, R=R, L=L, C=C)
                    self.set_messages(prompt)
                    self.named_timer.add("prepare_model_messages")

                    # Step 2: 请求 LLM 得到 Content、Tool Calls 和 Message
                    response_list, usage = self.request_llm(prompt, R=R, L=L, C=C)
                    self.named_timer.add("request_llm")

                    # Step 3: 执行 Tool Calls 得到 Results
                    results_list = self.execute_tool_calls(response_list, R=R, L=L, C=C)
                    self.named_timer.add("execute_tool_calls")

                    # Step 4: 记录当前搜索节点
                    self.record_search_iteration(
                        response_list, results_list, node_parents, prompt, usage, R, L, C,
                    )
                    self.named_timer.add("record_search_iteration")

                    # Step 5: 验证并收集候选公式
                    self.collect_candidates(response_list, results_list, R=R, L=L, C=C)
                    self.named_timer.add("collect_candidates")

                    # Step 6: 更新对话 Buffer 和父节点关系
                    buffer, node_parents = self.update_conversation(
                        buffer, response_list, results_list, node_parents, R, L, C,
                    )
                    self.named_timer.add("update_conversation")

                    # Step 7: 打印本轮日志
                    self.log_info(response_list, R=R, L=L, C=C)
                    self.named_timer.add("log_info")
                    self.total_timer.add()

                    # Step 8: 判断是否终止当前搜索
                    status = self.finish_iteration(buffer, R=R, L=L, C=C)
                    if status is not None:
                        _logger.note("Early stopping triggered. Returning best result.")
                        return self.build_search_result(status, R=R, L=L, C=C)
                    L += 1
                if next_restart:
                    break
                C += 1
            R += 1

        _logger.note("Finished all iterations. Returning best result.")
        coordinate = self.run_state.latest_coordinate
        return self.build_search_result(
            "completed",
            R=coordinate.R if coordinate else None,
            C=coordinate.C if coordinate else None,
            L=coordinate.L if coordinate else None,
        )

    def _split_data(self, X: Dict[str, np.ndarray], y: Dict[str, np.ndarray]):
        """Split aligned arrays into train and validation data mappings."""
        self.context.args.validation_fraction = self.validation_fraction
        self.context.args.split_by = self.split_by
        self.context.args.split_ood_variable = getattr(
            self, "split_ood_variable", self.context.args.split_ood_variable
        )
        self.context.args.split_random_state = self.split_random_state
        target = next(iter(y))
        data = X | y
        variable_axes = {
            name: axes for name, axes in self.context.variable_axes.items() if name in data
        }
        for axis in {axis for axes in variable_axes.values() for axis in axes}:
            if axis in self.context.data:
                data.setdefault(axis, self.context.data[axis])
        variable_structures = {
            name: structure
            for name, structure in self.context.variable_structures.items()
            if name in data and structure in data
        }
        split_context = AgentContext(
            args=self.context.args,
            data=data,
            target=target,
            variable_descriptions={name: self.context.variable_descriptions.get(name, "") for name in data},
            variable_axes=variable_axes or None,
            variable_structures=variable_structures,
            relation_names=self.context.relation_names & set(data),
            num_nodes=self.context.num_nodes if self.context.relation_names & set(data) else None,
            evaluator=self.context.evaluator,
            workspace=self.context.workspace,
        )
        splits = split_context.evaluator.split(split_context)
        return splits["train"].data, splits["validation"].data

    # Prompt and conversation-buffer lifecycle

    def create_initial_buffer(self, problem_description: str, X: dict[str, np.ndarray], y: dict[str, np.ndarray], restart_records: list[CandidateRecord]) -> list[Message]:
        """Build the initial conversation buffer for a new branch, including the opening progress summary.

        Args:
            problem_description: Natural-language description of the discovery task.
            X: Input feature arrays keyed by variable name.
            y: Target variable mapping ``{target_name: array}``.
            restart_records: Top historical candidates from prior restarts used to seed the prompt.

        Returns:
            list[Message]: Initial message list ready to start a conversation branch.
        """
        self._task_route_score, self._task_route_reasons = self.model_router.assess(
            problem_description,
            feature_count=len(X),
        )
        initial_buffer = [
            *self.create_initial_prompt_messages(
                problem_description, X, y, restart_records,
            ),
            self.build_progress_message(L=0),
        ]
        self.on_buffer_messages_added(initial_buffer)
        return initial_buffer

    def create_initial_prompt_messages(self, problem_description: str, X: dict[str, np.ndarray], y: dict[str, np.ndarray], restart_records: list[CandidateRecord]) -> list[Message]:
        """Assemble the initial system and user messages before branch buffer metadata is attached.

        Args:
            problem_description: Natural-language description of the discovery task.
            X: Input feature arrays keyed by variable name.
            y: Target variable mapping ``{target_name: array}``.
            restart_records: Top historical candidates from prior restarts.

        Returns:
            list[Message]: Two-element list containing the finalized system and user messages.
        """
        messages = [{
            "role": "system",
            "content": self.create_initial_system_prompt(restart_records),
        }, {
            "role": "user",
            "content": self.create_initial_user_prompt(
                problem_description, X, y, restart_records,
            ),
        }]
        return self.customize_initial_prompts(messages, X=X, y=y)

    @staticmethod
    def _build_mse_goal(restart_records) -> str:
        """Describe the next MSE objective from the current restart seeds."""
        return (
            "Seek a compact expression with reliable held-out predictive performance. "
            "Establish constant and simple linear baselines before increasing complexity. "
            "Fit coefficients and preprocessing on training data only; use validation for "
            "model selection and reserve any external test set for a single final assessment. "
            "Measurements may be noisy: do not require zero error or arbitrary tenfold "
            "improvement. Prefer simpler expressions when error differences are not robust "
            "to resampling, and report competing forms when the observed range cannot "
            "distinguish them. Exact recovery is warranted only by independent evidence "
            "that the data are effectively noiseless."
        )

    def create_initial_system_prompt(self, restart_records: list[CandidateRecord]) -> str:
        """Render the system prompt defining the agent's role, workflow, and tool instructions.

        Args:
            restart_records: Historical candidates from prior restarts (used to adjust guidance).

        Returns:
            str: Formatted system prompt text.
        """
        mse_goal = self._build_mse_goal(restart_records)
        return (
            "You are a Symbolic Regression Agent. Your goal is to discover mathematical formulas "
            "that explain the relationship between feature variables and the target variable. "
            "DO NOT be satisfied with an accurate but complex formula — prefer simple, interpretable expressions. "
            f"You have at most {self.max_refinement_depth} refinement rounds in each conversation branch. "
            "Plan tool use within this budget: use early rounds for targeted exploration, keep concrete "
            "candidate formulas as the budget shrinks, and avoid open-ended searches near the end. "
            "If possible, try calling multiple tools in each round. "
            f"{mse_goal} Please start by analyzing the data to understand the relationship between features and target."
        )

    def create_initial_user_prompt(self, problem_description: str, X: dict[str, np.ndarray], y: dict[str, np.ndarray], restart_records: list[CandidateRecord]) -> str:
        """Render the initial user prompt describing the problem, variables, and prior restart results.

        Args:
            problem_description: Natural-language description of the discovery task.
            X: Input feature arrays keyed by variable name.
            y: Target variable mapping ``{target_name: array}``.
            restart_records: Top historical candidates seeded from earlier restarts.

        Returns:
            str: Formatted user prompt text.
        """
        content = (
            f"{problem_description}\n\n"
            f"- Feature names: {list(X.keys())}\n"
            f"- Target name: {next(iter(y))}\n"
        )
        if not restart_records:
            return content + "Please start by analyzing the data to understand the relationship between features and target."

        content += (
            "\n--- Previously Explored Formulas (from best to worst) ---\n"
            "Use these as inspiration. Try to improve upon them or find simpler alternatives.\n\n"
        )
        for record in restart_records:
            mse = record.metric("mse", "validation")
            if mse is None:
                mse = record.metric("mse", "train")
            r2 = record.metric("r2", "validation")
            if r2 is None:
                r2 = record.metric("r2", "train")
            metric_text = f"MSE={mse:.6g}" if mse is not None else "MSE=unavailable"
            if r2 is not None:
                metric_text += f", R²={r2:.6g}"
            content += f"  • Formula: {record.formula}\n    {metric_text}\n\n"
        return content + (
            "---\n\nAnalyze why the previous best formulas may not be perfect, and try a different "
            "approach or structure to improve the result."
        )

    def customize_initial_prompts(self, messages: list[Message], *, X: dict[str, np.ndarray], y: dict[str, np.ndarray]) -> list[Message]:
        """Hook for subclasses to modify initial system and user messages before they enter the buffer.

        Args:
            messages: Initial system and user message dictionaries.
            X: Input feature arrays keyed by variable name.
            y: Target variable mapping ``{target_name: array}``.

        Returns:
            list[Message]: Customized message list to insert into the branch buffer.
        """
        return messages

    def on_buffer_messages_added(self, messages: list[Message], **coordinate: int) -> None:
        """Hook invoked whenever new messages are appended to a branch conversation buffer.

        Args:
            messages: Messages that were just appended to the buffer.
            **coordinate: Optional ``R``, ``C``, and ``L`` coordinates for the active step.
        """

    def _append_buffer_messages(self, buffer, messages, **coordinate: int) -> None:
        """Append messages and notify subclasses through one mutation path."""
        messages = list(messages)
        buffer.extend(messages)
        self.on_buffer_messages_added(messages, **coordinate)

    def prepare_model_messages(self, buffer: List[Dict[str, Any]], R: int, L: int, C: int) -> List[Dict[str, Any]]:
        """Build the full message list sent to the language model for step ``(R, C, L)``.

        Runs initial diagnostics on ``L=1`` when ``force_initial_diagnostics`` is
        enabled and strips internal buffer metadata keys before sending.

        Args:
            buffer: Current branch conversation buffer.
            R: One-based restart index.
            L: One-based refinement-step index.
            C: One-based conversation-branch index.

        Returns:
            List[Dict[str, Any]]: Provider-ready conversation messages.
        """
        if self.force_initial_diagnostics and L == 1:
            # Persist the evidence in the branch buffer so later refinement
            # rounds retain the diagnostics and skill instructions.
            self._append_buffer_messages(
                buffer,
                [self.run_initial_diagnostics(R=R, L=L, C=C)],
                R=R,
                C=C,
                L=L,
            )
        prompt = deepcopy(buffer)
        _logger.info(f"Built prompt with {len(prompt)} messages.")
        logs = []
        for msg in prompt:
            msg = msg.copy()
            order = ['role', 'tool_call_id', 'reasoning', 'content', 'tool_call']
            order = [k for k in order if k in msg] + [k for k in msg if k not in order]
            msg = { k: msg[k] for k in order }

            log = ''
            log += tag2ansi(f"[red bold][{msg.pop('role')}][reset]")
            for k, v in msg.items():
                if k == 'content':
                    v = render_markdown(v or "(empty)")
                v = str(v).strip()
                if '\n' in v:
                    v = '\n        '.join(['', *v.splitlines()])
                log += tag2ansi(f"\n    [blue]{k}[reset]") + '=' + v
            logs.append(log)
        _logger.debug("Messages:\n" + '\n---\n'.join(logs))
        return prompt

    def prepare_iteration(self, buffer: List[Dict[str, Any]], R: int, L: int, C: int) -> str | None:
        """Apply any pending runtime updates or control commands before step ``(R, C, L)`` begins.

        Args:
            buffer: Current branch conversation buffer.
            R: One-based restart index.
            L: One-based refinement-step index.
            C: One-based conversation-branch index.

        Returns:
            str | None: Control transition token (``"stop"``, ``"next_c"``, ``"next_r"``),
                or ``None`` to proceed with the step.
        """
        return None

    def refresh_data(self) -> dict[str, Any] | None:
        """Synchronize the agent's feature and target views if the shared ``context.data`` revision changed.

        Returns:
            dict[str, Any] | None: Summary of variable or role changes when a new
                data revision was applied, or ``None`` if the dataset is unchanged.
        """
        revision = int(self.context.args.data_revision)
        if revision == self._data_revision:
            return None
        if self.context.target is None or not self.context.feature_names():
            raise ValueError("The updated context does not define a target and features")

        def selected_value(name: str) -> np.ndarray:
            if name in self.context.data:
                return self.context.data[name]
            raise ValueError(f"The selected variable or axis no longer exists: {name}")

        X = {name: selected_value(name) for name in self.context.feature_names()}
        y = {self.context.target: selected_value(self.context.target)}
        self.context.invalidate_splits()
        self._active_X.clear()
        self._active_X.update(X)
        self._active_y.clear()
        self._active_y.update(y)
        previous_revision = self._data_revision
        self._data_revision = revision
        descriptions = {
            name: description
            for name in [self.context.target, *self.context.feature_names()]
            if (description := self.context.variable_descriptions.get(name, "").strip())
        }
        return {
            "previous_revision": previous_revision,
            "revision": revision,
            "target": self.context.target,
            "features": list(self.context.feature_names()),
            "variable_descriptions": descriptions,
        }

    def finish_iteration(self, buffer: List[Dict[str, Any]], R: int, L: int, C: int) -> str | None:
        """Check whether the search should terminate at the end of step ``(R, C, L)``.

        Args:
            buffer: Current branch conversation buffer.
            R: One-based restart index.
            L: One-based refinement-step index.
            C: One-based conversation-branch index.

        Returns:
            str | None: Terminal status string (such as ``"early_stopped"``) when
                stopping criteria are met, or ``None`` to continue searching.
        """
        best_candidate = self.best_candidate()
        if (
            best_candidate is not None and best_candidate.metric("mse", "train") == 0.0
        ):
            return "early_stopped"
        return None

    def run_initial_diagnostics(self, R: int, L: int, C: int) -> Dict[str, str]:
        """Execute opening statistical, relationship, and skill diagnostics for the start of a branch.

        Args:
            R: One-based restart index.
            L: One-based refinement-step index.
            C: One-based conversation-branch index.

        Returns:
            Dict[str, str]: Formatted user-role message containing the diagnostic outputs.
        """
        calls = [
            ToolCall(name="statistics_analysis", params={}),
            ToolCall(name="relationship_analysis", params={}),
            ToolCall(name="read_skill", params={"name": "discover-symbolic-laws"}),
        ]
        results = self.execute_action(calls)
        self.record_tool_calls(calls, results, R=R, L=L, C=C, forced=True)
        failures = [
            f"{call.name}: {result.result_str}"
            for call, result in zip(calls, results)
            if not result.ok
        ]
        if failures:
            raise RuntimeError(
                "Required initial diagnostic tool call(s) failed:\n" + "\n".join(failures)
            )
        sections = [
            f"## {call.name}\n{result.result_str}"
            for call, result in zip(calls, results)
        ]
        return {
            "role": "user",
            "content": (
                "[Required initial diagnostics]\n"
                "The framework ran these mandatory tools before your first response in this branch. "
                "Use their evidence and the skill instructions to plan the search.\n\n"
                + "\n\n".join(sections)
            ),
        }

    # Model and tool execution

    def request_llm(self, prompt: List[Dict[str, Any]], R: int, L: int, C: int, callback: Callable[[dict[str, Any]], None] | None = None) -> tuple[list[APICallSample], Usage | None]:
        """Route the request to the appropriate model tier and sample ``K`` responses for step ``(R, C, L)``.

        Args:
            prompt: Provider-ready conversation messages.
            R: One-based restart index.
            L: One-based refinement-step index.
            C: One-based conversation-branch index.
            callback: Optional callback receiving live streaming progress updates.

        Returns:
            tuple[list[APICallSample], Usage | None]: Sampled assistant responses
                and aggregated token/cost usage.
        """
        response_list = []
        route = self.model_router.route(
            task_score=self._task_route_score,
            task_reasons=self._task_route_reasons,
            refinement_step=L,
        )
        self._last_model_route = route
        api = self.api
        if route.tier == "strong":
            if self._strong_api is None:
                self._strong_api = BaseAPI.create(
                    route.provider,
                    model=route.model,
                    tool_box=self.tool_box,
                    environment=getattr(self.context.args, "api_environment", None),
                    save_path=self.save_path,
                )
            api = self._strong_api
        _logger.info(
            f"Model route: tier={route.tier}, backend={route.provider}/{route.model}, "
            f"score={route.score}, reason={route.reason}"
        )
        llm_result = api(
            prompt,
            n=self.local_sample_size,
            max_tokens=self.llm_max_tokens,
            callback=callback,
        )
        for K, response in enumerate(llm_result, 1):  # K 次重复采样
            content = response.content
            tool_calls = response.tool_calls
            response_list.append(response)
            content_for_log = render_markdown(content or "(empty)").strip()
            tool_calls_for_log = '\n'.join(str(tool_call) for tool_call in tool_calls)
            content_for_log = '\n        '.join(['', *content_for_log.splitlines()]) if '\n' in content_for_log else content_for_log
            tool_calls_for_log = '\n        '.join(['', *tool_calls_for_log.splitlines()]) if '\n' in tool_calls_for_log else tool_calls_for_log
            _logger.info(
                f"(R={R}/{self.max_restart_loop}) × (C={C}/{self.global_width}) × (L={L}/{self.max_refinement_depth}) × Local Sample (K={K}/{self.local_sample_size})\n"
                f"LLM response content: {content_for_log}\n"
                f"LLM tool calls: ({len(tool_calls)} tool calls)"
            )
            _logger.debug(tool_calls_for_log)
        usage = self.record_llm_result(llm_result, R=R, L=L, C=C)
        self._last_response_was_truncated = llm_result.truncated
        if llm_result.ok is False and not llm_result.truncated:
            raise RuntimeError(llm_result.error or "Model API request failed.")
        return response_list, usage

    def execute_tool_calls(self, response_list: list[APICallSample], R: int, L: int, C: int) -> list[list[ToolCallResult]]:
        """Execute all tool calls across the ``K`` sampled model responses for step ``(R, C, L)``.

        Args:
            response_list: Sampled model responses for the current step.
            R: One-based restart index.
            L: One-based refinement-step index.
            C: One-based conversation-branch index.

        Returns:
            list[list[ToolCallResult]]: Tool execution results grouped by sample index.
        """
        # 合并 - 调用 - 分割
        all_tool_calls = []
        num_tool_calls = []
        for response in response_list:
            all_tool_calls.extend(response.tool_calls)
            num_tool_calls.append(len(response.tool_calls))
        if self.max_workers and len(all_tool_calls) > 1:
            all_results = self.execute_action_parallel(all_tool_calls, max_workers=self.max_workers)
        else:
            all_results = self.execute_action(all_tool_calls)
        results_iter = iter(all_results)
        results_list = [list(islice(results_iter, l)) for l in num_tool_calls]
        # 打印工具调用结果
        all_results_for_log = '\n'.join(str(result) for result in all_results or [])
        all_results_for_log = '\n        '.join(['', *all_results_for_log.splitlines()]) if '\n' in all_results_for_log else all_results_for_log
        _logger.debug(f"Action result: {all_results_for_log}")
        self.record_tool_calls(all_tool_calls, all_results, R=R, L=L, C=C)
        return results_list

    def record_tool_calls(
        self, tool_calls: List[ToolCall],
        results: List[ToolCallResult],
        R: int, L: int, C: int, forced: bool = False
    ) -> None:
        """Append tool call inputs and outputs to ``tool_calls.jsonl`` and update usage counters.

        Args:
            tool_calls: Tool calls executed in the current batch.
            results: Corresponding tool execution results.
            R: One-based restart index.
            L: One-based refinement-step index.
            C: One-based conversation-branch index.
            forced: Whether the calls were triggered by automatic initial diagnostics
                rather than emitted by the model.
        """
        if self.save_path is None:
            return
        with open(Path(self.save_path) / 'tool_calls.jsonl', 'a') as f:
            for tool_call, result in zip(tool_calls, results):
                json.dump({
                    "progress": self.format_progress(R, L, C),
                    "forced": forced,
                    'name': tool_call.name,
                    'params': tool_call.params,
                    "ok": result.ok,
                    "result": result.result,
                    "result_str": result.result_str,
                    "meta_data": result.meta_data,
                }, f)
                f.write('\n')

    def update_conversation(
        self,
        buffer: List[Dict[str, Any]],
        response_list: List[Tuple[str, List[ToolCall], Dict[str, Any]]],
        results_list: List[List[ToolCallResult]],
        node_parents: Dict[str, str], R: int, L: int, C: int
    ) -> tuple[list[Message], dict[str, str]]:
        """Select the best-performing ``K`` sample to continue the branch and fold in sibling analysis results.

        Args:
            buffer: Current branch conversation buffer.
            response_list: Sampled model responses for the current step.
            results_list: Tool results aligned with ``response_list``.
            node_parents: Mapping of parent node IDs by link relation (``"strong"`` / ``"weak"``).
            R: One-based restart index.
            L: One-based refinement-step index.
            C: One-based conversation-branch index.

        Returns:
            tuple[list[Message], dict[str, str]]: Updated conversation buffer and
                the parent-node mapping for the next refinement step.
        """
        # 如果没有成功的回复，跳过本轮更新
        if len(response_list) == 0:
            return buffer, node_parents
        node_parents = {}
        # 选择产生了最佳排序指标的 tool_call 所在的 response 分支
        selected_K = 1
        selected_priority = float('inf')
        for K, results in enumerate(results_list, 1):
            for result in results:
                if (priorities := self.candidate_sort_key(result.result)) is not None and priorities[0] < selected_priority:
                    selected_K = K
                    selected_priority = priorities[0]
        node_parents[self.run_state.node_id(R=R, C=C, L=L, K=selected_K)] = 'continuation'
        _logger.info(f"Selected LLM branch: {selected_K}/{len(results_list)}")
        selected_response = response_list[selected_K - 1]
        tool_calls = selected_response.tool_calls
        message = selected_response.message
        results = results_list[selected_K - 1]
        tool_calls = tool_calls.copy()
        message = deepcopy(message)
        results = results.copy()
        # 将其他 (tool_call, result) pairs 中不涉及 formula & metrics 的 pair 也加入 buffer, 以免丢失有用信息
        for K, (extra_response, extra_results) in enumerate(zip(response_list, results_list), 1):
            extra_tool_calls = extra_response.tool_calls
            for tool_call, result in zip(extra_tool_calls, extra_results):
                # 只考虑不涉及 formula & metrics 的工具调用结果
                if K == selected_K or result.get('data_split_results', {}).get('train', {}).get('metrics') is not None:
                    continue
                tool_calls.append(tool_call)
                results.append(result)
                # 对于 openai parser, 将 extra_message['tool_calls'] 拼到 message 中
                if self.tool_parser == 'openai':
                    if not isinstance(message.get('tool_calls'), list):
                        message['tool_calls'] = []
                    message['tool_calls'].append(tool_call.raw)
                # 对于 non-openai parser, 将 tool_calls 拼到 content 中
                else:
                    message['content'] += "\n\n" + tool_call.raw_str
                node_parents[self.run_state.node_id(R=R, C=C, L=L, K=K)] = 'context_merge'
        # 将 message 和 (tool_call, result) pairs 加入 buffer
        if tool_calls or (message.get('content') or '').strip() or message.get('reasoning'):
            result_messages = (
                self.tool_box.format_tool_result_messages(tool_calls, results)
                if tool_calls else []
            )
            self._append_buffer_messages(
                buffer,
                [message, *result_messages],
                R=R,
                C=C,
                L=L,
            )
        else:
            _logger.warning("Skipping empty LLM response (no content nor tool calls).")
        followup_messages = self.build_response_followup_messages(
            response_list, results_list, R=R, L=L, C=C,
        )
        if followup_messages:
            self._append_buffer_messages(
                buffer, followup_messages, R=R, C=C, L=L,
            )
        process_message = self.build_progress_message(L)
        self._append_buffer_messages(buffer, [process_message], R=R, C=C, L=L)
        return buffer, node_parents

    def build_response_followup_messages(
        self,
        response_list: list[APICallSample],
        results_list: list[list[ToolCallResult]],
        *,
        R: int,
        L: int,
        C: int,
    ) -> list[Message]:
        """Build any framework follow-up messages to append after processing model responses.

        Args:
            response_list: Sampled model responses for the current step.
            results_list: Tool results aligned with ``response_list``.
            R: One-based restart index.
            L: One-based refinement-step index.
            C: One-based conversation-branch index.

        Returns:
            list[Message]: Follow-up messages to append (empty in non-interactive mode).
        """
        return []

    # Progress prompts and candidate state

    def build_progress_message(self, L: int) -> dict[str, str]:
        # 将当前搜索进度加入 buffer
        """Format a user-role message summarizing remaining step budget and the current Pareto front.

        Args:
            L: Next one-based refinement-step index.

        Returns:
            dict[str, str]: User-role message injected before the next model request.
        """
        remaining_rounds = self.max_refinement_depth - L - 1
        progress_line = (
            f"Current progress: refinement round L={L+1}/{self.max_refinement_depth}. "
            f"From now on, {remaining_rounds} refinement round(s) remain in this branch."
        )
        if remaining_rounds > 1:
            policy = (
                "Plan tool use within the remaining refinement budget. "
                "Prefer targeted actions that can lead to a simpler and lower-MSE formula."
            )
        elif remaining_rounds == 1:
            policy = (
                "Only one refinement round remains after this response. Use at most a tightly targeted "
                "tool call now, and preserve a concrete formula candidate so the next round can submit it."
            )
        else:
            policy = (
                "This is the final refinement round for this branch. Do not spend this response on "
                "new data exploration, broad searches, or diagnostic-only evaluations. Submit or state "
                "your best available target formula now using the final-answer mechanism available in "
                "this environment, with a brief justification if text is required."
            )
        pareto_front = self.get_pareto_front()
        metric_path = f"validation.metrics.{self.ranking_metric}"
        train_metric_path = f"train.metrics.{self.ranking_metric}"
        metric_label = self.ranking_metric.replace("_", " ").upper()
        pareto_front_str = format_pareto_front(
            [self.candidate_to_dict(record) for record in pareto_front],
            concise=True,
            formula_max_length=160,
            balance=(
                ("validation.metrics.complexity", "minimize"),
                (metric_path, "maximize" if self.larger_is_better else "minimize"),
            ),
            columns=("validation.metrics.complexity", metric_path, train_metric_path, "formula"),
            title_mapping={
                "validation.metrics.complexity": "Complexity",
                metric_path: f"Validation {metric_label}",
                train_metric_path: f"Train {metric_label}",
                "formula": "Formula",
            },
        )
        diagnostics = []
        for record in pareto_front:
            if eic := record.details.get("eic_diagnostics"):
                diagnostics.append(
                    f"- {record.formula}: EIC={eic['eic']:.6g}; "
                    f"worst subtree={eic['worst_subtree']}"
                )
        available_tools = {tool.metadata.name for tool in getattr(self, "tools", [])}
        routing = []
        distinct_formulas = list(dict.fromkeys(
            record.formula for record in self.run_state.ranked_candidates()
        ))
        if (
            len(distinct_formulas) >= 2
            and "delegate_subagent" in available_tools
            and self.tools_counter.named_count.get("delegate_subagent", 0) == 0
            and remaining_rounds >= 1
        ):
            routing.append(
                "There are multiple viable formulas. Use delegate_subagent in "
                "candidate_critique mode with the leading formulas and their metrics, then "
                "run the cheapest discriminating check it recommends."
            )
        diagnostics_text = (
            "\n\n[Candidate structural diagnostics]\n" + "\n".join(diagnostics)
            if diagnostics else ""
        )
        routing_text = (
            "\n\n[Specialist routing]\n" + "\n".join(f"- {item}" for item in routing)
            if routing else ""
        )
        return {"role": "user", "content": (
            f"[Iteration status]\n"
            f"{progress_line} {policy}\n\n"
            f"[Current Pareto Front]\n"
            f"{pareto_front_str}"
            f"{diagnostics_text}"
            f"{routing_text}"
        )}

    def push_candidate(self, record: CandidateRecord) -> None:
        """Add or update a candidate formula record in the run state.

        Args:
            record: Evaluated candidate formula record.
        """
        if not self.run_state.push_candidate(record):
            _logger.warning(
                "Skipping candidate with missing or non-finite ranking metrics: "
                f"{record.formula!r}"
            )

    def collect_candidates(self, response_list: list[APICallSample], results_list: list[list[ToolCallResult]], R: int, L: int, C: int) -> list[CandidateRecord]:
        """Extract valid candidate formulas from tool results and update the global leaderboard.

        Args:
            response_list: Sampled model responses for the current step.
            results_list: Tool results aligned with ``response_list``.
            R: One-based restart index.
            L: One-based refinement-step index.
            C: One-based conversation-branch index.

        Returns:
            list[CandidateRecord]: All candidate records ranked under the active metric.
        """
        loader = []
        for K in range(1, len(response_list) + 1):
            response = response_list[K - 1]
            for _, res in zip(response.tool_calls, results_list[K - 1]):
                if res.result.get('is_candidate'):
                    loader.append((K, res))

        for K, res in loader:
            train_metrics = res.result['data_split_results']['train']['metrics']
            assert self.ranking_metric in train_metrics, f"Tool result must contain '{self.ranking_metric}' in metrics for candidate formulas."
            assert 'complexity' in train_metrics, "Tool result must contain 'complexity' in metrics for candidate formulas."
            details = {
                key: value for key, value in res.result.items()
                if key not in {"formula", "is_candidate", "all_formulas"}
            }
            record = CandidateRecord(
                formula=res.result['formula'],
                node_id=self.run_state.node_id(R=R, C=C, L=L, K=K),
                details=details,
            )
            if diagnostics := res.result.get("eic_diagnostics"):
                record.details["eic_diagnostics"] = diagnostics
                self.run_state.update_diagnostics(record.formula, diagnostics)
            self.push_candidate(record)
            # 对于 call_pysr 等工具，可能会返回多个 candidate formulas, 可以将它们全部加入 top-k
            for formula_dict in res.result.get('all_formulas', []):
                assert self.ranking_metric in formula_dict["data_split_results"]["train"]["metrics"], (
                    f"Tool result must contain '{self.ranking_metric}' in metrics for candidate formulas."
                )
                record = CandidateRecord(
                    formula=formula_dict["formula"],
                    node_id=self.run_state.node_id(R=R, C=C, L=L, K=K),
                    details={key: value for key, value in formula_dict.items() if key != "formula"},
                )
                self.push_candidate(record)
        return self.run_state.ranked_candidates()

    def log_info(self, response_list: list[APICallSample], R: int, L: int, C: int) -> None:
        """Log step timing, token/cost usage, best candidate score, and tool-call counts.

        Args:
            response_list: Sampled model responses for the current step.
            R: One-based restart index.
            L: One-based refinement-step index.
            C: One-based conversation-branch index.
        """
        new_count = defaultdict(int)
        for response in response_list:
            for tool_call in response.tool_calls:
                new_count[tool_call.name] += 1
        tool_calls_str = ', '.join(
            f"{name}: {count} ({new_count[name]} new)"
            for name, count in self.tools_counter.named_count.items()
        )
        if best_record := self.best_candidate():
            metric_label, metric_value = self.get_ranking_metric(best_record)
            best_metric = f"{best_record.formula} ({metric_label}={metric_value:.6g})"
        else:
            best_metric = "None"
        log = {
            "Progress": self.format_progress(R, L, C),
            "Best": best_metric,
            "Tool Calls": tool_calls_str,
            "Speed": self.total_timer.to_str('pace'),
            "Time Usage": self.named_timer.to_str('time', 'pace', 'by_time'),
            "Token Usage": self.token_counter.to_str('count', 'speed', 'by_count'),
            "Price Usage": self.money_counter.to_str('count', 'speed', 'by_count'),
        }
        msg = "[gray] | [reset]".join(f"[blue]{k}[reset]={v}" for k, v in log.items())
        _logger.info(tag2ansi(msg))

    # Persistence and result projection

    def record_llm_result(self, llm_result: Any, R: int, L: int, C: int) -> Dict[str, Any] | None:
        """Update cumulative token and cost counters and append raw responses to ``response.jsonl``.

        Args:
            llm_result: Completed :class:`~sr_harness.core.APICallSummary` from the provider.
            R: One-based restart index.
            L: One-based refinement-step index.
            C: One-based conversation-branch index.

        Returns:
            Dict[str, Any] | None: Step and cumulative token/price usage dictionary,
                or ``None`` if usage data is unavailable.
        """
        usage = {
            "token": llm_result.token_usage,
            "price": llm_result.money_usage,
        }
        for name, num in usage['token'].items():
            self.token_counter.add(name, num)
        for name, num in usage['price'].items():
            self.money_counter.add(name, num)
        if self.save_path is not None:
            model_router = vars(self._last_model_route) if self._last_model_route is not None else None
            with open(Path(self.save_path) / 'response.jsonl', 'a') as f:
                json.dump({
                    "responses": [response.message for response in llm_result.yielded],
                    "progress": self.format_progress(R, L, C),
                    "usage": usage,
                    "model_route": model_router
                }, f)
                f.write('\n')
        return usage

    def record_search_iteration(
        self, response_list: list[APICallSample], results_list: list[list[ToolCallResult]],
        parent_nodes: dict[str, str], prompt: list[Message], usage: Usage | None,
        R: int, L: int, C: int,
    ) -> None:
        """Register search-tree nodes for all ``K`` samples in step ``(R, C, L)``.

        Args:
            response_list: Sampled model responses for the current step.
            results_list: Tool results aligned with ``response_list``.
            parent_nodes: Mapping of parent node IDs by relation type.
            prompt: Prompt messages sent to the model for this step.
            usage: Step and cumulative token/cost usage dictionary.
            R: One-based restart index.
            L: One-based refinement-step index.
            C: One-based conversation-branch index.
        """
        parents: list[ParentLink] = []
        for parent_node_id, relation in parent_nodes.items():
            if relation not in {"restart_seed", "continuation", "context_merge"}:
                _logger.warning(f"Unknown parent relation: {relation} for node_id: {parent_node_id}.")
                continue
            parents.append(self.run_state.parent_link(parent_node_id, relation))

        self.run_state.register_iteration(response_list, results_list, tuple(parents), prompt, usage, R, L, C)

    def format_progress(self, R: int | None, L: int | None, C: int | None) -> str:
        """Format the current ``(R, C, L, K)`` search coordinates as a human-readable string.

        Args:
            R: Current one-based restart index, or ``None`` before starting.
            L: Current one-based refinement-step index, or ``None``.
            C: Current one-based conversation-branch index, or ``None``.

        Returns:
            str: Formatted coordinate string such as ``"(R=1/1) × (C=1/1) × (L=2/20) × (K=1)"``.
        """
        return (
            f"(R={R}/{self.max_restart_loop}) × "
            f"(C={C}/{self.global_width}) × "
            f"(L={L}/{self.max_refinement_depth}) × "
            f"(K={self.local_sample_size})"
        )

    def get_ranking_metric(self, record: CandidateRecord | dict[str, Any]) -> tuple[str | None, float | int | None]:
        """Extract the configured ranking metric value and its display label from a candidate record.

        Args:
            record: :class:`~sr_harness.core.CandidateRecord` or candidate dictionary.

        Returns:
            tuple[str | None, float | int | None]: Pair of ``(display_label, metric_value)``,
                or ``(None, None)`` if the metric is missing.
        """
        metric_label = self.ranking_metric.replace('_', ' ').upper()
        if isinstance(record, CandidateRecord):
            split_results = record.details.get("data_split_results")
        elif isinstance(record, dict):
            split_results = record.get("data_split_results")
        else:
            return None, None
        if not isinstance(split_results, dict):
            return None, None
        validation_metrics = split_results.get("validation", {}).get("metrics", {})
        if (metric_value := validation_metrics.get(self.ranking_metric)) is not None:
            return f"validation {metric_label}", metric_value
        train_metrics = split_results.get("train", {}).get("metrics", {})
        if (metric_value := train_metrics.get(self.ranking_metric)) is not None:
            return f"training {metric_label}", metric_value
        return None, None

    def candidate_sort_key(self, record: CandidateRecord | dict[str, Any]) -> tuple[float, float] | None:
        """Compute a ``(metric_key, complexity_key)`` tuple for sorting candidates (smaller sorts first).

        Args:
            record: :class:`~sr_harness.core.CandidateRecord` or candidate dictionary.

        Returns:
            tuple[float, float] | None: Sort key tuple where lower values indicate higher
                rank, or ``None`` if the candidate lacks a finite ranking metric.
        """
        _, metric_value = self.get_ranking_metric(record)
        if metric_value is None:
            return None

        split_results = (
            record.details.get('data_split_results', {})
            if isinstance(record, CandidateRecord)
            else record.get('data_split_results', {})
        )
        train_metrics = split_results.get('train', {}).get('metrics', {})
        validation_metrics = split_results.get('validation', {}).get('metrics', {})
        metric_values = [train_metrics.get(self.ranking_metric)]
        if self.ranking_metric in validation_metrics:
            metric_values.append(validation_metrics[self.ranking_metric])
        complexity = train_metrics.get('complexity', float('inf'))
        try:
            finite_values = [float(value) for value in metric_values]
            finite_complexity = float(complexity)
        except (TypeError, ValueError):
            return None
        if any(not np.isfinite(value) for value in finite_values) or not np.isfinite(finite_complexity):
            return None

        return (
            -float(metric_value) if self.larger_is_better else float(metric_value),
            finite_complexity,
        )

    @staticmethod
    def candidate_to_dict(record: CandidateRecord) -> dict[str, Any]:
        """Convert a :class:`~sr_harness.core.CandidateRecord` into a flat dictionary for formatting utilities.

        Args:
            record: Candidate record to convert.

        Returns:
            dict[str, Any]: Flattened candidate dictionary with top-level split results.
        """
        return {
            "formula": record.formula,
            "node_id": record.node_id,
            **record.details,
        }

    def best_candidate(self) -> CandidateRecord | None:
        """Return the highest-ranked candidate formula discovered so far.

        Returns:
            CandidateRecord | None: Top-ranked candidate record, or ``None`` if no valid
                candidate has been evaluated yet.
        """
        candidates = self.run_state.ranked_candidates()
        return candidates[0] if candidates else None

    def get_pareto_front(self) -> list[CandidateRecord]:
        """Return candidate formulas on the accuracy-versus-complexity Pareto front.

        Returns:
            list[CandidateRecord]: Pareto-optimal candidates ordered from simplest to most accurate.
        """
        candidates = self.run_state.ranked_candidates()
        return [candidates[index] for index in self.run_state.pareto_indices(candidates)]

    def build_search_result(self, status: str, R: int | None, L: int | None, C: int | None) -> dict[str, Any]:
        """Assemble a serializable final result dictionary for the run.

        Args:
            status: Terminal run status (``"completed"``, ``"early_stopped"``,
                ``"interrupted"``, or ``"failed"``).
            R: Final one-based restart index, or ``None``.
            L: Final one-based refinement-step index, or ``None``.
            C: Final one-based conversation-branch index, or ``None``.

        Returns:
            dict[str, Any]: Complete search result dictionary ready for JSON serialization.
        """
        progress = self.format_progress(R, L, C)
        return self.run_state.result(status=status, progress=progress).to_dict()
