"""Tests for XML-formatted model tool calls."""

from __future__ import annotations

from sr_harness.core import ToolMetadata
from sr_harness.parser import BaseParser, XMLParser
from sr_harness.tools import BaseTool


class XMLDemoTool(BaseTool):
    metadata = ToolMetadata(
        name="xml_demo",
        description="Compare x < y & report the result.",
        parameters={
            "type": "object",
            "properties": {
                "x": {"type": "number"},
                "options": {"type": "object"},
            },
        },
    )

    def execute(self, x: float, options: dict | None = None):
        return {"x": x, "options": options}


def test_xml_parser_is_registered_and_formats_bound_tools():
    parser = BaseParser.create("xml", tool_list=[XMLDemoTool()])

    assert isinstance(parser, XMLParser)
    formatted = parser.format_tools()
    assert '<tool name="xml_demo">' in formatted
    assert "Compare x &lt; y &amp; report the result." in formatted
    assert "<parameters>" in formatted
    assert '<tool_call name="tool_name">' in formatted


def test_xml_parser_parses_multiple_calls_and_json_value_types():
    parser = XMLParser(tool_list=[XMLDemoTool()])
    response = """First inspect the data.
<tool_call name="xml_demo">
  <arguments>{"x":2.5,"options":{"enabled":true,"labels":["a","b"]}}</arguments>
</tool_call>
Then run the default form.
<tool_call>
  <name>xml_demo</name>
  <arguments>{}</arguments>
</tool_call>
"""

    calls = parser.parse_response(response)

    assert [call.name for call in calls] == ["xml_demo", "xml_demo"]
    assert calls[0].params == {
        "x": 2.5,
        "options": {"enabled": True, "labels": ["a", "b"]},
    }
    assert calls[1].params == {}
    assert calls[0].raw.startswith('<tool_call name="xml_demo">')
    assert calls[0].raw_str == calls[0].raw


def test_xml_parser_decodes_xml_escaped_json_text():
    parser = XMLParser(tool_list=[])

    calls = parser.parse_response(
        '<tool_call name="xml_demo"><arguments>'
        '{"text":"x &lt; y &amp; z"}'
        "</arguments></tool_call>"
    )

    assert calls[0].params == {"text": "x < y & z"}


def test_xml_parser_accepts_empty_arguments_and_params_alias():
    parser = XMLParser(tool_list=[])

    calls = parser.parse_response(
        '<tool_call name="first"></tool_call>'
        '<tool_call name="second"><params>{"count":3}</params></tool_call>'
    )

    assert [(call.name, call.params) for call in calls] == [
        ("first", {}),
        ("second", {"count": 3}),
    ]


def test_xml_parser_skips_malformed_calls_without_losing_valid_calls():
    parser = XMLParser(tool_list=[])
    response = """
<tool_call name="bad-json"><arguments>{not json}</arguments></tool_call>
<tool_call name="not-an-object"><arguments>[1,2]</arguments></tool_call>
<tool_call><arguments>{}</arguments></tool_call>
<tool_call name="valid"><arguments>{"x":1}</arguments></tool_call>
"""

    calls = parser.parse_response(response)

    assert [(call.name, call.params) for call in calls] == [("valid", {"x": 1})]
