import numpy as np
import pytest
from scipy.linalg import cholesky, solve_triangular
import sr_harness_engine as engine

from sr_harness.evaluator.parameter_fitting import (
    fit_expression_least_squares, is_affine_in_parameters,
)


def test_weighted_svd_handles_near_collinear_columns_and_scale():
    x = 0.35 + np.linspace(-0.002, 0.002, 81)
    y = 0.7 + 120 * (x - 0.35) - 30000 * (x - 0.35) ** 2
    sigma = np.linspace(0.01, 0.03, len(x))
    expression = engine.parse("param('a', value=0) + param('b', value=0)*x + param('c', value=0)*x**2")
    fit = fit_expression_least_squares(expression, {'x': x}, y, sigma=sigma, max_model_evals=6)
    assert fit.diagnostics['converged']
    assert fit.diagnostics['evaluations'] == 6
    assert fit.diagnostics['condition'] > 1e5
    assert fit.diagnostics['objective'] < 1e-15
    np.testing.assert_allclose(engine.evaluate(fit.expression, {'x': x}), y, atol=2e-11)


def test_whitened_covariance_matches_generalized_least_squares():
    x = np.arange(5.0)
    y = np.array([0.0, 1.3, 2.7, 2.8, 4.2])
    covariance = np.diag(np.linspace(1, 2, 5)) + np.ones((5, 5)) * 0.2
    factor = cholesky(covariance, lower=True)
    whiten = lambda array: solve_triangular(factor, array, lower=True)
    expression = engine.parse("param('slope', value=0)*x + param('offset', value=0)")
    fit = fit_expression_least_squares(expression, {'x': x}, y, whitener=whiten)
    A = np.column_stack([x, np.ones(5)])
    expected = np.linalg.lstsq(whiten(A), whiten(y), rcond=None)[0]
    np.testing.assert_allclose([fit.parameters['slope'], fit.parameters['offset']], expected)
    assert fit.diagnostics['rank'] == 2


def test_parameter_nonlinearity_is_not_mistaken_for_fixed_basis():
    assert is_affine_in_parameters(engine.parse("param('a', value=1)*exp(x) + param('b', value=0)/x"))
    assert is_affine_in_parameters(engine.parse("param('a', value=1)*x + param('a', value=1)"))
    assert not is_affine_in_parameters(engine.parse("param('a', value=1)*param('b', value=1)*x"))
    assert not is_affine_in_parameters(engine.parse("exp(param('a', value=1)*x)"))
    assert not is_affine_in_parameters(engine.parse("x/param('a', value=1)"))


def test_nonlinear_fit_uses_scale_and_counts_finite_difference_calls(monkeypatch):
    x = np.linspace(0, 0.002, 50)
    y = 2.0 * np.exp(-1200 * x) + 0.4
    expression = engine.parse("param('a', value=1)*exp(param('rate', value=-500)*x) + param('b', value=0)")
    original = engine.evaluate
    calls = []
    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(engine, 'evaluate', counted)
    fit = fit_expression_least_squares(expression, {'x': x}, y, max_model_evals=120)
    assert fit.diagnostics['converged']
    assert fit.diagnostics['objective'] < 1e-15
    assert len(calls) == fit.diagnostics['evaluations'] <= 120


def test_budget_exhaustion_preserves_a_finite_incumbent(monkeypatch):
    x = np.linspace(0, 1, 20)
    expression = engine.parse("exp(param('a', value=0)*x)")
    calls = []
    original = engine.evaluate
    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(engine, 'evaluate', counted)
    fit = fit_expression_least_squares(expression, {'x': x}, np.exp(2*x), max_model_evals=3)
    assert len(calls) == 3
    assert fit.diagnostics['evaluations'] == 3
    assert fit.diagnostics['budget_exhausted']
    assert not fit.diagnostics['converged']
    assert np.isfinite(fit.diagnostics['objective'])
    assert fit.diagnostics['objective'] <= fit.diagnostics['initial_objective']


def test_rank_deficiency_is_reported_without_normal_equations():
    x = np.arange(10.)
    expression = engine.parse("param('a', value=0)*x + param('b', value=0)*(2*x)")
    fit = fit_expression_least_squares(expression, {'x': x}, 3*x)
    assert fit.diagnostics['rank'] == 1
    assert fit.diagnostics['rank_deficient']
    np.testing.assert_allclose(engine.evaluate(fit.expression, {'x': x}), 3*x, atol=1e-12)


@pytest.mark.parametrize('sigma', [np.zeros(3), np.ones(2), np.array([1., np.nan, 1.])])
def test_invalid_weights_fail_explicitly(sigma):
    with pytest.raises(ValueError, match='sigma'):
        fit_expression_least_squares(engine.parse("param('a', value=0)"), {}, np.ones(3), sigma=sigma)


def test_no_silent_initialization_or_density_mode():
    with pytest.raises(ValueError, match='initial'):
        fit_expression_least_squares(engine.parse("param('a')*x"), {'x': np.ones(3)}, np.ones(3))
    fit = fit_expression_least_squares(engine.parse("exp(param('a', value=0)*x)"), {'x': np.ones(3)}, np.ones(3), allow_nonlinear=False)
    assert fit.diagnostics['method'] == 'unsupported_nonlinear'
    assert not fit.diagnostics['converged']
    assert fit.diagnostics['evaluations'] == 1
