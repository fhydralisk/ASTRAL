"""All default scientific agents describe the same user-facing division of work."""

import numpy as np

from sr_harness.agents.data_preparation_agent import DataPreparationAgent
from sr_harness.agents.evaluator_construction_agent import EvaluatorConstructionAgent
from sr_harness.agents.sr_agent import SRAgent
from sr_harness.agents.sr_agent_interactive import SRAgentInteractive
from sr_harness.api import BaseAPI
from sr_harness.core import AgentContext
from sr_harness.runtime import InteractionManager
from sr_harness.tools import VariableRolesTool


def test_all_default_system_prompts_explain_responsibilities_and_handoffs(monkeypatch):
    monkeypatch.setattr(BaseAPI, "create", lambda *args, **kwargs: object())
    context = AgentContext(data={"x": np.arange(6.), "y": np.arange(6.)}, target="y")
    data = DataPreparationAgent(
        llm_provider="openrouter", llm_model="test", context=context,
        tools=["workspace_shell"], skills=[], interaction_manager=InteractionManager(),
    )
    evaluator = EvaluatorConstructionAgent(
        llm_provider="openrouter", llm_model="test", context=context,
        tools=[VariableRolesTool(context=context)], interaction_manager=InteractionManager(),
    )
    prompts = [data.buffer[0]["content"], evaluator.buffer[0]["content"]]
    for cls in [SRAgent, SRAgentInteractive]:
        agent = object.__new__(cls)
        agent.max_refinement_depth = 10
        prompts.append(agent.create_initial_system_prompt([]))
    for prompt in prompts:
        assert "working together on an astronomical discovery task" in prompt
        assert "working together on a symbolic regression task" not in prompt
        assert "Data Preparation Agent" in prompt
        assert "Evaluator Construction Agent" in prompt
        assert "Symbolic Regression Agent" in prompt
        assert "name the responsible agent" in prompt
        assert "only when the user explicitly asks" in prompt
        assert "Computational file chunking is data preparation" in prompt
        assert "not pipes or &&" not in prompt

    for prompt in prompts[:2]:
        assert "supports documented commands and | pipelines" in prompt
    for prompt in prompts[2:]:
        assert "workspace_shell" not in prompt
        assert "workspace_code_executor" not in prompt
