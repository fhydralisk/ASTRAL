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
    """Base class for model tool-call parsers."""

    native_tool_calls = False

    def __init__(self, tool_list: list[BaseTool] | None = None) -> None:
        """初始化工具解析器。

        Args:
            tool_list: Bound tool instances. ``None`` and an empty list both
                expose no tools.
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
        """Format tools.

        Returns:
            str: The operation result.
        """
        pass

    @abstractmethod
    def parse_response(self, response: Any) -> List[ToolCall]:
        """Parse response.

        Args:
            response: Provider response object.

        Returns:
            List[ToolCall]: The operation result.
        """
        pass

    def format_tool_result_messages(self, tool_calls: List[ToolCall], results: List[ToolCallResult]) -> List[Dict[str, Any]]:
        """Format tool result messages.

        Args:
            tool_calls: Tool calls returned by the model.
            results: Result records to process.

        Returns:
            List[Dict[str, Any]]: The operation result.
        """
        lines = []
        for tool_call, result in zip(tool_calls, results):
            lines.append(f"=== Results for `{tool_call.name}` with params `{tool_call.params}` ===")
            lines.append(result.result_str)
        return [{"role": "user", "content": "\n".join(lines)}] if lines else []
