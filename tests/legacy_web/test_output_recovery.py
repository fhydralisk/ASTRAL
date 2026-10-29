"""Regression coverage for output limits and terminal model events."""
from sr_harness.api import BaseAPI
from sr_harness.api.base_api import ProviderSampleResult
from sr_harness.core import APICallSample
from sr_harness.web.session import InteractiveSession


class PartialAPI(BaseAPI):
    model_list = ["test"]

    def format_response(self, message, tool_calls, content=None):
        return self._build_response(message, tool_calls, content)

    def _request_sample(self, messages, *, sample_index, callback=None, **kwargs):
        self.prompts.append(messages)
        cut = len(self.prompts) == 1
        content = "Partial scientific explanation" if cut else "Finished"
        self.report_progress(callback, {"type": "delta", "content": content})
        return ProviderSampleResult(
            response=APICallSample(content, finish_reason="length" if cut else "stop"),
            token_usage={"answer": 4096 if cut else 3},
            error="exhausted max_tokens=4096" if cut else None,
        )


def test_data_truncation_settles_response_and_preserves_continuation(tmp_path, monkeypatch):
    api = PartialAPI()
    api.prompts = []
    monkeypatch.setattr(BaseAPI, "create", lambda *args, **kwargs: api)
    session = InteractiveSession(tmp_path)
    session.prepare_data("Prepare the observations")
    session.data_thread.join(5)
    assert not session.data_thread.is_alive()
    assert session.data_state == "completed"
    assert session.data_result["finish_reason"] == "length"
    events = session.data_interaction_manager.get_recent_events()["events"]
    started = [e for e in events if e["kind"] == "assistant_started"]
    settled = [e for e in events if e["kind"] == "assistant_completed"]
    assert len(started) == len(settled) == 1
    assert started[0]["payload"]["response_id"] == settled[0]["payload"]["response_id"]
    assert settled[0]["payload"]["finish_reason"] == "length"
    assert settled[0]["payload"]["usage"]["token"]["answer"] == 4096
    assert not any(e["kind"] == "execution_failed" for e in events)
    session.prepare_data("Continue")
    session.data_thread.join(5)
    assert session.data_state == "completed"
    assert session.data_result["finish_reason"] == "stop"
    assert any(m.get("content") == "Partial scientific explanation" for m in api.prompts[1])
    assert api.prompts[1][-1]["content"] == "Continue"


def test_automatic_budget_defaults_and_explicit_limits(tmp_path):
    session = InteractiveSession(tmp_path)
    for settings in (
        session.settings, session.data_agent_settings, session.evaluator_agent_settings,
    ):
        assert settings["llm_max_tokens"] is None
    for validate in (session.validate_settings, session.validate_data_agent_settings,
                     session.validate_evaluator_agent_settings):
        assert validate({"llm_max_tokens": None})["llm_max_tokens"] is None
        assert validate({"llm_max_tokens": 4096})["llm_max_tokens"] == 4096


def test_interactive_search_pauses_at_boundary_after_truncation():
    from sr_harness.agents.sr_agent_interactive import SRAgentInteractive
    from sr_harness.runtime.interaction_manager import SRInteractionManager

    agent = SRAgentInteractive.__new__(SRAgentInteractive)
    agent.interaction_manager = SRInteractionManager()
    agent.interaction_manager.start_agent_execution()
    agent._forced_interruption_pending = False
    agent._last_response_was_truncated = True
    agent.pause_on_truncated_response = True
    agent.finish_iteration([], R=1, L=1, C=1)
    assert agent.interaction_manager.state == "pausing"


def test_evaluator_truncation_waits_for_continuation(tmp_path, monkeypatch):
    import threading
    import time
    from sr_harness.agents.evaluator_construction_agent import EvaluatorConstructionAgent

    api = PartialAPI()
    api.prompts = []
    monkeypatch.setattr(BaseAPI, "create", lambda *args, **kwargs: api)
    session = InteractiveSession(tmp_path)
    manager = session.evaluator_interaction_manager
    manager.start_agent_execution()
    agent = EvaluatorConstructionAgent(
        llm_provider="openrouter", llm_model="test", context=session.context,
        tools=[], interaction_manager=manager,
    )
    outcomes = []
    thread = threading.Thread(
        target=lambda: outcomes.append(agent.run("Write evaluator")), daemon=True,
    )
    thread.start()
    try:
        deadline = time.monotonic() + 3
        while manager.state != "paused" and time.monotonic() < deadline:
            time.sleep(.01)
        assert manager.state == "paused"
        assert thread.is_alive()
        events = manager.get_recent_events()["events"]
        assert any(e["kind"] == "assistant_completed" and
                   e["payload"].get("finish_reason") == "length" for e in events)
        manager.command("message", "Continue")
        thread.join(3)
        assert not thread.is_alive()
        assert outcomes[0]["message"] == "Finished"
        assert any(m.get("content") == "Partial scientific explanation" for m in api.prompts[1])
    finally:
        if thread.is_alive():
            manager.command("message", "Continue")
            thread.join(3)


def test_truncated_batch_starts_only_samples_that_are_requested(tmp_path):
    from sr_harness.agents.sr_agent_interactive import SRAgentInteractive
    from sr_harness.runtime.interaction_manager import SRInteractionManager
    from sr_harness.parser import BaseParser

    api = PartialAPI()
    api.prompts = []
    manager = SRInteractionManager()
    manager.start_agent_execution()
    agent = SRAgentInteractive(
        llm_provider="unused", llm_model="unused", tools=[], skills=[],
        save_path=str(tmp_path), interaction_manager=manager, local_sample_size=3,
    )
    agent.tool_box = BaseParser.create("openai", tool_list=[])
    agent.api = api
    responses, usage = agent.request_llm(
        [{"role": "user", "content": "Find a formula."}], R=1, L=1, C=1,
    )
    assert len(responses) == len(api.prompts) == 1
    assert responses[0].truncated
    events = manager.get_recent_events()["events"]
    started = [e["payload"]["response_id"] for e in events if e["kind"] == "assistant_started"]
    settled = [e["payload"]["response_id"] for e in events if e["kind"] == "assistant_completed"]
    assert len(started) == 1
    assert started == settled
    agent.finish_iteration([], R=1, L=1, C=1)
    assert manager.state == "pausing"
