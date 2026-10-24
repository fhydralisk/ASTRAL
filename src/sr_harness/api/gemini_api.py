# Copyright (c) 2024-present, Yumeow. Licensed under the MIT License.
import httpx
from typing import Any, Generator, List, Dict
from google import genai
from google.genai import types
from .base_api import BaseAPI
from ..core import APICallSample, ToolCall


@BaseAPI.register("gemini")
class GeminiAPI(BaseAPI):
    """LLM provider adapter for Google Gemini models via the ``google-genai`` SDK."""

    def __init__(self, model: str = "gemini-2.5-pro", **kwargs: Any) -> None:
        """Initialize the Google Gemini API adapter.

        Args:
            model: Gemini model identifier (defaults to ``"gemini-2.5-pro"``).
            **kwargs: Additional arguments forwarded to :class:`BaseAPI`.
        """
        super().__init__(model=model, **kwargs)

    def cancel(self) -> str:
        """Request cancellation and note that synchronous Gemini SDK calls pause after the in-flight HTTP request returns.

        Returns:
            str: Human-readable notice explaining when the cancellation will take effect.
        """
        return (
            "GeminiAPI does not support force-interrupting an active non-streaming request. "
            "The Agent will pause at its next safe boundary."
        )

    def format_response(
        self, message: dict[str, Any], tool_calls: list[ToolCall], content: str | None = None
    ) -> APICallSample:
        """Convert a Gemini response dictionary into a normalized :class:`~sr_harness.core.APICallSample`.

        Args:
            message: Normalized Gemini message dictionary.
            tool_calls: Parsed tool calls from the response.
            content: Optional explicit text content override.

        Returns:
            APICallSample: Normalized assistant response sample.
        """
        return self._build_response(message, tool_calls, content)

    @property
    def model_list(self) -> list[str]:
        """Return the list of Google Gemini model identifiers supported by this adapter.

        Returns:
            list[str]: Supported Gemini model names.
        """
        return [
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite-preview-06-17",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
        ]

    def _request_samples(
        self, messages: List[Dict[str, str]], n=1, callback=None, max_tokens=None
    ) -> Generator[APICallSample, None, dict[str, Any]]:
        ## Ensure this is a generator
        yield from []
        messages = [dict(message) for message in messages]
        if self.tool_box is None:
            pass
        elif not self.tool_box.native_tool_calls:
            description = (
                "Use the following tools when a tool call is needed. "
                "Return tool calls in the specified format.\n\n"
                f"{self.tool_box.format_tools()}"
            )
            if messages[0]["role"] in {"system", "developer"}:
                first = messages[0]
                messages[0] = {
                    **first,
                    "content": f"{first['content']}\n\n{description}",
                }
            else:
                messages.insert(0, {"role": "system", "content": description})
        else:
            raise NotImplementedError(
                "GeminiAPI does not support parser='openai' native tool calls."
            )
        api_key = self.get_env("GEMINI_API_KEY")
        config = types.GenerateContentConfig(
            candidate_count=n,
            max_output_tokens=max_tokens,
            thinking_config=types.ThinkingConfig(
                thinking_budget=0,
                include_thoughts=True,
            ),
        )
        if self.model in ["gemini-2.0-flash", "gemini-2.0-flash-lite"]:
            config.thinking_config = None
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                httpx_client=httpx.Client(
                    proxy=self.proxy_url(),
                    trust_env=False,
                ),
            ),
        )
        self.report_progress(callback, {"type": "start", "sample": 1})
        try:
            response = client.models.generate_content(
                model=self.model,
                contents=messages,
                config=config,
            )
        except InterruptedError:
            raise
        except Exception as error:
            public_error = self.error_message(error)
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
        usage = response.usage_metadata
        prompt_tokens = usage.prompt_token_count
        reason_tokens = usage.thoughts_token_count or 0
        answer_tokens = usage.total_token_count - prompt_tokens - reason_tokens
        token_usage = {
            "prompt": prompt_tokens,
            "answer": answer_tokens,
            "reason": reason_tokens,
        }
        price_usage = {"total": 0.0}
        details = []
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if not (content := part.text):
                    continue
                elif part.thought:
                    continue
                else:
                    message = {"role": "assistant", "content": content}
                    finish_reason = getattr(candidate.finish_reason, "value", candidate.finish_reason)
                    tool_call = [] if finish_reason == "MAX_TOKENS" else self.parse_tool_calls(message, content)
                    details.append(
                        {
                            "content": content,
                            "tool_call": tool_call,
                            "token_usage": usage,
                            "price_usage": price_usage,
                            "response": candidate.to_json_dict(),
                            "message": message,
                        }
                    )
                    sample_response = self.format_response(message, tool_call, content)
                    sample_response.finish_reason = finish_reason
                    sample = len(details)
                    if callback is not None:
                        self.report_progress(callback, {
                            "type": "complete",
                            "sample": sample,
                            "content": sample_response.content,
                            "reasoning": sample_response.reasoning,
                            "tool_calls": [call.raw for call in sample_response.tool_calls],
                        })
                        if sample < n:
                            self.report_progress(callback, {
                                "type": "start",
                                "sample": sample + 1,
                            })
                    yield sample_response
                    break
        return {
            "ok": True,
            "error": None,
            "token_usage": token_usage,
            "money_usage": price_usage,
            "extra": {"responses": [detail["response"] for detail in details]},
        }
