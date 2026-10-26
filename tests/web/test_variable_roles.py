"""Evaluator-assisted selection shares the manual workbench selection state."""

import hashlib
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from sr_harness.core import load_context_data
from sr_harness.tools import VariableRolesTool
from sr_harness.web.app import create_app
from sr_harness.web.session import EVALUATOR_DEFAULT_TOOLS, InteractiveSession


@pytest.fixture
def workbench(tmp_path):
    session = InteractiveSession(tmp_path / "logs", workspace_path=tmp_path / "work")
    directory = session.workspace / "context.data"
    directory.mkdir()
    manifest = {"variables": {}, "axes": {"sample": {"size": 6, "description": "Observation"}}}
    for name in ["x", "z", "y", "error"]:
        np.save(directory / f"{name}.npy", np.arange(6.) + 1)
        manifest["variables"][name] = {
            "file": f"{name}.npy", "axes": ["sample"], "description": f"Meaning of {name}, units",
        }
    (directory / "manifest.json").write_text(json.dumps(manifest))
    session.context.commit_context_data(load_context_data(directory))
    tool = VariableRolesTool(context=session.context)
    tool.update_roles = session.configure_variable_roles
    with TestClient(create_app(tmp_path / "logs", session=session)) as client:
        yield client, session, tool


def test_inspection_does_not_choose_roles_or_change_data(workbench):
    _, session, tool = workbench
    before = session.context.schema()
    result = tool.execute()
    assert not result["changed"]
    assert result["target"] is None
    assert next(v for v in result["variables"] if v["name"] == "y")["description"] == "Meaning of y, units"
    assert next(v for v in result["variables"] if v["name"] == "sample")["configurable"] is False
    assert session.context.schema() == before


def test_agent_roles_are_visible_editable_and_persisted(workbench, tmp_path):
    client, session, tool = workbench
    directory = session.workspace / "context.data"
    original = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir()}
    result = tool.execute(roles={"y": "target", "x": "feature", "z": "unused", "error": "unused"},
                          user_request="Please configure y as target and x as the only feature.")
    assert result["changed"]
    assert result["target"] == "y" and result["features"] == ["x"]
    assert next(v for v in result["variables"] if v["name"] == "z")["role"] == "unused"
    preview = client.get("/api/data/context").json()
    assert set(preview["columns"]) == {"sample", "x", "z", "y", "error"}
    assert preview["features"] == ["x"]
    assert preview["data"][0]["z"] == 1
    assert client.get("/api/data/context/plot", params={"x": "z", "y": "y"}).status_code == 200
    assert client.post("/api/data/context/heatmap", json={"row": ["sample"], "column": ["z", "y"]}).status_code == 200
    grouped = client.get("/api/data/context/preview", params={"group": "axis:sample"}).json()
    assert "z" in grouped["columns"]
    assert original == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir()}
    original_manifest = json.loads((directory / "manifest.json").read_text())

    # Manual edits can re-enable an unused variable, and the agent sees that edit.
    response = client.put("/api/data/selection", json={"target": "y", "features": ["z"]})
    assert response.status_code == 200, response.text
    assert tool.execute()["features"] == ["z"]
    restored = InteractiveSession(tmp_path / "restored", workspace_path=session.workspace)
    restored.restore_persistent_state(session.export_persistent_state())
    assert restored.context.target == "y"
    assert restored.context.feature_names() == ("z",)
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == original[p.name]
               for p in directory.glob("*.npy"))
    assert json.loads((directory / "manifest.json").read_text()) == original_manifest


@pytest.mark.parametrize("roles", [
    {"not_a_variable": "target"}, {"x": "target", "y": "target"},
    {"y": "wrong_role"}, {"sample": "target"},
])
def test_bad_role_edits_are_atomic(workbench, roles):
    _, session, tool = workbench
    before = session.context.schema()
    result = tool(roles=roles, user_request="Configure the variables.")
    assert not result.ok
    assert session.context.schema() == before


def test_writes_require_a_request_and_a_safe_session(workbench, monkeypatch):
    _, session, tool = workbench
    roles = {"y": "target"}
    before = session.context.schema()
    assert not tool(roles=roles).ok
    session.data_state = "running"
    assert not tool(roles=roles, user_request="Configure variables.").ok
    session.data_state = "completed"
    session.state = "running"
    monkeypatch.setattr(session.sr_interaction_manager, "status", lambda: {"interaction_state": "running"})
    assert not tool(roles=roles, user_request="Configure variables.").ok
    assert session.context.schema() == before
    monkeypatch.setattr(session.sr_interaction_manager, "status", lambda: {"interaction_state": "paused"})
    assert tool(roles=roles, user_request="Configure variables.").ok


def test_default_tool_upgrade_does_not_override_custom_tool_choices(workbench, tmp_path):
    _, session, _ = workbench
    snapshot = session.export_persistent_state()
    snapshot.pop("context_features")  # Historical snapshots remain loadable.
    snapshot["evaluator_agent_settings"]["tools"] = [
        name for name in EVALUATOR_DEFAULT_TOOLS if name != "configure_variable_roles"
    ]
    restored = InteractiveSession(tmp_path / "restored", workspace_path=session.workspace)
    restored.restore_persistent_state(snapshot)
    assert restored.evaluator_agent_settings["tools"] == list(EVALUATOR_DEFAULT_TOOLS)
    snapshot["evaluator_agent_settings"]["tools"] = ["read_source", "validate_evaluator"]
    restored.restore_persistent_state(snapshot)
    assert restored.evaluator_agent_settings["tools"] == ["read_source", "validate_evaluator"]
