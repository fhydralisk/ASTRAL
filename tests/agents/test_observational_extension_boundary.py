"""Optional observational metadata must not change the shared execution paths."""
from contextlib import nullcontext
from types import SimpleNamespace

import numpy as np
import pytest

from sr_harness.agents.sr_agent import SRAgent
from sr_harness.core import AgentContext
from sr_harness.runtime.workspace import Workspace
from sr_harness.tools.evaluate_formula import EvaluateTool
from sr_harness.tools.statistics_analysis import StatisticsTool
from sr_harness.service.session import InteractiveSession


def ordinary_context(tmp_path):
    workspace = Workspace(tmp_path)
    x = np.arange(1., 9.)
    return AgentContext(data={"x": x, "y": 2 * x}, target="y", workspace=workspace)


def test_generic_formula_tool_ignores_optional_contract_and_keeps_regression_semantics(tmp_path):
    context = ordinary_context(tmp_path)
    (tmp_path / "discovery_contract.json").write_text("invalid optional metadata")
    tool = EvaluateTool(context=context)
    assert tool.execute("2*x")["is_candidate"]
    result = tool.execute("y")
    assert not result["is_candidate"]
    assert any("depends on y" in reason for reason in result["candidate_ineligibility_reasons"])


def test_generic_statistics_use_live_arrays_without_requiring_a_frozen_handoff(tmp_path):
    context = ordinary_context(tmp_path)
    (tmp_path / "discovery_contract.json").write_text("invalid optional metadata")
    context.data["new_measurement"] = np.array([5., 15., 1000.])
    result = StatisticsTool(context=context).execute(["new_measurement"])
    assert set(result) == {"statistics", "config", "exceptions"}
    assert result["statistics"]["new_measurement"]["n_samples"] == 3
    assert result["statistics"]["new_measurement"]["max"] == 1000.


def test_generic_prompt_preview_does_not_read_or_append_optional_metadata(tmp_path):
    session = InteractiveSession(tmp_path / "logs", workspace_path=tmp_path / "work")
    payload = {"problem_description": "Compare measurements without prescribing a formula."}
    before = session.preview_initial_prompts(payload)
    (session.workspace / "discovery_contract.json").write_text("invalid optional metadata")
    assert session.preview_initial_prompts(payload) == before


def test_generic_search_reaches_its_normal_initialization_without_contract_checks(tmp_path):
    context = ordinary_context(tmp_path)
    (tmp_path / "discovery_contract.json").write_text("invalid optional metadata")

    class EnteredNormalSearch(Exception):
        pass

    def initialize(_):
        raise EnteredNormalSearch

    agent = SimpleNamespace(
        context=context, llm_provider="manual", llm_model="unused", llm_max_tokens=None,
        skill_manager=None, enabled_skills=set(), prepare_tool_context=nullcontext,
        initialize_with_context=initialize,
    )
    with pytest.raises(EnteredNormalSearch):
        SRAgent.run(agent, {"x": context.data["x"]}, {"y": context.data["y"]}, "Study measurements")


def test_generic_reload_and_snapshot_ignore_optional_contract_status(tmp_path):
    import json
    from sr_harness.evaluator import DefaultEvaluator

    session = InteractiveSession(tmp_path / "logs", workspace_path=tmp_path / "work")
    directory = session.workspace / "context.data"
    directory.mkdir()
    variables = {}
    for name, values in {"x": np.arange(4.), "y": np.arange(4.) * 2}.items():
        np.save(directory / f"{name}.npy", values)
        variables[name] = {"file": f"{name}.npy", "axes": ["sample"], "description": name}
    (directory / "manifest.json").write_text(json.dumps({
        "axes": {"sample": {"size": 4, "description": "source rows"}}, "variables": variables,
    }))
    for optional in ('{"replication_status": "insufficient_measurements"}', '{'):
        (session.workspace / "discovery_contract.json").write_text(optional)
        result = session.reload_context_data()
        assert type(session.context.evaluator) is DefaultEvaluator
        assert "scientific_status" not in result
        assert "scientific_status" not in session.snapshot()
        np.testing.assert_array_equal(session.context.data["y"], np.arange(4.) * 2)
