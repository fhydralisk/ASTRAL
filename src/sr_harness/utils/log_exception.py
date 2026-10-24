# Copyright (c) 2024-present, Yumeow. Licensed under the MIT License.
import traceback
from .tag2ansi import tag2ansi


def log_exception(e: Exception, with_traceback=True) -> str:
    """Format an exception (and optional traceback) as a concise diagnostic string for logging.

    Args:
        e: Exception instance to format.
        with_traceback: Whether to include the formatted traceback lines.

    Returns:
        str: Formatted exception summary.
    """
    return tag2ansi(
        f"[red bold]{type(e).__name__}[reset]: "
        f"[red]{str(e)}[reset]"
        f"\n[gray]{traceback.format_exc() if with_traceback else ''}[reset]"
    )
