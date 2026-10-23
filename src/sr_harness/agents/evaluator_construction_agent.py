"""Restricted agent for constructing and repairing custom evaluators."""

from __future__ import annotations

import json
import math
import numbers
import time
import uuid
from typing import Any

from ..api import BaseAPI
from ..core import AgentContext, json_value
from ..parser import BaseParser
from ..runtime import InteractionManager
from ..tools import BaseTool
from ..utils import ParallelTimer
from .agent import Agent


def evaluator_probe_is_finite(result: Any) -> bool:
    """Accept finite error metrics with or without extra diagnostics.

    A split-only evaluator is valid without inventing a custom metric. Natural
    language words such as "指标" do not declare a required metric contract.
    This check validates execution, not whether the science task was fulfilled.
    """
    if not result.ok or not isinstance(result.result, dict):
        return False
    standard = {"mse", "rmse", "mae", "mape", "r2", "aic", "bic",
                "pearson_r", "spearman_r", "complexity"}
    splits = result.result.get("data_split_results", {})
    if not isinstance(splits, dict) or not {"train", "validation"} <= set(splits):
        return False
    for split in splits.values():
        metrics = split.get("metrics", {}) if isinstance(split, dict) else {}
        if not isinstance(metrics, dict) or not standard <= set(metrics):
            return False
        if not all(isinstance(value, numbers.Real) and not isinstance(value, bool)
                   for value in metrics.values()):
            return False
        # Constant baselines have undefined rank correlation; perfect fits can
        # have -inf information criteria. Do not make those block a valid probe.
        finite_names = (set(metrics) - standard) | {"mse", "rmse", "mae", "complexity"}
        if not all(math.isfinite(float(metrics[name])) for name in finite_names):
            return False
    return True


class EvaluatorConstructionAgent(Agent):
    """Construct and validate evaluator scripts without mutating live context state."""

    def __init__(
        self,
        *,
        llm_provider: str,
        llm_model: str,
        context: AgentContext,
        tools: list[BaseTool],
        interaction_manager: InteractionManager,
        tool_parser: str = "openai",
        llm_max_tokens: int | None = None,
        max_steps: int = 16,
    ) -> None:
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.tool_parser = tool_parser
        self.llm_max_tokens = llm_max_tokens
        self.max_steps = max_steps
        self.context = context
        if not isinstance(interaction_manager, InteractionManager):
            raise TypeError("interaction_manager must be an InteractionManager")
        self.interaction_manager = interaction_manager
        self._force_recorded = False
        self._pending_runtime_settings: dict[str, Any] | None = None
        self.tool_box = BaseParser.create(tool_parser, tool_list=tools)
        for tool in self.tool_box.tools:
            tool.cancel_event = self.interaction_manager.cancellation_signal
        self.tools_counter = ParallelTimer(unit="call")
        self.api = BaseAPI.create(
            llm_provider,
            model=llm_model,
            tool_box=self.tool_box,
            environment=getattr(context.args, "api_environment", None),
        )
        self.buffer: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You construct SRHarness DefaultEvaluator subclasses using only the tools and skills "
                    "enabled for this session. Create evaluator scripts under context.evaluator/ with "
                    "workspace_code_executor, inspect workspace files with workspace_shell, and test scripts "
                    "with validate_evaluator. Never mutate the live AgentContext evaluator; InteractiveSession "
                    "alone loads the selected file. Consult read_skill when useful. Use read_source to inspect "
                    "src/sr_harness/evaluator/ and only the implementation symbols needed for the task. "
                    "Keep custom subclasses short and reuse evaluator.utils infrastructure. "
                    "DefaultEvaluator defines class methods split(context), fit(f, y, context), "
                    "evaluate(f, y, context), fit_candidate(f, context), and "
                    "evaluate_candidate(f, context). Override fit/evaluate to affect all equations, or "
                    "override the candidate-only methods for behavior such as ODE trajectory rollouts. "
                    "fit must return an Expression with every parameter bound. evaluate must return a "
                    "flat dictionary whose values are only float or int. Preserve mse, rmse, mae, mape, r2, aic, "
                    "bic, pearson_r, spearman_r, and complexity unless the user explicitly asks to remove "
                    "one. Metric, split, "
                    "index-selection, and ODE helpers live in `sr_harness.evaluator.utils`. New evaluator-specific "
                    "helpers belong on the custom subclass. Never hide metric failures in broad "
                    "try/except blocks or return placeholders such as strings or NaN: evaluate_formula "
                    "must exercise the new metric and return a finite numeric value before you finish. "
                    "Extract only necessary control values from context.args before passing them to other "
                    "helpers. Test changes when data are available and repair failures before answering.\n\n"
                    "The current dataset schema below is authoritative. Use its variable names, shapes, "
                    "axis relationships, target, and descriptions when implementing dataset-specific "
                    "metrics such as trajectory rollouts. A derivative target and its corresponding "
                    "observed state trajectory are distinct arrays.\n\n"
                    "For a trajectory rollout metric, preserve chronological order in split "
                    "instead of applying a random row split, integrate the fitted RHS from the first "
                    "observed state of each split, and compare the integrated state with the observed "
                    "state. Prefer scipy.integrate.solve_ivp with t_eval over a low-accuracy Euler loop. "
                    "candidate fit/evaluate receive an already-split context: do not call split from "
                    "either method and do not refit inside evaluate because fit has already run. "
                    "split should return chronological AgentContext views where practical.\n\n"
                    "Before implementing numerical infrastructure yourself, inspect "
                    "src/sr_harness/evaluator/utils/.\n\n"
                    f"Current dataset schema:\n```json\n"
                    f"{json.dumps(json_value(context.schema()), ensure_ascii=False, indent=2)}\n```\n\n"
                    "Begin by inspecting src/sr_harness/evaluator/. If context.evaluator/ already exists, "
                    "inspect its scripts too. Do not create that directory merely to inspect the workspace; "
                    "create it only immediately before writing the first custom evaluator script."
                ),
            }
        ]

    def _publish(self, kind: str, payload: dict[str, Any]) -> None:
        self.interaction_manager.publish_event(kind, payload)

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
        """Queue validated settings for the next safe iteration boundary."""
        current = self._pending_runtime_settings or {}
        self._pending_runtime_settings = {**current, **settings}

    def _apply_pending_runtime_settings(self) -> None:
        settings = self._pending_runtime_settings
        if not settings:
            return
        self._pending_runtime_settings = None
        for name in ("llm_provider", "llm_model", "tool_parser", "llm_max_tokens", "max_steps"):
            if name in settings:
                setattr(self, name, settings[name])
        if "skills" in settings:
            self.context.args.enabled_skills = settings["skills"]
        if "tools" in settings:
            classes = {
                tool_cls.metadata.name: tool_cls for tool_cls in BaseTool.load_tool_classes()
            }
            tools = [classes[name](context=self.context) for name in settings["tools"]]
            self.tool_box = BaseParser.create(self.tool_parser, tool_list=tools)
            for tool in self.tool_box.tools:
                tool.cancel_event = self.interaction_manager.cancellation_signal
        self.api = BaseAPI.create(
            self.llm_provider,
            model=self.llm_model,
            tool_box=self.tool_box,
            environment=getattr(self.context.args, "api_environment", None),
        )

    def _append_prompt(self, message: dict[str, Any]) -> None:
        self.buffer.append(message)
        if message.get("role") in {"system", "user"}:
            self._publish("prompt_added", {"message": message})

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

    def run(self, instruction: str) -> dict[str, Any]:
        """Construct or repair a custom evaluator for one user instruction.

        Args:
            instruction: Natural-language evaluator requirements.

        Returns:
            The final assistant response and tool-event records produced during
            construction.

        Raises:
            ValueError: If ``instruction`` is empty.
        """
        instruction = instruction.strip()
        if not instruction:
            raise ValueError("Evaluator construction instruction must not be empty")
        if not any(
            event["kind"] == "prompt_added"
            for event in self.interaction_manager.get_recent_events()["events"]
        ):
            self._publish("prompt_added", {"message": self.buffer[0]})
        self._append_prompt({"role": "user", "content": instruction})
        tool_events: list[dict[str, Any]] = []
        timeline_events: list[dict[str, Any]] = []
        update_needs_test = False
        step = 0
        while step < self.max_steps:
            step += 1
            self._check_stop()
            response_id = f"evaluator:{uuid.uuid4().hex}"
            tool_schemas = {
                tool.metadata.name: {
                    "description": tool.metadata.description,
                    "parameters": tool.metadata.parameters or {},
                }
                for tool in self.tool_box.tools
            }
            event_context = {
                "response_id": response_id,
                "turn": step,
                "tool_schemas": tool_schemas,
                "provider": self.llm_provider,
                "model": self.llm_model,
            }
            self._publish(
                "context",
                {
                    "messages": json_value(self.buffer),
                    "turn": step,
                },
            )
            self._publish("assistant_started", event_context)
            last_stream_emit = 0.0
            latest_stream_update: dict[str, Any] = {}

            def callback(update: dict[str, Any]) -> None:
                nonlocal last_stream_emit, latest_stream_update
                latest_stream_update = update
                now = time.monotonic()
                if update.get("type") == "delta" and now - last_stream_emit < 0.08:
                    return
                last_stream_emit = now
                self._publish("assistant_delta", {**update, **event_context})

            try:
                with self.interaction_manager.cancellable(self.api.cancel):
                    call_result = self.api(
                        self.buffer,
                        n=1,
                        max_tokens=self.llm_max_tokens,
                        callback=callback,
                    )
                    rows = list(call_result)
                self._check_stop()
                if call_result.ok is False and not call_result.truncated:
                    raise RuntimeError(call_result.error or "Model API request failed.")
            except InterruptedError:
                self._record_force(latest_stream_update)
                self._publish(
                    "assistant_failed",
                    {
                        **latest_stream_update,
                        **event_context,
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
                        **event_context,
                        "error": str(exc),
                    },
                )
                raise
            if not rows:
                raise RuntimeError("EvaluatorConstructionAgent returned no usable response")
            response = rows[0]
            content, calls, message = response.content, response.tool_calls, response.message
            if content or not call_result.truncated:
                self.buffer.append(message)
            assistant_event = {
                "kind": "assistant",
                "timestamp": time.time(),
                "content": content or "",
                "finish_reason": response.finish_reason,
                "message": json_value(message),
                "tool_calls": [
                    {"name": call.name, "params": json_value(call.params), "id": call.id}
                    for call in calls
                ],
            }
            timeline_events.append(assistant_event)
            self._publish(
                "assistant_completed",
                {
                    **event_context,
                    "content": content or "",
                    "finish_reason": response.finish_reason,
                    "reasoning": message.get("reasoning", ""),
                    "message": json_value(message),
                    "tool_calls": assistant_event["tool_calls"],
                    "usage": {
                        "token": call_result.token_usage,
                        "price": call_result.money_usage,
                    },
                },
            )
            if call_result.truncated:
                self.interaction_manager.request_pause()
                self._wait()
                continue
            if not calls:
                if update_needs_test:
                    self._append_prompt(
                        {
                            "role": "user",
                            "content": (
                                "Completion is blocked: call validate_evaluator after the latest evaluator "
                                "file edit. Repair the evaluator until validation succeeds and every "
                                "evaluator-specific metric it returns is a finite number."
                            ),
                        }
                    )
                    self._wait()
                    continue
                if self._wait():
                    continue
                return {
                    "message": content or "",
                    "tool_events": tool_events,
                    "timeline_events": timeline_events,
                    "streamed": True,
                }
            results = []
            for call in calls:
                try:
                    tool = self.tool_box[call.name]
                except KeyError:
                    tool = None
                self._publish(
                    "tool_started",
                    {
                        "call": {
                            "name": call.name,
                            "params": json_value(call.params),
                            "id": call.id,
                        },
                    },
                )
                if tool is None:
                    results.extend(self.execute_action([call]))
                else:
                    with self.interaction_manager.cancellable(tool.cancel):
                        results.extend(self.execute_action([call]))
            completed = [
                {
                    "tool": call.name,
                    "ok": result.ok,
                    "call": {"name": call.name, "params": json_value(call.params), "id": call.id},
                    "result": {
                        "ok": result.ok,
                        "result": json_value(result.result),
                        "result_str": result.result_str,
                        "meta_data": json_value(result.meta_data),
                    },
                    "timestamp": float(result.meta_data.get("timestamp", time.time())),
                }
                for call, result in zip(calls, results)
            ]
            tool_events.extend(completed)
            timeline_events.extend({"kind": "tool_result", **event} for event in completed)
            for event in completed:
                self._publish("tool_completed", event)
            self.buffer.extend(self.tool_box.format_tool_result_messages(calls, results))
            if self.interaction_manager.is_interrupting:
                self._record_force()
                self._check_stop()
            for call, result in zip(calls, results):
                if call.name == "workspace_code_executor" and result.ok:
                    update_needs_test = True
                elif (
                    call.name == "validate_evaluator"
                    and update_needs_test
                    and evaluator_probe_is_finite(result)
                ):
                    update_needs_test = False
            self._wait()
        raise RuntimeError(
            f"EvaluatorConstructionAgent exceeded the {self.max_steps}-step repair limit"
        )
