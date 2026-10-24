"""Explicit request to stop an interactive symbolic-regression search."""
from __future__ import annotations

from .base_tool import BaseTool
from ..core import ToolMetadata


@BaseTool.register("finish_search")
class FinishSearchTool(BaseTool):
    """Tool for requesting early termination of an interactive symbolic-regression run."""

    metadata = ToolMetadata(
        name="finish_search",
        description=(
            "Request early termination of the current symbolic-regression search. "
            "The harness verifies its completion criteria and either pauses the run "
            "or explains why searching must continue."
        ),
        parameters={
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Concise summary of why the current best candidate satisfies the search goal.",
                },
            },
            "required": ["reason"],
            "additionalProperties": False,
        },
    )

    def execute(self, reason: str) -> dict[str, str]:
        """Request that the interactive Agent check its stopping policy and finish the search.

        Args:
            reason: Concise explanation of why the current search is ready to conclude.

        Returns:
            dict[str, str]: Request marker resolved by the interactive Agent loop.
        """
        return {"status": "requested", "reason": reason}

    @classmethod
    def format_result_dict(cls, result: dict[str, str]) -> str:
        """Format the resolved stop-request status for the Agent.

        Args:
            result: Resolution dictionary containing ``status`` and optional ``reason``.

        Returns:
            str: Message indicating whether the search stopped or why it must continue.
        """
        status = result.get("status")
        if status == "stopped":
            return "Search stopped. The run will pause at the next safe boundary."
        if status == "rejected":
            return f"Search cannot stop yet: {result.get('reason', 'completion check failed')}"
        return "Search stop requested."
