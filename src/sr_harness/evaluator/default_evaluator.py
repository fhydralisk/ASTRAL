"""Default evaluation protocol for ordinary aligned data."""
from __future__ import annotations

from typing import Literal, TypeAlias

import sr_harness_engine as engine

from ..core import AgentContext
from . import utils

MetricValue: TypeAlias = float | int
MetricDict: TypeAlias = dict[str, MetricValue]
ContextSplits: TypeAlias = dict[Literal["train", "validation"], AgentContext]


class DefaultEvaluator:
    """Base evaluation protocol for splitting datasets, fitting constants, and scoring formulas.

    Provides the five standard classmethod entry points shared by all formula
    evaluation tools: :meth:`split`, :meth:`fit`, :meth:`evaluate`,
    :meth:`fit_candidate`, and :meth:`evaluate_candidate`. Custom evaluators
    inherit from :class:`DefaultEvaluator` and override only the methods that
    need task-specific behavior.
    """

    @classmethod
    def split(cls, context: AgentContext) -> ContextSplits:
        """Partition ``context`` into ``"train"`` and ``"validation"`` :class:`~sr_harness.core.AgentContext` views.

        Args:
            context: Complete unsplit :class:`~sr_harness.core.AgentContext`.

        Returns:
            ContextSplits: Dictionary ``{"train": train_context, "validation": validation_context}``.
        """
        return utils.split_aligned_context(context)

    @classmethod
    def fit(cls, f: engine.Expression, y: engine.Expression, context: AgentContext) -> engine.Expression:
        """Optimize free parameters in ``f`` on the training split to approximate ``y``.

        Args:
            f: Right-hand side symbolic expression containing optional parameters.
            y: Left-hand side target expression.
            context: Training split :class:`~sr_harness.core.AgentContext`.

        Returns:
            engine.Expression: Copy of ``f`` with all parameter nodes bound to fitted numeric values.
        """
        target = engine.evaluate(y, context.data)
        return engine.fit(f, context.data, target).expression

    @classmethod
    def evaluate(cls, f: engine.Expression, y: engine.Expression, context: AgentContext) -> MetricDict:
        """Compute regression and complexity metrics for the equality ``y = f`` on ``context``.

        Args:
            f: Parameter-bound right-hand side expression.
            y: Left-hand side target expression.
            context: Training or validation :class:`~sr_harness.core.AgentContext`.

        Returns:
            MetricDict: Dictionary mapping metric names (``mse``, ``rmse``, ``mae``,
                ``mape``, ``r2``, ``aic``, ``bic``, ``pearson_r``, ``spearman_r``,
                ``complexity``) to numeric values.
        """
        target = engine.evaluate(y, context.data)
        prediction = engine.evaluate(f, context.data)
        return utils.regression_metrics(f, target, prediction)

    @classmethod
    def fit_candidate(cls, f: engine.Expression, context: AgentContext) -> engine.Expression:
        """Fit a formal candidate expression ``f`` predicting ``context.target`` on the training split.

        By default, delegates to ``cls.fit(f, Symbol(context.target), context)``.

        Args:
            f: Candidate symbolic expression predicting the target variable.
            context: Training split :class:`~sr_harness.core.AgentContext`.

        Returns:
            engine.Expression: Copy of ``f`` with fitted parameter values bound.
        """
        if context.target is None:
            raise ValueError("context.target must be configured before fitting a candidate")
        return cls.fit(f, engine.Symbol(context.target), context)

    @classmethod
    def evaluate_candidate(cls, f: engine.Expression, context: AgentContext) -> MetricDict:
        """Evaluate a fitted formal candidate expression ``f`` against ``context.target``.

        By default, delegates to ``cls.evaluate(f, Symbol(context.target), context)``.
        Override this method to add candidate-only metrics such as ODE trajectory rollout error.

        Args:
            f: Parameter-bound candidate expression.
            context: Training or validation :class:`~sr_harness.core.AgentContext`.

        Returns:
            MetricDict: Dictionary of numeric evaluation metrics.
        """
        if context.target is None:
            raise ValueError("context.target must be configured before evaluating a candidate")
        return cls.evaluate(f, engine.Symbol(context.target), context)
