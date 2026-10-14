from __future__ import annotations

import json

import pytest

from sr_harness.api import BaseAPI
from sr_harness.api.base_api import ProviderSampleResult
from sr_harness.api.deepseek_api import DeepSeekAPI
from sr_harness.api.gemini_api import GeminiAPI
from sr_harness.api.lmstudio_api import LMStudioAPI
from sr_harness.api.manual_api import ManualAPI
from sr_harness.api.openai_api import OpenAIAPI
from sr_harness.api.openrouter_api import OpenRouterAPI
from sr_harness.api.siliconflow_api import SiliconFlowAPI
from sr_harness.core import APICallSample, ToolCall, ToolMetadata
from sr_harness.parser import BaseParser
from sr_harness.tools import BaseTool


class ContractTool(BaseTool):
    metadata = ToolMetadata(
        name="contract_tool",
        description="Exercise the API contract.",
        parameters={"type": "object", "properties": {}},
    )

    def execute(self):
        return {}


class ShortAPI(BaseAPI):
    @property
    def model_list(self):
        return ["short"]

    def format_response(self, message, tool_calls, content=None):
        return self._build_response(message, tool_calls, content)

    def _request_sample(self, messages, *, sample_index, callback=None, **kwargs):
        self.report_progress(callback, {"type": "start", "sample": sample_index})
        message = {
            "role": "assistant",
            "content": "one response",
            "reasoning_content": "brief reasoning",
            "provider_field": 42,
        }
        response = self.format_response(message, [], message["content"])
        self.report_progress(callback, {
            "type": "complete",
            "sample": sample_index,
            "content": response.content,
            "reasoning": response.reasoning,
            "tool_calls": [],
        })
        return ProviderSampleResult(
            response=response,
            token_usage={"prompt": 3, "answer": 2},
            money_usage={"total": 0.25},
            raw_response={"provider_value": 42},
        )


def test_api_call_sample_reconstructs_message_from_normalized_fields():
    raw_call = {
        "id": "call-1",
        "type": "function",
        "function": {"name": "contract_tool", "arguments": "{}"},
    }
    response = APICallSample(
        content="done",
        tool_calls=[ToolCall("contract_tool", {}, id="call-1", raw=raw_call)],
        message_extra={
            "role": "assistant",
            "provider_field": 42,
            "reasoning_content": "because",
        },
    )

    assert response.message == {
        "role": "assistant",
        "content": "done",
        "provider_field": 42,
        "reasoning_content": "because",
        "tool_calls": [raw_call],
    }


@pytest.mark.parametrize(
    ("api", "message"),
    [
        (
            OpenRouterAPI(),
            {
                "role": "assistant",
                "content": "done",
                "reasoning": "because",
                "reasoning_details": [{"type": "reasoning.text", "text": "because"}],
            },
        ),
        (DeepSeekAPI(), {"role": "assistant", "content": "done", "reasoning_content": "because"}),
        (
            SiliconFlowAPI(),
            {"role": "assistant", "content": "done", "reasoning_content": "because"},
        ),
        (LMStudioAPI(), {"role": "assistant", "content": "done"}),
        (OpenAIAPI(), {"role": "assistant", "content": "done", "refusal": None}),
        (GeminiAPI(), {"role": "assistant", "content": "done"}),
        (ManualAPI(), {"role": "assistant", "content": "done"}),
    ],
)
def test_provider_format_response_round_trips_original_message(api, message):
    raw_call = {
        "id": "call-1",
        "type": "function",
        "function": {"name": "contract_tool", "arguments": "{}"},
    }
    original = {**message, "tool_calls": [raw_call]}
    tool_calls = [ToolCall("contract_tool", {}, id="call-1", raw=raw_call)]

    sample = api.format_response(original, tool_calls, original["content"])

    assert sample.message == original
    assert sample.tool_calls is tool_calls


def test_api_call_contract_rejects_partial_n(tmp_path):
    class PartialAPI(ShortAPI):
        def _request_samples(self, messages, *, n=1, callback=None, **kwargs):
            result = self._request_sample(
                messages,
                sample_index=1,
                callback=callback,
                **kwargs,
            )
            yield result.response
            return self.aggregate_sample_results([result])

    updates = []
    call = PartialAPI(save_path=tmp_path)("hello", n=2, callback=updates.append)

    with pytest.raises(ValueError, match="returned 1 of 2.*without reporting an error"):
        list(call)

    assert [update["type"] for update in updates] == ["start", "complete"]

    records = [
        json.loads(line)
        for line in (tmp_path / "api_calls.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [record["type"] for record in records] == ["response"]


def test_api_call_preserves_provider_result_and_adds_sample_counts(tmp_path):
    call = ShortAPI(save_path=tmp_path)("hello")

    responses = list(call)

    assert responses[0].content == "one response"
    assert call.ok is True
    assert call.error is None
    assert call.token_usage == {"prompt": 3, "answer": 2}
    assert call.money_usage == {"total": 0.25}
    assert call.extra == {
        "responses": [{"provider_value": 42}],
        "requested_samples": 1,
        "completed_samples": 1,
    }


def test_default_sample_request_calls_single_sample_hook_n_times():
    api = ShortAPI()

    responses = list(api("hello", n=3))

    assert [response.content for response in responses] == ["one response"] * 3


def test_batch_override_does_not_require_single_sample_hook():
    class BatchOnlyAPI(ShortAPI):
        def _request_sample(self, *args, **kwargs):
            raise AssertionError("batch provider must not use the single-sample hook")

        def _request_samples(self, messages, *, n=1, callback=None, **kwargs):
            responses = []
            for sample_index in range(1, n + 1):
                message = {"role": "assistant", "content": f"batch {sample_index}"}
                response = self.format_response(message, [], message["content"])
                responses.append(response)
                yield response
            return {
                "ok": True,
                "error": None,
                "token_usage": {},
                "money_usage": {},
                "extra": {},
            }

    assert [response.content for response in BatchOnlyAPI()("hello", n=2)] == [
        "batch 1",
        "batch 2",
    ]


def test_api_call_rejects_nonconforming_provider_result():
    class MissingFieldsAPI(ShortAPI):
        def _request_samples(self, messages, n=1, callback=None, **kwargs):
            yield from []
            return {"token_usage": {}, "money_usage": {}}

    with pytest.raises(ValueError, match="missing required fields"):
        list(MissingFieldsAPI()("hello"))


def test_api_uses_one_explicit_tool_box():
    tool = ContractTool()
    tool_box = BaseParser.create("openai", tool_list=[tool])
    api = ShortAPI(tool_box=tool_box)

    assert api.tool_box is tool_box
    assert tool_box.tools == [tool]
    assert not hasattr(tool_box, "tool_instances")
    assert tool_box["contract_tool"] is tool
    with pytest.raises(KeyError, match="missing"):
        tool_box["missing"]
    assert tool_box.format_tools()[0]["function"]["name"] == "contract_tool"
    assert ShortAPI().tool_box is None
    with pytest.raises(ValueError, match="not-a-parser"):
        BaseParser.create("not-a-parser", tool_list=[tool])


def test_parser_none_and_empty_list_both_expose_no_tools():
    assert BaseParser.create("openai", tool_list=None).tools == []
    assert BaseParser.create("openai", tool_list=[]).tools == []


def test_parser_reports_duplicate_tool_names():
    with pytest.raises(ValueError, match="duplicate tool names: contract_tool"):
        BaseParser.create("openai", tool_list=[ContractTool(), ContractTool()])


def test_independent_sample_boundary_never_retries_user_interruption():
    class InterruptedAPI(ShortAPI):
        attempts = 0

        def _request_sample(self, messages, *, sample_index, callback=None, **kwargs):
            self.attempts += 1
            raise InterruptedError("cancelled")

    api = InterruptedAPI()
    with pytest.raises(InterruptedError, match="cancelled"):
        list(api("hello"))
    assert api.attempts == 1


def test_cancel_interrupts_from_an_api_owned_progress_boundary():
    api = ShortAPI()

    def cancel_without_raising(_update):
        api.cancel()

    with pytest.raises(InterruptedError, match="cancelled"):
        list(api("hello", callback=cancel_without_raising))


def test_cancel_before_result_consumption_is_not_lost_and_is_reset_afterward():
    api = ShortAPI()
    result = api("hello")
    api.cancel()

    with pytest.raises(InterruptedError, match="cancelled"):
        list(result)

    assert len(list(api("hello"))) == 1


@pytest.mark.parametrize(
    "api",
    [OpenAIAPI(), GeminiAPI(), SiliconFlowAPI(), LMStudioAPI(), ManualAPI()],
)
def test_non_streaming_providers_report_unsupported_force_cancel(api):
    message = api.cancel()

    assert "does not support force-interrupting" in message


def test_get_env_can_require_values_and_proxy_uses_standard_no_proxy(monkeypatch):
    monkeypatch.delenv("SR_HARNESS_MISSING_TEST_VALUE", raising=False)
    api = ShortAPI(
        environment={
            "TOKEN": "session-token",
            "HTTPS_PROXY": "http://proxy.example:8080",
            "NO_PROXY": ".internal.example,10.0.0.0/8",
        }
    )

    assert api.get_env("TOKEN", required=True) == "session-token"
    with pytest.raises(KeyError, match="SR_HARNESS_MISSING_TEST_VALUE"):
        api.get_env("SR_HARNESS_MISSING_TEST_VALUE", required=True)
    assert api.proxy_url("https://service.internal.example/v1") is None
    assert api.proxy_url("https://10.2.3.4/v1") is None
    assert api.proxy_url("https://public.example/v1") == "http://proxy.example:8080"
