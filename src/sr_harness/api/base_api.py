# Copyright (c) 2024-present, Yumeow. Licensed under the MIT License.
"""Base class and shared tool-call support for LLM provider adapters."""

from __future__ import annotations

import json
import logging
import time
import threading
import queue
import traceback
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any, Callable, Generator, Mapping
from requests.utils import should_bypass_proxies

from ..core import APICallSample, APICallSummary, ToolCall
from ..parser import BaseParser
from ..utils import FactoryMixin
from .error_filter import screen_frontend_error

_logger = logging.getLogger(f"sr_harness.{__name__}")
_api_log_lock = threading.Lock()

ProgressCallback = Callable[[dict[str, Any]], None]


@dataclass(slots=True)
class ProviderSampleResult:
    """Internal container pairing one sampled :class:`~sr_harness.core.APICallSample` with its token usage, cost, and error status."""

    response: APICallSample
    token_usage: dict[str, int | float] = field(default_factory=dict)
    money_usage: dict[str, int | float] = field(default_factory=dict)
    raw_response: Any = None
    error: str | None = None


class BaseAPI(ABC, FactoryMixin):
    """Abstract base adapter for language-model providers.

    Handles API key and proxy resolution from the session environment, native or
    parser-based tool formatting, OpenAI-compatible streaming and non-streaming
    chat completions, retry backoff, and cooperative cancellation.
    """

    STREAM_IDLE_TIMEOUT_SECONDS = 300.0

    def __init__(
        self,
        model: str | None = None,
        tool_box: BaseParser | None = None,
        environment: Mapping[str, str] | None = None,
        save_path: str | Path | None = None,
    ) -> None:
        """Initialize the LLM provider adapter.

        Args:
            model: Model identifier to request (defaults to the subclass's default model).
            tool_box: Optional :class:`~sr_harness.parser.BaseParser` holding enabled tools.
            environment: Optional session-scoped environment mapping for API keys and proxies.
            save_path: Optional directory path for logging raw provider responses.
        """
        self.model = model
        if tool_box is not None and not isinstance(tool_box, BaseParser):
            raise TypeError("tool_box must be a BaseParser instance or None")
        self.tool_box = tool_box
        self.environment = environment if environment is not None else {}
        self.save_path = Path(save_path) if save_path is not None else None
        self._cancel_requested = threading.Event()

    @property
    @abstractmethod
    def model_list(self) -> list[str]:
        """Return the list of model identifiers supported by this provider adapter.

        Returns:
            list[str]: Supported model names.
        """
        raise NotImplementedError

    def get_env(
        self,
        name: str,
        default: str | None = None,
        *,
        required: bool = False,
    ) -> str | None:
        """Read an environment variable from the session environment (falling back to ``os.environ``).

        Args:
            name: Environment variable name (e.g., ``"OPENROUTER_API_KEY"``).
            default: Fallback value returned when the variable is unset or empty.
            required: If ``True``, raise a ``ValueError`` when no non-empty value is found.

        Returns:
            str | None: Resolved environment variable value, or ``default``.
        """
        value = self.environment.get(name, os.environ.get(name, default))
        if required and value is None:
            raise KeyError(name)
        return value

    def proxy_url(self, url: str | None = None) -> str | None:
        """Resolve the outbound HTTP/SOCKS proxy URL for ``url``, honoring ``NO_PROXY`` exclusions.

        Args:
            url: Target request URL used to check ``NO_PROXY`` rules, or ``None``.

        Returns:
            str | None: Effective proxy URL, or ``None`` when direct connection should be used.
        """
        if url and should_bypass_proxies(
            url, no_proxy=self.get_env("NO_PROXY") or self.get_env("no_proxy")
        ):
            return None
        return (
            self.get_env("HTTPS_PROXY")
            or self.get_env("https_proxy")
            or self.get_env("HTTP_PROXY")
            or self.get_env("http_proxy")
        )

    def report_progress(
        self,
        callback: ProgressCallback | None,
        update: dict[str, Any],
    ) -> None:
        """Invoke the caller's progress callback with a live streaming or status update.

        Args:
            callback: Optional progress callback supplied by the caller.
            update: Progress event dictionary to pass to ``callback``.
        """
        if callback is not None:
            callback(update)

    def raise_if_cancelled(self) -> None:
        """Raise :class:`~sr_harness.core.ToolRunAbort` immediately if cancellation has been requested."""
        if self._cancel_requested.is_set():
            raise InterruptedError("Model API request was cancelled")

    def wait_before_retry(self, delay: float) -> None:
        """Sleep for ``delay`` seconds before retrying a failed request while remaining immediately cancellable.

        Args:
            delay: Backoff duration in seconds.
        """
        if self._cancel_requested.wait(delay):
            raise InterruptedError("Model API request was cancelled")

    def _request_samples(
        self,
        messages: list[dict[str, Any]],
        n: int = 1,
        callback: ProgressCallback | None = None,
        **kwargs: Any,
    ) -> Generator[APICallSample, None, dict[str, Any]]:
        """Request ``n`` samples, using one independent request per sample by default."""
        attempts = 3
        results: list[ProviderSampleResult] = []
        description = f"{type(self).__name__}({self.model})"
        for sample_index in range(1, n + 1):
            for attempt in range(1, attempts + 1):
                try:
                    self.raise_if_cancelled()
                    sample_result = self._request_sample(
                        messages,
                        sample_index=sample_index,
                        callback=callback,
                        **kwargs,
                    )
                    self.raise_if_cancelled()
                    break
                except InterruptedError:
                    raise
                except Exception as error:
                    self.raise_if_cancelled()
                    public_error = self.error_message(error, description=description)
                    if attempt == attempts:
                        self.report_progress(callback, {
                            "type": "failed",
                            "sample": sample_index,
                            "error": public_error,
                        })
                        result = self.aggregate_sample_results(results)
                        result["ok"] = False
                        result["error"] = public_error
                        return result
                    self.report_progress(callback, {
                        "type": "retry",
                        "sample": sample_index,
                        "attempt": attempt,
                        "error": public_error,
                    })
                    delay = self.retry_delay(error, attempt)
                    _logger.info(
                        f"Retrying {description} in {delay:g}s "
                        f"(attempt {attempt}/{attempts})."
                    )
                    self.wait_before_retry(delay)
            if not isinstance(sample_result, ProviderSampleResult):
                raise TypeError(
                    "_request_sample() must return ProviderSampleResult, "
                    f"not {type(sample_result).__name__}"
                )
            results.append(sample_result)
            yield sample_result.response
            if sample_result.error:
                self.report_progress(callback, {
                    "type": "truncated" if sample_result.response.truncated else "failed",
                    "finish_reason": sample_result.response.finish_reason,
                    "sample": sample_index,
                    "error": sample_result.error,
                })
                return self.aggregate_sample_results(results)
        return self.aggregate_sample_results(results)

    def _request_sample(
        self,
        messages: list[dict[str, Any]],
        *,
        sample_index: int,
        callback: ProgressCallback | None = None,
        **kwargs: Any,
    ) -> ProviderSampleResult:
        """Perform one request attempt; only ``_request_samples`` should call this hook."""
        raise NotImplementedError(
            f"{type(self).__name__} must either implement _request_sample() or reimplement _request_samples()"
        )

    def error_message(self, error: BaseException, *, description: str | None = None) -> str:
        """Log a provider exception and return a sanitized error message safe for the frontend.

        Args:
            error: Exception raised during the provider request.
            description: Optional human-readable context describing the failed operation.

        Returns:
            str: Sanitized error message with sensitive tokens redacted.
        """
        label = description or f"{type(self).__name__}({self.model})"
        formatted_error = "".join(traceback.format_exception(error)).rstrip()
        _logger.error(f"Error requesting {label}:\n{formatted_error}")
        message, findings = screen_frontend_error(error, self.environment)
        if findings:
            _logger.warning(
                f"Withheld {label} error details from the frontend after detecting: "
                f"{', '.join(findings)}"
            )
        return message

    @staticmethod
    def retry_delay(error: Exception, attempt: int) -> float:
        """Compute the retry backoff delay from a ``Retry-After`` header or exponential backoff.

        Args:
            error: Exception raised by the HTTP/SDK client.
            attempt: Zero-based retry attempt index.

        Returns:
            float: Delay in seconds before the next retry attempt.
        """
        headers = getattr(getattr(error, "response", None), "headers", None) or {}
        retry_after = headers.get("retry-after") or headers.get("Retry-After")
        if retry_after is None:
            body = getattr(error, "body", None)
            if isinstance(body, dict):
                error_body = body.get("error", body)
                metadata = error_body.get("metadata", {}) if isinstance(error_body, dict) else {}
                retry_headers = metadata.get("headers", {}) if isinstance(metadata, dict) else {}
                retry_after = retry_headers.get("Retry-After") or retry_headers.get("retry-after")
        try:
            return max(1.0, min(float(retry_after), 300.0))
        except (TypeError, ValueError):
            return min(float(2 ** (attempt - 1)), 30.0)

    def openai_chat_completion(
        self,
        client: Any,
        payload: dict[str, Any],
        *,
        sample: int,
        callback: ProgressCallback | None = None,
    ) -> tuple[Any, dict[str, Any], dict[str, Any], str]:
        """Execute one OpenAI-compatible chat completion (streaming when a callback is provided) and normalize the output.

        Args:
            client: OpenAI-compatible SDK client instance.
            payload: Request keyword arguments passed to ``client.chat.completions.create``.
            sample: Zero-based sample index within the current batch.
            callback: Optional callback receiving live streaming deltas.

        Returns:
            tuple[Any, dict[str, Any], dict[str, Any], str]: Tuple of
                ``(completion_object, assistant_message_dict, usage_dict, finish_reason)``.
        """
        if callback is not None:
            return self.stream_openai_chat_completion(
                client,
                payload,
                sample=sample,
                callback=callback,
            )
        completion = client.chat.completions.create(**payload)
        response = completion.to_dict()
        message_object = completion.choices[0].message
        message = (
            message_object.to_dict() if hasattr(message_object, "to_dict") else dict(message_object)
        )
        return completion, response, message, message.get("content") or ""

    def _cancellable_stream(self, client: Any, payload: dict[str, Any]):
        """Keep cancellation responsive even while the provider has stopped sending.

        The reader owns the SDK iterator. A bounded queue prevents it from racing
        ahead; abandoning a request cannot publish into a subsequent request.
        Network reads also have the provider adapter's finite idle timeout.
        """
        updates: queue.Queue = queue.Queue(maxsize=8)
        abandoned = threading.Event()

        def publish(kind, value):
            while not abandoned.is_set():
                try:
                    updates.put((kind, value), timeout=0.05)
                    return
                except queue.Full:
                    pass

        def read():
            stream = None
            try:
                stream = client.chat.completions.create(**payload)
                for chunk in stream:
                    if abandoned.is_set():
                        break
                    publish("chunk", chunk)
                publish("done", None)
            except Exception as exc:
                publish("error", exc)
            finally:
                if stream is not None and callable(close := getattr(stream, "close", None)):
                    try:
                        close()
                    except Exception:
                        _logger.debug("Stream cleanup failed", exc_info=True)

        reader = threading.Thread(target=read, name="srh-model-stream", daemon=True)
        self.raise_if_cancelled()
        reader.start()
        last_chunk_at = time.monotonic()
        try:
            while True:
                self.raise_if_cancelled()
                try:
                    kind, value = updates.get(timeout=0.05)
                except queue.Empty:
                    if time.monotonic() - last_chunk_at >= self.STREAM_IDLE_TIMEOUT_SECONDS:
                        raise TimeoutError("Model stream stopped responding for the idle timeout")
                    continue
                self.raise_if_cancelled()
                last_chunk_at = time.monotonic()
                if kind == "error":
                    raise value
                if kind == "done":
                    return
                yield value
        finally:
            abandoned.set()
            # Close the transport away from the UI/control thread. Some SDKs
            # block while closing a read; their configured timeout bounds it.
            if callable(close := getattr(client, "close", None)):
                threading.Thread(target=close, name="srh-close-stream", daemon=True).start()

    def stream_openai_chat_completion(
        self,
        client: Any,
        payload: dict[str, Any],
        *,
        sample: int,
        callback: ProgressCallback,
    ) -> tuple[Any, dict[str, Any], dict[str, Any], str]:
        """Consume an OpenAI-compatible SSE stream, publishing incremental reasoning/content deltas and assembling the final message.

        Args:
            client: OpenAI-compatible SDK client instance.
            payload: Request keyword arguments passed to ``client.chat.completions.create``.
            sample: Zero-based sample index within the current batch.
            callback: Callback invoked for each incremental stream delta.

        Returns:
            tuple[Any, dict[str, Any], dict[str, Any], str]: Tuple of
                ``(synthetic_completion, assistant_message_dict, usage_dict, finish_reason)``.
        """
        stream_payload = {
            **payload,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        stream = self._cancellable_stream(client, stream_payload)
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        reasoning_details: list[Any] = []
        raw_chunks: list[dict[str, Any]] = []
        raw_tool_calls: dict[int, dict[str, Any]] = {}
        usage = None
        finish_reason = None
        self.report_progress(callback, {"type": "start", "sample": sample})
        for chunk in stream:
            self.raise_if_cancelled()
            chunk_dict = chunk.to_dict() if hasattr(chunk, "to_dict") else {}
            raw_chunks.append(chunk_dict)
            if getattr(chunk, "usage", None) is not None:
                usage = chunk.usage
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            choice = choices[0]
            if getattr(choice, "finish_reason", None) is not None:
                finish_reason = choice.finish_reason
            delta = choice.delta
            if text := getattr(delta, "content", None):
                content_parts.append(text)
            reasoning_delta = (
                getattr(delta, "reasoning", None) or getattr(delta, "reasoning_content", None) or ""
            )
            new_details = getattr(delta, "reasoning_details", None) or []
            if new_details:
                normalized_details = [
                    item.to_dict() if hasattr(item, "to_dict") else item for item in new_details
                ]
                reasoning_details.extend(normalized_details)
                if not reasoning_delta:
                    reasoning_delta = "".join(
                        (item.get("text") or "") if isinstance(item, dict) else ""
                        for item in normalized_details
                    )
            if reasoning_delta:
                reasoning_parts.append(reasoning_delta)
            for tool_delta in getattr(delta, "tool_calls", None) or []:
                index = int(getattr(tool_delta, "index", 0) or 0)
                current = raw_tool_calls.setdefault(
                    index,
                    {
                        "id": None,
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    },
                )
                if getattr(tool_delta, "id", None):
                    current["id"] = tool_delta.id
                function = getattr(tool_delta, "function", None)
                if function is not None:
                    if getattr(function, "name", None):
                        current["function"]["name"] += function.name
                    if getattr(function, "arguments", None):
                        current["function"]["arguments"] += function.arguments
            self.report_progress(callback, {
                "type": "delta",
                "sample": sample,
                "content": "".join(content_parts),
                "reasoning": "".join(reasoning_parts),
                "tool_calls": [raw_tool_calls[key] for key in sorted(raw_tool_calls)],
            })
        content = "".join(content_parts)
        reasoning = "".join(reasoning_parts)
        message: dict[str, Any] = {"role": "assistant", "content": content}
        if reasoning:
            message["reasoning"] = reasoning
        if reasoning_details:
            message["reasoning_details"] = reasoning_details
        if raw_tool_calls:
            message["tool_calls"] = [raw_tool_calls[key] for key in sorted(raw_tool_calls)]
        self.report_progress(callback, {
            "type": "complete",
            "sample": sample,
            "content": content,
            "reasoning": reasoning,
            "tool_calls": message.get("tool_calls", []),
            "finish_reason": finish_reason,
        })
        completion = type("StreamCompletion", (), {"usage": usage})()
        return completion, {"chunks": raw_chunks, "finish_reason": finish_reason}, message, content

    def parse_tool_calls(self, message: dict[str, Any], content: str) -> list[ToolCall]:
        """Extract normalized :class:`~sr_harness.core.ToolCall` objects from an assistant message.

        Args:
            message: Raw provider assistant message dictionary.
            content: Assistant text content.

        Returns:
            list[ToolCall]: Parsed tool calls (empty list when no tools were called).
        """
        if self.tool_box is None:
            return []
        if not self.tool_box.native_tool_calls:
            return self.tool_box.parse_response(content)
        return self.tool_box.parse_response(message.get("tool_calls") or [])

    @staticmethod
    def openai_token_usage(completion: Any, *, other_key: str = "others") -> dict[str, int]:
        """Extract prompt, completion, reasoning, and cached token counts from an OpenAI-style completion object.

        Args:
            completion: OpenAI-compatible completion response object.
            other_key: Key name used to store cached/extra tokens (defaults to ``"others"``).

        Returns:
            dict[str, int]: Token usage breakdown dictionary.
        """
        usage = getattr(completion, "usage", None)
        if usage is None:
            return {}
        prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
        answer = int(getattr(usage, "completion_tokens", 0) or 0)
        result = {"prompt": prompt, "answer": answer}
        total = int(getattr(usage, "total_tokens", prompt + answer) or 0)
        if (other := total - prompt - answer) > 0:
            result[other_key] = other
        return result

    @staticmethod
    def aggregate_sample_results(results: list[ProviderSampleResult]) -> dict[str, Any]:
        """Combine per-sample token counts, costs, and error messages into a batch summary dictionary.

        Args:
            results: List of :class:`ProviderSampleResult` objects from one batch call.

        Returns:
            dict[str, Any]: Aggregated ``ok``, ``error``, ``token_usage``, ``money_usage``,
                and ``extra`` metadata.
        """
        token_usage: dict[str, int | float] = {}
        money_usage: dict[str, int | float] = {}
        for result in results:
            for key, value in result.token_usage.items():
                token_usage[key] = token_usage.get(key, 0) + value
            for key, value in result.money_usage.items():
                money_usage[key] = money_usage.get(key, 0) + value
        error = next((result.error for result in results if result.error), None)
        return {
            "ok": error is None,
            "error": error,
            "token_usage": token_usage,
            "money_usage": money_usage,
            "extra": {
                "responses": [
                    result.raw_response for result in results if result.raw_response is not None
                ],
            },
        }

    @staticmethod
    def _build_response(
        message: dict[str, Any],
        tool_calls: list[ToolCall],
        content: str | None = None,
    ) -> APICallSample:
        """Build a response while retaining enough fields to reconstruct ``message``."""
        message_extra = dict(message)
        message_content = message_extra.pop("content", content)
        raw_tool_calls = message_extra.get("tool_calls")
        normalized_raw_tool_calls = [call.raw for call in tool_calls if isinstance(call.raw, dict)]
        if raw_tool_calls == normalized_raw_tool_calls and raw_tool_calls != []:
            message_extra.pop("tool_calls")
        return APICallSample(
            content=message_content,
            tool_calls=tool_calls,
            message_extra=message_extra,
        )

    @abstractmethod
    def format_response(
        self,
        message: Any,
        tool_calls: list[ToolCall],
        content: str | None = None,
    ) -> APICallSample:
        """Convert a provider message and parsed tool calls into a normalized :class:`~sr_harness.core.APICallSample`.

        Args:
            message: Raw provider message object or dictionary.
            tool_calls: Normalized tool calls extracted from the message.
            content: Optional explicit text content override.

        Returns:
            APICallSample: Normalized response sample.
        """
        raise NotImplementedError

    def __call__(
        self,
        messages: list[dict[str, Any]] | str,
        callback: ProgressCallback | None = None,
        **kwargs: Any,
    ) -> APICallSummary:
        """Send conversation messages to the model provider and return an iterable :class:`~sr_harness.core.APICallSummary`.

        Args:
            messages: Conversation message list or a single user prompt string.
            callback: Optional callback for live streaming progress updates.
            **kwargs: Additional sampling parameters such as ``n``, ``max_tokens``,
                ``temperature``, and ``top_p``.

        Returns:
            APICallSummary: Iterable summary yielding :class:`~sr_harness.core.APICallSample`
                objects and capturing total token/cost usage.
        """
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        if callback is not None:
            kwargs["callback"] = callback
        if not isinstance(n := kwargs.get("n", 1), int) or n < 1:
            raise ValueError("n must be a positive integer")
        generator = self._normalize_request(
            self._request_samples(messages, **kwargs),
            requested_samples=n,
        )
        return APICallSummary(generator)

    def _normalize_request(
        self,
        generator: Generator[APICallSample, None, dict[str, Any]],
        requested_samples: int,
    ) -> Generator[APICallSample, None, dict[str, Any]]:
        """Normalize provider records, capture safe failures, and write call logs."""
        call_id = uuid.uuid4().hex
        completed_samples = 0
        try:
            while True:
                response = next(generator)
                if not isinstance(response, APICallSample):
                    raise TypeError(
                        "Provider generators must yield APICallSample instances, "
                        f"not {type(response).__name__}"
                    )
                if completed_samples >= requested_samples:
                    raise ValueError(
                        f"Provider yielded more than the requested n={requested_samples} samples"
                    )
                completed_samples += 1
                self._write_call_log(
                    call_id,
                    "response",
                    {
                        "sample": completed_samples,
                        "response": response.message,
                    },
                )
                yield response
        except StopIteration as stop:
            result = stop.value
            if not isinstance(result, dict):
                raise TypeError("Provider must return an API result dictionary")
            required = {"ok", "error", "token_usage", "money_usage", "extra"}
            if missing := sorted(required - result.keys()):
                raise ValueError(
                    "Provider API result is missing required fields: " + ", ".join(missing)
                )
            if unexpected := sorted(result.keys() - required):
                raise ValueError(
                    "Provider API result has unsupported fields; put them in extra: "
                    + ", ".join(unexpected)
                )
            if not isinstance(result["ok"], bool):
                raise TypeError("Provider API result field 'ok' must be bool")
            if result["error"] is not None and not isinstance(result["error"], str):
                raise TypeError("Provider API result field 'error' must be str or None")
            if result["ok"] != (result["error"] is None):
                raise ValueError("Provider API result fields 'ok' and 'error' are inconsistent")
            for field in ("token_usage", "money_usage", "extra"):
                if not isinstance(result[field], dict):
                    raise TypeError(f"Provider API result field {field!r} must be dict")
            if completed_samples < requested_samples and result["error"] is None:
                raise ValueError(
                    f"Provider returned {completed_samples} of {requested_samples} "
                    "requested responses without reporting an error"
                )
            result["extra"].update(
                {
                    "requested_samples": requested_samples,
                    "completed_samples": completed_samples,
                }
            )
            self._write_call_log(call_id, "result", result)
            return result
        finally:
            self._cancel_requested.clear()

    def _write_call_log(
        self,
        call_id: str,
        record_type: str,
        payload: dict[str, Any],
    ) -> None:
        """Append one final-response or result record when API logging is enabled."""
        if self.save_path is None:
            return
        path = (
            self.save_path
            if self.save_path.suffix == ".jsonl"
            else self.save_path / "api_calls.jsonl"
        )
        record = {
            "type": record_type,
            "call_id": call_id,
            "timestamp": time.time(),
            "provider": type(self).__name__,
            "model": self.model,
            **payload,
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with _api_log_lock, path.open("a", encoding="utf-8") as stream:
                json.dump(record, stream, ensure_ascii=False, default=str)
                stream.write("\n")
        except OSError as error:
            _logger.warning(f"Unable to append API call log {path}: {error}")

    def cancel(self) -> str | None:
        """Signal active provider requests to abort at the next cancellation boundary and close active streams.

        Returns:
            str | None: Optional diagnostic note if the underlying SDK cannot be preempted mid-request.
        """
        self._cancel_requested.set()
        return None
