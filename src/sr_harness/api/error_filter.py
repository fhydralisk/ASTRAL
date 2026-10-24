"""Temporary, weakly coupled screening for errors shown to frontend users."""

from __future__ import annotations

import os
from collections.abc import Mapping


_PRIVATE_PATH_MARKERS = ("yuzihan",)
_WITHHELD_MESSAGE = (
    "The model API request failed. Its detailed error was written to the server log "
    "because it may contain sensitive information."
)


def screen_frontend_error(
    error: BaseException,
    environment: Mapping[str, str] | None = None,
) -> tuple[str, tuple[str, ...]]:
    """Redact sensitive API keys or credentials from an exception message before displaying it in the UI.

    Args:
        error: Exception raised during a provider or runtime operation.
        environment: Optional session environment containing API keys to scrub.

    Returns:
        tuple[str, tuple[str, ...]]: Pair of ``(sanitized_message, matched_markers)``.
    """
    message = str(error).strip() or type(error).__name__
    findings: list[str] = []
    chain: list[BaseException] = []
    current: BaseException | None = error
    while current is not None and current not in chain:
        chain.append(current)
        current = current.__cause__ or current.__context__
    inspected = "\n".join(str(item) for item in chain)
    lowered = inspected.casefold()
    if any(marker.casefold() in lowered for marker in _PRIVATE_PATH_MARKERS):
        findings.append("private-path marker")

    values = dict(os.environ)
    if environment is not None:
        values.update(environment)
    for name, value in values.items():
        if not name.upper().endswith("API_KEY") or len(value) < 16:
            continue
        if value[-3:] in inspected:
            findings.append(f"{name} suffix")

    return (_WITHHELD_MESSAGE if findings else message), tuple(sorted(set(findings)))
