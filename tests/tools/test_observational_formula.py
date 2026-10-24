"""Observational policies apply only through explicit extension tools/evaluators."""
import numpy as np
import pytest

from sr_harness.core import AgentContext
from sr_harness.evaluator import DefaultEvaluator
from sr_harness.runtime.workspace import Workspace
from sr_harness.tools import BaseTool
from sr_harness.tools.evaluate_formula import EvaluateTool
from sr_harness.tools.evaluate_observational_formula import (
    EvaluateObservationalFormulaTool, SubmitObservationalFormulaTool,
)
from tests.evaluator.test_observational_evaluator import context


def test_explicit_evaluator_selection_is_required(tmp_path):
    ctx = context(tmp_path, task="regression")
    ctx.evaluator = DefaultEvaluator()
    with pytest.raises(ValueError, match="Select ObservationalEvaluator explicitly"):
        EvaluateObservationalFormulaTool(context=ctx).execute("x")
    assert type(ctx.evaluator) is DefaultEvaluator


def test_generic_evaluation_is_not_controlled_by_contract_file(tmp_path):
    ctx = AgentContext(data={"x": np.arange(4.), "y": 2 * np.arange(4.)},
                       target="y", workspace=Workspace(tmp_path))
    (tmp_path / "discovery_contract.json").write_text("invalid extension JSON")
    result = EvaluateTool(context=ctx).execute("2*x")
    assert result["is_candidate"]
    assert result["data_split_results"]["train"]["metrics"]["mse"] == 0.
    assert not EvaluateTool(context=ctx).execute("y")["is_candidate"]


@pytest.mark.parametrize("expression", ["unknown*x", "sigma*x", "group", "y"])
def test_regression_rejects_undeclared_inputs_without_guessing_parameters(tmp_path, expression):
    ctx = context(tmp_path, task="regression")
    with pytest.raises(ValueError, match="predictor|target|eligible"):
        EvaluateObservationalFormulaTool(context=ctx).execute(expression, fit=True)


def test_weighted_fit_and_diagnostics_use_training_partition(tmp_path):
    ctx = context(tmp_path, task="regression")
    result = EvaluateObservationalFormulaTool(context=ctx).execute(
        "param('a', value=0.0)", fit=True,
    )
    expected = np.average(ctx.data["y"][:4], weights=[1, .25, 1, .25])
    assert result["is_candidate"] and result["training_samples"] == 4
    assert result["fitted_parameters"]["a"] == pytest.approx(expected)
    assert result["fit_diagnostics"]
    assert "diagnostics" in result["data_split_results"]["validation"]
    # A previous fit must not appear as diagnostics on a later non-fitting call.
    plain = EvaluateObservationalFormulaTool(context=ctx).execute("0.5")
    assert "fit_diagnostics" not in plain


def test_density_is_eligible_without_mse_or_regression_diagnostics(tmp_path):
    ctx = context(tmp_path)
    tool = SubmitObservationalFormulaTool(context=ctx)
    result = tool.execute("1")
    assert result["is_candidate"]
    assert result["objective"] == "negative_log_likelihood"
    for split in result["data_split_results"].values():
        assert np.isnan(split["metrics"]["mse"])
        assert split["metrics"]["negative_log_likelihood"] == pytest.approx(0.)
        assert "diagnostics" not in split
    assert "p(y) proportional" in tool.format_result_dict(result)


def test_count_diagnostics_use_bin_integrated_prediction(tmp_path):
    ctx = context(tmp_path, task="binned_distribution", objective="poisson_deviance",
                  arrays={"y": np.full(6, 2.), "lo": np.zeros(6), "hi": np.full(6, 2.),
                          "exposure": np.ones(6)},
                  density_coordinate="x", bin_lower="lo", bin_upper="hi", exposure="exposure")
    result = EvaluateObservationalFormulaTool(context=ctx).execute("1")
    assert result["data_split_results"]["validation"]["metrics"]["poisson_deviance"] == 0.
    diagnostics = result["data_split_results"]["validation"]["diagnostics"]
    # Generic f(x) would predict one event; the integrated model predicts two.
    assert diagnostics["error_profile"]["max_absolute_error"] == 0.


def test_stale_generic_split_cache_cannot_change_observational_fit(tmp_path):
    ctx = context(tmp_path, task="regression")
    ctx._split_cache = {
        "train": AgentContext(data={"x": ctx.data["x"][4:], "y": ctx.data["y"][4:]}, target="y"),
        "validation": AgentContext(data={"x": ctx.data["x"][:4], "y": ctx.data["y"][:4]}, target="y"),
    }
    original_cache = ctx._split_cache
    result = EvaluateObservationalFormulaTool(context=ctx).execute("param('a', value=0.)", fit=True)
    assert result["fitted_parameters"]["a"] == pytest.approx(.22)
    assert ctx._split_cache is original_cache


def test_submission_enters_existing_topk_by_declared_metric(tmp_path):
    from sr_harness.core.search import CandidateRecord, SearchRunState
    ctx = context(tmp_path)
    result = SubmitObservationalFormulaTool(context=ctx).execute("1")
    state = SearchRunState(save_path=None, ranking_metric="negative_log_likelihood", larger_is_better=False)
    record = CandidateRecord(formula=result["formula"], node_id="node", details=result)
    assert state.push_candidate(record)
    assert state.ranked_candidates() == [record]
    assert BaseTool.create("evaluate_observational_formula", create_instance=False) is EvaluateObservationalFormulaTool
    assert BaseTool.create("submit_observational_formula", create_instance=False) is SubmitObservationalFormulaTool
