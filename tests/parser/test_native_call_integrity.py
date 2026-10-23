import pytest
from sr_harness.parser.openai_parser import OpenAIParser


def test_truncated_call_is_not_a_normal_empty_response():
    parser = OpenAIParser.__new__(OpenAIParser)
    with pytest.raises(ValueError, match='not complete JSON'):
        parser.parse_response([{'id': 'x', 'function': {'name': 'workspace_code_executor', 'arguments': '{"code":"unfinished'}}])


@pytest.mark.parametrize('arguments', ['[]', '1', 'null'])
def test_non_object_arguments_are_rejected(arguments):
    parser = OpenAIParser.__new__(OpenAIParser)
    with pytest.raises(ValueError, match='JSON object'):
        parser.parse_response([{'function': {'name': 'test', 'arguments': arguments}}])


def test_valid_and_empty_responses_are_preserved():
    parser = OpenAIParser.__new__(OpenAIParser)
    assert parser.parse_response([]) == []
    calls = parser.parse_response([{'id': 'x', 'function': {'name': 'test', 'arguments': '{"x":1}'}}])
    assert calls[0].params == {'x': 1}
