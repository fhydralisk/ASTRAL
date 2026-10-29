"""A failed model call must settle its matching active response."""
from sr_harness.api import BaseAPI
from sr_harness.api.base_api import ProviderSampleResult
from sr_harness.core import APICallSample
from sr_harness.web.session import InteractiveSession


class FailedAPI(BaseAPI):
    model_list = ["test"]

    def format_response(self, message, tool_calls, content=None):
        return self._build_response(message, tool_calls, content)

    def _request_sample(self, messages, *, sample_index, callback=None, **kwargs):
        return ProviderSampleResult(response=APICallSample(""), error="Provider unavailable")


def test_data_api_failure_settles_active_response(tmp_path, monkeypatch):
    api = FailedAPI()
    monkeypatch.setattr(BaseAPI, "create", lambda *args, **kwargs: api)
    session = InteractiveSession(tmp_path)
    session.prepare_data("Prepare observations")
    session.data_thread.join(5)
    events = session.data_interaction_manager.get_recent_events()["events"]
    started = next(e for e in events if e["kind"] == "assistant_started")
    failed = next(e for e in events if e["kind"] == "assistant_failed")
    assert started["payload"]["response_id"] == failed["payload"]["response_id"]
    assert failed["payload"]["error"] == "Provider unavailable"
    assert session.data_state == "failed"
