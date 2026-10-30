"""Budgeted parameter fitting for a fixed regression expression.

This module never proposes expression structure or reads validation data.  An
AST check selects a direct, column-scaled SVD solve when the *entire* expression
is affine in its named parameters.  Other expressions can use a local
Jacobian-scaled least-squares solve; there are no restarts or parameter grids.
Only fixed quadratic residual objectives belong here, not density likelihoods,
residual-dependent error bars, or fitted covariance models.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

import numpy as np
from scipy.optimize import least_squares
import sr_harness_engine as engine
from sr_harness_engine.expression import Binary, GroupedParameter, Parameter, Unary


class ModelEvaluationBudgetExceeded(RuntimeError):
    """Raised internally before a model evaluation would exceed the cap."""


@dataclass(frozen=True)
class ParameterFitResult:
    expression: Any
    parameters: dict[str, float]
    diagnostics: dict[str, Any]


def _parameter_degree(node) -> int:
    """Conservative degree: 0 independent, 1 affine, 2 nonlinear/unknown."""
    if isinstance(node, GroupedParameter):
        return 2
    if isinstance(node, Parameter):
        return 1
    if isinstance(node, Unary):
        return _parameter_degree(node.operand)
    if isinstance(node, Binary):
        left, right = _parameter_degree(node.left), _parameter_degree(node.right)
        if node.operator in ('+', '-'):
            return max(left, right)
        if node.operator == '*':
            return min(left + right, 2)
        if node.operator == '/' and right == 0:
            return left
        if node.operator == '**' and right == 0:
            if isinstance(node.right, engine.Number) and node.right.value == 1:
                return left
        return 2 if left or right else 0
    # Nonlinear functions of predictors are still valid fixed design columns;
    # functions of parameters are deliberately not guessed to be affine.
    return 2 if any(_parameter_degree(child) for child in node.operands) else 0


def is_affine_in_parameters(expression) -> bool:
    """Return true only for structurally certified scalar affine parameters."""
    return _parameter_degree(expression) <= 1


def fit_expression_least_squares(
    expression,
    values: Mapping[str, np.ndarray],
    target: np.ndarray,
    *,
    sigma: np.ndarray | None = None,
    whitener: np.ndarray | Callable[[np.ndarray], np.ndarray] | None = None,
    max_model_evals: int = 512,
    allow_nonlinear: bool = True,
) -> ParameterFitResult:
    """Fit a supplied expression against only the arrays supplied by the caller.

    ``sigma`` contains fixed, positive standard deviations. Alternatively,
    ``whitener`` is a fixed linear operator W with W.T @ W = covariance^-1;
    a callable must accept either an (n,) residual or an (n,p) design matrix.
    No validation data, uncertainty estimation, or model selection occurs here.

    The budget counts *every* engine.evaluate call, including initial prediction,
    design construction, finite-difference Jacobians, and final direct-model
    verification.  On exhaustion the best finite evaluated parameter vector is
    returned with ``converged=False``.  A budget can thus bound numerical work
    consistently across optimizers rather than counting optimizer iterations.
    """
    if isinstance(max_model_evals, bool) or int(max_model_evals) != max_model_evals or max_model_evals < 1:
        raise ValueError('max_model_evals must be a positive integer')
    maximum = int(max_model_evals)
    y = np.asarray(target, dtype=float)
    if y.ndim != 1 or not y.size or not np.isfinite(y).all():
        raise ValueError('target must be a finite, nonempty one-dimensional array')
    if sigma is not None and whitener is not None:
        raise ValueError('Supply sigma or whitener, not both')
    if sigma is not None:
        sigma = np.asarray(sigma, dtype=float)
        if sigma.shape != y.shape or not np.isfinite(sigma).all() or np.any(sigma <= 0):
            raise ValueError('sigma must match target and be finite and positive')

        def transform(array):
            return array / (sigma[:, None] if array.ndim == 2 else sigma)
    elif whitener is not None:
        if callable(whitener):
            transform = whitener
        else:
            matrix = np.asarray(whitener, dtype=float)
            if matrix.shape != (len(y), len(y)) or not np.isfinite(matrix).all():
                raise ValueError('whitener must be a finite square matrix matching target')
            transform = lambda array: matrix @ array
    else:
        transform = lambda array: array

    def whiten(array):
        result = np.asarray(transform(array), dtype=float)
        if result.shape != array.shape or not np.isfinite(result).all():
            raise ValueError('whitener must preserve shape and produce finite values')
        return result

    nodes = tuple(expression.iter_preorder())
    if any(isinstance(node, GroupedParameter) for node in nodes):
        raise ValueError('Only named scalar parameters are supported')
    names = list(dict.fromkeys(node.name for node in nodes if isinstance(node, Parameter)))
    initial = engine.parameter_values(expression)
    if any(name not in initial or not np.isfinite(initial[name]) for name in names):
        raise ValueError('Parameters require explicit finite initial values')
    x0 = np.asarray([initial[name] for name in names], dtype=float)
    count = 0
    best_x = x0.copy()
    best_loss = float('inf')

    def predict(parameters):
        nonlocal count
        if count >= maximum:
            raise ModelEvaluationBudgetExceeded('model evaluation budget exhausted')
        count += 1
        with np.errstate(all='ignore'):
            prediction = np.asarray(engine.evaluate(
                expression, values, parameters=dict(zip(names, parameters))
            ), dtype=float)
        prediction = np.broadcast_to(prediction, y.shape)
        if not np.isfinite(prediction).all():
            raise ValueError('Nonfinite model prediction')
        return prediction

    def residual(parameters):
        nonlocal best_x, best_loss
        r = whiten(predict(parameters) - y)
        loss = float(np.mean(r ** 2))
        if not np.isfinite(loss):
            raise ValueError('Nonfinite squared residual objective')
        if loss < best_loss:
            best_x, best_loss = parameters.copy(), loss
        return r

    residual(x0)  # Fail clearly if the supplied initialization is not valid.
    initial_loss = best_loss
    affine = is_affine_in_parameters(expression)
    diagnostics = dict(
        method='fixed_expression' if not names else 'scaled_svd' if affine else 'jacobian_scaled_least_squares',
        evaluations=0, max_model_evals=maximum, rank=None, condition=None,
        scaled_condition=None, converged=False, budget_exhausted=False,
        initial_objective=initial_loss,
    )
    if not names:
        diagnostics.update(converged=True, message='No free parameters')
    elif not affine and not allow_nonlinear:
        diagnostics.update(method='unsupported_nonlinear', message='Expression is not affine in parameters')
    else:
        try:
            if affine:
                zero = np.zeros(len(names))
                offset = predict(zero)
                design = np.column_stack([
                    predict(np.eye(len(names))[j]) - offset for j in range(len(names))
                ])
                weighted_design = whiten(design)
                weighted_target = whiten(y - offset)
                scales = np.linalg.norm(weighted_design, axis=0)
                scales[scales == 0] = 1
                scaled_design = weighted_design / scales
                solution, _, rank, singular = np.linalg.lstsq(scaled_design, weighted_target, rcond=None)
                coefficients = solution / scales
                diagnostics.update(
                    rank=int(rank), condition=float(np.linalg.cond(weighted_design)),
                    scaled_condition=float(singular[0] / singular[-1]) if singular[-1] > 0 else float('inf'),
                    rank_deficient=bool(rank < len(names)),
                )
                # The returned engine expression, not just A @ coefficients, is
                # scored. This catches cancellation in a poorly scaled syntax.
                r = residual(coefficients)
                expected = weighted_design @ coefficients - weighted_target
                mismatch = float(np.linalg.norm(r - expected) / max(1.0, np.linalg.norm(expected)))
                diagnostics.update(
                    model_verification_relative_error=mismatch,
                    converged=bool(mismatch <= 1e-7),
                    message='Direct weighted SVD solve' if mismatch <= 1e-7 else 'Expression cancellation requires rescaled syntax',
                )
            else:
                def nonlinear_residual(parameters):
                    try:
                        return residual(parameters)
                    except (ValueError, FloatingPointError, OverflowError):
                        return np.full(len(y), 1e50)

                fit = least_squares(
                    nonlinear_residual, x0, method='trf', x_scale='jac',
                    max_nfev=maximum, ftol=1e-10, xtol=1e-10, gtol=1e-10,
                )
                diagnostics.update(converged=bool(fit.success), message=str(fit.message))
        except ModelEvaluationBudgetExceeded:
            diagnostics.update(budget_exhausted=True, converged=False, message='Model evaluation budget exhausted; retained best finite evaluated candidate')
    diagnostics.update(evaluations=count, objective=best_loss)
    parameters = dict(zip(names, map(float, best_x)))
    return ParameterFitResult(
        expression=engine.bind_parameters(expression, parameters),
        parameters=parameters,
        diagnostics=diagnostics,
    )
