# Copyright (c) 2026-present, Yumeow. Licensed under the MIT License.
"""Evaluate Python-defined models inside a data-only OS sandbox."""

from __future__ import annotations

from typing import Any, Dict

import numpy as np
import sr_harness_engine as engine

from ..runtime.sandbox import _run_sandbox_protocol
from .base_tool import BaseTool, ToolMetadata
from .code_executor import CodeExecutorTool


@BaseTool.register("evaluate_code")
class EvaluateCodeTool(BaseTool):
    """Tool for evaluating Python-defined candidate models inside an isolated OS sandbox."""

    metadata = ToolMetadata(name="evaluate_code")
    DEFAULT_TIMEOUT_SECONDS = CodeExecutorTool.DEFAULT_TIMEOUT_SECONDS
    DEFAULT_MEMORY_LIMIT_MB = CodeExecutorTool.DEFAULT_MEMORY_LIMIT_MB
    DEFAULT_OUTPUT_LIMIT_BYTES = CodeExecutorTool.DEFAULT_OUTPUT_LIMIT_BYTES
    MAX_TIMEOUT_SECONDS = CodeExecutorTool.MAX_TIMEOUT_SECONDS
    MAX_MEMORY_LIMIT_MB = CodeExecutorTool.MAX_MEMORY_LIMIT_MB
    MAX_OUTPUT_LIMIT_BYTES = CodeExecutorTool.MAX_OUTPUT_LIMIT_BYTES

    def execute(
        self,
        model_code: str,
        predict_code: str,
        y: str = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB,
        output_limit_bytes: int = DEFAULT_OUTPUT_LIMIT_BYTES,
        show_diagnostics: bool = True,
    ) -> Dict[str, Any]:
        """Evaluate a Python-defined candidate model on the train and validation splits.

        Before using this tool, call ``read_skill`` to check ``sr-harness-engine-syntax`` (and
        ``sr-harness-engine-graph-syntax`` for graph/hypergraph problems). Prefer symbolic formulas
        in ``evaluate_formula`` whenever SRHarness Engine syntax can express the model; use
        ``evaluate_code`` only when custom Python logic is genuinely required. Returns a
        submission-eligible candidate when ``y`` is the default target variable and ``predict_code``
        does not depend on ``y``.

        Args:
            model_code: Python source defining ``def func(data) -> dict`` (plus optional imports) that fits parameters on ``data`` and returns a model dict containing a concise mathematical ``description`` string.
            predict_code: Python source defining ``def func(data, model)`` (plus optional imports) that computes predicted target values without reading the target variable from ``data``.
            y: Target variable name or expression, e.g., ``"y"`` or ``"log(y)"``. Defaults to ``context.target``.
            timeout_seconds: Sandbox execution timeout in seconds (1-120, default 30).
            memory_limit_mb: Sandbox memory limit in MB (64-4096, default 1024).
            output_limit_bytes: Maximum captured output in bytes (1024-1048576, default 65536).
            show_diagnostics: Whether to include residual diagnostics in the evaluation result.

        Returns:
            Dict[str, Any]: Model description, candidate eligibility, and per-split fit metrics.
        """
        train_data = self.context.train_split.data
        validation_data = self.context.validation_split.data
        y = (y or self.context.target).strip().strip('"').strip("'")
        eq_y = self.parse_formula(y)
        timeout_seconds = CodeExecutorTool.bounded_int(
            timeout_seconds, self.DEFAULT_TIMEOUT_SECONDS, 1, self.MAX_TIMEOUT_SECONDS
        )
        memory_limit_mb = CodeExecutorTool.bounded_int(
            memory_limit_mb, self.DEFAULT_MEMORY_LIMIT_MB, 64, self.MAX_MEMORY_LIMIT_MB
        )
        output_limit_bytes = CodeExecutorTool.bounded_int(
            output_limit_bytes, self.DEFAULT_OUTPUT_LIMIT_BYTES, 1024, self.MAX_OUTPUT_LIMIT_BYTES
        )
        groups = {"train": train_data}
        if validation_data:
            groups["validation"] = validation_data
        result = _run_sandbox_protocol(
            operation="evaluate-code",
            request={
                "model_code": CodeExecutorTool.extract_code(model_code),
                "predict_code": CodeExecutorTool.extract_code(predict_code),
                "target": self.context.target,
            },
            arrays=groups,
            timeout_seconds=timeout_seconds,
            memory_limit_mb=memory_limit_mb,
            output_limit_bytes=output_limit_bytes,
            interruption_event=getattr(self, "cancel_event", None),
        )
        predictions = result.arrays.get("predictions", {})
        opaque_f = engine.parse("__code_model_prediction__")
        data_split_results: dict[str, dict[str, Any]] = {}
        for split_name, split_values in groups.items():
            if split_name not in predictions:
                raise ValueError(f"Sandbox did not return {split_name} predictions")
            y_pred = np.asarray(predictions[split_name])
            y_true = np.asarray(eq_y.eval(split_values))
            y_pred, y_true = np.broadcast_arrays(y_pred, y_true)
            metrics = self.calculate_metrics(opaque_f, y_true, y_pred)
            metrics["complexity"] = len(model_code) + len(predict_code)
            metrics.pop("aic", None)
            metrics.pop("bic", None)
            split_result: dict[str, Any] = {"metrics": metrics}
            if show_diagnostics:
                split_result["diagnostics"] = self.residual_diagnostics(
                    y_true=y_true,
                    y_pred=y_pred,
                    data=split_values,
                    target_expression=eq_y.to_str(),
                )
            data_split_results[split_name] = split_result
        return {
            "formula": str(result.payload["model_str"]),
            "is_candidate": bool(result.payload["is_candidate"])
            and eq_y.to_str() == self.context.target,
            "data_split_results": data_split_results,
        }

    @classmethod
    def format_result_dict(cls, result: Dict[str, Any]) -> str:
        """Format the code-model evaluation report with character-based code complexity notes.

        Args:
            result: Result dictionary returned by :meth:`execute`.

        Returns:
            str: Formatted evaluation summary for the code-defined model.
        """
        text = cls.format_evaluation_result(result, title="Evaluated code-defined model")
        marker = "Formula Complexity="
        if text.count(marker) > 1:
            raise ValueError(
                f"Expected at most one '{marker}' field in formatted evaluation output, "
                f"but found {text.count(marker)}."
            )
        text = text.replace(marker, "Code Complexity=")
        return (
            text + "\n"
            "(Note: The Code Complexity is measured as source-code character count, so it is not "
            "directly comparable to Formula Complexity defined as the symbolic formula node count.)"
        )
