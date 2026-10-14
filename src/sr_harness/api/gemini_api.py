# Copyright (c) 2024-present, Yumeow. Licensed under the MIT License.
import httpx
from typing import Any, Generator, List, Dict
from google import genai
from google.genai import types
from .base_api import BaseAPI
from ..core import APICallSample, ToolCall


@BaseAPI.register("gemini")
class GeminiAPI(BaseAPI):
    """Google Gemini adapter for the explicitly listed SDK workflows."""

    def __init__(self, model: str = "gemini-2.5-pro", **kwargs: Any) -> None:
        super().__init__(model=model, **kwargs)

    def cancel(self) -> str:
        """Report that the current synchronous SDK request cannot be preempted."""
        return (
            "GeminiAPI does not support force-interrupting an active non-streaming request. "
            "The Agent will pause at its next safe boundary."
        )

    def format_response(
        self, message: dict[str, Any], tool_calls: list[ToolCall], content: str | None = None
    ) -> APICallSample:
        """Convert one Gemini message into one API-call sample."""
        return self._build_response(message, tool_calls, content)

    @property
    def model_list(self) -> list[str]:
        """Return the Gemini models explicitly supported by this adapter."""
        return [
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite-preview-06-17",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
        ]

    def _request_samples(
        self, messages: List[Dict[str, str]], n=1, callback=None
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
                    tool_call = self.parse_tool_calls(message, content)
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
