from __future__ import annotations

import json
import os

import numpy as np
import pytest

from sr_harness.core import load_context_data
from sr_harness.runtime import Workspace


def test_open_within_workspace_reads_regular_and_internal_symlink(tmp_path, monkeypatch):
    workspace = Workspace(tmp_path / "workspace")
    target = workspace.path / "data" / "value.txt"
    target.parent.mkdir()
    target.write_text("inside", encoding="utf-8")
    os.symlink("data/value.txt", workspace.path / "alias.txt")
    monkeypatch.chdir(workspace.path)

    with workspace.safe_open("alias.txt") as stream:
        assert stream.read() == "inside"


def test_open_within_workspace_rejects_unregistered_external_symlink(tmp_path, monkeypatch):
    workspace = Workspace(tmp_path / "workspace")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    os.symlink(outside, workspace.path / "leak.txt")
    monkeypatch.chdir(workspace.path)

    with pytest.raises(PermissionError):
        workspace.safe_open("leak.txt")


def test_open_within_workspace_reads_registered_mount(tmp_path, monkeypatch):
    workspace = Workspace(tmp_path / "workspace")
    source = tmp_path / "mounted"
    source.mkdir()
    (source / "value.txt").write_text("mounted", encoding="utf-8")
    workspace.mount(source)
    os.symlink(source, workspace.path / "alias")
    monkeypatch.chdir(workspace.path)

    with workspace.safe_open("mounted/value.txt") as stream:
        assert stream.read() == "mounted"
    with workspace.safe_open(workspace.path / "mounted" / "value.txt") as stream:
        assert stream.read() == "mounted"
    with workspace.safe_open("alias/value.txt") as stream:
        assert stream.read() == "mounted"
    resolved = workspace.resolve("mounted/value.txt")
    with workspace.safe_open(resolved) as stream:
        assert stream.read() == "mounted"


def test_open_within_workspace_rejects_symlink_escaping_mount(tmp_path, monkeypatch):
    workspace = Workspace(tmp_path / "workspace")
    source = tmp_path / "mounted"
    source.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    os.symlink(outside, source / "leak.txt")
    workspace.mount(source)
    monkeypatch.chdir(workspace.path)

    with pytest.raises(PermissionError):
        workspace.safe_open("mounted/leak.txt")


def test_relative_path_is_resolved_from_current_working_directory(tmp_path, monkeypatch):
    workspace = Workspace(tmp_path / "workspace")
    (workspace.path / "value.txt").write_text("inside", encoding="utf-8")
    (tmp_path / "value.txt").write_text("outside", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(PermissionError):
        workspace.safe_open("value.txt")


def test_context_data_loader_cannot_follow_external_array_symlink(tmp_path):
    workspace = Workspace(tmp_path / "workspace")
    data_directory = workspace.path / "context.data"
    data_directory.mkdir()
    outside = tmp_path / "secret.npy"
    np.save(outside, np.arange(3))
    os.symlink(outside, data_directory / "x.npy")
    (data_directory / "manifest.json").write_text(
        json.dumps({
            "variables": {
                "x": {"file": "x.npy", "description": "x", "axes": ["sample"]},
            },
            "axes": {
                "sample": {"description": "sample", "size": 3},
            },
        }),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Invalid context.data"):
        load_context_data(data_directory, workspace=workspace)
