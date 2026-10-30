"""Large single events must not permanently block the timeline cursor."""

import json

import pytest
from sr_harness.service import ServiceError as HTTPException
from fastapi.testclient import TestClient

from sr_harness.runtime import SRInteractionManager
from sr_harness.service import events as responses
from sr_harness.http.app import create_app
from sr_harness.service import LocalHarnessService


@pytest.fixture
def timeline(tmp_path):
    service = LocalHarnessService(tmp_path)
    sid = service.create(tags={}, idempotency_key="timeline")["id"]
    session = service._session(sid)
    with TestClient(
        create_app(service, token="timeline-test-token-1234567890"),
        headers={"Authorization": "Bearer timeline-test-token-1234567890"},
    ) as client:
        original_get = client.get
        client.get = lambda path, **kwargs: original_get(
            f"/v1/sessions/{sid}" + path.replace("/api", "", 1), **kwargs
        )
        client.timeline_session = session
        yield (
            client,
            {
                "/api/control/events": session.sr_interaction_manager,
                "/api/data/agent/events": session.data_interaction_manager,
                "/api/evaluator/agent/events": session.evaluator_interaction_manager,
            },
        )


def collect(client, endpoint):
    result, cursor, sizes = [], 0, []
    for _ in range(20):
        response = client.get(endpoint, params={"after_seq": cursor})
        assert response.status_code == 200, response.text
        sizes.append(len(response.content))
        batch = response.json()
        responses.check_response_budget(batch)
        if not batch["events"]:
            return result, sizes
        assert batch["events"][-1]["seq"] > cursor
        if len(batch["events"]) == 32:
            assert batch["has_more"]
        result.extend(batch["events"])
        cursor = result[-1]["seq"]
    pytest.fail("Event cursor did not reach the end")


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/control/events",
        "/api/data/agent/events",
        "/api/evaluator/agent/events",
    ],
)
def test_realistic_node_heavy_context_advances_and_downloads_losslessly(timeline, endpoint):
    client, managers = timeline
    manager = managers[endpoint]
    first = manager.publish_event("prompt_added", {"message": {"role": "user", "content": "start"}})
    messages = [{"role": "system", "content": "Scientific workflow"}]
    messages += [{"role": "tool", "content": "diagnostics", "samples": list(range(210_000))}]
    messages += [{"role": "user", "content": f"turn {index}"} for index in range(10)]
    large = manager.publish_event("context", {"turn": 19, "messages": messages})
    last = manager.publish_event(
        "assistant_completed", {"content": "Processing continues", "turn": 19}
    )
    original = json.dumps(manager.export_state(), ensure_ascii=False)
    with pytest.raises(HTTPException) as failure:
        responses.check_response_budget({"events": [large]})
    assert failure.value.status_code == 413

    events, sizes = collect(client, endpoint)
    assert [event["seq"] for event in events] == [first["seq"], large["seq"], last["seq"]]
    assert events[0] == first and events[-1] == last
    preview = events[1]
    assert preview["transport"]["truncated"] is True
    assert preview["transport"]["original_message_count"] == len(messages)
    assert preview["payload"]["turn"] == 19
    assert preview["payload"]["messages"][0]["role"] == "system"
    assert preview["payload"]["messages"][-1]["content"] == "turn 9"
    assert max(sizes) <= responses.MAX_RESPONSE_BYTES
    assert json.dumps(manager.export_state(), ensure_ascii=False) == original

    downloaded = client.get(endpoint + "/" + str(large["seq"]))
    assert downloaded.status_code == 200
    assert downloaded.json() == large
    assert "attachment" in downloaded.headers["content-disposition"]
    assert json.dumps(manager.export_state(), ensure_ascii=False) == original


def test_oversized_unicode_and_escaped_text_respects_wire_byte_limit(timeline, monkeypatch):
    client, managers = timeline
    monkeypatch.setattr(responses, "MAX_RESPONSE_BYTES", 2000)
    manager = managers["/api/data/agent/events"]
    large = manager.publish_event(
        "assistant_completed",
        {
            "response_id": "completion-id",
            "turn": 3,
            "content": '天文观测\\"\n' * 50_000,
        },
    )
    final = manager.publish_event("execution_completed", {"status": "completed"})
    events, sizes = collect(client, "/api/data/agent/events")
    assert [event["seq"] for event in events] == [large["seq"], final["seq"]]
    assert events[0]["payload"]["response_id"] == "completion-id"
    assert events[0]["payload"]["turn"] == 3
    assert max(sizes) <= 2000
    assert client.get(f"/api/data/agent/events/{large['seq']}").json() == large


def test_deep_payload_preview_does_not_change_full_event(timeline):
    client, managers = timeline
    nested = "leaf"
    for _ in range(90):
        nested = [nested]
    event = managers["/api/control/events"].publish_event(
        "tool_completed",
        {
            "call": {"id": "call-1", "name": "workspace_code_executor"},
            "result": {"ok": True, "result_str": "done", "result": nested},
        },
    )
    previews, _ = collect(client, "/api/control/events")
    assert previews[0]["transport"]["truncated"]
    assert previews[0]["payload"]["call"]["id"] == "call-1"
    assert previews[0]["payload"]["result"]["result_str"] == "done"
    assert client.get(f"/api/control/events/{event['seq']}").json() == event


def test_one_large_message_is_also_bounded_without_dropping_the_event(timeline):
    client, managers = timeline
    event = managers["/api/data/agent/events"].publish_event(
        "context",
        {
            "turn": 2,
            "messages": [{"role": "tool", "content": {"samples": list(range(210_000))}}],
        },
    )
    previews, _ = collect(client, "/api/data/agent/events")
    assert previews[0]["seq"] == event["seq"]
    assert previews[0]["transport"]["truncated"]
    assert len(previews[0]["payload"]["messages"][0]["content"]["samples"]) < 210_000
    assert client.get(f"/api/data/agent/events/{event['seq']}").json() == event


def test_missing_or_discarded_download_does_not_return_another_event(timeline):
    client, _ = timeline
    manager = SRInteractionManager(event_capacity=2)
    client.timeline_session.sr_interaction_manager = manager
    for index in range(3):
        manager.publish_event("command_received", {"action": "pause", "index": index})
    for sequence in [-1, 0, 1, 1000]:
        assert client.get(f"/api/control/events/{sequence}").status_code == 404
    assert client.get("/api/control/events/2").json()["payload"]["index"] == 1


def test_download_requires_service_authentication(timeline):
    client, managers = timeline
    managers["/api/control/events"].publish_event("context", {"messages": []})
    assert client.get("/api/control/events/1", headers={"Authorization": ""}).status_code == 401
