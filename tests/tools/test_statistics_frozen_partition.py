"""Diagnostics used to initialize search must not summarize validation responses."""
import json

import numpy as np
import pytest

from sr_harness.core import AgentContext
from sr_harness.tools.statistics_analysis import StatisticsTool
from sr_harness.tools.observational_statistics import ObservationalStatisticsTool
from tests.evaluator.test_observational_evaluator import context


def test_observational_statistics_and_expressions_use_only_frozen_training(tmp_path):
    values = np.array([1., 2., 3., 4., 1e8, 2e8])
    ctx = context(tmp_path, task="regression", arrays={"y": values})
    before = ctx.data["y"].copy()
    tool = ObservationalStatisticsTool(context=ctx)
    result = tool.execute(["y", "y**2", "x+y"], n_bins=2)
    assert result["partition"] == "train"
    assert result["partition_source"] == "discovery_contract.json"
    assert result["n_rows"] == 4 and result["validation_included"] is False
    assert result["statistics"]["y"]["mean"] == 2.5
    assert result["statistics"]["y**2"]["mean"] == 7.5
    assert result["statistics"]["x+y"]["max"] == 7.
    assert result["statistics"]["y"]["q3"] == 3.25
    assert sum(b["count"] for b in result["statistics"]["y"]["distribution"]["bins"]) == 4
    assert result["statistics"]["y"]["distribution"]["bins"][-1]["right"] == 4.
    assert np.array_equal(ctx.data["y"], before)
    rendered = tool.format_result_dict(result)
    assert "Analysis partition: train" in rendered and "validation excluded" in rendered


def test_statistics_ignore_active_split_cache_and_do_not_fit(tmp_path):
    ctx = context(tmp_path, task="regression")

    class NeverEvaluate:
        def split(self, _):
            raise AssertionError("Diagnostics must use the declared frozen rows")

        def fit(self, *args, **kwargs):
            raise AssertionError("Statistics must not fit")

    ctx.evaluator = NeverEvaluate()
    result = ObservationalStatisticsTool(context=ctx).execute()
    assert result["statistics"]["y"]["n_samples"] == 4
    assert result["statistics"]["y"]["max"] == .4


def test_validation_view_still_defaults_to_training_diagnostics(tmp_path):
    ctx = context(tmp_path, task="regression")
    tool = ObservationalStatisticsTool(context=ctx.validation_split)
    result = tool.execute(["y"])
    assert result["partition"] == "train"
    assert result["statistics"]["y"]["mean"] == pytest.approx(.25)


def test_blocked_but_valid_contract_allows_training_data_audit(tmp_path):
    ctx = context(tmp_path, task="regression", replication_status="insufficient_measurements",
                  blocked_reason=["Independent physical response is unavailable"])
    result = ObservationalStatisticsTool(context=ctx).execute(["y"])
    assert result["partition"] == "train" and result["statistics"]["y"]["n_samples"] == 4


@pytest.mark.parametrize("change", [{"split": None}, {"split": "missing"}, {"features": ["missing"]}])
def test_contract_errors_never_fall_back_to_all_development_rows(tmp_path, change):
    ctx = context(tmp_path, task="regression")
    path = tmp_path / "discovery_contract.json"
    contract = json.loads(path.read_text())
    contract.update(change)
    path.write_text(json.dumps(contract))
    with pytest.raises(ValueError, match="frozen"):
        ObservationalStatisticsTool(context=ctx).execute(["y"])


def test_new_live_arrays_require_a_validated_handoff(tmp_path):
    ctx = context(tmp_path, task="regression")
    ctx.data["unrecorded"] = np.arange(6.)
    with pytest.raises(ValueError, match="not in the frozen handoff"):
        ObservationalStatisticsTool(context=ctx).execute()


def test_legacy_without_contract_keeps_full_data_and_output_shape():
    tool = StatisticsTool(context=AgentContext(data={"x": np.array([1., 2., 1000.])}))
    result = tool.execute()
    assert set(result) == {"statistics", "config", "exceptions"}
    assert result["statistics"]["x"]["n_samples"] == 3
    assert result["statistics"]["x"]["max"] == 1000.


def test_generic_statistics_ignores_contract_and_uses_current_memory(tmp_path):
    ctx = context(tmp_path, task="regression")
    ctx.data["y"] = np.array([2., 4., 6., 8., 10., 12.])
    ctx.data["new_column"] = np.arange(6.)
    # Even a malformed optional extension file cannot affect the generic tool.
    (tmp_path / "discovery_contract.json").write_text("not valid JSON")
    result = StatisticsTool(context=ctx).execute(["y", "new_column"])
    assert set(result) == {"statistics", "config", "exceptions"}
    assert result["statistics"]["y"]["mean"] == 7.
    assert result["statistics"]["y"]["n_samples"] == 6
    assert result["statistics"]["new_column"]["max"] == 5.


def test_observational_statistics_requires_explicit_contract(tmp_path):
    from sr_harness.runtime.workspace import Workspace
    ctx = AgentContext(data={"x": np.arange(3.)}, workspace=Workspace(tmp_path))
    with pytest.raises(ValueError, match="requires an explicit"):
        ObservationalStatisticsTool(context=ctx).execute()
