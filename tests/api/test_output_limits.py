"""Provider output budgets, without network requests."""
from types import SimpleNamespace

import pytest

from sr_harness.api.openrouter_api import OpenRouterAPI
from sr_harness.api.deepseek_api import DeepSeekAPI


@pytest.mark.parametrize("api_cls,module", [
    (OpenRouterAPI, "openrouter_api"), (DeepSeekAPI, "deepseek_api"),
])
@pytest.mark.parametrize("budget", [None, 32768])
def test_auto_budget_omitted_and_explicit_budget_forwarded(monkeypatch, api_cls, module, budget):
    payloads = []
    monkeypatch.setattr(f"sr_harness.api.{module}.OpenAI", lambda **kwargs: object())
    api = api_cls(environment={"OPENROUTER_API_KEY": "test", "DEEPSEEK_API_KEY": "test"})
    def completion(client, payload, **kwargs):
        payloads.append(payload)
        return SimpleNamespace(usage=None), {}, {"content": "done"}, "done"
    monkeypatch.setattr(api, "openai_chat_completion", completion)
    result = api("hello", max_tokens=budget)
    assert list(result)[0].content == "done"
    assert result.ok
    if budget is None:
        assert "max_tokens" not in payloads[0]
    else:
        assert payloads[0]["max_tokens"] == budget


@pytest.mark.parametrize("api_cls,module", [
    (OpenRouterAPI, "openrouter_api"), (DeepSeekAPI, "deepseek_api"),
])
def test_truncated_tool_arguments_never_reach_parser(monkeypatch, api_cls, module):
    monkeypatch.setattr(f"sr_harness.api.{module}.OpenAI", lambda **kwargs: object())
    api = api_cls(environment={"OPENROUTER_API_KEY": "test", "DEEPSEEK_API_KEY": "test"})
    message = {"content": "Partial", "tool_calls": [
        {"function": {"name": "shell", "arguments": '{"command":'}},
    ]}
    monkeypatch.setattr(api, "openai_chat_completion", lambda *a, **k: (
        SimpleNamespace(usage=None), {"finish_reason": "length"}, message, "Partial"))
    def unexpected(*args):
        pytest.fail("Incomplete tool JSON reached the parser")
    monkeypatch.setattr(api, "parse_tool_calls", unexpected)
    result = api("hello")
    rows = list(result)
    assert result.truncated
    assert rows[0].tool_calls == []
    assert "tool_calls" not in rows[0].message
