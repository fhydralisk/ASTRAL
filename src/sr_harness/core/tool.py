# Copyright (c) 2026-present, Yumeow. Licensed under the MIT License.
"""Shared data contracts for tool definitions, calls, and results."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class ToolMetadata:
    """Declarative metadata describing a tool's name, purpose, and JSON parameter schema.

    When ``description`` or ``parameters`` are omitted, :class:`~sr_harness.tools.BaseTool`
    infers them automatically from ``execute()``'s type annotations and Google-style docstring.
    """

    name: str
    description: str | None = None
    parameters: Dict[str, Any] | None = None


@dataclass
class ToolCall:
    """Normalized representation of a single tool invocation requested by a language model.

    Attributes:
        name: Registered name of the tool to invoke.
        params: Dictionary of keyword arguments passed to ``tool.execute(**params)``.
        id: Optional provider-assigned tool-call identifier.
        raw: Optional raw provider tool-call structure.
        raw_str: Optional raw text snippet from which the call was parsed.
    """

    name: str
    params: dict
    id: str | None = None
    raw: Any = None
    raw_str: str | None = None

    def __post_init__(self) -> None:
        """Normalize the former textual raw field into the common raw field."""
        if self.raw is None and self.raw_str is not None:
            self.raw = self.raw_str
        elif self.raw_str is None and isinstance(self.raw, str):
            self.raw_str = self.raw


@dataclass
class ToolCallResult:
    """Standardized outcome returned by ``BaseTool.__call__()``.

    ``result`` preserves the full machine-readable dictionary for run logging and
    candidate extraction, whereas ``result_str`` is a concise, length-bounded text
    summary formatted for the language model's next turn.
    """

    ok: bool
    result: Dict[str, Any]
    result_str: str
    meta_data: Dict[str, Any]

    def get(self, key: str, default: Any = None) -> Any:
        """Look up a key inside the structured ``result`` dictionary when ``result`` is a mapping.

        Args:
            key: Dictionary key to look up in ``self.result``.
            default: Value returned when ``key`` is absent.

        Returns:
            Any: Value associated with ``key``, or ``default``.
        """
        return self.result.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.result[key]
