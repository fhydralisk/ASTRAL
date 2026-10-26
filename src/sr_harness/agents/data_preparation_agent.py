# Copyright (c) 2026-present, Yumeow. Licensed under the MIT License.
"""Persistent tool-using agent for preparing structured research data."""

from __future__ import annotations

import time
import uuid
from copy import deepcopy
from typing import Any

from ..core import AgentContext
from ..runtime import InteractionManager
from ..parser import BaseParser
from ..skills import SkillManager
from ..tools import BaseTool
from ..utils import ParallelTimer
from .agent import Agent
from .workflow_roles import collaborative_workflow_prompt


class DataPreparationAgent(Agent):
    """Interactive agent that inspects raw workspace files and builds ``context.data/``.

    Maintains a multi-turn conversation across user instructions, running
    sandboxed Python scripts and workspace utilities to clean data, derive
    variables, and validate ``context.data/manifest.json`` before committing
    structured arrays to the shared :class:`~sr_harness.core.AgentContext`.
    """

    DEFAULT_TOOLS = [
        "workspace_shell",
        "workspace_code_executor",
        "web_search",
        "web_fetch",
        "read_pdf",
        "read_skill",
        "validate_context_data",
    ]
    DEFAULT_EXCLUDED_SKILLS = frozenset({"discover-symbolic-laws"})

    def __init__(
        self,
        llm_provider: str,
        llm_model: str,
        *,
        context: AgentContext,
        tools: list[str] | None = None,
        tool_parser: str | BaseParser = "openai",
        llm_max_tokens: int | None = None,
        skills: list[str] | None = None,
        interaction_manager: InteractionManager,
    ) -> None:
        """Initialize the data preparation agent.

        Args:
            llm_provider: Name of the LLM provider backend (e.g., ``"openrouter"``).
            llm_model: Model identifier requested from the provider.
            context: Shared runtime context holding the workspace and active dataset.
            tools: Optional list of enabled tool names. Defaults to ``DEFAULT_TOOLS``.
            tool_parser: Tool-call parser name or instance.
            llm_max_tokens: Optional per-response output token cap.
            skills: Optional list of enabled skill names.
            interaction_manager: Manager handling user stop commands and timeline events.
        """
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.tool_parser = tool_parser
        self.llm_max_tokens = llm_max_tokens
        self.turn_count = 0
        if hasattr(context.args, "skill_manager"):
            skill_manager = context.args.skill_manager
            if not isinstance(skill_manager, SkillManager):
                raise TypeError("context.args.skill_manager must be a SkillManager")
        else:
            skill_manager = SkillManager(workspace=context.workspace)
            context.args.skill_manager = skill_manager
        self.skills = (
            list(skills)
            if skills is not None
            else [
                name
                for name in skill_manager.load_skills()
                if name not in self.DEFAULT_EXCLUDED_SKILLS
            ]
        )
        if not isinstance(interaction_manager, InteractionManager):
            raise TypeError("interaction_manager must be an InteractionManager")
        self.interaction_manager = interaction_manager
        self.tool_cls_list = BaseTool.load_tool_classes(tools or self.DEFAULT_TOOLS)
        self.tools_counter = ParallelTimer(unit="call")
        self.tool_box = None
        self.api = None
        self.context = context
        self._force_recorded = False
        self._pending_runtime_settings: dict[str, Any] | None = None
        self.buffer: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": collaborative_workflow_prompt("data") + (
                    "You are the data-preparation agent in ASTRAL. Help the user inspect raw workspace "
                    "files and build a validated `context.data/` dataset for astronomical discovery.\n\n"
                    "Workflow & Tools (only for requested data-preparation work):\n"
                    "- Inspect uploaded files with `workspace_shell` and `read_pdf` (when PDFs are present).\n"
                    "- Use `web_search` and `web_fetch` when external data or literature is requested. If "
                    "`web_fetch` reports blocked access (401/403/429), do not retry that URL; search for an "
                    "accessible authoritative alternative.\n"
                    "- Run reproducible cleaning and transformation scripts via `workspace_code_executor`.\n"
                    "workspace_shell supports documented commands and | pipelines, but not &&; "
                    "use Python pathlib/glob for file discovery. Start with metadata and one small slice. "
                    "Verify dimensions, units and masks before processing full arrays; chunk large files "
                    "and save short, independently executable script stages to avoid truncated tool calls. "
                    "For observational data, read relevant data-preparation skills when available.\n\n"
                    "Separate scientific sample selection from computational subsampling. Derive quality "
                    "cuts from documented flags and the user's research scope, never from how well a desired "
                    "relationship fits. Record selection rules and a row-count audit before searching formulas. "
                    "Declare cuts on the target or its uncertainty as response-dependent selection, and "
                    "check truncation effects; do not describe the sample as target-independent if such cuts "
                    "were applied. This stage prepares data and diagnostics for a separate discovery agent. "
                    "Do not choose a final formula or compare candidate formulas on external-test labels. "
                    "Keep those labels sealed for a single assessment after the downstream expression is "
                    "frozen; field-level diagnostics are allowed, but leave candidate fitting to symbolic regression. "
                    "When a sample is selected, actually apply its mask to every aligned array exported for "
                    "regression; writing a mask or a plan alone does not apply it. Preserve excluded samples "
                    "and external holdouts separately with source-row provenance. Identify evaluator requirements "
                    "explicitly; do not claim that a grouping, uncertainty model, or holdout is enforced merely "
                    "because it appears in analysis_plan.json. If the downstream interface cannot enforce it, "
                    "report that limitation instead of silently replacing the scientific task.\n\n"
                    "- Always call `validate_context_data` after writing or updating `context.data/`, and fix "
                    "every reported error before finishing (`InteractiveSession` loads the validated dataset "
                    "after your turn completes).\n"
                    "- Preserve existing variables unless asked to replace them, and clearly state your "
                    "assumptions and data sources.\n\n"
                    "`context.data/` & `manifest.json` Specification:\n"
                    "- Store all arrays flat under `context.data/<name>.npy` so they load with "
                    "`allow_pickle=False` (numeric, boolean, or fixed-width Unicode strings; never use "
                    "`object` dtypes, and keep categorical variables as Unicode strings unless encoding is "
                    "explicitly requested).\n"
                    "- `context.data/manifest.json` may contain only top-level keys `variables`, `axes`, and "
                    "(solely when graph/hypergraph relations exist) a positive integer `num_nodes`. Do not add "
                    "`format`, `version`, `revision`, `problem`, `attributes`, `shape`, or `dtype`.\n"
                    "- Each entry in `variables` must define `file` (`'<name>.npy'`), `description` (scientific "
                    "meaning and units), and `axes` (axis names in array dimension order).\n"
                    "- Each entry in `axes` must define `description` and exactly one of `values` (short inline "
                    "JSON array, preferred for semantic labels like `['target', 'source']`), `file` "
                    "(`'<axis>.npy'`), or `size` (positive integer length).\n"
                    "- For directed graphs `(E, 2)` or ternary hypergraphs `(H, 3)` with integer endpoints in "
                    "`[0, num_nodes)`, set `'kind': 'relation'` on the relation variable itself (do not set "
                    "`structure` on it) and set `num_nodes` at the manifest root.\n"
                    "- For any edge- or hyperedge-aligned variable of shape `(..., E)` or `(..., H)`, set "
                    "`'structure': '<relation_name>'`."
                ),
            }
        ]
        self.initialize_with_context(context)

    def _check_stop(self) -> None:
        if self.interaction_manager.is_interrupting:
            raise InterruptedError("用户强制中止")

    def _wait(self) -> bool:
        with self.interaction_manager.wait() as messages:
            for pending in messages:
                self._append_prompt({"role": "user", "content": pending.content})
        self._apply_pending_runtime_settings()
        return bool(messages)

    def queue_runtime_settings(self, settings: dict[str, Any]) -> None:
        """Queue validated model and capability settings to apply before the next turn.

        Args:
            settings: Validated dictionary of provider, model, parser, token-limit,
                tool, and skill settings.
        """
        current = self._pending_runtime_settings or {}
        self._pending_runtime_settings = {**current, **settings}

    def _apply_pending_runtime_settings(self) -> None:
        settings = self._pending_runtime_settings
        if not settings:
            return
        self._pending_runtime_settings = None
        for name in ("llm_provider", "llm_model", "tool_parser", "llm_max_tokens", "skills"):
            if name in settings:
                setattr(self, name, settings[name])
        if "tools" in settings:
            self.tool_cls_list = BaseTool.load_tool_classes(settings["tools"])
        self.initialize_with_context(self.context)

    def _record_force(self, update: dict[str, Any] | None = None) -> None:
        if self._force_recorded:
            return
        if update and (update.get("content") or update.get("reasoning")):
            message = {"role": "assistant", "content": update.get("content", "")}
            if update.get("reasoning"):
                message["reasoning"] = update["reasoning"]
            self.buffer.append(message)
        self._append_prompt({"role": "user", "content": "用户强制中止"})
        self._force_recorded = True

    def _append_prompt(self, message: dict[str, Any]) -> None:
        self.buffer.append(message)
        if message.get("role") in {"system", "user"}:
            self.interaction_manager.publish_event("prompt_added", {"message": message})

    def initialize_with_context(self, context: AgentContext) -> None:
        """Bind configured skills and initialize context-aware data-preparation tools.

        Args:
            context: Shared runtime context providing workspace and dataset access.
        """
        context.args.enabled_skills = self.skills
        super().initialize_with_context(context)
        for tool in self.tool_box.tools:
            tool.cancel_event = self.interaction_manager.cancellation_signal

    def run(self, instruction: str) -> dict[str, Any]:
        """Process a user instruction and run tool turns until preparation completes or pauses.

        Args:
            instruction: Natural-language data-preparation request from the user.

        Returns:
            dict[str, Any]: Execution summary containing ``status``, ``message``,
                ``finish_reason``, ``turn_count``, and the current context schema.
        """
        instruction = instruction.strip()
        if not instruction:
            raise ValueError("instruction must not be empty")
        self.context.args.llm_provider = self.llm_provider
        self.context.args.llm_model = self.llm_model
        self.context.args.llm_max_tokens = self.llm_max_tokens
        if not any(
            event["payload"].get("message") == self.buffer[0]
            for event in self.interaction_manager.get_recent_events()["events"]
            if event["kind"] == "prompt_added"
        ):
            self.interaction_manager.publish_event("prompt_added", {"message": self.buffer[0]})
        self._append_prompt({"role": "user", "content": instruction})
        committed = False
        final_content = ""
        truncated = False
        while True:
            self._check_stop()
            self.turn_count += 1
            turn = self.turn_count
            prompt = deepcopy(self.buffer)
            self.set_messages(prompt)
            self._publish("context", {"messages": prompt, "turn": turn})
            response_id = f"data:{uuid.uuid4().hex}"
            tool_schemas = {
                tool.metadata.name: {
                    "description": tool.metadata.description,
                    "parameters": tool.metadata.parameters or {},
                }
                for tool in self.tool_box.tools
            }
            self._publish(
                "assistant_started",
                {
                    "response_id": response_id,
                    "turn": turn,
                    "tool_schemas": tool_schemas,
                    "provider": self.llm_provider,
                    "model": self.llm_model,
                },
            )
            last_stream_emit = 0.0
            latest_stream_update: dict[str, Any] = {}

            def callback(update: dict[str, Any]) -> None:
                nonlocal last_stream_emit, latest_stream_update
                latest_stream_update = update
                now = time.monotonic()
                if update.get("type") == "delta" and now - last_stream_emit < 0.08:
                    return
                last_stream_emit = now
                self._publish(
                    "assistant_delta",
                    {
                        **update,
                        "response_id": response_id,
                        "turn": turn,
                        "tool_schemas": tool_schemas,
                        "provider": self.llm_provider,
                        "model": self.llm_model,
                    },
                )

            try:
                with self.interaction_manager.cancellable(self.api.cancel):
                    call_result = self.api(
                        prompt,
                        n=1,
                        max_tokens=self.llm_max_tokens,
                        callback=callback,
                    )
                    responses = list(call_result)
                self._check_stop()
                if call_result.ok is False and not call_result.truncated:
                    raise RuntimeError(call_result.error or "Model API request failed.")
            except InterruptedError:
                self._record_force(latest_stream_update)
                self._publish(
                    "assistant_failed",
                    {
                        **latest_stream_update,
                        "response_id": response_id,
                        "turn": turn,
                        "provider": self.llm_provider,
                        "model": self.llm_model,
                        "error": "用户强制中止",
                        "interrupted": True,
                    },
                )
                self._wait()
                continue
            except Exception as exc:
                self._publish(
                    "assistant_failed",
                    {
                        **latest_stream_update,
                        "response_id": response_id,
                        "turn": turn,
                        "provider": self.llm_provider,
                        "model": self.llm_model,
                        "error": str(exc),
                    },
                )
                raise
            usage = {
                "token": call_result.token_usage,
                "price": call_result.money_usage,
            }
            if not responses:
                raise RuntimeError("The model returned no usable response")
            response = responses[0]
            content, calls, message = response.content, response.tool_calls, response.message
            final_content = content or ""
            truncated = call_result.truncated
            self._publish(
                "assistant_completed",
                {
                    "response_id": response_id,
                    "content": content,
                    "finish_reason": response.finish_reason,
                    "message": message,
                    "tool_calls": calls,
                    "tool_schemas": tool_schemas,
                    "turn": turn,
                    "usage": usage,
                    "provider": self.llm_provider,
                    "model": self.llm_model,
                },
            )
            if truncated:
                if content:
                    self.buffer.append(message)
                break
            if not calls:
                self.buffer.append(message)
                if self._wait():
                    continue
                break
            results = self._execute_with_events(calls)
            self.buffer.append(message)
            self.buffer.extend(self.tool_box.format_tool_result_messages(calls, results))
            committed = committed or any(result.result.get("data_committed") for result in results)
            if self.interaction_manager.is_interrupting:
                self._record_force()
                self._check_stop()
            self._wait()
        result = {
            "message": final_content,
            "finish_reason": "length" if truncated else "stop",
            "committed": committed,
            "context": self.context.schema(),
        }
        self._publish("execution_completed", result)
        return result

    def _execute_with_events(self, calls):
        results = []
        for call in calls:
            schema = next(
                (
                    {
                        "description": tool.metadata.description,
                        "parameters": tool.metadata.parameters or {},
                    }
                    for tool in self.tool_box.tools
                    if tool.metadata.name == call.name
                ),
                {},
            )
            self._publish("tool_started", {"call": call, "tool_schema": schema})
            started_at = time.monotonic()
            try:
                tool = self.tool_box[call.name]
            except KeyError:
                tool = None
            if tool is None:
                result = super().execute_action([call])[0]
            else:
                with self.interaction_manager.cancellable(tool.cancel):
                    result = super().execute_action([call])[0]
            self._publish(
                "tool_completed",
                {
                    "call": call,
                    "tool_schema": schema,
                    "result": result,
                    "duration_seconds": time.monotonic() - started_at,
                    "interrupted": self.interaction_manager.is_interrupting,
                },
            )
            results.append(result)
        return results

    def _publish(self, kind: str, payload: Any) -> None:
        self.interaction_manager.publish_event(kind, payload)
