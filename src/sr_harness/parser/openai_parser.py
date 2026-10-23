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
    """Parser for native OpenAI-compatible tool calls."""

    native_tool_calls = True

    def format_tools(self) -> List[Dict[str, Any]]:
        """Return OpenAI-compatible native function descriptions."""
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
        """Normalize provider-native function calls already extracted by BaseAPI."""
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
        """Format tool result messages.

        Args:
            tool_calls: Tool calls returned by the model.
            results: Result records to process.

        Returns:
            List[Dict[str, Any]]: The operation result.
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
