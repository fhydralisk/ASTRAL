"""Explicit formula evaluation for the optional observational extension."""
from __future__ import annotations

from numbers import Real
from typing import Any

import numpy as np
import sr_harness_engine as engine

from ..evaluator.observational_evaluator import ObservationalEvaluator
from .base_tool import BaseTool, ToolMetadata


@BaseTool.register("evaluate_observational_formula")
class EvaluateObservationalFormulaTool(BaseTool):
    """Fit and evaluate a declared observational model without changing generic tools."""

    metadata = ToolMetadata(name="evaluate_observational_formula")

    def execute(
        self, f: str, y: str | None = None, fit: bool = False,
        show_diagnostics: bool = True,
    ) -> dict[str, Any]:
        """Evaluate a regression, count intensity or unnormalized density.

        Requires an explicitly selected ObservationalEvaluator and a prepared
        discovery contract. Fits use frozen training observations only. A density
        may use its measured coordinate; ordinary regression may not use its
        target as a predictor. Unknown variable names are errors, not parameters.

        Args:
            f: Candidate expression. Use explicit parameters such as
                param('slope', value=0.0), and fit=true to optimize them.
            y: Declared target name; defaults to the current target.
            fit: Fit parameters under the declared objective on training rows.
            show_diagnostics: Include regression/count residual diagnostics.
                Density results instead expose likelihood and normalization.
        """
        evaluator = self.context.evaluator
        if not isinstance(evaluator, ObservationalEvaluator):
            raise ValueError("Select ObservationalEvaluator explicitly before using observational tools")
        target = y if y is not None else self.context.target
        if not target:
            raise ValueError("Select the prepared observational target first")
        expression, target_expression = self.parse_formula(f), self.parse_formula(target)
        evaluator.validate_expression(expression, target_expression, self.context)
        contract, _ = evaluator._load(self.context)
        # Revalidate the disk-backed selection, even if another tool populated a
        # context split cache before the observational evaluator was selected.
        splits = evaluator.split(self.context)
        train = splits["train"]
        fitted = evaluator.fit(expression, target_expression, train) if fit else expression
        if not isinstance(fitted, engine.Expression):
            raise TypeError("ObservationalEvaluator.fit() must return an Expression")
        if missing := engine.unbound_parameters(fitted):
            raise ValueError(f"unbound parameters: {', '.join(missing)}")
        objective = contract.get("objective", "mse")
        density = contract["task_type"] == "unbinned_distribution"
        results, reasons = {}, []
        for split_name, context in splits.items():
            if not context.data:
                continue
            metrics = evaluator.evaluate(fitted, target_expression, context)
            if not isinstance(metrics, dict):
                raise TypeError("ObservationalEvaluator.evaluate() must return a dictionary")
            if any(isinstance(value, (bool, np.bool_)) or not isinstance(value, Real)
                   for value in metrics.values()):
                raise TypeError("Observational evaluator metrics must be numeric")
            metrics = {name: value.item() if isinstance(value, np.generic) else value
                       for name, value in metrics.items()}
            result = {"metrics": metrics}
            if not np.isfinite(metrics.get(objective, np.nan)):
                reasons.append(f"the {objective} on {split_name} is not finite")
            if show_diagnostics and not density:
                # Count intensities are integrated over bins by the evaluator;
                # pointwise f(x) is not the predicted number of events.
                prediction = (evaluator._counts(fitted, context)[1]
                              if contract["task_type"] == "binned_distribution"
                              else fitted.eval(context.data, num_nodes=context.num_nodes))
                result["diagnostics"] = self.residual_diagnostics(
                    y_true=np.asarray(target_expression.eval(context.data)),
                    y_pred=np.asarray(prediction), data=context.data,
                    target_expression=target_expression.to_str(),
                    **({"max_samples": 10} if split_name == "train" else {}),
                )
            results[split_name] = result
        result = {
            "formula": fitted.to_str(number_format=".17g"),
            "target_expression": target_expression.to_str(number_format=".17g"),
            "task_type": contract["task_type"], "objective": objective,
            "is_candidate": not reasons, "candidate_ineligibility_reasons": reasons,
            "data_split_results": results, "parameters_optimized": fit,
            "training_samples": int(np.asarray(train.data[self.context.target]).size),
        }
        if fit:
            result["fitted_parameters"] = engine.parameter_values(fitted)
            if evaluator.last_fit_diagnostics is not None:
                result["fit_diagnostics"] = dict(evaluator.last_fit_diagnostics)
        return result

    @classmethod
    def format_result_dict(cls, result: dict[str, Any]) -> str:
        """Format the observational result for the scientific agent timeline."""
        if result["task_type"] == "unbinned_distribution":
            text = (f"Evaluated density: p({result['target_expression']}) proportional to "
                    f"{result['formula']}\nObjective: {result['objective']}")
            for split, value in result["data_split_results"].items():
                text += f"\n{split}: {value['metrics']}"
            for reason in result["candidate_ineligibility_reasons"]:
                text += f"\nNot eligible: {reason}"
        else:
            text = cls.format_evaluation_result(result, title="Evaluated observational formula")
        if result["parameters_optimized"]:
            text += f"\nParameters fitted on {result['training_samples']} frozen training rows."
        if info := result.get("fit_diagnostics"):
            text += f"\nFit diagnostics: {info}"
        return text


@BaseTool.register("submit_observational_formula")
class SubmitObservationalFormulaTool(EvaluateObservationalFormulaTool):
    """Submit an observational candidate through the ordinary candidate registry."""

    metadata = ToolMetadata(name="submit_observational_formula")
