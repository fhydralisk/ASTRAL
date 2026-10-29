# Copyright (c) 2024-present, Yumeow. Licensed under the MIT License.
import httpx
import logging
import requests
from dotenv import load_dotenv
from typing import Any, Callable, Dict, Generator, List

from .base_api import BaseAPI, ProgressCallback, ProviderSampleResult
from .utils import RemoteModelCatalog
from ..core import APICallSample, ToolCall

_logger = logging.getLogger(f"sr_harness.{__name__}")


class _SiliconFlowRequestFailed(RuntimeError):
    """Carry one SiliconFlow request failure already prepared for the frontend."""


@BaseAPI.register("siliconflow")
class SiliconFlowAPI(BaseAPI):
    """LLM provider adapter for SiliconFlow chat and reasoning models."""

    def __init__(self, model: str = "Qwen3-8B", **kwargs: Any) -> None:
        """Initialize the SiliconFlow API adapter.

        Args:
            model: SiliconFlow model identifier (defaults to ``"Qwen3-8B"``).
            **kwargs: Additional arguments forwarded to :class:`BaseAPI`.
        """
        super().__init__(model=model, **kwargs)
        self._model_catalog = RemoteModelCatalog(
            lambda url: httpx.Client(proxy=self.proxy_url(url), trust_env=False)
        )

    def cancel(self) -> str:
        """Request cancellation and note that synchronous SiliconFlow HTTP requests pause once the active call returns.

        Returns:
            str: Human-readable notice describing cancellation behavior.
        """
        return (
            "SiliconFlowAPI does not support force-interrupting an active non-streaming "
            "request. The Agent will pause at its next safe boundary."
        )

    def format_response(
        self, message: dict[str, Any], tool_calls: list[ToolCall], content: str | None = None
    ) -> APICallSample:
        """Convert a SiliconFlow response message into a normalized :class:`~sr_harness.core.APICallSample`.

        Args:
            message: Raw SiliconFlow assistant message dictionary.
            tool_calls: Normalized tool calls extracted from the message.
            content: Optional explicit text content override.

        Returns:
            APICallSample: Normalized assistant response sample.
        """
        return self._build_response(message, tool_calls, content)

    @property
    def model_list(self) -> list[str]:
        """Fetch and return the available chat models from SiliconFlow's model catalog.

        Returns:
            list[str]: Supported SiliconFlow model identifiers.
        """
        chat_endpoint = self.get_env(
            "SILICONFLOW_ENDPOINT",
            "https://api.siliconflow.cn/v1/chat/completions",
        )
        normalized_endpoint = chat_endpoint.rstrip("/")
        default_models_endpoint = normalized_endpoint.removesuffix("/chat/completions") + "/models"
        models_endpoint = self.get_env(
            "SILICONFLOW_MODELS_ENDPOINT",
            default_models_endpoint,
        )
        return self._model_catalog.get(
            models_endpoint,
            description="SiliconFlow chat-model catalog",
            api_key=self.get_env("SILICONFLOW_API_KEY", required=True),
            params={"sub_type": "chat"},
        )

    def _post_json(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        *,
        description: str,
        sample: int | None = None,
        validate: Callable[[dict[str, Any]], None] | None = None,
        callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """POST one SiliconFlow request with provider-local retry handling."""
        for attempt in range(1, 4):
            try:
                proxy = self.proxy_url(url)
                response = requests.request(
                    "POST",
                    url,
                    json=payload,
                    headers=headers,
                    proxies={"http": proxy, "https": proxy} if proxy else None,
                )
                if response.status_code != 200:
                    response.raise_for_status()
                data = response.json()
                if validate is not None:
                    validate(data)
                return data
            except InterruptedError:
                raise
            except Exception as error:
                public_error = self.error_message(error, description=description)
                if attempt == 3:
                    update = {"type": "failed", "error": public_error}
                    if sample is not None:
                        update["sample"] = sample
                    self.report_progress(callback, update)
                    raise _SiliconFlowRequestFailed(public_error) from error
                update = {
                    "type": "retry",
                    "attempt": attempt,
                    "error": public_error,
                }
                if sample is not None:
                    update["sample"] = sample
                self.report_progress(callback, update)
                delay = self.retry_delay(error, attempt)
                _logger.info(
                    f"Retrying {description} in {delay:g}s (attempt {attempt}/3)."
                )
                self.wait_before_retry(delay)
        raise AssertionError("unreachable")

    @staticmethod
    def _validate_chat_response(response: dict[str, Any]) -> None:
        choices = response.get("choices") or []
        if not choices or any(
            not (
                ((choice.get("message") or {}).get("content") or "").strip()
                or (choice.get("message") or {}).get("tool_calls")
            )
            for choice in choices
        ):
            raise ValueError("SiliconFlow returned an empty chat completion.")

    def _request_samples(
        self,
        messages: List[Dict[str, str]],
        n=1,
        max_tokens=None,
        temperature=1.0,
        top_p=1.0,
        callback: ProgressCallback | None = None,
    ) -> Generator[APICallSample, None, dict[str, Any]]:
        yield from []
        if not getattr(self.environment, "strict", False):
            load_dotenv()
        url = self.get_env(
            "SILICONFLOW_ENDPOINT",
            "https://api.siliconflow.cn/v1/chat/completions",
        )
        headers = {
            "Authorization": f"Bearer {self.get_env('SILICONFLOW_API_KEY', required=True)}",
            "Content-Type": "application/json",
        }
        payload = {
            "messages": [dict(message) for message in messages],
            "n": n,
            "stop": [],
            "top_k": 50,
            "top_p": top_p,
            "min_p": 0.05,
            "stream": False,
            "thinking_budget": 1024,
            **({"max_tokens": max_tokens} if max_tokens is not None else {}),
            "temperature": temperature,
            "frequency_penalty": 0.5,
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
        model = self.model
        try:
            if model == "Qwen3-8B":
                results = yield from self._request_qwen3_8b(url, headers, payload, callback)
            elif model == "Deepseek-V3":
                results = yield from self._request_deepseek_v3(url, headers, payload, callback)
            else:
                raise ValueError(f"Model {model} not supported in SiliconFlowAPI.")
        except _SiliconFlowRequestFailed as error:
            return {
                "ok": False,
                "error": str(error),
                "token_usage": {},
                "money_usage": {},
                "extra": {},
            }
        return results

    def _request_qwen3_8b(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        callback: ProgressCallback | None,
    ) -> Generator[APICallSample, None, dict[str, Any]]:
        """Run the ``qwen3 8b`` operation.

        Args:
            url: The url value.
            headers: The headers value.
            payload: Serializable event payload.

        Returns:
            Generator yielding call samples and returning aggregate metadata.
        """
        yield from []
        payload = {
            "model": "Qwen/Qwen3-8B",
            "enable_thinking": True,
            **payload,
        }
        self.report_progress(callback, {"type": "start", "sample": 1})
        responses = self._post_json(
            url,
            headers,
            payload,
            description=f"SiliconFlowAPI({self.model})",
            sample=1,
            validate=self._validate_chat_response,
            callback=callback,
        )
        for sample, choice in enumerate(responses["choices"], 1):
            content = choice["message"].get("content") or ""
            message = dict(choice["message"])
            truncated = choice.get("finish_reason") == "length"
            if truncated:
                message.pop("tool_calls", None)
            tool_call = [] if truncated else self.parse_tool_calls(message, content)
            sample_response = self.format_response(message, tool_call, content)
            sample_response.finish_reason = choice.get("finish_reason")
            if callback is not None:
                self.report_progress(callback, {
                    "type": "complete",
                    "sample": sample,
                    "content": sample_response.content,
                    "reasoning": sample_response.reasoning,
                    "tool_calls": [call.raw for call in sample_response.tool_calls],
                })
                if sample < len(responses["choices"]):
                    self.report_progress(callback, {
                        "type": "start",
                        "sample": sample + 1,
                    })
            yield sample_response
        prompt_tokens = responses["usage"]["prompt_tokens"]
        reason_tokens = (
            responses["usage"].get("completion_tokens_details", {}).get("reasoning_tokens", 0)
        )
        answer_tokens = responses["usage"]["completion_tokens"] - reason_tokens
        token_usage = {
            "prompt": prompt_tokens,
            "answer": answer_tokens,
            "reason": reason_tokens,
        }
        if (
            other := responses["usage"]["total_tokens"]
            - prompt_tokens
            - answer_tokens
            - reason_tokens
        ) != 0:
            token_usage["other"] = other
        return {
            "ok": True,
            "error": None,
            "token_usage": token_usage,
            "money_usage": {"prompt": 0.0, "answer": 0.0, "reason": 0.0},
            "extra": {"responses": [responses]},
        }

    def _request_deepseek_v3(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        callback: ProgressCallback | None,
    ) -> Generator[APICallSample, None, dict[str, Any]]:
        """Run the ``deepseek v3`` operation.

        Args:
            url: The url value.
            headers: The headers value.
            payload: Serializable event payload.

        Returns:
            Generator yielding call samples and returning aggregate metadata.
        """
        yield from []
        payload = {
            "model": "deepseek-ai/DeepSeek-V3",
            **payload,
        }
        n, payload["n"] = payload["n"], 1
        model = payload["model"]
        details = []
        for idx in range(1, n + 1):
            self.report_progress(callback, {"type": "start", "sample": idx})
            response = self._post_json(
                url,
                headers,
                payload,
                description=f"SiliconFlowAPI({model})",
                sample=idx,
                validate=self._validate_chat_response,
                callback=callback,
            )
            prompt_tokens = response["usage"]["prompt_tokens"]
            answer_tokens = response["usage"]["completion_tokens"]
            token_usage = {"prompt": prompt_tokens, "answer": answer_tokens}
            if (other := response["usage"]["total_tokens"] - prompt_tokens - answer_tokens) > 0:
                token_usage["other"] = other
            price_usage = {
                "prompt": 2 / 7.0 * prompt_tokens / 1e6,
                "answer": 8 / 7.0 * answer_tokens / 1e6,
            }
            message = response["choices"][0]["message"]
            content = message["content"] or ""
            tool_call = self.parse_tool_calls(message, content)
            sample_response = self.format_response(message, tool_call, content)
            details.append(
                ProviderSampleResult(
                    response=sample_response,
                    token_usage=token_usage,
                    money_usage=price_usage,
                    raw_response=response,
                )
            )
            if callback is not None:
                self.report_progress(callback, {
                    "type": "complete",
                    "sample": idx,
                    "content": sample_response.content,
                    "reasoning": sample_response.reasoning,
                    "tool_calls": [call.raw for call in sample_response.tool_calls],
                })
            yield sample_response
        return self.aggregate_sample_results(details)
