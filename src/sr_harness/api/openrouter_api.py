# Copyright (c) 2024-present, Yumeow. Licensed under the MIT License.
import httpx
from openai import DefaultHttpxClient, OpenAI
from dotenv import load_dotenv
from typing import Any
from .base_api import BaseAPI, ProgressCallback, ProviderSampleResult
from .utils import RemoteModelCatalog
from ..core import APICallSample, ToolCall


@BaseAPI.register("openrouter")
class OpenRouterAPI(BaseAPI):
    """LLM provider adapter for OpenRouter, supporting live model discovery and streaming tool calls."""

    def __init__(self, model: str = "qwen/qwen3.6-plus", **kwargs: Any) -> None:
        """Initialize the OpenRouter API adapter.

        Args:
            model: OpenRouter model slug (defaults to ``"qwen/qwen3.6-plus"``).
            **kwargs: Additional arguments forwarded to :class:`BaseAPI`.
        """
        super().__init__(model=model, **kwargs)
        self._model_catalog = RemoteModelCatalog(
            lambda url: httpx.Client(proxy=self.proxy_url(url), trust_env=False)
        )

    def format_response(
        self, message: dict[str, Any], tool_calls: list[ToolCall], content: str | None = None
    ) -> APICallSample:
        """Convert an OpenRouter completion message into a normalized :class:`~sr_harness.core.APICallSample`.

        Args:
            message: Raw OpenRouter assistant message dictionary.
            tool_calls: Normalized tool calls extracted from the message.
            content: Optional explicit text content override.

        Returns:
            APICallSample: Normalized assistant response sample.
        """
        return self._build_response(message, tool_calls, content)

    @property
    def model_list(self) -> list[str]:
        """Fetch and return all text-capable model identifiers from the live OpenRouter catalog.

        Returns:
            list[str]: Available OpenRouter model slugs.
        """
        endpoint = self.get_env("OPENROUTER_ENDPOINT", "https://openrouter.ai/api/v1")

        def supports_text_output(record: dict[str, Any]) -> bool:
            architecture = record.get("architecture")
            if not isinstance(architecture, dict):
                return True
            output_modalities = architecture.get("output_modalities")
            return not isinstance(output_modalities, list) or "text" in output_modalities

        return self._model_catalog.get(
            f"{endpoint.rstrip('/')}/models",
            description="OpenRouter model catalog",
            api_key=self.get_env("OPENROUTER_API_KEY"),
            include=supports_text_output,
        )

    def _request_sample(
        self,
        messages: list[dict[str, Any]],
        *,
        sample_index: int,
        max_tokens=None,
        temperature=1.0,
        top_p=1.0,
        callback: ProgressCallback | None = None,
    ) -> ProviderSampleResult:
        if not getattr(self.environment, "strict", False):
            load_dotenv()
        api_key = self.get_env("OPENROUTER_API_KEY", required=True)
        endpoint = self.get_env("OPENROUTER_ENDPOINT", "https://openrouter.ai/api/v1")
        client = OpenAI(
            timeout=300.0,
            max_retries=0,
            base_url=endpoint,
            api_key=api_key,
            http_client=DefaultHttpxClient(
                proxy=self.proxy_url(endpoint),
                trust_env=False,
            ),
        )
        payload = {
            "model": self.model,
            "messages": [dict(message) for message in messages],
            "top_p": top_p,
            **({"max_tokens": max_tokens} if max_tokens is not None else {}),
            "temperature": temperature,
        }
        if self.model == "openai/gpt-oss-120b":
            # Keep benchmark inference reproducible across OpenRouter calls. The
            # default router otherwise mixes providers with different weight
            # quantizations (for example bf16 and fp8) in one experiment.
            payload["extra_body"] = {
                "provider": {
                    "order": ["AkashML"],
                    "allow_fallbacks": False,
                }
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
        choices = raw_response.get("choices") or [{}]
        finish_reason = raw_response.get("finish_reason") or choices[0].get("finish_reason")
        token_usage = self.openai_token_usage(completion)
        usage = getattr(completion, "usage", None)
        money_usage = {"total": getattr(usage, "cost", 0)} if usage is not None else {}
        if finish_reason == "length":
            partial_message = dict(message)
            partial_message.pop("tool_calls", None)
            budget = max_tokens if max_tokens is not None else "provider default"
            error = (
                f"OpenRouterAPI({self.model}) exhausted max_tokens={budget}; "
                "the response was truncated before the model completed its turn. "
                "Increase the Agent's maximum output length and retry. "
                f"模型已耗尽 max_tokens={budget}，响应在本轮完成前被截断；"
                "请增大 Agent 的最大输出长度后重试。"
            )
            partial_response = self.format_response(partial_message, [], content)
            partial_response.finish_reason = "length"
            return ProviderSampleResult(
                response=partial_response,
                token_usage=token_usage,
                money_usage=money_usage,
                raw_response=raw_response,
                error=error,
            )
        tool_calls = self.parse_tool_calls(message, content)
        if not (tool_calls or content.strip()):
            raise ValueError(
                f"OpenRouterAPI({self.model}) returned empty content and no usable tool calls."
            )
        return ProviderSampleResult(
            response=self.format_response(message, tool_calls, content),
            token_usage=token_usage,
            money_usage=money_usage,
            raw_response=raw_response,
        )
