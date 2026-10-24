"""Proxy custom evaluator calls into the data-only OS sandbox."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import sr_harness_engine as engine

from ..core import AgentContext
from ..runtime.sandbox import _context_array_snapshot, _run_sandbox_protocol
from ..runtime.sandbox_context import sandbox_arguments
from .default_evaluator import DefaultEvaluator, MetricDict


def _context_payload(context: AgentContext) -> dict[str, Any]:
    return {
        "args": sandbox_arguments(context.args),
        "target": context.target,
        "variable_descriptions": context.variable_descriptions,
        "variable_axes": {name: list(axes) for name, axes in context.variable_axes.items()},
        "variable_structures": context.variable_structures,
        "relation_names": sorted(context.relation_names),
        "num_nodes": context.num_nodes,
    }


class SandboxedCustomEvaluator(DefaultEvaluator):
    """Out-of-process proxy for a user-defined :class:`DefaultEvaluator` subclass.

    Delegates :meth:`split`, :meth:`fit`, :meth:`evaluate`, :meth:`fit_candidate`,
    and :meth:`evaluate_candidate` to an isolated OS sandbox worker so untrusted
    custom evaluator code never runs inside the main server process.
    """

    CUSTOM_EVALUATOR: dict[str, Any]
    SANDBOX_SOURCE: str
    SANDBOX_FILENAME: str

    @classmethod
    def _request(
        cls,
        action: str,
        context: AgentContext | None = None,
        *,
        f: engine.Expression | None = None,
        y: engine.Expression | None = None,
        candidate: bool = False,
    ):
        request: dict[str, Any] = {
            "action": action,
            "source": cls.SANDBOX_SOURCE,
            "filename": cls.SANDBOX_FILENAME,
        }
        array_snapshot = None
        if context is not None:
            request["context"] = _context_payload(context)
            array_snapshot = _context_array_snapshot(context)
        if f is not None:
            request["f"] = f.to_str(number_format=".17g")
        if y is not None:
            request["y"] = y.to_str(number_format=".17g")
        request["candidate"] = candidate
        return _run_sandbox_protocol(
            operation="evaluator",
            request=request,
            array_snapshot=array_snapshot,
            timeout_seconds=120,
            memory_limit_mb=4096,
            output_limit_bytes=64 * 1024,
        )

    @classmethod
    def split(cls, context: AgentContext):
        """Execute the custom evaluator's ``split(context)`` method inside the OS sandbox.

        Args:
            context: Complete unsplit :class:`~sr_harness.core.AgentContext`.

        Returns:
            dict[str, AgentContext]: Training and validation context views reconstructed from sandbox outputs.
        """
        result = cls._request("split", context)
        if set(result.arrays) != {"train", "validation"}:
            raise ValueError("Custom evaluator split() must return train and validation data")
        return {name: context.with_data(data) for name, data in result.arrays.items()}

    @classmethod
    def fit(
        cls, f: engine.Expression, y: engine.Expression, context: AgentContext
    ) -> engine.Expression:
        """Execute the custom evaluator's ``fit(f, y, context)`` method inside the OS sandbox.

        Args:
            f: Symbolic expression whose parameters will be fitted.
            y: Target symbolic expression.
            context: Training split :class:`~sr_harness.core.AgentContext`.

        Returns:
            engine.Expression: Parameter-bound expression returned by the sandboxed worker.
        """
        result = cls._request("fit", context, f=f, y=y)
        return engine.parse(str(result.payload["expression"]))

    @classmethod
    def evaluate(
        cls, f: engine.Expression, y: engine.Expression, context: AgentContext
    ) -> MetricDict:
        """Execute the custom evaluator's ``evaluate(f, y, context)`` method inside the OS sandbox.

        Args:
            f: Parameter-bound expression to evaluate.
            y: Target symbolic expression.
            context: Training or validation :class:`~sr_harness.core.AgentContext`.

        Returns:
            MetricDict: Validated dictionary of numeric metrics.
        """
        result = cls._request("evaluate", context, f=f, y=y)
        return dict(result.payload["metrics"])

    @classmethod
    def fit_candidate(cls, f: engine.Expression, context: AgentContext) -> engine.Expression:
        """Execute the custom evaluator's ``fit_candidate(f, context)`` method inside the OS sandbox.

        Args:
            f: Candidate symbolic expression predicting ``context.target``.
            context: Training split :class:`~sr_harness.core.AgentContext`.

        Returns:
            engine.Expression: Parameter-bound candidate expression.
        """
        result = cls._request("fit", context, f=f, candidate=True)
        return engine.parse(str(result.payload["expression"]))

    @classmethod
    def evaluate_candidate(cls, f: engine.Expression, context: AgentContext) -> MetricDict:
        """Execute the custom evaluator's ``evaluate_candidate(f, context)`` method inside the OS sandbox.

        Args:
            f: Parameter-bound candidate expression.
            context: Training or validation :class:`~sr_harness.core.AgentContext`.

        Returns:
            MetricDict: Validated dictionary of numeric candidate metrics.
        """
        result = cls._request("evaluate", context, f=f, candidate=True)
        return dict(result.payload["metrics"])

    @classmethod
    def _evaluate_formula_isolated(
        cls,
        f: engine.Expression,
        y: engine.Expression,
        context: AgentContext,
        *,
        fit: bool,
        candidate: bool,
    ) -> tuple[engine.Expression, dict[str, MetricDict], dict[str, AgentContext]]:
        """Run split, optional fit, and both evaluations in one sandbox call."""
        request = {
            "action": "evaluate-formula",
            "source": cls.SANDBOX_SOURCE,
            "filename": cls.SANDBOX_FILENAME,
            "context": _context_payload(context),
            "f": f.to_str(number_format=".17g"),
            "y": y.to_str(number_format=".17g"),
            "fit": fit,
            "candidate": candidate,
        }
        result = _run_sandbox_protocol(
            operation="evaluator",
            request=request,
            arrays={"context": context.data},
            timeout_seconds=120,
            memory_limit_mb=4096,
            output_limit_bytes=64 * 1024,
        )
        split_contexts = {name: context.with_data(data) for name, data in result.arrays.items()}
        return (
            engine.parse(str(result.payload["expression"])),
            {name: dict(values) for name, values in result.payload["metrics"].items()},
            split_contexts,
        )


@lru_cache(maxsize=128)
def _inspect_source(source: str, filename: str) -> tuple[str, tuple[tuple[str, Any], ...]]:
    """Inspect immutable evaluator source once per process."""
    result = _run_sandbox_protocol(
        operation="evaluator",
        request={"action": "inspect", "source": source, "filename": filename},
        timeout_seconds=30,
        memory_limit_mb=2048,
        output_limit_bytes=64 * 1024,
    )
    return (
        str(result.payload["class_name"]),
        tuple(sorted(dict(result.payload.get("class_attributes", {})).items())),
    )


def create_sandboxed_evaluator(source: str, file: Path | None = None) -> DefaultEvaluator:
    """Validate custom evaluator Python source in the sandbox and construct a named proxy instance.

    Args:
        source: Python source code defining a single ``DefaultEvaluator`` subclass.
        file: Optional source file path recorded for provenance.

    Returns:
        DefaultEvaluator: Proxy instance whose class name matches the custom subclass.
    """
    filename = file.name if file is not None else "custom_evaluator.py"
    class_name, class_attributes = _inspect_source(source, filename)
    module_name = f"sr_harness.evaluator.{Path(filename).stem}"
    proxy_class = type(
        class_name,
        (SandboxedCustomEvaluator,),
        {
            **dict(class_attributes),
            "__module__": module_name,
            "CUSTOM_EVALUATOR": {"source": source, "file": file},
            "SANDBOX_SOURCE": source,
            "SANDBOX_FILENAME": filename,
        },
    )
    return proxy_class()
