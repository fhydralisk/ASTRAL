"""Unit tests for representative LLM API tool handling."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from sr_harness.api.deepseek_api import DeepSeekAPI
from sr_harness.api.openrouter_api import OpenRouterAPI
from sr_harness.api.siliconflow_api import SiliconFlowAPI
from sr_harness.core import ToolCall
from sr_harness.parser import BaseParser
from sr_harness.tools import BaseTool, ToolMetadata


class DemoTool(BaseTool):
    metadata = ToolMetadata(
        name="demo_tool",
        description="Return a demo value.",
        parameters={
            "type": "object",
            "properties": {"x": {"type": "integer"}},
            "required": ["x"],
        },
    )

    def execute(self, x: int):
        return {"x": x}


class _FakeUsage:
    prompt_tokens = 7
    completion_tokens = 11


class _FakeOpenRouterMessage:
    def __init__(self, content: str, tool_calls: list[dict] | None = None):
        self.content = content
        self.tool_calls = tool_calls or []

    def to_dict(self):
        return {
            "role": "assistant",
            "content": self.content,
            "tool_calls": self.tool_calls,
        }


class _FakeOpenRouterChoice:
    def __init__(self, message: _FakeOpenRouterMessage):
        self.message = message


class _FakeOpenRouterCompletion:
    def __init__(self, message_dict: dict):
        self.usage = _FakeUsage()
        content = message_dict.get("content") or ""
        tool_calls = message_dict.get("tool_calls") or []
        self.choices = [_FakeOpenRouterChoice(_FakeOpenRouterMessage(content, tool_calls))]
        self._message_dict = {"role": "assistant", **message_dict}

    def to_dict(self):
        return {
            "choices": [{"message": self._message_dict}],
            "usage": {
                "prompt_tokens": self.usage.prompt_tokens,
                "completion_tokens": self.usage.completion_tokens,
            },
        }


class _FakeOpenRouterClient:
    payloads: list[dict[str, Any]] = []
    api_keys: list[str | None] = []
    base_urls: list[str | None] = []
    message: dict[str, Any] = {"content": "ok"}

    def __init__(self, *args, **kwargs):
        self.api_keys.append(kwargs.get("api_key"))
        self.base_urls.append(kwargs.get("base_url"))
        self.chat = self
        self.completions = self

    def create(self, **payload):
        self.payloads.append(payload)
        return _FakeOpenRouterCompletion(self.message)


class _RetryableOpenRouterError(Exception):
    def __init__(self):
        super().__init__("temporarily over the in-flight budget")
        self.body = {
            "error": {
                "metadata": {"headers": {"Retry-After": "120"}},
            }
        }


class _ForbiddenOpenRouterError(Exception):
    status_code = 403


class _RetryingOpenRouterClient(_FakeOpenRouterClient):
    attempts = 0

    def create(self, **payload):
        self.payloads.append(payload)
        self.__class__.attempts += 1
        if self.__class__.attempts == 1:
            raise _RetryableOpenRouterError()
        return _FakeOpenRouterCompletion({"content": "recovered"})


class _FakeStreamChunk:
    def __init__(self, delta=None, usage=None, finish_reason=None):
        self.choices = (
            []
            if delta is None
            else [
                SimpleNamespace(
                    delta=delta,
                    finish_reason=finish_reason,
                )
            ]
        )
        self.usage = usage

    def to_dict(self):
        return {"stream_chunk": True}


class _StreamingOpenRouterClient(_FakeOpenRouterClient):
    def create(self, **payload):
        self.payloads.append(payload)
        assert payload["stream"] is True
        assert payload["stream_options"] == {"include_usage": True}
        return iter(
            [
                _FakeStreamChunk(
                    SimpleNamespace(
                        content=None,
                        reasoning="inspect ",
                        reasoning_content=None,
                        reasoning_details=None,
                        tool_calls=[],
                    )
                ),
                _FakeStreamChunk(
                    SimpleNamespace(
                        content="ready",
                        reasoning=None,
                        reasoning_content=None,
                        reasoning_details=None,
                        tool_calls=[
                            SimpleNamespace(
                                index=0,
                                id="call_stream",
                                function=SimpleNamespace(name="demo_tool", arguments='{"x":'),
                            )
                        ],
                    )
                ),
                _FakeStreamChunk(
                    SimpleNamespace(
                        content=None,
                        reasoning=None,
                        reasoning_content=None,
                        reasoning_details=None,
                        tool_calls=[
                            SimpleNamespace(
                                index=0,
                                id=None,
                                function=SimpleNamespace(name=None, arguments=" 7}"),
                            )
                        ],
                    )
                ),
                _FakeStreamChunk(
                    usage=SimpleNamespace(
                        prompt_tokens=7,
                        completion_tokens=11,
                        total_tokens=18,
                        cost=0.001,
                    )
                ),
            ]
        )


class _FakeSiliconFlowResponse:
    def __init__(self, response: dict, status_code: int = 200):
        self._response = response
        self.status_code = status_code
        self.text = str(response)

    def json(self):
        return self._response


class _FakeModelListResponse:
    def __init__(self, records: list[dict[str, Any]]):
        self.records = records

    def raise_for_status(self):
        return None

    def json(self):
        return {"data": self.records}


class _FakeModelListClient:
    def __init__(self, records: list[dict[str, Any]]):
        self.records = records
        self.requests: list[dict[str, Any]] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def get(self, url, **kwargs):
        self.requests.append({"url": url, **kwargs})
        return _FakeModelListResponse(self.records)


def _siliconflow_response(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "choices": [{"message": {"role": "assistant", **message}}],
        "usage": {
            "prompt_tokens": 5,
            "completion_tokens": 9,
            "total_tokens": 14,
            "completion_tokens_details": {"reasoning_tokens": 0},
        },
    }


def _consume(result):
    chunks = list(result)
    return chunks, result


def test_openrouter_native_tools_are_sent_and_tool_calls_are_extracted(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_ENDPOINT", "http://openrouter-gateway:8080/api/v1")
    monkeypatch.setattr("sr_harness.api.openrouter_api.OpenAI", _FakeOpenRouterClient)
    _FakeOpenRouterClient.payloads = []
    _FakeOpenRouterClient.message = {
        "content": "ready",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "demo_tool", "arguments": '{"x": 1}'},
            }
        ],
    }

    api = OpenRouterAPI(
        model="qwen/qwen3.6-flash",
        tool_box=BaseParser.create("openai", tool_list=[DemoTool()]),
    )
    chunks, return_value = _consume(api([{"role": "user", "content": "use the tool"}]))

    payload = _FakeOpenRouterClient.payloads[0]
    assert _FakeOpenRouterClient.base_urls[-1] == "http://openrouter-gateway:8080/api/v1"
    assert payload["model"] == "qwen/qwen3.6-flash"
    assert payload["tools"][0]["function"]["name"] == "demo_tool"
    assert payload["tool_choice"] == "auto"
    expected_message = {
        "role": "assistant",
        "content": "ready",
        "tool_calls": _FakeOpenRouterClient.message["tool_calls"],
    }
    assert chunks[0].content == "ready"
    assert chunks[0].message == expected_message
    assert chunks[0].tool_calls == [
        ToolCall(
            "demo_tool", {"x": 1}, id="call_1", raw=_FakeOpenRouterClient.message["tool_calls"][0]
        )
    ]


def test_openrouter_honors_retry_after_and_recovers(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr("sr_harness.api.openrouter_api.OpenAI", _RetryingOpenRouterClient)
    sleeps = []
    monkeypatch.setattr(
        "sr_harness.api.base_api.BaseAPI.wait_before_retry",
        lambda _self, delay: sleeps.append(delay),
    )
    _RetryingOpenRouterClient.payloads = []
    _RetryingOpenRouterClient.attempts = 0

    api = OpenRouterAPI(model="deepseek/deepseek-v4-flash")
    chunks, _ = _consume(api([{"role": "user", "content": "retry"}]))

    assert sleeps == [120.0]
    assert chunks[0].content == "recovered"


def test_openrouter_logs_and_streams_raw_retry_error(monkeypatch, caplog):
    class ForbiddenThenStreamingClient(_StreamingOpenRouterClient):
        attempts = 0

        def create(self, **payload):
            self.__class__.attempts += 1
            if self.__class__.attempts == 1:
                raise _ForbiddenOpenRouterError("private regional provider detail")
            return super().create(**payload)

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr("sr_harness.api.openrouter_api.OpenAI", ForbiddenThenStreamingClient)
    monkeypatch.setattr(
        "sr_harness.api.base_api.BaseAPI.wait_before_retry",
        lambda _self, _delay: None,
    )
    updates = []
    api = OpenRouterAPI(model="openai/gpt-5.6-sol")

    with caplog.at_level("ERROR", logger="sr_harness.sr_harness.api.base_api"):
        chunks, _ = _consume(
            api(
                [{"role": "user", "content": "retry"}],
                callback=updates.append,
            )
        )

    retry = next(update for update in updates if update["type"] == "retry")
    assert retry["error"] == "private regional provider detail"
    assert "private regional provider detail" in caplog.text
    assert chunks[0].content == "ready"


def test_openrouter_callback_receives_incremental_snapshots(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr("sr_harness.api.openrouter_api.OpenAI", _StreamingOpenRouterClient)
    _StreamingOpenRouterClient.payloads = []
    updates = []
    api = OpenRouterAPI(
        model="deepseek/deepseek-v4-flash-0731",
        tool_box=BaseParser.create("openai", tool_list=[DemoTool()]),
    )

    chunks, returned = _consume(
        api(
            [{"role": "user", "content": "stream"}],
            callback=updates.append,
        )
    )

    call = ToolCall(
        "demo_tool",
        {"x": 7},
        id="call_stream",
        raw={
            "id": "call_stream",
            "type": "function",
            "function": {"name": "demo_tool", "arguments": '{"x": 7}'},
        },
    )
    assert chunks[0].content == "ready"
    assert chunks[0].tool_calls == [call]
    assert chunks[0].message["reasoning"] == "inspect "
    assert [update["type"] for update in updates] == [
        "start",
        "delta",
        "delta",
        "delta",
        "complete",
    ]
    assert updates[-1]["content"] == "ready"
    assert updates[-1]["tool_calls"][0]["function"]["arguments"] == '{"x": 7}'
    assert returned.token_usage == {"prompt": 7, "answer": 11}


def test_openrouter_stream_preserves_reasoning_when_output_limit_is_exhausted(monkeypatch):
    class ReasoningLengthClient(_FakeOpenRouterClient):
        attempts = 0

        def create(self, **payload):
            self.__class__.attempts += 1
            return iter(
                [
                    _FakeStreamChunk(
                        SimpleNamespace(
                            content=None,
                            reasoning="a long chain of reasoning",
                            reasoning_content=None,
                            reasoning_details=None,
                            tool_calls=[],
                        )
                    ),
                    _FakeStreamChunk(
                        SimpleNamespace(
                            content=None,
                            reasoning=None,
                            reasoning_content=None,
                            reasoning_details=None,
                            tool_calls=[],
                        ),
                        finish_reason="length",
                    ),
                ]
            )

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr("sr_harness.api.openrouter_api.OpenAI", ReasoningLengthClient)
    updates = []
    api = OpenRouterAPI(model="deepseek/deepseek-v4-flash-0731")

    chunks, result = _consume(
        api(
            [{"role": "user", "content": "reason for a long time"}],
            max_tokens=64,
            callback=updates.append,
        )
    )

    assert result.ok is False
    assert "exhausted max_tokens=64" in result.error
    assert chunks[0].reasoning == "a long chain of reasoning"
    assert chunks[0].tool_calls == []
    assert ReasoningLengthClient.attempts == 1
    assert updates[-2]["type"] == "complete"
    assert updates[-2]["reasoning"] == "a long chain of reasoning"
    assert updates[-2]["finish_reason"] == "length"
    assert updates[-1]["type"] == "failed"


def test_openrouter_empty_response_uses_same_retry_backoff(monkeypatch):
    class EmptyThenValidClient(_FakeOpenRouterClient):
        attempts = 0

        def create(self, **payload):
            self.__class__.attempts += 1
            content = "" if self.__class__.attempts == 1 else "recovered"
            return _FakeOpenRouterCompletion({"content": content})

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr("sr_harness.api.openrouter_api.OpenAI", EmptyThenValidClient)
    sleeps = []
    monkeypatch.setattr(
        "sr_harness.api.base_api.BaseAPI.wait_before_retry",
        lambda _self, delay: sleeps.append(delay),
    )

    api = OpenRouterAPI(model="deepseek/deepseek-v4-flash")
    chunks, _ = _consume(api([{"role": "user", "content": "retry empty"}]))

    assert sleeps == [1.0]
    assert chunks[0].content == "recovered"


def test_openrouter_all_empty_responses_return_raw_error(monkeypatch):
    class AlwaysEmptyClient(_FakeOpenRouterClient):
        attempts = 0

        def create(self, **payload):
            self.__class__.attempts += 1
            return _FakeOpenRouterCompletion({"content": ""})

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr("sr_harness.api.openrouter_api.OpenAI", AlwaysEmptyClient)
    sleeps = []
    monkeypatch.setattr(
        "sr_harness.api.base_api.BaseAPI.wait_before_retry",
        lambda _self, delay: sleeps.append(delay),
    )

    api = OpenRouterAPI(model="deepseek/deepseek-v4-flash")
    chunks, result = _consume(api([{"role": "user", "content": "retry empty"}]))

    assert chunks == []
    assert result.ok is False
    assert result.error == (
        "OpenRouterAPI(deepseek/deepseek-v4-flash) returned empty content and no usable tool calls."
    )
    assert AlwaysEmptyClient.attempts == 3
    assert sleeps == [1.0, 2.0]


def test_openrouter_uses_standard_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr("sr_harness.api.openrouter_api.OpenAI", _FakeOpenRouterClient)
    _FakeOpenRouterClient.api_keys = []
    _FakeOpenRouterClient.message = {"content": "ok"}

    api = OpenRouterAPI(model="deepseek/deepseek-v4-flash")
    _consume(api([{"role": "user", "content": "test key selection"}]))

    assert _FakeOpenRouterClient.api_keys == ["test-key"]


def test_openrouter_model_list_is_remote_filtered_and_cached(monkeypatch):
    client = _FakeModelListClient(
        [
            {
                "id": "vendor/text-z",
                "architecture": {"output_modalities": ["text"]},
            },
            {
                "id": "vendor/image-only",
                "architecture": {"output_modalities": ["image"]},
            },
            {"id": "vendor/text-a"},
        ]
    )
    api = OpenRouterAPI(
        environment={
            "OPENROUTER_API_KEY": "catalog-key",
            "OPENROUTER_ENDPOINT": "https://router.example/v1/",
        }
    )
    monkeypatch.setattr(api._model_catalog, "_http_client", lambda _url: client)

    assert api.model_list == ["vendor/text-a", "vendor/text-z"]
    assert api.model_list == ["vendor/text-a", "vendor/text-z"]
    assert len(client.requests) == 1
    assert client.requests[0]["url"] == "https://router.example/v1/models"
    assert client.requests[0]["headers"] == {"Authorization": "Bearer catalog-key"}


def test_openrouter_model_list_propagates_and_does_not_cache_failure(monkeypatch):
    import pytest

    attempts = 0
    api = OpenRouterAPI(environment={})

    def fail(_url):
        nonlocal attempts
        attempts += 1
        raise ConnectionError("catalog unavailable")

    monkeypatch.setattr(api._model_catalog, "_http_client", fail)

    with pytest.raises(ConnectionError, match="catalog unavailable"):
        _ = api.model_list
    with pytest.raises(ConnectionError, match="catalog unavailable"):
        _ = api.model_list
    assert attempts == 2


def test_deepseek_model_list_uses_official_compatible_endpoint(monkeypatch):
    client = _FakeModelListClient([{"id": "deepseek-chat"}, {"id": "deepseek-reasoner"}])
    api = DeepSeekAPI(
        environment={
            "DEEPSEEK_API_KEY": "catalog-key",
            "DEEPSEEK_ENDPOINT": "https://deepseek.example/v1",
        }
    )
    monkeypatch.setattr(api._model_catalog, "_http_client", lambda _url: client)

    assert api.model_list == ["deepseek-chat", "deepseek-reasoner"]
    assert client.requests[0]["url"] == "https://deepseek.example/v1/models"


def test_siliconflow_model_list_requests_chat_models(monkeypatch):
    client = _FakeModelListClient(
        [
            {"id": "Qwen/Qwen3-8B"},
            {"id": "deepseek-ai/DeepSeek-V4-Flash"},
        ]
    )
    api = SiliconFlowAPI(
        environment={
            "SILICONFLOW_API_KEY": "catalog-key",
            "SILICONFLOW_ENDPOINT": "https://silicon.example/v1/chat/completions",
        }
    )
    monkeypatch.setattr(api._model_catalog, "_http_client", lambda _url: client)

    assert api.model_list == [
        "Qwen/Qwen3-8B",
        "deepseek-ai/DeepSeek-V4-Flash",
    ]
    assert client.requests[0]["url"] == "https://silicon.example/v1/models"
    assert client.requests[0]["params"] == {"sub_type": "chat"}


def test_openrouter_implements_n_as_independent_requests(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr("sr_harness.api.openrouter_api.OpenAI", _FakeOpenRouterClient)
    _FakeOpenRouterClient.payloads = []
    _FakeOpenRouterClient.message = {"content": "sample"}

    api = OpenRouterAPI(model="deepseek/deepseek-v4-flash")
    chunks, returned = _consume(
        api(
            [{"role": "user", "content": "sample three times"}],
            n=3,
        )
    )

    assert [chunk.content for chunk in chunks] == ["sample", "sample", "sample"]
    assert len(_FakeOpenRouterClient.payloads) == 3
    assert all("n" not in payload for payload in _FakeOpenRouterClient.payloads)
    assert returned.token_usage == {"prompt": 21, "answer": 33}


def test_openrouter_skips_malformed_native_tool_calls(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr("sr_harness.api.openrouter_api.OpenAI", _FakeOpenRouterClient)
    _FakeOpenRouterClient.payloads = []
    _FakeOpenRouterClient.message = {
        "content": "ready",
        "tool_calls": [
            {
                "id": "call_bad",
                "type": "function",
                "function": {"name": "demo_tool", "arguments": '{"x": "unterminated'},
            },
            {
                "id": "call_good",
                "type": "function",
                "function": {"name": "demo_tool", "arguments": '{"x": 5}'},
            },
        ],
    }

    api = OpenRouterAPI(
        model="deepseek/deepseek-v4-pro",
        tool_box=BaseParser.create("openai", tool_list=[DemoTool()]),
    )
    chunks, return_value = _consume(api([{"role": "user", "content": "use the tool"}]))

    expected_call = ToolCall(
        "demo_tool", {"x": 5}, id="call_good", raw=_FakeOpenRouterClient.message["tool_calls"][1]
    )
    assert chunks[0].content == "ready"
    assert chunks[0].tool_calls == [expected_call]
    assert chunks[0].message == {
        "role": "assistant",
        "content": "ready",
        "tool_calls": _FakeOpenRouterClient.message["tool_calls"],
    }


def test_openrouter_text_parser_injects_tool_prompt_and_parses_action(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr("sr_harness.api.openrouter_api.OpenAI", _FakeOpenRouterClient)
    _FakeOpenRouterClient.payloads = []
    _FakeOpenRouterClient.message = {"content": "Action: demo_tool(x=2)"}

    api = OpenRouterAPI(
        model="qwen/qwen3.6-flash",
        tool_box=BaseParser.create("text", tool_list=[DemoTool()]),
    )
    messages = [{"role": "user", "content": "call demo"}]
    chunks, _return_value = _consume(api(messages))

    payload = _FakeOpenRouterClient.payloads[0]
    assert messages == [{"role": "user", "content": "call demo"}]
    assert "tools" not in payload
    assert payload["messages"][0]["role"] == "system"
    assert "## Available Tools:" in payload["messages"][0]["content"]
    assert chunks[0].tool_calls == [
        ToolCall("demo_tool", {"x": 2}, raw_str="Action: demo_tool(x=2)")
    ]


def test_deepseek_reuses_openai_streaming_and_issues_independent_samples(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr("sr_harness.api.deepseek_api.OpenAI", _StreamingOpenRouterClient)
    _StreamingOpenRouterClient.payloads = []
    updates = []
    api = DeepSeekAPI(
        model="deepseek-chat",
        tool_box=BaseParser.create("openai", tool_list=[DemoTool()]),
    )

    chunks, returned = _consume(
        api(
            [{"role": "user", "content": "stream twice"}],
            n=2,
            callback=updates.append,
        )
    )

    assert [chunk.content for chunk in chunks] == ["ready", "ready"]
    assert len(_StreamingOpenRouterClient.payloads) == 2
    assert all("n" not in payload for payload in _StreamingOpenRouterClient.payloads)
    assert [update["type"] for update in updates].count("start") == 2
    assert returned.token_usage == {"prompt": 14, "answer": 22}
    assert all(len(chunk.tool_calls) == 1 for chunk in chunks)


def test_deepseek_retries_with_shared_policy(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr("sr_harness.api.deepseek_api.OpenAI", _RetryingOpenRouterClient)
    sleeps = []
    monkeypatch.setattr(
        "sr_harness.api.base_api.BaseAPI.wait_before_retry",
        lambda _self, delay: sleeps.append(delay),
    )
    _RetryingOpenRouterClient.attempts = 0

    api = DeepSeekAPI(model="deepseek-chat")
    chunks, _ = _consume(api([{"role": "user", "content": "retry"}]))

    assert sleeps == [120.0]
    assert chunks[0].content == "recovered"


def test_siliconflow_qwen_text_parser_injects_tool_prompt_and_parses_action(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "test-key")
    payloads = []

    def fake_request(method, url, json, headers, **kwargs):
        payloads.append(json)
        return _FakeSiliconFlowResponse(
            _siliconflow_response({"content": "Action: demo_tool(x=3)"})
        )

    monkeypatch.setattr("sr_harness.api.siliconflow_api.requests.request", fake_request)

    api = SiliconFlowAPI(
        model="Qwen3-8B",
        tool_box=BaseParser.create("text", tool_list=[DemoTool()]),
    )
    chunks, _return_value = _consume(api([{"role": "user", "content": "call demo"}]))

    payload = payloads[0]
    assert payload["model"] == "Qwen/Qwen3-8B"
    assert payload["enable_thinking"] is True
    assert "tools" not in payload
    assert "## Available Tools:" in payload["messages"][0]["content"]
    assert chunks[0].tool_calls == [
        ToolCall("demo_tool", {"x": 3}, raw_str="Action: demo_tool(x=3)")
    ]


def test_siliconflow_qwen_native_tools_are_sent_and_tool_calls_are_extracted(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "test-key")
    payloads = []

    def fake_request(method, url, json, headers, **kwargs):
        payloads.append(json)
        return _FakeSiliconFlowResponse(
            _siliconflow_response(
                {
                    "content": "ready",
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {"name": "demo_tool", "arguments": '{"x": 4}'},
                        }
                    ],
                }
            )
        )

    monkeypatch.setattr("sr_harness.api.siliconflow_api.requests.request", fake_request)

    api = SiliconFlowAPI(
        model="Qwen3-8B",
        tool_box=BaseParser.create("openai", tool_list=[DemoTool()]),
    )
    chunks, return_value = _consume(api([{"role": "user", "content": "call demo"}]))

    payload = payloads[0]
    assert payload["tools"][0]["function"]["name"] == "demo_tool"
    assert payload["tool_choice"] == "auto"
    expected = [
        ToolCall(
            "demo_tool",
            {"x": 4},
            raw=_siliconflow_response(
                {
                    "content": "ready",
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {"name": "demo_tool", "arguments": '{"x": 4}'},
                        }
                    ],
                }
            )["choices"][0]["message"]["tool_calls"][0],
        )
    ]
    assert chunks[0].content == "ready"
    assert chunks[0].tool_calls == expected
    assert chunks[0].message == {
        "role": "assistant",
        "content": "ready",
        "tool_calls": [
            {
                "type": "function",
                "function": {"name": "demo_tool", "arguments": '{"x": 4}'},
            }
        ],
    }


def test_siliconflow_reuses_shared_retry_policy(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "test-key")
    attempts = 0
    sleeps = []

    def fake_request(method, url, json, headers, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise requests.ConnectionError("temporary private network detail")
        return _FakeSiliconFlowResponse(_siliconflow_response({"content": "recovered"}))

    import requests

    monkeypatch.setattr("sr_harness.api.siliconflow_api.requests.request", fake_request)
    monkeypatch.setattr(
        "sr_harness.api.base_api.BaseAPI.wait_before_retry",
        lambda _self, delay: sleeps.append(delay),
    )

    api = SiliconFlowAPI(model="Qwen3-8B")
    chunks, _ = _consume(api([{"role": "user", "content": "retry"}]))

    assert attempts == 2
    assert sleeps == [1.0]
    assert chunks[0].content == "recovered"
