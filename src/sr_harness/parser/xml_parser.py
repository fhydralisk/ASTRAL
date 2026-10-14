# Copyright (c) 2026-present, Yumeow. Licensed under the MIT License.
from __future__ import annotations
import json
import re
import xml.etree.ElementTree as ET
from logging import getLogger
from xml.sax.saxutils import escape, quoteattr

from .base_parser import BaseParser
from ..core import ToolCall

_logger = getLogger(f'sr_harness.{__name__}')
_TOOL_CALL_PATTERN = re.compile(
    r"<tool_call\b[^>]*>.*?</tool_call\s*>",
    flags=re.DOTALL,
)


@BaseParser.register('xml')
class XMLParser(BaseParser):
    """Parser for XML-formatted tool calls."""

    def format_tools(self) -> str:
        """Return tool metadata and the required XML call syntax."""
        lines = ["## Available Tools:", "", "<tools>"]
        for tool in self.tools:
            metadata = tool.metadata
            parameters = json.dumps(
                metadata.parameters or {"type": "object", "properties": {}},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            lines.extend([
                f"  <tool name={quoteattr(metadata.name)}>",
                f"    <description>{escape(metadata.description or '')}</description>",
                f"    <parameters>{escape(parameters)}</parameters>",
                "  </tool>",
            ])
        lines.extend([
            "</tools>",
            "",
            "## Output Format:",
            "",
            "Emit each tool call as a separate XML element. The arguments must be one JSON object:",
            "",
            '<tool_call name="tool_name">',
            '  <arguments>{"param1":"value1","param2":2}</arguments>',
            "</tool_call>",
            "",
            "You may emit multiple <tool_call> elements in one response.",
        ])
        return "\n".join(lines)

    def parse_response(self, response: str) -> list[ToolCall]:
        """Parse independent ``tool_call`` elements embedded in model text."""
        tool_calls = []
        for raw in _TOOL_CALL_PATTERN.findall(response):
            try:
                element = ET.fromstring(raw)
                name = (element.get("name") or element.findtext("name") or "").strip()
                if not name:
                    raise ValueError("tool_call has no tool name")
                arguments_element = element.find("arguments")
                if arguments_element is None:
                    arguments_element = element.find("params")
                arguments_text = (
                    "".join(arguments_element.itertext()).strip()
                    if arguments_element is not None
                    else ""
                )
                params = json.loads(arguments_text) if arguments_text else {}
                if not isinstance(params, dict):
                    raise ValueError("tool_call arguments must be a JSON object")
            except (ET.ParseError, json.JSONDecodeError, ValueError) as error:
                _logger.warning(f"Skip malformed XML tool call {raw!r}: {error}")
                continue
            tool_calls.append(ToolCall(name=name, params=params, raw=raw))
        return tool_calls
