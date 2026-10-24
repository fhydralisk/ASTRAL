# Copyright (c) 2026-present, Yumeow. Licensed under the MIT License.
"""Formula evaluation and candidate submission tools."""
from typing import Dict, Any

import numpy as np
import sr_harness_engine as engine
from .base_tool import BaseTool, ToolMetadata


@BaseTool.register('evaluate_formula')
class EvaluateTool(BaseTool):
    """Tool for scoring a symbolic formula against a target variable or expression."""
    metadata = ToolMetadata(name="evaluate_formula")

    def execute(
        self,
        f: str,
        y: str = None,
        fit: bool = False,
        show_diagnostics: bool = True,
    ) -> Dict[str, Any]:
        """Evaluate how well a symbolic formula ``f`` fits target ``y`` on train and validation splits.

        Automatically treats unknown variable names in ``f`` as tunable parameters and optimizes
        them with BFGS. Records a submission-eligible candidate when ``y`` is the default target
        variable and ``f`` does not reference ``y``.

        Args:
            f: Symbolic formula string, e.g., ``"x1**2 + sin(x2) + 3.5 * tanh(x3)"``. Standard math operators (``sin``, ``sinh``, ``sec``, ``sech``, ``sigmoid``, etc.) are supported directly without ``np.`` prefixes.
            y: Target variable name or expression, e.g., ``"y"``, ``"log(y)"``, or ``"y - x1"``. Defaults to ``context.target``.
            fit: Whether to optimize scalar parameters in ``f`` on the training split via BFGS.
            show_diagnostics: Whether to return residual quantiles, worst samples, and residual-feature correlations.

        Returns:
            Dict[str, Any]: Fit metrics across splits, candidate eligibility, fitted parameters, and residual diagnostics.
        """
        data = self.context.data
        y = y or self.context.target
        y = y.strip().strip('"').strip("'")
        eq_y = self.parse_formula(y)
        eq_f = self.parse_formula(f)
        variables = [var for var in eq_f.iter_preorder() if isinstance(var, engine.Variable)]
        for var in variables:
            if var.name not in data:
                eq_f = eq_f.replace(var, engine.Parameter(var.name, np.random.rand()))
                fit = True # If there are unknown variables, we must fit the formula to data.

        evaluation = self.evaluate(
            f=eq_f,
            y=eq_y,
            show_diagnostics=show_diagnostics,
            fit=fit,
        )
        split_context = self.context.train_split
        y_true = np.asarray(eq_y.eval(
            split_context.data, num_nodes=split_context.num_nodes,
        ))
        parameters = engine.parameter_values(self.parse_formula(evaluation["formula"])) if fit else None
        return {
            **evaluation,
            "parameters_optimized": fit,
            **({"fitted_parameters": parameters} if parameters is not None else {}),
            "training_samples": int(y_true.size),
        }

    @classmethod
    def format_result_dict(cls, result: Dict[str, Any]) -> str:
        """Format formula evaluation metrics and parameter-fitting notes for the Agent.

        Args:
            result: Result dictionary returned by :meth:`execute`.

        Returns:
            str: Formatted evaluation summary.
        """
        text = cls.format_evaluation_result(result, title="Evaluated formula")
        if result.get("parameters_optimized"):
            lines = text.splitlines()
            lines.insert(
                2,
                f"    (Parameters are re-fitted on {result['training_samples']} train-set samples)",
            )
            text = "\n".join(lines)
        return text

@BaseTool.register('submit_formula')
class SubmitFormulaTool(EvaluateTool):
    """Tool for evaluating and submitting a candidate formula to the search harness."""
    metadata = ToolMetadata(
        name="submit_formula",
        description=(
            "Evaluate and submit a candidate formula for the discovery target. "
            "Call this tool whenever you find a strong formula; you may submit multiple times and the harness retains the best candidate. "
            "A submission is recorded as a valid candidate only when `y` is the default target variable and `f` does not reference `y`."
        ),
    )
