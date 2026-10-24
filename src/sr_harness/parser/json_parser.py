# Copyright (c) 2026-present, Yumeow. Licensed under the MIT License.
from __future__ import annotations
import re
import json
import inspect
from typing import List
from logging import getLogger
from ..core import ToolCall
from .base_parser import BaseParser

_logger = getLogger(f'sr_harness.{__name__}')


@BaseParser.register('json')
class JSONParser(BaseParser):
    """Tool-call parser that instructs the model to emit JSON tool calls and parses them from text."""

    def format_tools(self) -> str:
        """Render enabled tool schemas and JSON call formatting instructions for the system prompt.

        Returns:
            str: Prompt block describing available tools and the required JSON call syntax.
        """
        lines = ["## Available Tools:", ""]

        for tool in self.tools:
            name = tool.metadata.name
            desc = tool.metadata.description

            # 获取工具类的签名
            try:
                if (tool_cls := type(tool)):
                    sig = inspect.signature(tool_cls.execute)
                    params = []
                    for param_name, param in sig.parameters.items():
                        if param_name in ('self', 'args', 'kwargs'):
                            continue
                        param_type = param.annotation.__name__ if param.annotation != inspect.Parameter.empty else 'Any'
                        if param.default is inspect.Parameter.empty:
                            params.append(f'"{param_name}": {param_type}')
                        else:
                            params.append(f'"{param_name}": {param_type} = {param.default}')
                    signature = "{" + ", ".join(params) + "}"
                else:
                    signature = "{}"
            except Exception:
                signature = "{}"

            lines.append(f"### {name}")
            lines.append(f"- **Description**: {desc}")
            lines.append(f"- **Params**: `{signature}`")
            lines.append("")

        lines.append("## Output Format:")
        lines.append("")
        lines.append("Respond with a JSON object in the following format:")
        lines.append("")
        lines.append("```json")
        lines.append('{"tool": "tool_name", "params": {"param1": "value1", "param2": "value2"}}')
        lines.append("```")
        lines.append("")
        lines.append("You can include multiple tool call blocks in one response if needed.")

        return "\n".join(lines)

    def parse_response(self, response: str) -> List[ToolCall]:
        """Extract :class:`~sr_harness.core.ToolCall` objects from JSON blocks in the model's text response.

        Args:
            response: Model text output potentially containing JSON tool-call blocks.

        Returns:
            List[ToolCall]: Normalized tool calls recovered from ``response``.
        """
        tool_calls = []

        # 尝试从响应中提取 JSON
        if (json_match := re.search(r'```(?:json)?\s*({.*?})\s*```', response, re.DOTALL)):
            json_str = json_match.group(1)
        else:
            # 如果没有代码块标记，尝试直接解析整个响应
            json_str = response.strip()

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            _logger.warning(f"Failed to parse JSON: {e}")
            return tool_calls

        for action in data["actions"]:
            tool_calls.append(ToolCall(name=action["tool"], params=action["params"], raw=json_str))

        return tool_calls
