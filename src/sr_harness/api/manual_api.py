# Copyright (c) 2024-present, Yumeow. Licensed under the MIT License.
import logging
import tempfile
from pathlib import Path
from typing import Any, Generator, List, Dict
from .base_api import BaseAPI
from ..core import APICallSample, ToolCall

_logger = logging.getLogger(f"sr_harness.{__name__}")


@BaseAPI.register("manual")
class ManualAPI(BaseAPI):
    """Interactive terminal adapter that prints prompts to stdout and reads human-typed responses from stdin."""

    def __init__(self, model="manual", save_path=None, **kwargs):
        """Initialize the manual terminal provider adapter.

        Args:
            model: Placeholder model name (defaults to ``"manual"``).
            save_path: Optional directory path for saving transcripts.
            **kwargs: Additional arguments forwarded to :class:`BaseAPI`.
        """
        super().__init__(model=model, **kwargs)
        self.save_path = Path(save_path or tempfile.gettempdir())

    def cancel(self) -> str:
        """Report that interactive stdin reads in the terminal cannot be preempted remotely from the WebUI.

        Returns:
            str: Notice explaining that terminal input must complete first.
        """
        return (
            "ManualAPI does not support force-interrupting terminal input. "
            "The Agent will pause at its next safe boundary."
        )

    def format_response(
        self, message: dict[str, Any], tool_calls: list[ToolCall], content: str | None = None
    ) -> APICallSample:
        """Wrap manually entered terminal text and parsed tool calls into an :class:`~sr_harness.core.APICallSample`.

        Args:
            message: Dictionary containing the manually entered response content.
            tool_calls: Tool calls parsed from the manual text.
            content: Optional explicit text content override.

        Returns:
            APICallSample: Normalized response sample.
        """
        return self._build_response(message, tool_calls, content)

    @property
    def model_list(self) -> list[str]:
        """Return the synthetic ``["manual"]`` model list for the terminal provider.

        Returns:
            list[str]: ``["manual"]``.
        """
        return ["manual"]

    def _request_samples(
        self, messages: List[Dict[str, str]], n=1, callback=None, max_tokens=None
    ) -> Generator[APICallSample, None, dict[str, Any]]:
        import pyperclip, tiktoken

        prompt = "\n---\n".join(f"[role: {msg['role']}] {msg['content']}" for msg in messages)

        # Copy the prompt to clipboard and save it to a file for manual input
        pyperclip.copy(prompt)
        prompt_path = self.save_path / "prompt.md"
        prompt_path.write_text(prompt, encoding="utf-8")
        _logger.note(
            f"Prompt copied to clipboard and saved to {prompt_path}. "
            f"Please send it into any LLM and return the response content for {n} times."
        )
        details = []
        for idx in range(1, n + 1):
            self.report_progress(callback, {"type": "start", "sample": idx})
            # Wait for user input or clipboard content
            content = input(
                f"Please enter the generated content {idx}/{n} (press Enter to use clipboard): "
            )
            if not content.strip():
                content = pyperclip.paste()
            # Calculate token usage
            encoding = tiktoken.encoding_for_model("gpt-3.5")
            prompt_tokens = len(encoding.encode(prompt))
            answer_tokens = len(encoding.encode(content))
            token_usage = {"prompt": prompt_tokens, "answer": answer_tokens}
            tool_call = self.parse_tool_calls({"role": "assistant", "content": content}, content)
            message = {"role": "assistant", "content": content}
            details.append(
                {
                    "content": content,
                    "tool_call": tool_call,
                    "token_usage": token_usage,
                    "message": message,
                }
            )
            sample_response = self.format_response(message, tool_call, content)
            if callback is not None:
                self.report_progress(callback, {
                    "type": "complete",
                    "sample": idx,
                    "content": sample_response.content,
                    "reasoning": sample_response.reasoning,
                    "tool_calls": [call.raw for call in sample_response.tool_calls],
                })
            yield sample_response
        token_usage = {"prompt": 0, "answer": 0}
        for detail in details:
            token_usage["prompt"] += detail["token_usage"]["prompt"]
            token_usage["answer"] += detail["token_usage"]["answer"]
        return {
            "ok": True,
            "error": None,
            "token_usage": token_usage,
            "money_usage": {"prompt": 0, "answer": 0},
            "extra": {},
        }
