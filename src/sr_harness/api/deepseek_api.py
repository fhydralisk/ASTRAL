# Copyright (c) 2024-present, Yumeow. Licensed under the MIT License.
import httpx
from openai import DefaultHttpxClient, OpenAI
from typing import Any
from .base_api import BaseAPI, ProgressCallback, ProviderSampleResult
from .utils import RemoteModelCatalog
from ..core import APICallSample, ToolCall


@BaseAPI.register("deepseek")
class DeepSeekAPI(BaseAPI):
    """DeepSeek adapter accepting models in its live provider catalog."""

    def __init__(self, model: str = "deepseek-chat", **kwargs: Any) -> None:
        super().__init__(model=model, **kwargs)
        self._model_catalog = RemoteModelCatalog(
            lambda url: httpx.Client(proxy=self.proxy_url(url), trust_env=False)
        )

    def format_response(
        self, message: dict[str, Any], tool_calls: list[ToolCall], content: str | None = None
    ) -> APICallSample:
        """Convert one DeepSeek message into the public response contract."""
        return self._build_response(message, tool_calls, content)

    @property
    def model_list(self) -> list[str]:
        """Return the current DeepSeek model catalog."""
        endpoint = self.get_env("DEEPSEEK_ENDPOINT", "https://api.deepseek.com")
        return self._model_catalog.get(
            f"{endpoint.rstrip('/')}/models",
            description="DeepSeek model catalog",
            api_key=self.get_env("DEEPSEEK_API_KEY", required=True),
        )

    def _request_sample(
        self,
        messages: list[dict[str, Any]],
        *,
        sample_index: int,
        max_tokens=4096,
        temperature=1,
        callback: ProgressCallback | None = None,
    ) -> ProviderSampleResult:
        endpoint = self.get_env("DEEPSEEK_ENDPOINT", "https://api.deepseek.com")
        client = OpenAI(
            timeout=300.0,
            max_retries=0,
            api_key=self.get_env("DEEPSEEK_API_KEY", required=True),
            base_url=endpoint,
            http_client=DefaultHttpxClient(
                proxy=self.proxy_url(endpoint),
                trust_env=False,
            ),
        )
        payload = {
            "model": self.model,
            "messages": [
                {
                    key: value
                    for key, value in message.items()
                    if not (key == "tool_calls" and value == [])
                }
                for message in messages
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if self.tool_box is None:
            pass
        elif not self.tool_box.native_tool_calls:
            description = (
                "Use the following tools when a tool call is needed. "
                "Return tool calls in the specified format.\n\n"
                f"{self.tool_box.format_tools()}"
            )
            if payload["messages"][0]["role"] in {"system", "developer"}:
                first = payload["messages"][0]
                payload["messages"][0] = {
                    **first,
                    "content": f"{first['content']}\n\n{description}",
                }
            else:
                payload["messages"].insert(0, {"role": "system", "content": description})
        else:
            tools = self.tool_box.format_tools()
            if not isinstance(tools, list):
                raise TypeError("Native tool parser must return JSON tool descriptions")
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        completion, raw_response, message, content = self.openai_chat_completion(
            client,
            payload,
            sample=sample_index,
            callback=callback,
        )
        tool_calls = self.parse_tool_calls(message, content)
        token_usage = self.openai_token_usage(completion, other_key="other")
        money_usage = {
            "prompt": 0.28 / 1e6 * token_usage.get("prompt", 0),
            "answer": 0.42 / 1e6 * token_usage.get("answer", 0),
        }
        if "other" in token_usage:
            money_usage["other"] = 0.42 / 1e6 * token_usage["other"]
        choices = raw_response.get("choices") or [{}]
        finish_reason = raw_response.get("finish_reason") or choices[0].get("finish_reason")
        if finish_reason == "length":
            partial_message = dict(message)
            partial_message.pop("tool_calls", None)
            return ProviderSampleResult(
                response=self.format_response(partial_message, [], content),
                token_usage=token_usage,
                money_usage=money_usage,
                raw_response=raw_response,
                error=(
                    f"DeepSeekAPI({self.model}) exhausted max_tokens={max_tokens}; "
                    "increase the Agent's maximum output length and retry."
                ),
            )
        if not (tool_calls or content.strip()):
            raise ValueError(
                f"DeepSeekAPI({self.model}) returned empty content and no usable tool calls."
            )
        return ProviderSampleResult(
            response=self.format_response(message, tool_calls, content),
            token_usage=token_usage,
            money_usage=money_usage,
            raw_response=raw_response,
        )
