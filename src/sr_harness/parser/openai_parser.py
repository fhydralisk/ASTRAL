# Copyright (c) 2026-present, Yumeow. Licensed under the MIT License.
from __future__ import annotations
import json
from logging import getLogger
from typing import List, Dict, Any
from .base_parser import BaseParser
from ..core import ToolCall, ToolCallResult

_logger = getLogger(f'sr_harness.{__name__}')


@BaseParser.register('openai')
class OpenAIParser(BaseParser):
    """Tool-call parser for providers supporting native OpenAI-compatible function calling."""

    native_tool_calls = True

    def format_tools(self) -> List[Dict[str, Any]]:
        """Return OpenAI-compatible function tool schema definitions for all enabled tools.

        Returns:
            List[Dict[str, Any]]: List of ``{"type": "function", "function": ...}`` tool schemas.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.metadata.name,
                    "description": tool.metadata.description,
                    "parameters": tool.metadata.parameters,
                },
            }
            for tool in self.tools
        ]

    def parse_response(self, response: Any) -> List[ToolCall]:
        """Normalize native ``tool_calls`` structures returned by an OpenAI-compatible provider.

        Args:
            response: Provider message dictionary or list of raw tool-call objects.

        Returns:
            List[ToolCall]: Normalized :class:`~sr_harness.core.ToolCall` instances.
        """
        normalized = []
        for tool_call in response or []:
            if isinstance(tool_call, dict):
                raw = tool_call
            elif hasattr(tool_call, "to_dict"):
                raw = tool_call.to_dict()
            elif hasattr(tool_call, "model_dump"):
                raw = tool_call.model_dump()
            else:
                raise ValueError(f"Unrecognized tool call format: {tool_call}")
            function = raw.get("function") or {}
            name = function.get("name") or raw.get("name") or None
            params = (
                function.get("arguments")
                or raw.get("arguments")
                or raw.get("arguments_json")
                or raw.get("args")
                or {}
            )
            try:
                if isinstance(params, str):
                    params = json.loads(params) if params.strip() else {}
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Malformed native tool call {name!r}: arguments are not complete JSON. "
                    "Retry with a shorter tool call or a larger output-token budget."
                ) from error
            if not isinstance(params, dict):
                raise ValueError(f"Native tool call {name!r} arguments must be a JSON object.")
            normalized.append(ToolCall(
                name=name,
                params=params,
                id=raw.get("id") or raw.get("call_id"),
                raw=raw,
            ))
        return normalized

    def format_tool_result_messages(
        self,
        tool_calls: List[ToolCall],
        results: List[ToolCallResult],
    ) -> List[Dict[str, Any]]:
        """Format each :class:`~sr_harness.core.ToolCallResult` as a ``role="tool"`` message linked by ``tool_call_id``.

        Args:
            tool_calls: Executed tool calls carrying provider ``id`` values.
            results: Corresponding tool execution results.

        Returns:
            List[Dict[str, Any]]: OpenAI ``tool`` role messages.
        """
        messages = []
        for tool_call, result in zip(tool_calls, results):
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_call.name,
                "content": result.result_str,
            })
        return messages
