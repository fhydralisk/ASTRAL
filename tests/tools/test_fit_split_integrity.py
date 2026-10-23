"""Validation labels must not affect fitted coefficients or serialized predictions."""
import numpy as np
import pytest
from sr_harness.core import AgentContext
from sr_harness.tools.polynomial_fit import PolynomialFitTool
from sr_harness.tools.power_law_fit import PowerLawFitTool
from sr_harness.tools.rational_fit import RationalFitTool


def context(x, y):
    c = AgentContext(data={'x': x, 'y': y}, target='y')
    c.args.validation_fraction = .2
    c.args.split_random_state = 42
    return c


@pytest.mark.parametrize('tool,kwargs', [
    (PolynomialFitTool, {'max_degree': 2}),
    (PowerLawFitTool, {}),
    (RationalFitTool, {'numerator_degree': 1, 'denominator_degree': 1}),
])
def test_validation_label_perturbation_cannot_change_fit(tool, kwargs):
    x = np.linspace(.3, 2, 100)
    y = 1 + x ** 2
    a = context(x, y)
    changed = y.copy()
    changed[np.isin(x, a.validation_split.data['x'])] += 30
    b = context(x, changed)
    np.testing.assert_array_equal(a.train_split.data['y'], b.train_split.data['y'])
    first = tool(context=a).execute(x=['x'], **kwargs)
    second = tool(context=b).execute(x=['x'], **kwargs)
    assert first['formula'] == second['formula']
    assert first['data_split_results']['validation']['metrics']['mse'] != second['data_split_results']['validation']['metrics']['mse']


def test_machine_formula_preserves_cancellation_sensitive_predictions():
    x = np.linspace(.744, .746, 100)
    y = 1e8 * x - 74499999.12345678
    c = context(x, y)
    tool = PolynomialFitTool(context=c)
    result = tool.execute(x=['x'], max_degree=1, simplify=False)
    prediction = tool.parse_formula(result['formula']).eval(c.train_split.data)
    rmse = np.sqrt(np.mean((prediction - c.train_split.data['y']) ** 2))
    assert rmse < 1e-6
    assert abs(rmse - result['data_split_results']['train']['metrics']['rmse']) < 1e-9
