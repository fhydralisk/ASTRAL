# Copyright (c) 2026-present, Yumeow. Licensed under the MIT License.
from __future__ import annotations

import logging
from typing import Any, Dict, Generator, List
from urllib.parse import urlsplit, urlunsplit

import requests
from dotenv import load_dotenv

from .base_api import BaseAPI
from ..core import APICallSample, ToolCall

_logger = logging.getLogger(f"sr_harness.{__name__}")


@BaseAPI.register("lmstudio")
class LMStudioAPI(BaseAPI):
    """LLM provider adapter for a local or remote LM Studio server.

    Automatically normalizes LM Studio's ``/api/v1/chat`` endpoint to the
    OpenAI-compatible ``/v1/chat/completions`` route required for multi-turn
    conversations and function calling.
    """

    def __init__(self, model: str = "qwen_qwen3-4b-instruct-2507", **kwargs: Any) -> None:
        """Initialize the LM Studio API adapter.

        Args:
            model: Local model identifier loaded in LM Studio.
            **kwargs: Additional arguments forwarded to :class:`BaseAPI`.
        """
        super().__init__(model=model, **kwargs)

    def cancel(self) -> str:
        """Request cancellation and note that synchronous LM Studio HTTP calls finish the active request before stopping.

        Returns:
            str: Human-readable notice describing cancellation behavior.
        """
        return (
            "LMStudioAPI does not support force-interrupting an active non-streaming request. "
            "The Agent will pause at its next safe boundary."
        )

    def format_response(
        self, message: dict[str, Any], tool_calls: list[ToolCall], content: str | None = None
    ) -> APICallSample:
        """Convert an LM Studio completion message into a normalized :class:`~sr_harness.core.APICallSample`.

        Args:
            message: Raw message dictionary returned by LM Studio.
            tool_calls: Normalized tool calls extracted from the message.
            content: Optional explicit text content override.

        Returns:
            APICallSample: Normalized assistant response sample.
        """
        return self._build_response(message, tool_calls, content)

    @property
    def model_list(self) -> list[str]:
        """Return the configured model identifier for this LM Studio instance.

        Returns:
            list[str]: Single-element list containing the active model name.
        """
        return ["qwen_qwen3-4b-instruct-2507"]

    @staticmethod
    def normalize_endpoint(endpoint: str) -> str:
        """Convert an LM Studio base URL or native chat path into the ``/v1/chat/completions`` endpoint URL.

        Args:
            endpoint: Raw endpoint URL from ``LMSTUDIO_ENDPOINT`` or settings.

        Returns:
            str: Normalized OpenAI-compatible chat completions URL.
        """
        endpoint = endpoint.strip()
        parts = urlsplit(endpoint)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError(f"Invalid LMSTUDIO_ENDPOINT: {endpoint!r}")

        path = (
            parts.path.rstrip("/").removesuffix("/api/v1/chat").removesuffix("/v1/chat/completions")
            + "/v1/chat/completions"
        )
        return urlunsplit((parts.scheme, parts.netloc, path, "", ""))

    def _request_samples(
        self,
        messages: List[Dict[str, str]],
        n: int = 1,
        max_tokens: int | None = None,
        temperature: float = 1.0,
        top_p: float = 1.0,
        callback=None,
    ) -> Generator[APICallSample, None, dict[str, Any]]:
        yield from []
        load_dotenv()

        endpoint = self.normalize_endpoint(self.get_env("LMSTUDIO_ENDPOINT", required=True))
        api_key = self.get_env("LMSTUDIO_API_KEY", required=True)
        payload = {
            "model": self.model,
            "messages": [dict(message) for message in messages],
            "n": n,
            "top_p": top_p,
            **({"max_tokens": max_tokens} if max_tokens is not None else {}),
            "temperature": temperature,
            "stream": False,
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

        # LM Studio is normally on the local network. Ignore shell proxy
        # variables so a loopback proxy cannot intercept or block the request.
        session = requests.Session()
        session.trust_env = False
        timeout = float(self.get_env("LMSTUDIO_TIMEOUT", "300"))
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        max_retry = 3
        self.report_progress(callback, {"type": "start", "sample": 1})
        for attempt in range(1, max_retry + 1):
            try:
                response = session.post(endpoint, headers=headers, json=payload, timeout=timeout)
                response.raise_for_status()
                response_dict = response.json()
                choices = response_dict.get("choices") or []
                if not choices:
                    raise ValueError(f"LMStudioAPI({self.model}) returned no choices.")
                break
            except InterruptedError:
                raise
            except Exception as error:
                public_error = self.error_message(error)
                if attempt == max_retry:
                    self.report_progress(callback, {
                        "type": "failed",
                        "sample": 1,
                        "error": public_error,
                    })
                    return {
                        "ok": False,
                        "error": public_error,
                        "token_usage": {},
                        "money_usage": {},
                        "extra": {},
                    }
                if callback is not None:
                    self.report_progress(callback, {
                        "type": "retry",
                        "sample": 1,
                        "attempt": attempt,
                        "error": public_error,
                    })
                delay = min(float(2 ** (attempt - 1)), 30.0)
                _logger.info(
                    f"Retrying LMStudioAPI({self.model}) in {delay:g}s "
                    f"(attempt {attempt}/{max_retry})."
                )
                self.wait_before_retry(delay)

        details = []
        for sample, choice in enumerate(choices, 1):
            message = choice.get("message") or {}
            content = message.get("content") or ""
            truncated = choice.get("finish_reason") == "length"
            if truncated:
                message = {key: value for key, value in message.items() if key != "tool_calls"}
            tool_call = [] if truncated else self.parse_tool_calls(message, content)
            if not (content.strip() or tool_call):
                _logger.warning(f"LMStudioAPI({self.model}) returned an empty choice.")
            details.append({"content": content, "tool_call": tool_call, "message": message})
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
                if sample < len(choices):
                    self.report_progress(callback, {
                        "type": "start",
                        "sample": sample + 1,
                    })
            yield sample_response

        raw_usage = response_dict.get("usage") or {}
        prompt_tokens = int(raw_usage.get("prompt_tokens") or 0)
        completion_tokens = int(raw_usage.get("completion_tokens") or 0)
        reasoning_tokens = int(
            (raw_usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
        )
        token_usage = {
            "prompt": prompt_tokens,
            "answer": max(completion_tokens - reasoning_tokens, 0),
        }
        if reasoning_tokens:
            token_usage["reason"] = reasoning_tokens
        total_tokens = int(raw_usage.get("total_tokens") or prompt_tokens + completion_tokens)
        accounted = prompt_tokens + completion_tokens
        if total_tokens > accounted:
            token_usage["other"] = total_tokens - accounted

        return {
            "ok": True,
            "error": None,
            "token_usage": token_usage,
            "money_usage": {"total": 0.0},
            "extra": {"responses": [response_dict]},
        }
