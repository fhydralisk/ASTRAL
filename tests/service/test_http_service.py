import io
import threading
import time

import pytest
from fastapi.testclient import TestClient

from sr_harness.http.app import create_app
from sr_harness.service import LocalHarnessService, ServiceError
from sr_harness.service.environment import StrictEnvironment
from sr_harness.api import BaseAPI
from sr_harness.runtime import InteractionManager

TOKEN = "test-internal-service-token-12345678"


@pytest.fixture
def service(tmp_path):
    service = LocalHarnessService(tmp_path)
    yield service
    service.close()


@pytest.fixture
def client(service):
    with TestClient(
        create_app(service, token=TOKEN), headers={"Authorization": "Bearer " + TOKEN}
    ) as client:
        yield client


def test_auth_explicit_session_and_contract(client):
    assert client.get("/health", headers={"Authorization": ""}).status_code == 200
    assert client.get("/v1/sessions", headers={"Authorization": ""}).status_code == 401
    assert client.get("/api/session").status_code == 404
    result = client.post(
        "/v1/sessions", json={"tags": {"user_ref": "one"}, "idempotency_key": "create"}
    )
    assert result.status_code == 201
    sid = result.json()["id"]
    assert (
        client.post(
            "/v1/sessions", json={"tags": {"user_ref": "one"}, "idempotency_key": "create"}
        ).json()["id"]
        == sid
    )
    assert (
        client.post("/v1/sessions", json={"tags": {}, "idempotency_key": "create"}).status_code
        == 409
    )
    assert client.get(f"/v1/sessions/{sid}").status_code == 200
    assert client.get("/v1/sessions/" + "0" * 32).status_code == 404
    assert "sr_harness_client" not in client.cookies
    assert client.patch(f"/v1/sessions/{sid}", json={"archived": True}).status_code == 200
    assert client.post(f"/v1/sessions/{sid}/settings", json={}).status_code == 409
    assert len(client.get("/openapi.json").json()["paths"]) >= 40


def test_credentials_are_role_scoped_and_never_persisted(client, service, tmp_path, monkeypatch):
    sid = client.post("/v1/sessions", json={"tags": {}, "idempotency_key": "key-test"}).json()["id"]
    monkeypatch.setenv("COMPATIBLE_API_KEY", "process-key-must-not-be-used")
    for role in ("data", "search", "evaluator"):
        result = client.put(
            f"/v1/sessions/{sid}/credentials/{role}",
            json={
                "provider": "compatible",
                "model": "test-model",
                "endpoint": "http://localhost:9000/v1",
                "api_key": f"role-secret-{role}-123456789",
            },
        )
        assert result.status_code == 204, result.text
    session = service._session(sid)
    assert (
        session.context.args.agent_environments["data"]["COMPATIBLE_API_KEY"]
        != session.context.args.agent_environments["search"]["COMPATIBLE_API_KEY"]
    )
    service._checkpoint(sid)
    assert not list(tmp_path.rglob(".env"))
    for file in tmp_path.rglob("*.json"):
        assert "role-secret" not in file.read_text(encoding="utf-8")
    exported = client.get(f"/v1/sessions/{sid}/export")
    assert exported.status_code == 200
    import zipfile

    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        assert not any(".env" in name for name in archive.namelist())
        assert all(b"role-secret" not in archive.read(name) for name in archive.namelist())
    service.close()
    recovered = LocalHarnessService(tmp_path)
    try:
        assert not recovered._session(sid).context.args.agent_environments["data"]
    finally:
        recovered.close()


def test_command_idempotency_and_events(client):
    sid = client.post("/v1/sessions", json={"tags": {}, "idempotency_key": "command-test"}).json()[
        "id"
    ]
    url = f"/v1/sessions/{sid}/control/command"
    headers = {"Idempotency-Key": "guidance-one"}
    body = {"action": "message", "message": "Use a linear baseline", "role": "search"}
    first = client.post(url, json=body, headers=headers)
    assert first.status_code == 202
    assert client.post(url, json=body, headers=headers).json() == first.json()
    assert (
        client.post(url, json={**body, "message": "different"}, headers=headers).status_code == 409
    )
    assert first.json()["operation_id"] == "guidance-one"
    receipt = client.get(f"/v1/sessions/{sid}/operations/guidance-one")
    assert receipt.status_code == 200
    assert receipt.json()["operation_id"] == "guidance-one"
    assert client.get(f"/v1/sessions/{sid}/operations/missing").status_code == 404
    assert client.get(f"/v1/sessions/{sid}/control/status").json()["pending_messages"] == 1


def test_restore_interrupted_state_and_pending_command(service, tmp_path):
    sid = service.create(tags={}, idempotency_key="restore")["id"]
    session = service._session(sid)
    session.state = "running"
    service._checkpoint(sid)
    other = LocalHarnessService(tmp_path)
    try:
        state = other.invoke(sid, "status", {})
        assert state["state"] == "idle"
        assert state["result"]["status"] == "interrupted"
    finally:
        other.close()


def test_resume_and_stop_at_safe_boundary():
    manager = InteractionManager()
    manager.start_agent_execution()
    manager.command("pause")
    finished = threading.Event()

    def worker():
        with manager.wait():
            finished.set()

    thread = threading.Thread(target=worker)
    thread.start()
    for _ in range(100):
        if manager.state == "paused":
            break
        time.sleep(0.005)
    assert not finished.is_set()
    manager.command("resume")
    thread.join(2)
    assert finished.is_set()
    manager.command("stop")
    with pytest.raises(InterruptedError):
        with manager.wait():
            pass


def test_strict_credentials_do_not_fall_back(monkeypatch):
    monkeypatch.setenv("COMPATIBLE_API_KEY", "unexpected")
    api = BaseAPI.create("compatible", model="model", environment=StrictEnvironment())
    with pytest.raises(KeyError):
        api.get_env("COMPATIBLE_API_KEY", required=True)


def test_capacity_is_per_user_and_includes_paused(service, monkeypatch):
    first = service.create(tags={"user_ref": "same"}, idempotency_key="first")["id"]
    second = service.create(tags={"user_ref": "same"}, idempotency_key="second")["id"]
    third = service.create(tags={"user_ref": "other"}, idempotency_key="third")["id"]
    service.per_user_tasks = 1
    for sid in (first, second, third):
        session = service._session(sid)
        session.context.args.agent_environments["data"]["_configured"] = "1"

    def execute(session, op, parameters):
        session.data_interaction_manager._state = "paused"
        return {"state": "paused"}

    monkeypatch.setattr(service, "_execute", execute)
    service.invoke(first, "prepare_data", {"payload": {"message": "test"}})
    with pytest.raises(ServiceError) as error:
        service.invoke(second, "prepare_data", {"payload": {"message": "test"}})
    assert error.value.status_code == 429
    assert service.invoke(third, "prepare_data", {"payload": {"message": "test"}})


def test_scientific_service_has_no_http_or_cookie_imports():
    import ast
    from pathlib import Path

    root = Path(__file__).parents[2] / "src/sr_harness/service"
    for file in root.glob("*.py"):
        tree = ast.parse(file.read_text(encoding="utf-8"))
        imports = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        assert not any(x.startswith(("fastapi", "starlette")) for x in imports), file


def test_started_operation_with_response_failure_is_not_executed_twice(service, monkeypatch):
    from sr_harness.service.session import SessionStartError

    sid = service.create(tags={}, idempotency_key="response-failure")["id"]
    calls = []

    def execute(*args):
        calls.append(True)
        raise SessionStartError("response failed", run_id="test", started=True)

    monkeypatch.setattr(service, "_execute", execute)
    with pytest.raises(SessionStartError):
        service.invoke(
            sid, "control_command", {"action": "message", "message": "test"}, idempotency_key="once"
        )
    result = service.invoke(
        sid, "control_command", {"action": "message", "message": "test"}, idempotency_key="once"
    )
    assert result["operation_id"] == "once"
    assert len(calls) == 1


def test_upload_stream_is_not_subject_to_json_body_limit(client, service, monkeypatch):
    sid = service.create(tags={}, idempotency_key="large-upload")["id"]
    monkeypatch.setattr(service, "upload", lambda sid, path, stream: {"size": len(stream.read())})
    payload = b"x" * (5 * 1024 * 1024)
    result = client.put(f"/v1/sessions/{sid}/workspace/upload?path=data.csv", content=payload)
    assert result.status_code == 200
    assert result.json()["size"] == len(payload)
    assert client.post(f"/v1/sessions/{sid}/settings", content=payload).status_code == 413


def test_nested_model_tools_receive_the_calling_agents_strict_environment(service, monkeypatch):
    from sr_harness.tools.call_llm import LLMTool
    from sr_harness.core import APICallSample, APICallSummary

    sid = service.create(tags={}, idempotency_key="nested-key")["id"]
    session = service._session(sid)
    environment = StrictEnvironment({"COMPATIBLE_API_KEY": "data-only-key"})
    session.context.args.agent_environments["data"] = environment
    captured = []

    class FakeAPI:
        def __call__(self, *args, **kwargs):
            def samples():
                yield APICallSample(content="ok")
                return {
                    "ok": True,
                    "error": None,
                    "token_usage": {},
                    "money_usage": {},
                    "extra": {},
                }

            return APICallSummary(samples())

    def create(*args, **kwargs):
        captured.append(kwargs["environment"])
        return FakeAPI()

    monkeypatch.setattr(BaseAPI, "create", create)
    tool = LLMTool(context=session.context)
    tool.agent_role = "data"
    assert tool.execute("compatible", "model", "test")["content"] == "ok"
    assert captured == [environment]
    assert captured[0].strict
