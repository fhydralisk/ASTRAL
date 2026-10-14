"""Explicit request to stop an interactive symbolic-regression search."""
from __future__ import annotations

from .base_tool import BaseTool
from ..core import ToolMetadata


@BaseTool.register("finish_search")
class FinishSearchTool(BaseTool):
    """Ask the harness to stop after its configured completion checks pass."""

    metadata = ToolMetadata(
        name="finish_search",
        description=(
            "Request that the current symbolic-regression search stop. The harness "
            "checks its configured stopping policy and returns either a stopped status "
            "or a reason why the search must continue."
        ),
        parameters={
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "A concise explanation of why the search is ready to stop.",
                },
            },
            "required": ["reason"],
            "additionalProperties": False,
        },
    )

    def execute(self, reason: str) -> dict[str, str]:
        """Return a request marker for the interactive agent to resolve.

        Args:
            reason: Why the model considers the search complete.

        Returns:
            A marker replaced by the interactive Agent with the stop-check result.
        """
        return {"status": "requested", "reason": reason}

    @classmethod
    def format_result_dict(cls, result: dict[str, str]) -> str:
        """Format the resolved stop status for the model."""
        status = result.get("status")
        if status == "stopped":
            return "Search stopped. The run will pause at the next safe boundary."
        if status == "rejected":
            return f"Search cannot stop yet: {result.get('reason', 'completion check failed')}"
        return "Search stop requested."
