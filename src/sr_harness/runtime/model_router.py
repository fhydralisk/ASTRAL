"""Deterministic cost-aware routing between base and strong LLM backends."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelRoute:
    """Routing decision specifying which provider/model tier to call and why.

    Attributes:
        tier: Selected tier label (``"base"`` or ``"strong"``).
        provider: Selected LLM provider name.
        model: Selected model identifier.
        score: Complexity score computed for the task and step.
        reason: Human-readable explanation of the routing decision.
    """
    tier: str
    provider: str
    model: str
    score: int
    reason: str


class ModelRouter:
    """Policy that dynamically selects between a fast base model and an optional stronger model.

    Evaluates task complexity (such as PDEs, ODEs, graph/network structure,
    noise, or high feature counts) and current refinement depth ``L`` to route
    key steps to the strong model when automatic routing is enabled.
    """

    COMPLEX_PATTERNS = {
        r"\b(?:pde|ode|differential equation|network dynamics|graph dynamics)\b": 3,
        r"\b(?:implicit|piecewise|singular|stiff|chaotic|high[- ]dimensional)\b": 2,
        r"\b(?:noise|noisy|numerical stability|floating[- ]point|cancellation)\b": 1,
        r"(?:微分方程|网络动力学|图动力学|隐式|分段|奇异|混沌|高维)": 3,
        r"(?:噪声|数值稳定|浮点|消减误差)": 1,
    }

    def __init__(
        self,
        *,
        enabled: bool,
        base_provider: str,
        base_model: str,
        strong_provider: str | None = None,
        strong_model: str | None = None,
    ) -> None:
        """Initialize the model router with base and optional strong model backends.

        Args:
            enabled: Whether automatic routing to the strong model is enabled.
            base_provider: Provider name for the base model.
            base_model: Model identifier for the base model.
            strong_provider: Optional provider name for the strong model (defaults to ``base_provider``).
            strong_model: Optional model identifier for the strong model.
        """
        for name, value in (("base_provider", base_provider), ("base_model", base_model)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        for name, value in (("strong_provider", strong_provider), ("strong_model", strong_model)):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be None or a non-empty string")
        self.enabled = enabled
        self.base_provider = base_provider
        self.base_model = base_model
        self.strong_provider = base_provider if strong_provider is None else strong_provider
        self.strong_model = strong_model

    @property
    def has_strong_backend(self) -> bool:
        """Return whether a distinct strong provider/model backend is configured.

        Returns:
            bool: ``True`` if ``strong_model`` is set and differs from the base provider/model.
        """
        return bool(
            self.strong_model
            and (self.strong_provider, self.strong_model)
            != (self.base_provider, self.base_model)
        )

    def assess(self, task: str, feature_count: int) -> tuple[int, list[str]]:
        """Score the intrinsic difficulty of a discovery task from its description and feature count.

        Args:
            task: Natural-language problem description.
            feature_count: Number of input feature variables.

        Returns:
            tuple[int, list[str]]: Pair of ``(complexity_score, matched_reason_tags)``.
        """
        text = task.lower()
        score = max(0, feature_count - 3)
        reasons = [f"{feature_count} features"] if feature_count > 3 else []
        for pattern, weight in self.COMPLEX_PATTERNS.items():
            if re.search(pattern, text):
                score += weight
                reasons.append(pattern)
        return score, reasons

    def route(
        self,
        *,
        task_score: int,
        task_reasons: list[str],
        refinement_step: int,
    ) -> ModelRoute:
        """Select the base or strong model backend for a specific refinement step.

        Args:
            task_score: Task complexity score returned by :meth:`assess`.
            task_reasons: Matched difficulty reasons returned by :meth:`assess`.
            refinement_step: Current one-based refinement step index ``L``.

        Returns:
            ModelRoute: Selected model route and rationale.
        """
        if not self.enabled:
            return self._base(task_score, "automatic routing disabled")
        if not self.has_strong_backend:
            return self._base(task_score, "no distinct strong backend configured")
        if task_score >= 3:
            reason = "complex task signals: " + ", ".join(task_reasons or [str(task_score)])
            return self._strong(task_score, reason)
        if refinement_step >= 3:
            return self._strong(task_score, "base backend did not converge within two rounds")
        return self._base(task_score, "simple task or early exploration")

    def _base(self, score: int, reason: str) -> ModelRoute:
        return ModelRoute("base", self.base_provider, self.base_model, score, reason)

    def _strong(self, score: int, reason: str) -> ModelRoute:
        return ModelRoute(
            "strong",
            self.strong_provider,
            self.strong_model or self.base_model,
            score,
            reason,
        )
