"""Actual application-service workflows; model calls are deterministic test doubles."""

import json
import sys

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from sr_harness.api import BaseAPI
from sr_harness.core import APICallSample, APICallSummary, ToolCall
from sr_harness.http.app import create_app
from sr_harness.service import HttpHarnessService, LocalHarnessService

TOKEN = "scientific-test-service-token-123456"


def test_remote_client_implements_the_same_service_contract(tmp_path):
    service = LocalHarnessService(tmp_path)
    with TestClient(create_app(service, token=TOKEN)) as server:

        def exchange(request):
            result = server.request(
                request.method,
                str(request.url),
                headers=dict(request.headers),
                content=request.read(),
            )
            return httpx.Response(
                result.status_code, headers=result.headers, content=result.content
            )

        remote = HttpHarnessService(
            "http://testserver", TOKEN, transport=httpx.MockTransport(exchange)
        )
        try:
            session = remote.create(
                tags={"user_ref": "remote-user"}, idempotency_key="remote-create"
            )
            assert remote.list_sessions({"user_ref": "remote-user"})[0]["id"] == session["id"]
            assert remote.invoke(session["id"], "status", {})["state"] == "idle"
            remote.invoke(
                session["id"],
                "control_command",
                {"action": "message", "message": "baseline"},
                idempotency_key="remote-command",
            )
            assert remote.invoke(session["id"], "control_status", {})["pending_messages"] == 1
        finally:
            remote.close()


@pytest.mark.skipif(sys.platform != "linux", reason="Scientific workspaces require Linux openat2")
def test_files_data_selection_evaluator_and_real_search_loop(tmp_path, monkeypatch):
    service = LocalHarnessService(tmp_path)
    with TestClient(
        create_app(service, token=TOKEN), headers={"Authorization": "Bearer " + TOKEN}
    ) as client:
        sid = client.post(
            "/v1/sessions", json={"tags": {"user_ref": "researcher"}, "idempotency_key": "science"}
        ).json()["id"]
        base = f"/v1/sessions/{sid}"
        session = service._session(sid)
        assert (
            client.put(base + "/workspace/upload?path=notes.txt", content=b"research").status_code
            == 200
        )
        assert client.get(base + "/workspace/download?path=notes.txt").content == b"research"
        assert client.put(
            base + "/workspace/upload?path=../outside.txt", content=b"bad"
        ).status_code in {400, 422}
        directory = session.workspace / "context.data"
        directory.mkdir()
        x = np.arange(1.0, 9.0)
        np.save(directory / "x.npy", x)
        np.save(directory / "y.npy", 2 * x)
        (directory / "manifest.json").write_text(
            json.dumps(
                {
                    "axes": {"sample": {"size": 8, "description": "Observation"}},
                    "variables": {
                        name: {"file": name + ".npy", "axes": ["sample"], "description": name}
                        for name in ["x", "y"]
                    },
                }
            )
        )
        assert client.post(base + "/data/context/reload").status_code == 200
        result = client.put(base + "/data/selection", json={"features": ["x"], "target": "y"})
        assert result.status_code == 200, result.text
        result = client.put(
            base + "/data/descriptions", json={"variable_descriptions": {"x": "Time (s)"}}
        )
        assert result.status_code == 200, result.text
        assert client.get(base + "/data/context").json()["variable_descriptions"]["x"] == "Time (s)"
        assert (
            client.get(base + "/data/context/plot", params={"x": "x", "y": "y"}).status_code == 200
        )
        assert (
            client.post(
                base + "/data/context/heatmap", json={"row": ["sample"], "column": ["x", "y"]}
            ).status_code
            == 200
        )
        evaluator = client.get(base + "/evaluator").json()
        assert evaluator["builtins"]
        assert (
            client.put(
                base + "/evaluator",
                json={"selected": evaluator["selected"], "source": evaluator["source"]},
            ).status_code
            == 200
        )
        client.put(
            base + "/credentials/search",
            json={
                "provider": "compatible",
                "model": "mock",
                "endpoint": "http://localhost:9001/v1",
                "api_key": "test-key-never-persist",
            },
        )

        class FakeAPI:
            def cancel(self):
                return None

            def __call__(self, messages, **kwargs):
                call = ToolCall(name="evaluate_formula", params={"f": "2*x"}, id="test-call")

                def samples():
                    yield APICallSample(
                        content="Evaluate the linear relation",
                        tool_calls=[call],
                        message_extra={
                            "role": "assistant",
                            "content": "Evaluate the linear relation",
                            "tool_calls": [
                                {
                                    "id": call.id,
                                    "type": "function",
                                    "function": {
                                        "name": call.name,
                                        "arguments": json.dumps(call.params),
                                    },
                                }
                            ],
                        },
                    )
                    return {"token_usage": {}, "money_usage": {}}

                return APICallSummary(samples())

        monkeypatch.setattr(BaseAPI, "create", lambda *args, **kwargs: FakeAPI())
        result = client.post(
            base + "/start",
            json={
                "max_refinement_depth": 1,
                "tools": ["evaluate_formula"],
                "skills": [],
                "problem_description": "Find y from x",
            },
            headers={"Idempotency-Key": "one-search"},
        )
        assert result.status_code == 202, result.text
        session.thread.join(20)
        assert not session.thread.is_alive()
        assert session.state == "completed", session.result
        assert client.get(base).json()["topk_records"]
        records = client.get(base + "/records").json()["records"]
        assert records
        assert client.get(base + "/records/" + records[0]["node_id"]).status_code == 200
