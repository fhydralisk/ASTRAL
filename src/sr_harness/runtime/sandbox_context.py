"""Serialize the deliberately limited context exposed to untrusted code."""

from __future__ import annotations

import argparse
from typing import Any


_UNSUPPORTED = object()
_ALLOWED_ARGUMENTS = {
    "larger_is_better",
    "ranking_metric",
    "split_by",
    "split_ood_variable",
    "split_random_state",
    "validation_fraction",
}


def _json_value(value: Any) -> Any:
    """Convert a harmless argument value to JSON or mark it unsupported."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        converted = [_json_value(item) for item in value]
        return converted if all(item is not _UNSUPPORTED for item in converted) else _UNSUPPORTED
    if isinstance(value, dict):
        converted = {str(key): _json_value(item) for key, item in value.items()}
        if all(item is not _UNSUPPORTED for item in converted.values()):
            return converted
    return _UNSUPPORTED


def sandbox_arguments(args: argparse.Namespace) -> dict[str, Any]:
    """Extract the allowlisted subset of ``AgentContext.args`` safe to expose to sandboxed code.

    Provider API keys, proxy settings, model configurations, callbacks, and
    session internals are excluded so untrusted custom tools and evaluators
    receive only data-splitting and scoring parameters.

    Args:
        args: Full runtime configuration namespace from ``AgentContext.args``.

    Returns:
        dict[str, Any]: Sanitized dictionary of allowlisted evaluation arguments.
    """
    result: dict[str, Any] = {}
    for name in _ALLOWED_ARGUMENTS:
        if not hasattr(args, name):
            continue
        value = getattr(args, name)
        converted = _json_value(value)
        if converted is not _UNSUPPORTED:
            result[name] = converted
    return result
