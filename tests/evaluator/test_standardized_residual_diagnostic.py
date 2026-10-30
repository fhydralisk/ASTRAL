"""Fixed-error residual diagnostics remain distinct from the optimized objective."""
import json

import numpy as np
import pytest
import sr_harness_engine as engine

from sr_harness.core import AgentContext, load_context_data
from sr_harness.evaluator import ObservationalEvaluator
from sr_harness.runtime.workspace import Workspace
from sr_harness.tools.evaluate_observational_formula import EvaluateObservationalFormulaTool


DIAGNOSTIC = "mean_standardized_squared_residual"


def make_context(path, *, objective, covariance=False, extra=0.):
    workspace = Workspace(path)
    directory = path / "context.data"
    directory.mkdir()
    arrays = {"x": np.arange(4.), "y": np.array([2., -1., 1., 2.]),
              "sigma": np.array([2., 1., 1., 2.]),
              "partition": np.array(["train", "train", "validation", "validation"])}
    contract = {"version": 1, "task_type": "regression", "target": "y",
                "features": ["x"], "roles": {"x": "predictor", "y": "target",
                                               "sigma": "uncertainty", "partition": "split"},
                "split": "partition", "selection": {}, "objective": objective,
                "uncertainty": "sigma", "extra_scatter": extra}
    if covariance:
        arrays["covariance"] = np.array([[4., 1., 0., 0.], [1., 1., 0., 0.],
                                         [0., 0., 1., .5], [0., 0., .5, 4.]])
        contract["covariance"] = "covariance"
    manifest = {"axes": {"row": {"size": 4, "description": "source row"}}, "variables": {}}
    for name, values in arrays.items():
        np.save(directory / f"{name}.npy", values)
        manifest["variables"][name] = {"file": f"{name}.npy", "axes": ["row"] * values.ndim,
                                       "description": name}
    (directory / "manifest.json").write_text(json.dumps(manifest))
    (path / "discovery_contract.json").write_text(json.dumps(contract))
    context = AgentContext(workspace=workspace)
    context.commit_context_data(load_context_data(directory, workspace=workspace))
    context.update_selection(target="y", features=["x"])
    context.evaluator = ObservationalEvaluator()
    return context


@pytest.mark.parametrize("objective", ["weighted_squared_error", "gaussian_nll"])
@pytest.mark.parametrize("extra,expected,logdet", [(0., 1., np.log(4.)), (1., .65, np.log(10.))])
def test_diagonal_errors_include_frozen_extra_variance_without_changing_loss(tmp_path, objective, extra, expected, logdet):
    context = make_context(tmp_path, objective=objective, extra=extra)
    result = EvaluateObservationalFormulaTool(context=context).execute("0", show_diagnostics=False)
    for partition in ("train", "validation"):
        metrics = result["data_split_results"][partition]["metrics"]
        assert metrics[DIAGNOSTIC] == pytest.approx(expected)
        expected_loss = expected if objective == "weighted_squared_error" else (
            .5 * (expected + logdet / 2 + np.log(2 * np.pi)))
        assert metrics[objective] == pytest.approx(expected_loss)
    old_api = context.evaluator._regression_loss(engine.parse("0"), context.train_split)
    with_diagnostics = context.evaluator._regression_loss(
        engine.parse("0"), context.train_split, include_diagnostics=True)
    assert len(old_api) == 2 and len(with_diagnostics) == 3
    assert old_api[0] == with_diagnostics[0]
    np.testing.assert_array_equal(old_api[1], with_diagnostics[1])
    assert DIAGNOSTIC in EvaluateObservationalFormulaTool.format_result_dict(result)


@pytest.mark.parametrize("objective", ["weighted_squared_error", "gaussian_nll"])
@pytest.mark.parametrize("extra,means,determinants", [
    (0., (2., .8), (3., 3.75)),
    (1., (17 / 18, 22 / 39), (9., 9.75)),
])
def test_correlated_errors_use_quadratic_form_and_partition_submatrix(tmp_path, objective, extra, means, determinants):
    context = make_context(tmp_path, objective=objective, covariance=True, extra=extra)
    result = EvaluateObservationalFormulaTool(context=context).execute("0", show_diagnostics=False)
    for partition, expected, determinant in zip(("train", "validation"), means, determinants):
        metrics = result["data_split_results"][partition]["metrics"]
        assert metrics[DIAGNOSTIC] == pytest.approx(expected)
        expected_loss = expected if objective == "weighted_squared_error" else (
            .5 * (expected + np.log(determinant) / 2 + np.log(2 * np.pi)))
        assert metrics[objective] == pytest.approx(expected_loss)


def test_mse_does_not_invent_a_standardized_residual_model(tmp_path):
    # A sigma array may exist as metadata, but MSE did not use it as a noise model.
    context = make_context(tmp_path, objective="mse", extra=1.)
    result = EvaluateObservationalFormulaTool(context=context).execute("0", show_diagnostics=False)
    for partition in ("train", "validation"):
        metrics = result["data_split_results"][partition]["metrics"]
        assert metrics["mse"] == 2.5
        assert DIAGNOSTIC not in metrics
    assert DIAGNOSTIC not in EvaluateObservationalFormulaTool.format_result_dict(result)


def test_diagnostic_is_visible_in_real_model_tool_text(tmp_path):
    context = make_context(tmp_path, objective="gaussian_nll", covariance=True)
    result = EvaluateObservationalFormulaTool(context=context)("0", show_diagnostics=False)
    assert "mean_standardized_squared_residual=2.00 | 0.800;" in result.result_str
