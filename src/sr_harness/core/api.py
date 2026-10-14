# Copyright (c) 2026-present, Yumeow. Licensed under the MIT License.
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator

from .tool import ToolCall


@dataclass(init=False)
class APICallSample:
    """One complete assistant sample returned by a model provider.

    ``message_extra`` contains provider message fields not represented by the
    normalized content and tool calls.  The :attr:`message`
    property reconstructs a provider-compatible assistant message without
    retaining a duplicate raw message object.
    """

    content: str | None
    _tool_calls: list[ToolCall] = field(default_factory=list, repr=False)
    message_extra: dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        content: str | None,
        tool_calls: list[ToolCall] | None = None,
        message_extra: dict[str, Any] | None = None,
    ) -> None:
        self.content = content
        self._tool_calls = tool_calls if tool_calls is not None else []
        self.message_extra = dict(message_extra or {})

    @property
    def tool_calls(self) -> list[ToolCall]:
        """Return the normalized tool calls used to construct this response."""
        return self._tool_calls

    @property
    def reasoning(self) -> Any:
        """Return provider reasoning without imposing one provider field name."""
        if "reasoning" in self.message_extra:
            return self.message_extra["reasoning"]
        return self.message_extra.get("reasoning_content")

    @property
    def message(self) -> dict[str, Any]:
        """Reconstruct the assistant message represented by this response."""
        message = {**self.message_extra, "content": self.content}
        raw_tool_calls = [call.raw for call in self.tool_calls if isinstance(call.raw, dict)]
        if raw_tool_calls and "tool_calls" not in message:
            message["tool_calls"] = raw_tool_calls
        message.setdefault("role", "assistant")
        return message


@dataclass
class APICallSummary:
    """
    Wrapper for LLM generator that captures the return value.

    Example:
        >>> api = OpenAIAPI(model='gpt-4o-mini')
        >>> result = api("Hello", n=3)  # Returns APICallSummary
        >>> for response in result:
        ...     print(response.content, response.tool_calls)
        >>> print(result.ok, result.error)
        >>> print(result.token_usage, result.money_usage)
    """

    gen: Iterator[APICallSample]
    yielded: list[APICallSample] = field(default_factory=list, init=False)
    ok: bool | None = field(default=None, init=False)
    error: str | None = field(default=None, init=False)
    token_usage: dict[str, float] = field(default_factory=dict, init=False)
    money_usage: dict[str, float] = field(default_factory=dict, init=False)
    extra: dict[str, Any] = field(default_factory=dict, init=False)

    def __iter__(self):
        """Iterate over the generated contents."""
        try:
            while True:
                response = next(self.gen)
                if not isinstance(response, APICallSample):
                    raise TypeError(
                        "API providers must yield APICallSample instances, "
                        f"not {type(response).__name__}"
                    )
                self.yielded.append(response)
                yield response
        except StopIteration as e:
            result = e.value or {}
            self.ok = bool(result.get("ok", True))
            self.error = result.get("error")
            self.token_usage = dict(result.get("token_usage") or {})
            self.money_usage = dict(result.get("money_usage") or {})
            self.extra = dict(result.get("extra") or {})
