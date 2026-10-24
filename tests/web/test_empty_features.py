"""Empty feature selections use the same API as ordinary regression tasks."""
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from sr_harness.core import load_context_data
from sr_harness.evaluator import DefaultEvaluator
from sr_harness.web.app import create_app
from sr_harness.web.session import InteractiveSession


def save_arrays(session, arrays):
    directory = session.workspace / "context.data"
    directory.mkdir(exist_ok=True)
    manifest = {"axes": {"sample": {"size": 6, "description": "Observation"}}, "variables": {}}
    for name, values in arrays.items():
        np.save(directory / f"{name}.npy", values)
        manifest["variables"][name] = {"file": f"{name}.npy", "axes": ["sample"], "description": name}
    (directory / "manifest.json").write_text(json.dumps(manifest))
    session.context.commit_context_data(load_context_data(directory))
    session.context.target = "y"


@pytest.fixture
def workbench(tmp_path, monkeypatch):
    session = InteractiveSession(tmp_path / "logs", workspace_path=tmp_path / "work")
    save_arrays(session, {"x": np.arange(6.), "y": np.linspace(.1, .8, 6)})
    seen = []

    def capture_run(X, y, description):
        seen.append({"X": X, "y": y, "description": description,
                     "user_prompt": session.prompt_overrides.get("user")})
        session.state = "completed"

    monkeypatch.setattr(session, "_run", capture_run)
    with TestClient(create_app(tmp_path / "logs", session=session)) as client:
        yield client, session, seen


def start(client, session, seen, **payload):
    response = client.post("/api/session/start", json={"target": "y", **payload})
    assert response.status_code == 200, response.text
    session.thread.join(timeout=2)
    assert not session.thread.is_alive()
    assert len(seen) == 1
    return seen[0]


def test_empty_selection_uses_regular_api_end_to_end(workbench):
    client, session, seen = workbench
    assert type(session.context.evaluator) is DefaultEvaluator
    assert not (session.workspace / "discovery_contract.json").exists()
    selected = client.put("/api/data/selection", json={"target": "y", "features": []})
    assert selected.status_code == 200, selected.text
    assert selected.json()["features"] == []
    assert session.context.feature_names() == ()
    prompts = client.post("/api/data/prompts", json={"target": "y", "features": []})
    assert prompts.status_code == 200, prompts.text
    assert "Feature names: []" in prompts.json()["user_prompt"]
    actual = start(client, session, seen, features=[], user_prompt="Use the selected data.")
    assert actual["X"] == {}
    assert list(actual["y"]) == ["y"]
    np.testing.assert_array_equal(actual["y"]["y"], np.linspace(.1, .8, 6))
    assert actual["user_prompt"] == "Use the selected data."


def test_explicit_empty_features_do_not_fall_back_to_current_features(workbench):
    client, session, seen = workbench
    assert session.context.feature_names() == ("x",)
    preview = client.post("/api/data/prompts", json={"target": "y", "features": []})
    assert preview.status_code == 200, preview.text
    assert "Feature names: []" in preview.json()["user_prompt"]
    assert session.context.feature_names() == ("x",)  # Preview is read-only.
    actual = start(client, session, seen, features=[])
    assert actual["X"] == {}


def test_omitting_features_preserves_existing_current_selection_default(workbench):
    client, session, seen = workbench
    preview = client.post("/api/data/prompts", json={"target": "y"})
    assert preview.status_code == 200, preview.text
    assert "Feature names: ['x']" in preview.json()["user_prompt"]
    actual = start(client, session, seen)
    assert list(actual["X"]) == ["x"]
    np.testing.assert_array_equal(actual["X"]["x"], np.arange(6.))


@pytest.mark.parametrize("endpoint", ["/api/data/prompts", "/api/session/start"])
@pytest.mark.parametrize("features", [None, "x", ["y"]])
def test_empty_feature_support_still_rejects_invalid_selection(workbench, endpoint, features):
    client, session, seen = workbench
    response = client.post(endpoint, json={"target": "y", "features": features})
    assert response.status_code == 400, response.text
    assert seen == []
    assert session.state == "idle"


@pytest.mark.parametrize("features", [None, "x"])
def test_selection_endpoint_rejects_non_list_features(workbench, features):
    client, session, _ = workbench
    response = client.put("/api/data/selection", json={"target": "y", "features": features})
    assert response.status_code == 400, response.text
    assert session.context.feature_names() == ("x",)
