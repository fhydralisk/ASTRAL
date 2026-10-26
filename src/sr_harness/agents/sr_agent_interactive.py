# Copyright (c) 2026-present, Yumeow. Licensed under the MIT License.
"""Interactive human-in-the-loop symbolic-regression agent with live timeline events."""

from __future__ import annotations
import json
import logging
import math
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, List, Optional

from ..api import BaseAPI
from ..core import APICallSample, AgentContext, CandidateRecord, ToolCall, ToolCallResult
from ..runtime import PendingMessage, SRInteractionManager
from ..skills import SkillManager
from .sr_agent import Message, SRAgent, Usage
from .workflow_roles import collaborative_workflow_prompt
from ..parser import BaseParser

_logger = logging.getLogger(f"sr_harness.{__name__}")


class SRAgentInteractive(SRAgent):
    """Interactive symbolic-regression agent with live timeline events and human-in-the-loop controls.

    Extends :class:`~sr_harness.agents.SRAgent` with real-time event publishing,
    safe pause and force-interrupt boundaries, live settings and data refresh
    between turns, configurable stop guards, and user guidance injection.
    """

    DEFAULT_TOOLS = (*SRAgent.DEFAULT_TOOLS, "finish_search")

    _LEGACY_WORKSPACE_GUIDANCE = (
        "The structured arrays are already loaded into the scientific tools; analyze them "
        "there rather than reconstructing them from workspace files. The workspace contains "
        "supplemental files and reproducible artifacts."
    )
    _TOOL_USAGE_GUIDANCE = (
        "Use only the tools available in the current request. Do not announce a tool call "
        "without making it. If a needed capability is unavailable, explain the limitation "
        "and continue with the available scientific tools."
    )

    # Construction and frontend event bridge

    def __init__(
        self,
        llm_provider: str,
        llm_model: str,
        interaction_manager: SRInteractionManager,
        tools: list[str] | None = None,
        skills: List[str] | None = None,
        verbose: bool = False,
        tool_parser: str | BaseParser = "openai",
        save_path: Optional[str] = None,
        run_id: str | None = None,
        local_sample_size: int = 1,
        max_refinement_depth: int = 50,
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
        use_workspace: bool = False,
        workspace_files: List[str | Path] | None = None,
        force_initial_diagnostics: bool = False,
        pause_on_truncated_response: bool = True,
        tool_free_stop_review_rounds: int = 1,
        stop_guard_mode: str = "none",
        stop_guard_metric: str | None = None,
        stop_guard_threshold: float | None = None,
        stop_guard_split: str = "validation",
        stop_guard_larger_is_better: bool = True,
        auto_routing: bool = True,
        strong_llm_provider: str | None = None,
        strong_llm_model: str | None = None,
        context: AgentContext | None = None,
        skill_manager: SkillManager | None = None,
    ) -> None:
        """Initialize the interactive symbolic-regression agent.

        Args:
            llm_provider: Base LLM provider name.
            llm_model: Base model identifier.
            interaction_manager: Manager coordinating pause/resume commands, branch
                transitions, and live timeline events.
            tools: Enabled tool names, or ``None`` to use ``DEFAULT_TOOLS``.
            skills: Enabled skill names, or ``None`` to expose all available skills.
            verbose: Whether to emit debug-level runtime logs.
            tool_parser: Tool-call parser mode or :class:`~sr_harness.parser.BaseParser` instance.
            save_path: Directory where run logs are persisted, or ``None``.
            run_id: Explicit unique run identifier, or ``None`` to generate one.
            local_sample_size: Number of model responses sampled per step (``K``).
            max_refinement_depth: Maximum iterative steps per branch (``L``).
            global_width: Number of parallel conversation branches per restart (``C``).
            max_restart_loop: Number of outer restart loops (``R``).
            restart_top_k: Number of top historical formulas injected into each new restart.
            llm_max_tokens: Optional maximum output tokens per model response.
            max_workers: Worker processes for parallel tool calls (``0`` runs serially).
            validation_fraction: Fraction of samples reserved for validation.
            split_by: Validation split strategy (``"random"`` or ``"ood"``).
            split_ood_variable: Variable name used to order OOD splits.
            split_random_state: Random seed for train/validation splitting.
            ranking_metric: Metric name used to rank candidate formulas.
            larger_is_better: Whether higher values of ``ranking_metric`` are better.
            use_workspace: Whether to create a managed workspace when none is supplied.
            workspace_files: Optional host files or directories to mount read-only.
            force_initial_diagnostics: Whether to run opening diagnostics at ``L=1``.
            pause_on_truncated_response: Whether to pause at the end of a turn if a
                model response hits its output token limit.
            tool_free_stop_review_rounds: Number of recent turns sent to a separate
                tool-free check when the model emits no tool calls (``0`` disables).
            stop_guard_mode: Stop-permission condition (``"none"``, ``"best_in_topk"``,
                ``"metric_threshold"``, or ``"budget_exhausted"``).
            stop_guard_metric: Metric inspected when ``stop_guard_mode="metric_threshold"``.
            stop_guard_threshold: Target metric threshold for ``metric_threshold`` mode.
            stop_guard_split: Dataset split (``"validation"`` or ``"train"``) checked by
                the metric threshold guard.
            stop_guard_larger_is_better: Whether the stop-guard metric is larger-is-better.
            auto_routing: Whether to dynamically route between base and strong models.
            strong_llm_provider: Provider for the strong model.
            strong_llm_model: Optional stronger model identifier.
            context: Optional shared :class:`~sr_harness.core.AgentContext`.
            skill_manager: Optional :class:`~sr_harness.skills.SkillManager`.
        """
        super().__init__(
            llm_provider=llm_provider,
            llm_model=llm_model,
            tools=tools,
            skills=skills,
            verbose=verbose,
            tool_parser=tool_parser,
            save_path=save_path,
            run_id=run_id,
            local_sample_size=local_sample_size,
            max_refinement_depth=max_refinement_depth,
            global_width=global_width,
            max_restart_loop=max_restart_loop,
            restart_top_k=restart_top_k,
            llm_max_tokens=llm_max_tokens,
            max_workers=max_workers,
            validation_fraction=validation_fraction,
            split_by=split_by,
            split_ood_variable=split_ood_variable,
            split_random_state=split_random_state,
            ranking_metric=ranking_metric,
            larger_is_better=larger_is_better,
            force_initial_diagnostics=force_initial_diagnostics,
            auto_routing=auto_routing,
            strong_llm_provider=strong_llm_provider,
            strong_llm_model=strong_llm_model,
            context=context,
            skill_manager=skill_manager,
        )

        # 工作区
        self.use_workspace = use_workspace
        self.workspace_files = workspace_files

        # 交互界面
        if not isinstance(interaction_manager, SRInteractionManager):
            raise TypeError("interaction_manager must be an SRInteractionManager")
        self.interaction_manager = interaction_manager
        self.pause_on_truncated_response = pause_on_truncated_response
        self.tool_free_stop_review_rounds = tool_free_stop_review_rounds
        self.stop_guard_mode = stop_guard_mode
        self.stop_guard_metric = stop_guard_metric
        self.stop_guard_threshold = stop_guard_threshold
        self.stop_guard_split = stop_guard_split
        self.stop_guard_larger_is_better = stop_guard_larger_is_better
        self._validate_stop_settings()
        self._last_iteration_had_tool_calls = True
        self._last_response_was_truncated = False
        self._forced_interruption_pending = False
        self._pending_stop_at_boundary = False
        self._stop_check_L: int | None = None
        self._stop_review_apis: dict[tuple[str, str], BaseAPI] = {}
        self._response_followup_messages: list[Message] = []
        self.initial_messages: list[PendingMessage] = []
        self.prompt_overrides: dict[str, str] = {}
        self.variable_descriptions: dict[str, str] = {}
        self.runtime_settings_supplier: Callable[[], dict[str, Any] | None] | None = None
        self.runtime_settings_committer: Callable[[dict[str, Any]], None] | None = None
        self._bind_tool_cancellation()

    def on_buffer_messages_added(self, messages: list[Message], **coordinate: int) -> None:
        """Publish ``prompt_added`` timeline events whenever system or user messages enter the buffer.

        Args:
            messages: Newly appended conversation messages.
            **coordinate: Active ``R``, ``C``, and ``L`` search coordinates.
        """
        for message in messages:
            if message.get("role") not in {"system", "user"}:
                continue
            payload: dict[str, Any] = {"message": message}
            if coordinate:
                payload["coord"] = coordinate
            self.interaction_manager.publish_event("prompt_added", payload)

    # Runtime settings and tool context

    def _take_runtime_settings(self) -> dict[str, Any] | None:
        return self.runtime_settings_supplier() if self.runtime_settings_supplier else None

    def _commit_runtime_settings(self, settings: dict[str, Any]) -> None:
        if self.runtime_settings_committer is not None:
            self.runtime_settings_committer(settings)

    def _bind_tool_cancellation(self) -> None:
        """Share the hard-interrupt event with every active tool instance."""
        for tool in self.tool_box.tools if self.tool_box is not None else []:
            tool.cancel_event = self.interaction_manager.cancellation_signal

    def _validate_stop_settings(self) -> None:
        """Validate settings that control model-requested safe stopping."""
        if (
            isinstance(self.tool_free_stop_review_rounds, bool)
            or not isinstance(self.tool_free_stop_review_rounds, int)
            or not 0 <= self.tool_free_stop_review_rounds <= 1000
        ):
            raise ValueError("tool_free_stop_review_rounds must be between 0 and 1000")
        if self.stop_guard_mode not in {
            "none", "best_in_topk", "metric_threshold", "budget_exhausted",
        }:
            raise ValueError(f"Unsupported stop_guard_mode: {self.stop_guard_mode}")
        if self.stop_guard_split not in {"train", "validation"}:
            raise ValueError("stop_guard_split must be train or validation")
        if self.stop_guard_metric is not None and (
            not isinstance(self.stop_guard_metric, str) or not self.stop_guard_metric.strip()
        ):
            raise ValueError("stop_guard_metric must be null or a non-empty string")
        if self.stop_guard_threshold is not None:
            if isinstance(self.stop_guard_threshold, bool) or not isinstance(
                self.stop_guard_threshold, (int, float)
            ) or not math.isfinite(float(self.stop_guard_threshold)):
                raise ValueError("stop_guard_threshold must be null or a finite number")
        if self.stop_guard_mode == "metric_threshold" and self.stop_guard_threshold is None:
            raise ValueError(f"{self.stop_guard_mode} requires stop_guard_threshold")

    def initialize_with_context(self, context: AgentContext) -> None:
        """Bind tools and API to the shared context and attach the cancellation signal.

        Args:
            context: Shared runtime context for the interactive session.
        """
        super().initialize_with_context(context)
        if hasattr(self, "interaction_manager"):
            self._bind_tool_cancellation()

    @contextmanager
    def prepare_tool_context(self, tool_context: AgentContext) -> Iterator[AgentContext]:
        """Bind interactive workspace and stop-check hooks to the tool context for the duration of a run.

        Args:
            tool_context: Shared context used to initialize tools.

        Yields:
            AgentContext: Context configured with workspace access and finish-search hooks.
        """
        if not self.use_workspace:
            yield tool_context
            return

        if tool_context.workspace is not None:
            yield tool_context
            return

        from ..runtime.workspace import Workspace

        workspace = Workspace(tempfile.mkdtemp(prefix="sr_workspace_"))
        for source in self.workspace_files or ():
            workspace.mount(source)
        _logger.note(f"Workspace initialized at: {workspace.path}")
        tool_context.workspace = workspace
        yield tool_context

    # Interactive search-boundary hooks

    def prepare_iteration(self, buffer: list[Message], R: int, L: int, C: int) -> str | None:
        """Handle pause requests, queued user messages, setting updates, and data refreshes before a turn.

        Args:
            buffer: Current branch conversation buffer.
            R: One-based restart index.
            L: One-based refinement-step index.
            C: One-based conversation-branch index.

        Returns:
            str | None: Branch transition command (``"next_c"`` or ``"next_r"``), or
                ``None`` to continue the current branch.
        """
        self.interaction_manager.publish_event("search_position_changed", {"R": R, "C": C, "L": L})
        with self.interaction_manager.wait() as boundary_messages:
            messages = [*self.initial_messages, *boundary_messages]
            self.initial_messages.clear()
            if data_change := self.refresh_data():
                self._append_buffer_messages(
                    buffer,
                    [self.build_data_refresh_message(data_change)],
                    R=R,
                    C=C,
                    L=L,
                )
            for message in messages:
                prompt = {
                    "role": "user",
                    "content": f"[Human guidance injected during the run]\n{message.content}",
                }
                self._append_buffer_messages(buffer, [prompt], R=R, C=C, L=L)
        if settings := self._take_runtime_settings():
            self._apply_runtime_settings(settings)
        return self.interaction_manager.consume_search_transition()

    @staticmethod
    def build_data_refresh_message(change: dict[str, Any]) -> dict[str, str]:
        """Format a user-role notification describing variable or role updates in ``context.data``.

        Args:
            change: Revision change dictionary returned by :meth:`refresh_data`.

        Returns:
            dict[str, str]: User-role message informing the model of the updated dataset.
        """
        descriptions = change["variable_descriptions"]
        description_text = (
            "\nVariable descriptions:\n"
            + "\n".join(f"- {name}: {description}" for name, description in descriptions.items())
            if descriptions else ""
        )
        return {
            "role": "user",
            "content": (
                "[Structured data updated by the data-preparation agent]\n"
                f"Data revision changed from {change['previous_revision']} to {change['revision']}. "
                f"The target is {change['target']!r}; available features are {change['features']}. "
                "Reassess earlier evidence against the updated variables and continue the investigation."
                f"{description_text}"
            ),
        }

    def _apply_runtime_settings(self, settings: dict[str, Any]) -> None:
        """Apply frontend-requested model and capability changes at a safe boundary."""
        try:
            tool_names = settings.get("tools")
            requested_tools = (
                set(self.available_tool_classes) if tool_names is None else set(tool_names)
            )
            if unknown_tools := requested_tools - self.available_tool_classes.keys():
                raise ValueError(f"Unknown tools: {', '.join(sorted(unknown_tools))}")
            self.tool_cls_list = [
                tool_cls for name, tool_cls in self.available_tool_classes.items()
                if name in requested_tools
            ]
            registered_skills = self.skill_manager.load_skills()
            self.skill_manager.register_tool_docs([
                tool_cls for tool_cls in self.tool_cls_list
                if (doc := tool_cls.get_doc()) is not None
                and doc["name"] not in registered_skills
            ])
            available_skills = self.skill_manager.load_skills()
            skill_names = settings.get("skills")
            requested_skills = set(available_skills) if skill_names is None else set(skill_names)
            if unknown_skills := requested_skills - available_skills.keys():
                raise ValueError(f"Unknown skills: {', '.join(sorted(unknown_skills))}")
            requested_skills.update(
                doc["name"]
                for tool_cls in self.tool_cls_list
                if (doc := tool_cls.get_doc()) is not None
            )
            self.enabled_skills = requested_skills
            self.llm_provider = settings["llm_provider"]
            self.llm_model = settings["llm_model"]
            for name in (
                "local_sample_size",
                "max_refinement_depth",
                "global_width",
                "max_restart_loop",
                "restart_top_k",
                "llm_max_tokens",
                "max_workers",
                "validation_fraction",
                "split_by",
                "split_ood_variable",
                "split_random_state",
                "ranking_metric",
                "larger_is_better",
                "force_initial_diagnostics",
                "pause_on_truncated_response",
                "tool_free_stop_review_rounds",
                "stop_guard_mode",
                "stop_guard_metric",
                "stop_guard_threshold",
                "stop_guard_split",
                "stop_guard_larger_is_better",
                "auto_routing",
                "tool_parser",
            ):
                if name in settings:
                    setattr(self, name, settings[name])
            self._validate_stop_settings()
            self.strong_llm_provider = (
                self.llm_provider
                if settings.get("strong_llm_provider") is None
                else settings["strong_llm_provider"]
            )
            self.strong_llm_model = settings.get("strong_llm_model")
            if self.force_initial_diagnostics:
                required_tools = {"statistics_analysis", "relationship_analysis", "read_skill"}
                if missing := required_tools - requested_tools:
                    raise ValueError(
                        "force_initial_diagnostics requires enabled tools: "
                        + ", ".join(sorted(missing))
                    )
                if "discover-symbolic-laws" not in self.enabled_skills:
                    raise ValueError(
                        "force_initial_diagnostics requires the discover-symbolic-laws skill"
                    )
            self.context.args.validation_fraction = self.validation_fraction
            self.context.args.split_by = self.split_by
            self.context.args.split_ood_variable = self.split_ood_variable
            self.context.args.split_random_state = self.split_random_state
            self.context.invalidate_splits()
            self.context.args.llm_provider = self.llm_provider
            self.context.args.llm_model = self.llm_model
            self.context.args.llm_max_tokens = self.llm_max_tokens
            self.context.args.enabled_skills = sorted(self.enabled_skills)
            self.initialize_with_context(self.context)
            self._bind_tool_cancellation()
            self.model_router.base_provider = self.llm_provider
            self.model_router.base_model = self.llm_model
            self.model_router.enabled = self.auto_routing
            self.model_router.strong_provider = self.strong_llm_provider
            self.model_router.strong_model = self.strong_llm_model
            self.run_state.ranking_metric = self.ranking_metric
            self.run_state.larger_is_better = self.larger_is_better
            self._strong_api = None
            self._stop_review_apis.clear()
            self._commit_runtime_settings(settings)
            self.interaction_manager.publish_event("settings_applied", settings)
        except Exception as exc:
            self.interaction_manager.publish_event("settings_failed", {"error": str(exc)})

    def finish_iteration(self, buffer: list[Message], R: int, L: int, C: int) -> str | None:
        """Check explicit ``finish_search`` requests or tool-free stop reviews at the end of a turn.

        Unlike non-interactive runs, satisfying a stop condition pauses the agent at
        a safe boundary rather than terminating the session thread, allowing the user
        to inspect results and resume exploration if desired.

        Args:
            buffer: Current branch conversation buffer.
            R: One-based restart index.
            L: One-based refinement-step index.
            C: One-based conversation-branch index.

        Returns:
            str | None: Always ``None`` so the interactive session remains resumable;
                pauses are coordinated through ``self.interaction_manager``.
        """
        if self._forced_interruption_pending or self.interaction_manager.is_interrupting:
            prompt = {"role": "user", "content": "用户强制中止"}
            self._append_buffer_messages(buffer, [prompt], R=R, C=C, L=L)
            self._forced_interruption_pending = False
            return None
        if self._last_response_was_truncated and self.pause_on_truncated_response:
            self.interaction_manager.request_pause()
        elif getattr(self, "_pending_stop_at_boundary", False):
            self._pending_stop_at_boundary = False
            self.interaction_manager.request_pause()
        elif (
            not self._last_iteration_had_tool_calls
            and not self._last_response_was_truncated
            and getattr(self, "tool_free_stop_review_rounds", 1) > 0
            and self.interaction_manager.state == "running"
            and not self.interaction_manager.status().get("pending_messages")
            and self.interaction_manager.status().get("pending_transition") is None
        ):
            should_stop, review_reason = self._review_tool_free_stop(buffer, R=R, L=L, C=C)
            if should_stop:
                rejection = self._stop_rejection_reason(L=L)
                if rejection is None:
                    self.interaction_manager.request_pause()
                else:
                    self._append_buffer_messages(buffer, [{
                        "role": "user",
                        "content": (
                            "[Stop request rejected]\n"
                            f"{rejection} Continue the symbolic-regression search."
                        ),
                    }], R=R, C=C, L=L)
            else:
                _logger.info(
                    f"Tool-free response will continue after stop review: {review_reason}"
                )
        self._last_response_was_truncated = False
        return None

    def _recent_agent_rounds(self, buffer: list[Message]) -> list[Message]:
        """Return a plain-message suffix containing the configured number of Agent turns."""
        assistant_indices = [
            index for index, message in enumerate(buffer) if message.get("role") == "assistant"
        ]
        if not assistant_indices:
            return []
        start = assistant_indices[-min(self.tool_free_stop_review_rounds, len(assistant_indices))]
        fields = {"role", "content", "reasoning", "tool_calls", "name"}
        return [
            {key: value for key, value in message.items() if key in fields}
            for message in buffer[start:]
        ]

    @staticmethod
    def _parse_stop_review(content: str) -> tuple[bool, str]:
        """Parse the review model's strict JSON decision conservatively."""
        try:
            start = content.index("{")
            end = content.rindex("}") + 1
            payload = json.loads(content[start:end])
            decision = payload.get("should_stop")
            reason = str(payload.get("reason", "")).strip()
            if not isinstance(decision, bool):
                raise ValueError("should_stop is not boolean")
            return decision, reason
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return False, f"invalid stop-review response: {exc}"

    def _review_tool_free_stop(
        self, buffer: list[Message], *, R: int, L: int, C: int,
    ) -> tuple[bool, str]:
        """Ask a tool-free BaseAPI call whether the Agent intended to stop."""
        route = self._last_model_route
        provider = route.provider if route is not None else self.llm_provider
        model = route.model if route is not None else self.llm_model
        key = (provider, model)
        api = self._stop_review_apis.get(key)
        if api is None:
            api = BaseAPI.create(
                provider,
                model=model,
                environment=getattr(self.context.args, "api_environment", None),
            )
            self._stop_review_apis[key] = api
        recent = self._recent_agent_rounds(buffer)
        messages = [{
            "role": "system",
            "content": (
                "Decide whether the symbolic-regression Agent intends to hand control back "
                "to the user now. Return JSON only: "
                '{"should_stop": true|false, "reason": "brief explanation"}. '
                "Answer false when it is planning, analyzing, describing a next action, or "
                "otherwise appears to have unfinished autonomous work. Answer true only for "
                "a final answer, an explicit request for user input, or an explicit decision to stop."
            ),
        }, {
            "role": "user",
            "content": "Recent Agent rounds:\n" + json.dumps(recent, ensure_ascii=False),
        }]
        try:
            with self.interaction_manager.cancellable(api.cancel):
                result = api(messages, n=1)
                responses = list(result)
            usage = {"token": result.token_usage, "price": result.money_usage}
            for name, value in usage.get("token", {}).items():
                self.token_counter.add(name, value)
            for name, value in usage.get("price", {}).items():
                self.money_counter.add(name, value)
            content = responses[0].content if responses else ""
            decision, reason = self._parse_stop_review(content)
            if self.save_path is not None:
                with open(Path(self.save_path) / "stop_reviews.jsonl", "a", encoding="utf-8") as stream:
                    json.dump({
                        "progress": self.format_progress(R, L, C),
                        "provider": provider,
                        "model": model,
                        "rounds": recent,
                        "response": content,
                        "should_stop": decision,
                        "reason": reason,
                        "usage": usage,
                    }, stream, ensure_ascii=False)
                    stream.write("\n")
            return decision, reason
        except Exception as exc:
            _logger.warning(f"Stop review failed; continuing the search: {exc}")
            return False, f"stop review failed: {exc}"

    @staticmethod
    def _result_metric_values(
        result: ToolCallResult, metric: str, split: str,
    ) -> list[float]:
        """Extract finite metric values from one candidate-producing tool result."""
        candidates = [result.result, *result.result.get("all_formulas", [])]
        values = []
        for candidate in candidates:
            value = (
                candidate.get("data_split_results", {})
                .get(split, {})
                .get("metrics", {})
                .get(metric)
            )
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(numeric):
                values.append(numeric)
        return values

    def _stop_metric_values(
        self, metric: str, split: str, extra_results: list[ToolCallResult] | None = None,
    ) -> list[float]:
        """Collect stop-check metrics from retained and same-response candidates."""
        values = []
        for record in self.run_state.ranked_candidates():
            try:
                value = float(record.metric(metric, split))
            except (TypeError, ValueError):
                continue
            if math.isfinite(value):
                values.append(value)
        for result in extra_results or []:
            values.extend(self._result_metric_values(result, metric, split))
        return values

    def _topk_ranking_values(
        self, extra_results: list[ToolCallResult] | None = None,
    ) -> dict[str, float]:
        """Return the best ranking-metric value retained for each distinct formula."""
        candidates: list[CandidateRecord | dict[str, Any]] = list(
            self.run_state.ranked_candidates()
        )
        for result in extra_results or []:
            if result.result.get("is_candidate"):
                candidates.append(result.result)
            candidates.extend(
                candidate
                for candidate in result.result.get("all_formulas", [])
                if isinstance(candidate, dict)
            )
        values: dict[str, float] = {}
        for index, candidate in enumerate(candidates):
            formula = (
                candidate.formula
                if isinstance(candidate, CandidateRecord)
                else candidate.get("formula")
            )
            _, value = self.get_ranking_metric(candidate)
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(numeric):
                continue
            key = str(formula) if formula is not None else f"<unnamed:{index}>"
            previous = values.get(key)
            if previous is None or (
                numeric > previous if self.larger_is_better else numeric < previous
            ):
                values[key] = numeric
        return values

    def _stop_rejection_reason(
        self, *, L: int, extra_results: list[ToolCallResult] | None = None,
    ) -> str | None:
        """Return why stopping is forbidden, or ``None`` when it is allowed."""
        if self.stop_guard_mode == "none":
            return None
        if self.stop_guard_mode == "budget_exhausted":
            if L < self.max_refinement_depth:
                return (
                    f"The configured search budget is not exhausted: current round L={L}, "
                    f"required L={self.max_refinement_depth}."
                )
            return None
        if self.stop_guard_mode == "best_in_topk":
            values_by_formula = self._topk_ranking_values(extra_results)
            if not values_by_formula:
                return (
                    f"topk_records contains no candidate with a finite ranking metric "
                    f"({self.ranking_metric}), so stopping is not allowed."
                )
            ordered = sorted(
                values_by_formula.items(),
                key=lambda item: item[1],
                reverse=self.larger_is_better,
            )
            if len(ordered) == 1:
                return None
            best_formula, best = ordered[0]
            runner_up_formula, runner_up = ordered[1]
            strictly_better = best > runner_up if self.larger_is_better else best < runner_up
            if strictly_better:
                return None
            direction = ">" if self.larger_is_better else "<"
            return (
                f"No result in topk_records strictly beats every other formula on "
                f"{self.ranking_metric}: {best_formula!r} and {runner_up_formula!r} are tied "
                f"at {best:.12g}; stopping requires a unique best value ({direction} all others)."
            )
        metric = self.stop_guard_metric or self.ranking_metric
        values = self._stop_metric_values(
            metric, self.stop_guard_split, extra_results=extra_results,
        )
        if not values:
            return (
                f"No candidate has a finite {self.stop_guard_split} {metric} value, "
                "so the configured stopping condition is not satisfied."
            )
        threshold = float(self.stop_guard_threshold)
        best = max(values) if self.stop_guard_larger_is_better else min(values)
        passed = best >= threshold if self.stop_guard_larger_is_better else best <= threshold
        if passed:
            return None
        direction = ">=" if self.stop_guard_larger_is_better else "<="
        return (
            f"The best {self.stop_guard_split} {metric} is {best:.12g}; stopping requires "
            f"{metric} {direction} {threshold:.12g}."
        )

    def build_response_followup_messages(
        self,
        response_list: list[APICallSample],
        results_list: list[list[ToolCallResult]],
        *,
        R: int,
        L: int,
        C: int,
    ) -> list[Message]:
        """Drain and return any follow-up user prompts generated during the current step (such as rejected stop reasons).

        Args:
            response_list: Sampled model responses for the current step.
            results_list: Tool results aligned with ``response_list``.
            R: One-based restart index.
            L: One-based refinement-step index.
            C: One-based conversation-branch index.

        Returns:
            list[Message]: Follow-up messages to append to the conversation buffer.
        """
        messages = self._response_followup_messages
        self._response_followup_messages = []
        return messages

    # Initial-prompt customization hooks

    def create_initial_system_prompt(self, restart_records: list[CandidateRecord]) -> str:
        """Create the interactive system prompt without advertising workspace-mutation tools.

        Args:
            restart_records: Top historical candidates from prior restarts.

        Returns:
            str: System prompt tailored for interactive symbolic regression.
        """
        mse_goal = self._build_mse_goal(restart_records)
        return collaborative_workflow_prompt("regression") + (
            "You are a Symbolic Regression Agent working with a human researcher. "
            "Your goal is to discover simple, interpretable mathematical formulas that explain "
            "the relationship between feature variables and the target variable.\n\n"
            "Guidelines:\n"
            "- Explore data thoroughly before proposing formulas.\n"
            "- Prefer simple, interpretable expressions over complex ones.\n"
            f"- {mse_goal}\n"
            f"- {self._TOOL_USAGE_GUIDANCE}"
        )

    @classmethod
    def normalize_system_prompt(cls, prompt: str) -> str:
        """Strip legacy workspace-tool instructions from a saved or user-submitted system prompt.

        Args:
            prompt: Raw system prompt string.

        Returns:
            str: Cleaned system prompt with capability-neutral guidance.
        """
        marker = cls._LEGACY_WORKSPACE_GUIDANCE
        start = prompt.find(marker)
        if start < 0:
            return prompt
        end = start + len(marker)
        for suffix in (
            " Use workspace_shell for bounded file operations and workspace_code_executor for Python analysis.",
            " Use workspace_shell for bounded file operations.",
            " Use workspace_code_executor for Python analysis.",
        ):
            if prompt.startswith(suffix, end):
                end += len(suffix)
                break
        before = prompt[:start].rstrip()
        after = prompt[end:].lstrip()
        replacement = f"- {cls._TOOL_USAGE_GUIDANCE}"
        return "\n".join(part for part in (before, replacement, after) if part)

    def customize_initial_prompts(self, messages: list[Message], *, X: dict[str, Any], y: dict[str, Any]) -> list[Message]:
        """Apply variable descriptions and user/system prompt overrides from the WebUI.

        Args:
            messages: Generated initial system and user messages.
            X: Input feature arrays keyed by variable name.
            y: Target variable mapping ``{target_name: array}``.

        Returns:
            list[Message]: Messages incorporating any active UI overrides.
        """
        descriptions = getattr(self, "variable_descriptions", {})
        rows = [f"- {name}: {descriptions[name]}" for name in [*X, *y] if descriptions.get(name)]
        if rows:
            messages[1]["content"] += "\n\nVariable descriptions:\n" + "\n".join(rows)
        overrides = getattr(self, "prompt_overrides", {})
        for message in messages:
            if message.get("role") in overrides:
                content = overrides[message["role"]]
                if message["role"] == "system":
                    content = self.normalize_system_prompt(content)
                message["content"] = content
        return messages

    # Streaming model and tool events

    def request_llm(self, prompt: list[Message], R: int, L: int, C: int) -> tuple[list[APICallSample], Usage]:
        """Sample model responses while streaming live delta events to the WebUI timeline.

        Handles mid-stream force-interruptions and optional pause-on-truncation policies.

        Args:
            prompt: Provider-ready conversation messages.
            R: One-based restart index.
            L: One-based refinement-step index.
            C: One-based conversation-branch index.

        Returns:
            tuple[list[APICallSample], Usage]: Completed or partially recovered
                model responses and token/cost usage.
        """
        coord = {"R": R, "C": C, "L": L}
        self.interaction_manager.publish_event("context", {"messages": prompt, "coord": coord})
        route = self.model_router.route(
            task_score=self._task_route_score,
            task_reasons=self._task_route_reasons,
            refinement_step=L,
        )
        tool_schemas = {
            tool.metadata.name: self.tool_schema(tool.metadata.name)
            for tool in self.tool_box.tools
            if getattr(tool, "metadata", None) is not None
        }
        response_ids = {
            K: f"{self.run_state.run_id}:{R}:{C}:{L}:{K}"
            for K in range(1, self.local_sample_size + 1)
        }
        started_samples: set[int] = set()

        def start_sample(K: int) -> None:
            if K in started_samples:
                return
            started_samples.add(K)
            self.interaction_manager.publish_event("assistant_started", {
                "response_id": response_ids[K],
                "coord": coord | {"K": K},
                "tool_schemas": tool_schemas,
                "provider": route.provider,
                "model": route.model,
            })
        # Show the first wait immediately; later samples start only when reached.
        start_sample(1)
        last_stream_emit: dict[int, float] = {}
        latest_stream_updates: dict[int, dict[str, Any]] = {}

        def callback(update: dict[str, Any]) -> None:
            K = max(1, min(int(update.get("sample", 1)), self.local_sample_size))
            start_sample(K)
            latest_stream_updates[K] = update
            now = time.monotonic()
            if update.get("type") == "delta" and now - last_stream_emit.get(K, 0.0) < 0.08:
                return
            last_stream_emit[K] = now
            self.interaction_manager.publish_event("assistant_delta", {
                **update,
                "response_id": response_ids[K],
                "coord": coord | {"K": K},
                "tool_schemas": tool_schemas,
                "provider": route.provider,
                "model": route.model,
            })

        interrupted = False
        response_error: str | None = None
        self._last_response_was_truncated = False
        try:
            with self.interaction_manager.cancellable(self.api.cancel):
                responses, usage = super().request_llm(
                    prompt,
                    R=R,
                    L=L,
                    C=C,
                    callback=callback,
                )
        except InterruptedError:
            interrupted = True
            response_error = "用户强制中止"
            self._forced_interruption_pending = True
            responses = []
            for K in sorted(started_samples):
                update = latest_stream_updates.get(K, {})
                message = {
                    "role": "assistant",
                    "content": update.get("content", ""),
                }
                if update.get("reasoning"):
                    message["reasoning"] = update["reasoning"]
                responses.append(APICallSample(
                    content=message["content"],
                    message_extra={key: value for key, value in message.items() if key != "content"},
                ))
            usage = {"token": {}, "price": {}}
        except Exception as exc:
            for K in sorted(started_samples):
                self.interaction_manager.publish_event("assistant_failed", {
                    **latest_stream_updates.get(K, {}),
                    "response_id": response_ids[K],
                    "coord": coord | {"K": K},
                    "provider": route.provider,
                    "model": route.model,
                    "error": str(exc),
                })
            raise
        self._last_iteration_had_tool_calls = any(response.tool_calls for response in responses)
        cumulative_usage = {
            "token": self.token_counter.named_count,
            "price": self.money_counter.named_count,
        }
        for K, response in enumerate(responses, 1):
            start_sample(K)
            content = response.content
            calls = response.tool_calls
            message = response.message
            self.interaction_manager.publish_event(
                "assistant_failed" if response_error else "assistant_completed",
                {
                    "response_id": response_ids[K],
                    "content": content,
                    "finish_reason": response.finish_reason,
                    "reasoning": message.get("reasoning", ""),
                    "message": message,
                    "tool_calls": calls,
                    "tool_schemas": tool_schemas,
                    "coord": coord | {"K": K},
                    "usage": usage,
                    "cumulative_usage": cumulative_usage,
                    "provider": route.provider,
                    "model": route.model,
                    **({"error": response_error, "interrupted": interrupted} if response_error else {}),
                },
            )
        return responses, usage

    def tool_schema(self, name: str) -> dict[str, Any]:
        """Return the JSON parameter schema for an initialized tool by name.

        Args:
            name: Registered tool name.

        Returns:
            dict[str, Any]: Tool parameter JSON schema, or an empty dict if not found.
        """
        return next(
            (
                {
                    "description": tool.metadata.description,
                    "parameters": tool.metadata.parameters or {},
                }
                for tool in self.tool_box.tools
                if tool.metadata.name == name
            ),
            {},
        )

    def execute_action(self, actions: list[ToolCall]) -> list[ToolCallResult]:
        """Execute tool calls sequentially while publishing start/completion events and honoring force-pause.

        Args:
            actions: Normalized tool calls to execute.

        Returns:
            list[ToolCallResult]: Tool execution results in call order.
        """
        results: list[ToolCallResult | None] = [None] * len(actions)
        finish_indices = []
        for index, action in enumerate(actions):
            if action.name == "finish_search" and any(
                tool.metadata.name == "finish_search" for tool in self.tool_box.tools
            ):
                finish_indices.append(index)
                continue
            tool_schema = self.tool_schema(action.name)
            self.interaction_manager.publish_event("tool_started", {"call": action, "tool_schema": tool_schema})
            started_at = time.monotonic()
            try:
                tool = self.tool_box[action.name]
            except KeyError:
                tool = None
            if tool is None:
                result = super().execute_action([action])[0]
            else:
                with self.interaction_manager.cancellable(tool.cancel):
                    result = super().execute_action([action])[0]
            self.interaction_manager.publish_event("tool_completed", {
                "call": action,
                "tool_schema": tool_schema,
                "duration_seconds": time.monotonic() - started_at,
                "result": result,
            })
            results[index] = result
        ordinary_results = [result for result in results if result is not None]
        for index in finish_indices:
            action = actions[index]
            tool = self.tool_box["finish_search"]
            tool_schema = self.tool_schema(action.name)
            self.interaction_manager.publish_event(
                "tool_started", {"call": action, "tool_schema": tool_schema},
            )
            started_at = time.monotonic()
            timestamp = time.time()
            self.tools_counter.add(action.name)
            rejection = self._stop_rejection_reason(
                L=self._stop_check_L or 1,
                extra_results=ordinary_results,
            )
            payload = (
                {"status": "stopped", "reason": str(action.params.get("reason", "")).strip()}
                if rejection is None
                else {"status": "rejected", "reason": rejection}
            )
            result = ToolCallResult(
                ok=True,
                result=payload,
                result_str=tool.format_result_dict(payload),
                meta_data={
                    "timestamp": timestamp,
                    "execution_time": time.monotonic() - started_at,
                    "tool": action.name,
                },
            )
            if rejection is None:
                self._pending_stop_at_boundary = True
            self.interaction_manager.publish_event("tool_completed", {
                "call": action,
                "tool_schema": tool_schema,
                "duration_seconds": time.monotonic() - started_at,
                "result": result,
            })
            results[index] = result
        if any(result is None for result in results):
            raise RuntimeError("Tool execution did not produce one result per call")
        return [result for result in results if result is not None]

    def execute_tool_calls(
        self, response_list: list[APICallSample], R: int, L: int, C: int,
    ) -> list[list[ToolCallResult]]:
        """Bind the current refinement step ``L`` and execute tool calls for all ``K`` samples.

        Args:
            response_list: Sampled model responses for the current step.
            R: One-based restart index.
            L: One-based refinement-step index.
            C: One-based conversation-branch index.

        Returns:
            list[list[ToolCallResult]]: Tool results grouped by sample index.
        """
        self._stop_check_L = L
        try:
            return super().execute_tool_calls(response_list, R=R, L=L, C=C)
        finally:
            self._stop_check_L = None

    def collect_candidates(self, *args: Any, **kwargs: Any) -> list[CandidateRecord]:
        """Collect candidate formulas and publish a ``topk_updated`` event to the WebUI.

        Args:
            *args: Positional arguments forwarded to :meth:`SRAgent.collect_candidates`.
            **kwargs: Keyword arguments forwarded to :meth:`SRAgent.collect_candidates`.

        Returns:
            list[CandidateRecord]: Ranked candidate records.
        """
        records = super().collect_candidates(*args, **kwargs)
        self.interaction_manager.publish_event("topk_updated", {"records": [record.display_dict() for record in records]})
        return records

    def record_tool_calls(
        self,
        tool_calls: list[ToolCall],
        results: list[ToolCallResult],
        R: int,
        L: int,
        C: int,
        forced: bool = False,
    ) -> None:
        """Persist tool calls and publish timeline cards for framework-initiated diagnostics.

        Args:
            tool_calls: Executed tool calls.
            results: Corresponding tool execution results.
            R: One-based restart index.
            L: One-based refinement-step index.
            C: One-based conversation-branch index.
            forced: Whether the calls were triggered automatically by initial diagnostics.
        """
        super().record_tool_calls(tool_calls, results, R=R, L=L, C=C, forced=forced)
        if forced:
            for call, result in zip(tool_calls, results):
                self.interaction_manager.publish_event("tool_completed", {
                    "call": call,
                    "tool_schema": self.tool_schema(call.name),
                    "result": result,
                    "forced": True,
                })

    def execute_action_parallel(self, actions: list[ToolCall], max_workers: int) -> list[ToolCallResult]:
        """Disallow parallel tool execution in interactive mode.

        Args:
            actions: Tool calls to execute.
            max_workers: Requested worker count.

        Raises:
            NotImplementedError: Always raised because interactive tool events and
                cancellation hooks are managed serially.
        """
        raise NotImplementedError(
            "Parallel execution is not supported in interactive mode, "
            "since workspace tools cannot guarantee read-only access. "
            "Please set max_workers=0 to disable parallel execution when using interactive tools."
        )
