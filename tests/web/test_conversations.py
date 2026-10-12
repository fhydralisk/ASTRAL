from __future__ import annotations

import io
import hashlib
import json
import os
import stat
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

import sr_harness.web.conversations as conversation_module
from sr_harness.web.app import create_app
from sr_harness.web.conversations import ConversationRegistry
from sr_harness.web.session import InteractiveSession


def _tree_signature(root):
    signature = []
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        relative = str(path.relative_to(root))
        if path.is_symlink():
            payload = ("symlink", os.readlink(path))
        elif path.is_file():
            payload = ("file", hashlib.sha256(path.read_bytes()).hexdigest())
        else:
            payload = ("directory", None)
        signature.append((relative, stat.S_IMODE(info.st_mode), info.st_mtime_ns, payload))
    return signature


def test_conversations_are_persisted_and_can_be_renamed(tmp_path):
    registry = ConversationRegistry(tmp_path)
    app = create_app(tmp_path, session=registry.session_proxy, conversation_registry=registry)
    with TestClient(app) as client:
        initial = client.get("/api/conversations").json()
        assert len(initial["conversations"]) == 1
        first_id = initial["conversations"][0]["id"]
        client.patch(
            f"/api/conversations/{first_id}", json={"name": "First"},
        )
        created = client.post("/api/conversations", json={"name": "Experiment"}).json()
        renamed = client.patch(
            f"/api/conversations/{created['id']}", json={"name": "Oscillator"},
        ).json()
        assert renamed["name"] == "Oscillator"
        assert len(client.get("/api/conversations").json()["conversations"]) == 2
    payload = json.loads((tmp_path / "conversations.json").read_text())
    assert {item["name"] for item in payload["conversations"]} == {"First", "Oscillator"}
    registry.close()
    restored = ConversationRegistry(tmp_path)
    assert {item["name"] for item in restored.list("browser")["conversations"]} == {
        "First", "Oscillator",
    }
    restored.close()


def test_conversation_registry_rejects_records_from_another_schema(tmp_path):
    (tmp_path / "conversations.json").write_text(json.dumps({
        "version": 1,
        "conversations": [{
            "id": "conversation",
            "name": "Old record",
            "owner_id": None,
            "workspace": "workspaces/conversation",
            "run_dir": "runs/conversation",
            "created_at": "2026-10-09T00:00:00+00:00",
            "updated_at": "2026-10-09T00:00:00+00:00",
        }],
    }))

    with pytest.raises(ValueError, match="invalid record"):
        ConversationRegistry(tmp_path)


def test_conversation_can_be_exported_and_archived_without_deleting_state(tmp_path):
    registry = ConversationRegistry(tmp_path)
    app = create_app(tmp_path, session=registry.session_proxy, conversation_registry=registry)
    with TestClient(app) as client:
        created = client.post("/api/conversations", json={"name": "Export me"}).json()
        conversation_id = created["id"]
        uploaded = client.put("/api/workspace/upload?path=notes.txt", content=b"retained")
        assert uploaded.status_code == 200
        assert client.put("/api/session/provider-credential", json={
            "provider": "openrouter", "api_key": "must-not-be-exported",
        }).status_code == 200
        record = next(item for item in registry._records if item["id"] == conversation_id)
        outside = tmp_path / "outside-export-sentinel.txt"
        outside.write_text("outside-export-sentinel")
        (tmp_path / record["workspace"] / "outside-link").symlink_to(outside)

        exported = client.get(f"/api/conversations/{conversation_id}/export")
        assert exported.status_code == 200
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            assert json.loads(archive.read("conversation.json"))["name"] == "Export me"
            assert archive.read("workspace/notes.txt") == b"retained"
            assert "interactive-session.json" in archive.namelist()
            assert "workspace/outside-link" not in archive.namelist()
            assert not any(name.endswith("/.env") for name in archive.namelist())
            assert b"must-not-be-exported" not in exported.content
            assert b"outside-export-sentinel" not in exported.content

        archived = client.delete(f"/api/conversations/{conversation_id}").json()
        assert archived["archived"] == conversation_id
        assert archived["selected"] != conversation_id
        assert conversation_id not in {
            item["id"] for item in client.get("/api/conversations").json()["conversations"]
        }

    payload = json.loads((tmp_path / "conversations.json").read_text())
    record = next(item for item in payload["conversations"] if item["id"] == conversation_id)
    assert record["archived"] is True
    assert (tmp_path / record["workspace"] / "notes.txt").read_bytes() == b"retained"
    assert conversation_id in registry._sessions
    registry.close()


def test_session_state_is_restored_and_active_work_is_interrupted(tmp_path):
    registry = ConversationRegistry(tmp_path, persist_sessions=True, persistence_interval=60)
    session = registry.default_session
    session.initial_prompt = "Persist this prompt"
    session.settings["ranking_metric"] = "rmse"
    protected = session.workspace / "protected.txt"
    protected.write_text("keep")
    session.workspace_manager.set_locked("protected.txt", True)
    session.sr_interaction_manager.command("message", "queued guidance")
    session.sr_interaction_manager.start_agent_execution()
    session.state = "running"
    session.sr_interaction_manager.publish_event(
        "prompt_added", {"message": {"role": "user", "content": "hello"}},
    )
    registry.persist()
    registry.close()

    restored = ConversationRegistry(tmp_path, persist_sessions=True, persistence_interval=60)
    recovered = restored.default_session
    assert recovered.initial_prompt == "Persist this prompt"
    assert recovered.settings["ranking_metric"] == "rmse"
    assert recovered.workspace_manager.lock_rules == {"protected.txt": True}
    assert recovered.workspace_manager.is_locked("protected.txt") is True
    assert recovered.state == "idle"
    assert recovered.result["status"] == "interrupted"
    events = recovered.sr_interaction_manager.get_recent_events()["events"]
    assert any(event["kind"] == "prompt_added" for event in events)
    assert any(
        event["kind"] == "command_received"
        and event["payload"].get("restored_after_restart") is True
        for event in events
    )
    restored.close()


def test_conversation_storage_separates_workspace_session_and_run_data(tmp_path):
    workspace_dir = tmp_path / "workspace-root"
    save_path = tmp_path / "saved-run"
    registry = ConversationRegistry(
        workspace_dir,
        run_root=save_path / "runs",
        persist_sessions=True,
        persistence_interval=60,
    )
    registry.default_session
    conversation_id = registry.list("browser")["conversations"][0]["id"]
    registry.default_session.initial_prompt = "durable"
    registry.persist()
    snapshot = workspace_dir / "sessions" / conversation_id / "interactive-session.json"
    assert json.loads(snapshot.read_text())["initial_prompt"] == "durable"
    assert registry.default_session.workspace == workspace_dir / "workspaces" / conversation_id
    assert registry.default_session.env_path == (
        workspace_dir / "sessions" / conversation_id / ".env"
    )
    assert registry.default_session.run_dir == save_path / "runs" / conversation_id
    registry.close()


def test_read_only_browsing_stays_transient_but_is_logged(tmp_path):
    registry = ConversationRegistry(tmp_path, isolate_users=True)
    app = create_app(tmp_path, session=registry.session_proxy, conversation_registry=registry)
    with TestClient(app) as client:
        listed = client.get("/api/conversations").json()
        transient_id = listed["selected"]
        assert client.get("/api/session").status_code == 200
        assert client.get("/api/workspace").status_code == 200
        assert not (tmp_path / "conversations.json").exists()
        assert not any((tmp_path / "workspaces").iterdir())
        assert not any((tmp_path / "sessions").iterdir())
        assert not any((tmp_path / "runs").iterdir())

    events = [
        json.loads(line)
        for line in (tmp_path / "conversation-visits.jsonl").read_text().splitlines()
    ]
    assert events == [{
        "timestamp": events[0]["timestamp"],
        "event": "visit_started",
        "visitor_id": events[0]["visitor_id"],
        "transient_id": transient_id,
        "reason": "visit",
    }]
    registry.close()


def test_new_shared_mode_visitor_does_not_attach_to_an_existing_conversation(tmp_path):
    registry = ConversationRegistry(tmp_path)
    existing = registry.create("owner", "Existing")
    app = create_app(tmp_path, session=registry.session_proxy, conversation_registry=registry)
    with TestClient(app) as client:
        listed = client.get("/api/conversations").json()
        assert listed["selected"] != existing["id"]
        assert {item["id"] for item in listed["conversations"]} == {
            existing["id"],
            listed["selected"],
        }
    registry.close()


def test_abandoned_transient_session_is_reclaimed_after_idle_timeout(
    tmp_path,
    monkeypatch,
):
    clock = [100.0]
    monkeypatch.setattr(conversation_module.time, "monotonic", lambda: clock[0])
    registry = ConversationRegistry(tmp_path, isolate_users=True)
    app = create_app(tmp_path, session=registry.session_proxy, conversation_registry=registry)
    with TestClient(app) as first:
        abandoned_id = first.get("/api/conversations").json()["selected"]
        abandoned_root = Path(registry._transient_roots[abandoned_id].name)

    clock[0] += conversation_module.TRANSIENT_IDLE_SECONDS + 1
    with TestClient(app) as second:
        assert second.get("/api/conversations").status_code == 200

    assert abandoned_id not in registry._transient_records
    assert abandoned_id not in registry._sessions
    assert not abandoned_root.exists()
    registry.close()


def test_three_hour_idle_page_keeps_its_transient_session(tmp_path, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(conversation_module.time, "monotonic", lambda: clock[0])
    registry = ConversationRegistry(tmp_path, isolate_users=True)
    app = create_app(tmp_path, session=registry.session_proxy, conversation_registry=registry)
    with TestClient(app) as client:
        conversation_id = client.get("/api/conversations").json()["selected"]
        clock[0] += 3 * 60 * 60
        assert client.get("/api/conversations").json()["selected"] == conversation_id
        assert conversation_id in registry._transient_records
    registry.close()


def test_first_agent_request_after_transient_cache_eviction_needs_no_refresh(
    tmp_path,
    monkeypatch,
):
    clock = [100.0]
    monkeypatch.setattr(conversation_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        InteractiveSession,
        "prepare_data",
        lambda self, message: {"message": message},
    )
    registry = ConversationRegistry(tmp_path, isolate_users=True)
    app = create_app(tmp_path, session=registry.session_proxy, conversation_registry=registry)
    with TestClient(app) as client:
        expired_id = client.get("/api/conversations").json()["selected"]
        clock[0] += conversation_module.TRANSIENT_IDLE_SECONDS + 1
        response = client.post("/api/data/agent", json={"message": "start after sleep"})
        assert response.status_code == 200
        assert response.json() == {"message": "start after sleep"}
        selected = client.get("/api/conversations").json()["selected"]
        assert selected == expired_id

    payload = json.loads((tmp_path / "conversations.json").read_text())
    assert [item["id"] for item in payload["conversations"]] == [selected]
    registry.close()


def test_successful_workspace_change_materializes_transient_conversation(tmp_path):
    registry = ConversationRegistry(tmp_path, isolate_users=True)
    app = create_app(tmp_path, session=registry.session_proxy, conversation_registry=registry)
    with TestClient(app) as client:
        transient_id = client.get("/api/conversations").json()["selected"]
        failed = client.post("/api/workspace/directory", json={})
        assert failed.status_code == 400
        assert not (tmp_path / "conversations.json").exists()

        uploaded = client.put("/api/workspace/upload?path=data.csv", content=b"x,y\n1,2\n")
        assert uploaded.status_code == 200
        payload = json.loads((tmp_path / "conversations.json").read_text())
        assert [item["id"] for item in payload["conversations"]] == [transient_id]
        assert (tmp_path / "workspaces" / transient_id / "data.csv").is_file()

    events = [
        json.loads(line)
        for line in (tmp_path / "conversation-visits.jsonl").read_text().splitlines()
    ]
    assert [event["event"] for event in events] == [
        "visit_started",
        "conversation_persisted",
    ]
    assert events[-1]["reason"] == "workspace_modified"
    assert events[-1]["visitor_id"] == events[0]["visitor_id"]
    registry.close()


def test_rename_and_agent_use_each_materialize_a_transient_conversation(
    tmp_path,
    monkeypatch,
):
    registry = ConversationRegistry(tmp_path, isolate_users=True)
    app = create_app(tmp_path, session=registry.session_proxy, conversation_registry=registry)
    monkeypatch.setattr(
        InteractiveSession,
        "prepare_data",
        lambda self, message: {"message": message},
    )
    with TestClient(app) as client:
        renamed_id = client.get("/api/conversations").json()["selected"]
        assert client.patch(
            f"/api/conversations/{renamed_id}",
            json={"name": "Kept by name"},
        ).status_code == 200

        agent_id = client.post("/api/conversations", json={}).json()["id"]
        response = client.post("/api/data/agent", json={"message": "inspect data"})
        assert response.status_code == 200
        assert response.json() == {"message": "inspect data"}

    payload = json.loads((tmp_path / "conversations.json").read_text())
    assert {item["id"] for item in payload["conversations"]} == {renamed_id, agent_id}
    events = [
        json.loads(line)
        for line in (tmp_path / "conversation-visits.jsonl").read_text().splitlines()
    ]
    reasons = {
        event["transient_id"]: event.get("reason")
        for event in events
        if event["event"] == "conversation_persisted"
    }
    assert reasons == {
        renamed_id: "conversation_renamed",
        agent_id: "agent_used",
    }
    registry.close()


def test_isolate_users_routes_workspace_requests_to_distinct_sessions(tmp_path):
    registry = ConversationRegistry(tmp_path, isolate_users=True)
    app = create_app(tmp_path, session=registry.session_proxy, conversation_registry=registry)
    with TestClient(app) as first, TestClient(app) as second:
        first_conversation = first.get("/api/conversations").json()
        second_conversation = second.get("/api/conversations").json()
        assert first_conversation["selected"] != second_conversation["selected"]

        first_upload = first.put("/api/workspace/upload?path=first.txt", content=b"first")
        second_upload = second.put("/api/workspace/upload?path=second.txt", content=b"second")
        assert first_upload.status_code == 200
        assert second_upload.status_code == 200
        first_files = {entry["name"] for entry in first.get("/api/workspace").json()["entries"]}
        second_files = {entry["name"] for entry in second.get("/api/workspace").json()["entries"]}
        assert first_files == {"first.txt"}
        assert second_files == {"second.txt"}
    registry.close()


def test_read_only_registry_serves_existing_conversations_without_changing_storage(tmp_path):
    writable = ConversationRegistry(tmp_path, persist_sessions=True, persistence_interval=60)
    first = writable.default_session
    first.initial_prompt = "first prompt"
    second_record = writable.create("browser", "Second")
    second = writable._session_for(second_record)
    second.initial_prompt = "second prompt"
    writable.persist()
    writable.close()

    for path in tmp_path.rglob("*"):
        if path.is_file():
            path.chmod(0o444)
    for path in sorted(
        (item for item in tmp_path.rglob("*") if item.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        path.chmod(0o555)
    tmp_path.chmod(0o555)
    before = _tree_signature(tmp_path)

    registry = None
    try:
        registry = ConversationRegistry(
            tmp_path,
            persist_sessions=True,
            persistence_interval=1,
            read_only=True,
        )
        assert registry.persist_sessions is False
        app = create_app(
            tmp_path,
            session=registry.session_proxy,
            conversation_registry=registry,
        )
        with TestClient(app) as client:
            listed = client.get("/api/conversations")
            assert listed.status_code == 200
            payload = listed.json()
            assert payload["read_only"] is True
            assert len(payload["conversations"]) == 2

            selected = client.post(
                f"/api/conversations/{second_record['id']}/select",
                json={},
            )
            assert selected.status_code == 200
            assert client.get("/api/session").json()["initial_prompt"] == "second prompt"

            heatmap = client.post("/api/data/context/heatmap", json={})
            assert heatmap.status_code != 403

            for route in app.routes:
                for method in getattr(route, "methods", None) or ():
                    if method in {"GET", "HEAD", "OPTIONS"}:
                        continue
                    path = route.path.replace("{conversation_id}", second_record["id"])
                    if path.endswith("/select") or path == "/api/data/context/heatmap":
                        continue
                    response = client.request(method, path, json={})
                    assert response.status_code == 403, (method, route.path, response.text)

            session = registry._sessions[second_record["id"]]
            assert session.workspace_manager.read_only is True
            with pytest.raises(PermissionError, match="read-only"):
                session.workspace_manager.open_for_write("blocked.txt", "w")
            with pytest.raises(PermissionError, match="read-only"):
                session.workspace_manager.mount(tmp_path / "conversations.json")
        registry.close()
        registry = None
        assert _tree_signature(tmp_path) == before
    finally:
        if registry is not None:
            registry.close()
        tmp_path.chmod(0o755)
        for path in tmp_path.rglob("*"):
            if path.is_dir():
                path.chmod(0o755)
            elif not path.is_symlink():
                path.chmod(0o644)


def test_read_only_registry_requires_existing_storage(tmp_path):
    missing = tmp_path / "missing"
    with pytest.raises(FileNotFoundError, match="does not exist"):
        ConversationRegistry(missing, read_only=True)
    assert not missing.exists()


def test_read_only_registry_can_isolate_users(tmp_path):
    writable = ConversationRegistry(tmp_path, isolate_users=True)
    first = writable.create("first-client", "First owner's conversation")
    second = writable.create("second-client", "Second owner's conversation")
    writable.close()

    registry = ConversationRegistry(tmp_path, read_only=True, isolate_users=True)
    assert registry.list("first-client")["conversations"] == [{
        key: first[key] for key in ("id", "name", "created_at", "updated_at")
    }]
    assert registry.list("second-client")["conversations"] == [{
        key: second[key] for key in ("id", "name", "created_at", "updated_at")
    }]
    registry.close()
