# Copyright (c) 2026-present, Yumeow. Licensed under the MIT License.
"""工具测试包。"""

from typing import Any

import numpy as np

from sr_harness.core import AgentContext


def tool_context(
    *,
    data: dict[str, Any],
    target: str,
    evaluation_data: dict[str, Any] | None = None,
) -> AgentContext:
    """Build an explicit context for standalone tool tests."""
    context = AgentContext(data=data, target=target)
    if evaluation_data is not None:
        context._split_cache = {
            "train": context.with_data(context.data),
            "validation": context.with_data(
                {name: np.asarray(value) for name, value in evaluation_data.items()}
            ),
        }
    return context
