# Copyright (c) 2026-present, Yumeow. Licensed under the MIT License.
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator

from .tool import ToolCall


@dataclass(init=False)
class APICallSample:
    """Single assistant completion sample normalized across model providers.

    Stores the assistant text ``content``, parsed ``tool_calls``, completion
    ``finish_reason``, and any provider-specific ``message_extra`` fields (such
    as reasoning traces). Accessing :attr:`message` reconstructs a provider-ready
    assistant message dictionary on demand.
    """

    content: str | None
    finish_reason: str | None
    _tool_calls: list[ToolCall] = field(default_factory=list, repr=False)
    message_extra: dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        content: str | None,
        tool_calls: list[ToolCall] | None = None,
        message_extra: dict[str, Any] | None = None,
        finish_reason: str | None = None,
    ) -> None:
        """Initialize a normalized assistant response sample.

        Args:
            content: Assistant text content, or ``None`` when only tool calls were emitted.
            tool_calls: Normalized tool calls extracted from the response.
            message_extra: Additional provider-specific message fields (e.g., ``reasoning``).
            finish_reason: Provider stop reason (such as ``"stop"``, ``"tool_calls"``, or ``"length"``).
        """
        self.content = content
        self.finish_reason = finish_reason
        self._tool_calls = tool_calls if tool_calls is not None else []
        self.message_extra = dict(message_extra or {})

    @property
    def tool_calls(self) -> list[ToolCall]:
        """Return a copy of the normalized tool calls emitted in this sample.

        Returns:
            list[ToolCall]: Normalized tool call objects.
        """
        return self._tool_calls

    @property
    def reasoning(self) -> Any:
        """Extract the model's reasoning trace across provider-specific field formats.

        Returns:
            Any: Reasoning text or structured reasoning blocks, or ``None`` if absent.
        """
        if self.message_extra.get("reasoning"):
            return self.message_extra["reasoning"]
        if self.message_extra.get("reasoning_content"):
            return self.message_extra["reasoning_content"]
        return "".join(
            item.get("text") or ""
            for item in (self.message_extra.get("reasoning_details") or [])
            if isinstance(item, dict)
        ) or None

    @property
    def truncated(self) -> bool:
        """Return whether generation stopped because it hit the output token limit.

        Returns:
            bool: ``True`` when ``finish_reason`` is ``"length"`` or ``"max_tokens"``.
        """
        return self.finish_reason in {"length", "max_tokens", "max_output_tokens", "MAX_TOKENS"}

    @property
    def message(self) -> dict[str, Any]:
        """Reconstruct a provider-compatible assistant message dictionary for conversation history.

        Returns:
            dict[str, Any]: Assistant message containing ``role``, ``content``,
                provider extras, and serialized ``tool_calls``.
        """
        message = {**self.message_extra, "content": self.content}
        raw_tool_calls = [call.raw for call in self.tool_calls if isinstance(call.raw, dict)]
        if raw_tool_calls and "tool_calls" not in message:
            message["tool_calls"] = raw_tool_calls
        message.setdefault("role", "assistant")
        return message


@dataclass
class APICallSummary:
    """Iterable wrapper over a provider response generator that captures aggregate usage and status.

    Iterating over an :class:`APICallSummary` yields individual
    :class:`APICallSample` instances as they complete, then populates ``ok``,
    ``error``, ``token_usage``, ``money_usage``, and ``extra`` from the
    generator's final return value.
    """

    gen: Iterator[APICallSample]
    yielded: list[APICallSample] = field(default_factory=list, init=False)
    ok: bool | None = field(default=None, init=False)
    error: str | None = field(default=None, init=False)
    token_usage: dict[str, float] = field(default_factory=dict, init=False)
    money_usage: dict[str, float] = field(default_factory=dict, init=False)
    extra: dict[str, Any] = field(default_factory=dict, init=False)

    @property
    def truncated(self) -> bool:
        """Return whether any yielded sample in this call was truncated by the token limit.

        Returns:
            bool: ``True`` if at least one sample has ``truncated == True``.
        """
        return any(sample.truncated for sample in self.yielded)

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
