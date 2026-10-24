"""Resolve expression inputs from value mappings or context objects."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def resolve_context(
    context: Mapping[str, Any] | Any | None,
    target: Any = None,
    num_nodes: int | None = None,
) -> tuple[Mapping[str, Any], Any, int | None]:
    """Extract the variable dictionary, target values, and node count from a mapping or ``AgentContext``.

    Args:
        context: Variable mapping ``{name: array}`` or an ``AgentContext`` object exposing ``.data``.
        target: Optional explicit target variable name or target array.
        num_nodes: Optional explicit node count for graph/hypergraph expressions.

    Returns:
        tuple[Mapping[str, Any], Any, int | None]: Tuple of
            ``(variable_mapping, resolved_target_array, resolved_num_nodes)``.
    """
    if context is None:
        values: Mapping[str, Any] = {}
    elif isinstance(context, Mapping):
        values = context
    else:
        candidate = getattr(context, "data", None)
        if not isinstance(candidate, Mapping):
            raise TypeError("context must expose mapping-valued data")
        values = candidate

    if num_nodes is None:
        num_nodes = getattr(context, "num_nodes", None)

    if target is None:
        target = getattr(context, "target", None)
    if isinstance(target, str) and target in values:
        target = values[target]
    return values, target, num_nodes
