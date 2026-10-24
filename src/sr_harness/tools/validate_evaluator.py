"""Validate a workspace evaluator against the current dataset."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core import AgentContext, ToolMetadata
from ..evaluator import load_custom_evaluator
from .base_tool import BaseTool
from .evaluate_formula import EvaluateTool


@BaseTool.register("validate_evaluator")
class ValidateEvaluatorTool(BaseTool):
    """Tool for testing a workspace custom evaluator file against a formula in isolation."""

    metadata = ToolMetadata(name="validate_evaluator")

    def execute(
        self,
        f: str,
        evaluator_file: str | None = None,
        y: str | None = None,
        fit: bool = False,
        show_diagnostics: bool = False,
    ) -> dict[str, Any]:
        """Load and test a custom evaluator on a formula without mutating the active ``AgentContext``.

        Args:
            f: Symbolic formula string to score with the evaluator.
            evaluator_file: Optional workspace-relative Python file (e.g., ``"context.evaluator/custom_evaluator.py"``). Tests the currently attached context evaluator when omitted.
            y: Optional target variable or expression; defaults to ``context.target``.
            fit: Whether to fit formula parameters on the training split before scoring.
            show_diagnostics: Whether to include residual diagnostics in the evaluation report.

        Returns:
            dict[str, Any]: Evaluator class name, source file, and formula evaluation output.
        """
        relative = None
        evaluator = self.context.evaluator
        if evaluator_file is not None:
            if self.context.workspace is None:
                raise RuntimeError("Workspace not initialized.")
            relative = Path(evaluator_file)
            if relative.suffix != ".py":
                raise ValueError("evaluator_file must identify a Python file")
            path = self.context.workspace.path / relative
            evaluator = load_custom_evaluator(
                file=path,
                workspace=self.context.workspace,
            )
        test_context = AgentContext(
            args=self.context.args,
            data=self.context.data,
            target=self.context.target,
            variable_descriptions=self.context.variable_descriptions,
            variable_axes=self.context.variable_axes,
            variable_structures=self.context.variable_structures,
            num_nodes=self.context.num_nodes,
            evaluator=evaluator,
            workspace=self.context.workspace,
        )
        result = EvaluateTool(context=test_context).execute(
            f=f, y=y, fit=fit, show_diagnostics=show_diagnostics,
        )
        return {
            "evaluator_file": str(relative) if relative is not None else None,
            "evaluator": type(evaluator).__name__,
            **result,
        }

    @classmethod
    def format_result_dict(cls, result: dict[str, Any]) -> str:
        """Format the evaluator identity and formula evaluation summary for the Agent.

        Args:
            result: Result dictionary returned by :meth:`execute`.

        Returns:
            str: Formatted evaluator validation output.
        """
        reference = result["evaluator_file"] or result["evaluator"]
        return f"Evaluator: {reference}\n" + EvaluateTool.format_result_dict(result)
