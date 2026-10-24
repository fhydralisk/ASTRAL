# Copyright (c) 2026-present, Yumeow. Licensed under the MIT License.
"""工具调用解析器模块。

负责将工具列表格式化为 LLM 可读的描述，以及从 LLM 响应中解析工具调用。
"""
from __future__ import annotations
from collections import Counter
from logging import getLogger
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from ..core import ToolCall, ToolCallResult
from ..tools import BaseTool
from ..utils import FactoryMixin

_logger = getLogger(f'sr_harness.{__name__}')


class BaseParser(ABC, FactoryMixin):
    """Abstract base class that translates tool declarations, calls, and results between models and tools.

    Normalizes provider-specific tool calling formats (native OpenAI function
    calling, JSON blocks, XML tags, or tagged text) into uniform
    :class:`~sr_harness.core.ToolCall` and :class:`~sr_harness.core.ToolCallResult`
    objects for the agent loop.
    """

    native_tool_calls = False

    def __init__(self, tool_list: list[BaseTool] | None = None) -> None:
        """Initialize the tool-call parser with the active tool instances for the run.

        Args:
            tool_list: Initialized :class:`~sr_harness.tools.BaseTool` instances to expose,
                or ``None`` / ``[]`` when no tools are enabled.
        """
        self.tools = list(tool_list or [])
        if invalid := [tool for tool in self.tools if not isinstance(tool, BaseTool)]:
            invalid_names = [type(tool).__name__ for tool in invalid]
            raise TypeError(
                f"tool_list must contain only BaseTool instances; got {', '.join(invalid_names)}"
            )
        name_counts = Counter(tool.metadata.name for tool in self.tools)
        if duplicated := sorted(name for name, count in name_counts.items() if count > 1):
            raise ValueError(f"tool_list contains duplicate tool names: {', '.join(duplicated)}")
        self._tools_by_name = {tool.metadata.name: tool for tool in self.tools}

    def __getitem__(self, name: str) -> BaseTool:
        """Return a bound tool by name, raising ``KeyError`` when absent."""
        return self._tools_by_name[name]

    @abstractmethod
    def format_tools(self) -> str | List[Dict[str, Any]]:
        """Format enabled tool names, descriptions, and parameter schemas for the model.

        Returns:
            str | List[Dict[str, Any]]: Prompt text block or list of native function-calling schemas.
        """
        pass

    @abstractmethod
    def parse_response(self, response: Any) -> List[ToolCall]:
        """Extract zero or more normalized :class:`~sr_harness.core.ToolCall` objects from a model response.

        Args:
            response: Raw model output text or provider message structure.

        Returns:
            List[ToolCall]: Parsed tool calls in emission order (empty when no tool was called).
        """
        pass

    def format_tool_result_messages(self, tool_calls: List[ToolCall], results: List[ToolCallResult]) -> List[Dict[str, Any]]:
        """Format tool execution results as conversation messages for the next model turn.

        Args:
            tool_calls: Tool calls that were executed.
            results: Corresponding :class:`~sr_harness.core.ToolCallResult` objects.

        Returns:
            List[Dict[str, Any]]: Conversation messages ready to append to the prompt buffer.
        """
        lines = []
        for tool_call, result in zip(tool_calls, results):
            lines.append(f"=== Results for `{tool_call.name}` with params `{tool_call.params}` ===")
            lines.append(result.result_str)
        return [{"role": "user", "content": "\n".join(lines)}] if lines else []
