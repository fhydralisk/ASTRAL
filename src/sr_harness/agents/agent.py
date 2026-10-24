# Copyright (c) 2026-present, Yumeow. Licensed under the MIT License.
"""Common runtime mechanics shared by SRHarness agents."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Any

from joblib import Parallel, delayed

from ..api import BaseAPI
from ..core import AgentContext, ToolCall, ToolCallResult
from ..parser import BaseParser
from ..tools import BaseTool
from ..utils import FactoryMixin

_logger = logging.getLogger(f"sr_harness.{__name__}")


def _execute_tool_call_in_subprocess(tool: BaseTool, tool_call: ToolCall) -> ToolCallResult:
    """Execute one tool call in a worker process."""
    return tool(**tool_call.params)


class Agent(ABC, FactoryMixin):
    """Abstract base class for tool-using language-model agents.

    Provides shared mechanics for binding an :class:`~sr_harness.core.AgentContext`,
    initializing enabled tools and the LLM provider adapter, and executing tool
    calls either serially or in parallel worker processes. Concrete subclasses
    implement their own conversation loop and domain state management.
    """

    context: AgentContext
    tool_box: BaseParser | None
    api: BaseAPI | None

    @abstractmethod
    def run(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the agent's main task loop.

        Args:
            *args: Positional arguments defined by the concrete agent subclass.
            **kwargs: Keyword arguments defined by the concrete agent subclass.

        Returns:
            Any: Task result produced by the concrete agent implementation.
        """

    def initialize_with_context(self, context: AgentContext) -> None:
        """Bind tools, skills, and the model API to a shared runtime context.

        Args:
            context: Shared agent and tool execution context containing data,
                workspace access, and runtime settings.
        """
        self.context = context
        tools = [tool_cls(context=context) for tool_cls in self.tool_cls_list]
        self.tool_box = BaseParser.create(self.tool_parser, tool_list=tools)
        self.api = BaseAPI.create(
            self.llm_provider,
            model=self.llm_model,
            tool_box=self.tool_box,
            environment=getattr(context.args, "api_environment", None),
            save_path=getattr(self, "save_path", None),
        )

    def set_messages(self, messages: list[dict[str, Any]]) -> None:
        """Store the active conversation messages on the shared tool context.

        Args:
            messages: Conversation messages ordered as sent to the model provider.
        """
        self.context.args.messages = deepcopy(messages)

    def execute_action(self, actions: list[ToolCall]) -> list[ToolCallResult]:
        """Execute a batch of tool calls sequentially in the current process.

        Args:
            actions: Normalized tool calls emitted by the language model.

        Returns:
            list[ToolCallResult]: Tool execution results in the same order as ``actions``.
        """
        if self.tool_box is None:
            raise RuntimeError("Agent must be initialized with context before executing tools")
        results: list[ToolCallResult] = []
        for action in actions:
            try:
                tool = self.tool_box[action.name]
            except KeyError:
                tool = None
            if tool is None:
                _logger.trace(f"Unknown tool call: {action.name}. Skipping execution.")
                results.append(ToolCallResult(
                    ok=False,
                    result={},
                    result_str=f'Unknown tool calling for "{action.name}"',
                    meta_data={"tool": action.name},
                ))
                continue
            self.tools_counter.add(action.name)
            results.append(tool(**action.params))
        return results

    def execute_action_parallel(
        self,
        actions: list[ToolCall],
        max_workers: int,
    ) -> list[ToolCallResult]:
        """Execute a batch of independent tool calls concurrently across worker processes.

        Args:
            actions: Normalized tool calls emitted by the language model.
            max_workers: Maximum number of worker processes to spawn.

        Returns:
            list[ToolCallResult]: Tool execution results in the same order as ``actions``.
        """
        if self.tool_box is None:
            raise RuntimeError("Agent must be initialized with context before executing tools")
        results: list[ToolCallResult | None] = [None] * len(actions)
        tasks = []
        for index, action in enumerate(actions):
            try:
                tool = self.tool_box[action.name]
            except KeyError:
                tool = None
            if tool is None:
                _logger.trace(f"Unknown tool call: {action.name}. Skipping execution.")
                results[index] = ToolCallResult(
                    ok=False,
                    result={},
                    result_str=f'Unknown tool calling for "{action.name}"',
                    meta_data={"tool": action.name},
                )
            else:
                tasks.append((index, delayed(_execute_tool_call_in_subprocess)(tool, action)))
                self.tools_counter.add(action.name)

        if tasks:
            workers = Parallel(n_jobs=max_workers, backend="loky")
            task_results = workers(task for _, task in tasks)
            for (index, _), result in zip(tasks, task_results):
                results[index] = result
        if any(result is None for result in results):
            raise RuntimeError("Parallel tool execution did not produce one result per call")
        return [result for result in results if result is not None]
