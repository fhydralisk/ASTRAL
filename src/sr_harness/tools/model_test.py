"""Internal tool used to verify model tool-calling support."""
from __future__ import annotations

from .base_tool import BaseTool
from ..core import ToolMetadata


class ModelTestTool(BaseTool):
    """Internal connectivity-check tool used to verify LLM tool-calling support."""

    metadata = ToolMetadata(
        name="report_model_test",
        description="Report the requested value to complete an SRHarness model test.",
        parameters={
            "type": "object",
            "properties": {
                "answer": {
                    "type": "string",
                    "description": "The exact value requested by the model-test prompt.",
                },
            },
            "required": ["answer"],
            "additionalProperties": False,
        },
    )

    def execute(self, answer: str) -> dict[str, str]:
        """Echo the exact answer string requested by a model connectivity check.

        Args:
            answer: Exact string requested by the connectivity test prompt.

        Returns:
            dict[str, str]: Dictionary mapping ``"answer"`` to ``answer``.
        """
        return {"answer": answer}
