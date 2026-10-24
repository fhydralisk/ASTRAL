"""Load user-authored evaluator implementations."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from .default_evaluator import DefaultEvaluator
from .sandboxed_evaluator import create_sandboxed_evaluator

if TYPE_CHECKING:
    from ..runtime.workspace import Workspace

CUSTOM_TEMPLATE = (
    '"""Custom evaluator."""\n'
    "from .default_evaluator import DefaultEvaluator\n\n\n"
    "class CustomEvaluator(DefaultEvaluator):\n"
    "    pass\n"
)


def evaluator_filename(class_name: str) -> str:
    """Convert an evaluator class name to a snake-case Python filename.

    Args:
        class_name: Evaluator class name.

    Returns:
        Filename ending in ``.py``.
    """
    stem = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", class_name)
    stem = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", stem).lower()
    return f"{stem}.py"


def load_custom_evaluator(
    source: str | None = None,
    file: Path | None = None,
    *,
    workspace: Workspace | None = None,
) -> DefaultEvaluator:
    """Load exactly one evaluator subclass as a virtual package module.

    Args:
        source: Python source defining one ``DefaultEvaluator`` subclass.
        file: Optional source file. Its contents are used when ``source`` is
            omitted and its path is retained for provenance.
        workspace: Workspace enforcing safe reads, when available.

    Returns:
        An instantiated custom evaluator with ``CUSTOM_EVALUATOR`` provenance.

    Raises:
        ValueError: If the source is unsafe, invalid, or does not define exactly
            one loadable evaluator subclass.
    """
    origin = Path(file).expanduser() if file is not None else None
    if source is None:
        if origin is None:
            raise ValueError("source or file must be provided")
        try:
            opener = workspace.safe_open if workspace is not None else open
            with opener(origin, "r", encoding="utf-8") as f:
                source = f.read()
        except OSError as exc:
            raise ValueError(f"Could not read custom evaluator: {exc}") from exc
    if not isinstance(source, str) or not source.strip():
        raise ValueError("Custom evaluator source must not be empty")
    if len(source) > 50_000:
        raise ValueError("Custom evaluator source exceeds 50000 characters")
    try:
        return create_sandboxed_evaluator(source, origin)
    except Exception as exc:
        if "SyntaxError:" in str(exc):
            raise ValueError(f"Invalid evaluator syntax: {exc}") from exc
        raise ValueError(f"Could not load custom evaluator: {exc}") from exc
