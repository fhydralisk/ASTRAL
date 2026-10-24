"""Independent numerical checks of the density measure over wide positive support."""
import numpy as np
import pytest

from sr_harness.tools.evaluate_observational_formula import EvaluateObservationalFormulaTool
from tests.evaluator.test_observational_evaluator import context


def metrics(tmp_path, formula, *, lower=1e-6, upper=1e6, values=None, **extra):
    observations = np.geomspace(lower, upper, 6) if values is None else values
    ctx = context(tmp_path, arrays={"y": observations},
                  support={"lower": lower, "upper": upper}, quadrature_scale="log", **extra)
    result = EvaluateObservationalFormulaTool(context=ctx).execute(formula)
    return result["data_split_results"]["validation"]["metrics"]


@pytest.mark.parametrize("power", [-2., -1., -.5, 0., 1.])
def test_power_density_analytic_integral_across_twelve_decades(tmp_path, power):
    lower, upper = 1e-6, 1e6
    result = metrics(tmp_path, f"y**({power})", lower=lower, upper=upper)
    expected = (np.log(upper / lower) if power == -1 else
                (upper**(power + 1) - lower**(power + 1)) / (power + 1))
    assert result["normalization"] == pytest.approx(expected, rel=1e-10)
    assert result["quadrature_relative_error"] < 1e-10


@pytest.mark.parametrize("amplitude", [1e-200, 1., 1e200])
def test_density_amplitude_does_not_change_normalized_likelihood(tmp_path, amplitude):
    values = np.geomspace(1e-6, 1e6, 6)
    result = metrics(tmp_path, f"{amplitude}/y", values=values)
    expected = np.mean(np.log(values[4:])) + np.log(np.log(1e12))
    assert result["negative_log_likelihood"] == pytest.approx(expected, abs=1e-11)


@pytest.mark.parametrize("unit_scale", [1e-50, 1., 1e50])
def test_unit_change_preserves_probability_and_has_correct_nll_jacobian(tmp_path, unit_scale):
    lower, upper = unit_scale, 1000 * unit_scale
    values = np.array([1.2, 2., 4., 8., 25., 300.]) * unit_scale
    result = metrics(tmp_path, "1/y", lower=lower, upper=upper, values=values)
    assert result["normalization"] == pytest.approx(np.log(1000), rel=1e-12)
    original_nll = np.mean(np.log([25., 300.])) + np.log(np.log(1000))
    assert result["negative_log_likelihood"] == pytest.approx(original_nll + np.log(unit_scale))


@pytest.mark.parametrize("lower,upper", [(0., 1.), (-1., 1.), (1., 1.), (1., float("inf"))])
def test_invalid_log_support_fails_instead_of_changing_integration_measure(tmp_path, lower, upper):
    with pytest.raises(ValueError, match="strictly positive|finite increasing"):
        metrics(tmp_path, "1", lower=lower, upper=upper, values=np.ones(6))
