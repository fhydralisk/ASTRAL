"""Check evaluator-only completion and scoped variable configuration without an LLM."""

import numpy as np
import pytest

from sr_harness.agents.evaluator_construction_agent import EvaluatorConstructionAgent
from sr_harness.api import BaseAPI
from sr_harness.core import AgentContext, APICallSample, APICallSummary, ToolCall
from sr_harness.runtime import InteractionManager
from sr_harness.tools import VariableRolesTool, ValidateEvaluatorTool, WorkspaceCodeExecutorTool


class ScriptedAPI:
    def __init__(self, samples):
        self.samples = iter(samples)

    def __call__(self, *args, **kwargs):
        return APICallSummary(iter([next(self.samples)]))

    def cancel(self):
        pass


def make_agent(monkeypatch, tools, samples=(), updater=None, max_steps=3):
    monkeypatch.setattr(BaseAPI, "create", lambda *args, **kwargs: ScriptedAPI(samples))
    context = tools[0].context
    agent = EvaluatorConstructionAgent(
        llm_provider="openrouter", llm_model="test", context=context, tools=tools,
        interaction_manager=InteractionManager(), variable_role_updater=updater, max_steps=max_steps,
    )
    monkeypatch.setattr(agent, "_wait", lambda: False)
    return agent


def test_successful_low_r2_probe_does_not_block_completion(monkeypatch):
    context = AgentContext(data={"x": np.arange(6.), "y": np.arange(6.)}, target="y")
    write = WorkspaceCodeExecutorTool(context=context)
    validate = ValidateEvaluatorTool(context=context)
    monkeypatch.setattr(write, "execute", lambda **kw: {"written": True})
    metrics = dict.fromkeys(["mse", "rmse", "mae", "mape", "r2", "aic", "bic", "pearson_r", "spearman_r", "complexity"], 1.)
    metrics["r2"] = -1000.
    monkeypatch.setattr(validate, "execute", lambda **kw: {
        "evaluator_file": "context.evaluator/test.py", "data_split_results": {
            name: {"metrics": metrics} for name in ["train", "validation"]
        },
    })
    monkeypatch.setattr(validate, "format_result_dict", lambda result: str(result))
    samples = [
        APICallSample(None, [ToolCall(name="workspace_code_executor", params={"program": "write evaluator"})]),
        APICallSample(None, [ToolCall(name="validate_evaluator", params={"f": "1"})]),
        APICallSample("Evaluator is ready; this smoke test has poor predictive performance."),
    ]
    agent = make_agent(monkeypatch, [write, validate], samples)
    result = agent.run("Build an evaluator, without searching for a scientific formula.")
    assert result["message"].startswith("Evaluator is ready")
    assert len(result["tool_events"]) == 2
    assert not any("Completion is blocked" in str(message) for message in agent.buffer)


def test_variable_write_quotes_real_user_and_survives_tool_reconfiguration(monkeypatch):
    context = AgentContext(data={"x": np.arange(6.), "y": np.arange(6.)})
    tool = VariableRolesTool(context=context)
    received = []
    agent = make_agent(monkeypatch, [tool], updater=lambda **kw: received.append(kw) or {})
    agent.buffer.append({"role": "user", "content": "Please configure the variables for me."})
    with pytest.raises(ValueError, match="actual user instruction"):
        agent._update_variable_roles(roles={"y": "target"}, user_request="invented permission")
    assert received == []
    agent.queue_runtime_settings({"tools": ["configure_variable_roles"]})
    agent._apply_pending_runtime_settings()
    rebound = agent.tool_box["configure_variable_roles"]
    rebound.execute(roles={"y": "target"}, user_request="configure the variables for me")
    assert received == [{"roles": {"y": "target"}, "user_request": "configure the variables for me"}]


def test_evaluator_prompt_preserves_roles_and_forbids_score_chasing(monkeypatch):
    context = AgentContext(data={"x": np.arange(6.), "y": np.arange(6.)})
    agent = make_agent(monkeypatch, [VariableRolesTool(context=context)])
    prompt = agent.buffer[0]["content"]
    assert "A request to build, test or repair an evaluator alone is not permission" in prompt
    assert "A low or negative R2" in prompt
    assert "do not perform symbolic regression" in prompt
    assert "Do not run or optimize on external-test labels" in prompt
