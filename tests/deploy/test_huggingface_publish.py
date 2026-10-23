"""Release publishing cannot leak local work or remove unrelated Space content."""
import importlib.util
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest


MODULE_PATH = Path(__file__).resolve().parents[2] / "deploy/huggingface/publish.py"
spec = importlib.util.spec_from_file_location("publish_huggingface", MODULE_PATH)
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


def git(repository, *args):
    return subprocess.check_output(["git", *args], cwd=repository, text=True).strip()


@pytest.fixture
def repository(tmp_path):
    git(tmp_path, "init", "--quiet")
    git(tmp_path, "config", "user.name", "Release test")
    git(tmp_path, "config", "user.email", "release@example.invalid")
    files = {
        "Dockerfile": "FROM python:3.12\n",
        ".dockerignore": ".git\n",
        "LICENSE": "MIT\n",
        "pyproject.toml": '[project]\nname = "test"\nversion = "1.0.7"\n',
        "README.md": "# GitHub introduction\n",
        "deploy/huggingface/README.space.md": "---\nsdk: docker\napp_port: 8000\n---\n",
        "src/package/app.py": "VERSION = 'committed'\n",
        "scratch/private.txt": "experiment: do not upload\n",
        "outputs/data.csv": "private,observations\n",
        "playground/trial.py": "print('experiment')\n",
    }
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "Release source")
    return tmp_path


def test_snapshot_uses_requested_commit_and_space_readme(repository):
    revision = git(repository, "rev-parse", "HEAD")
    (repository / "src/package/app.py").write_text("VERSION = 'new commit'\n")
    git(repository, "commit", "--quiet", "-am", "Later source")
    (repository / "src/package/app.py").write_text("VERSION = 'dirty local change'\n")
    (repository / "src/package/secret.env").write_text("LOCAL_SECRET=not-for-release\n")
    git(repository, "add", "src/package/secret.env")
    (repository / "src/package/untracked.py").write_text("print('local trial')\n")

    commit, version, files = publisher.source_snapshot(repository, revision)

    assert commit == revision
    assert version == "1.0.7"
    assert files["src/package/app.py"] == b"VERSION = 'committed'\n"
    assert files["README.md"].startswith(b"---\nsdk: docker\n")
    assert set(files) == {
        "Dockerfile", ".dockerignore", "LICENSE", "pyproject.toml", "README.md",
        "src/package/app.py",
    }


def test_publish_updates_managed_source_atomically_and_preserves_other_files(repository):
    from huggingface_hub import CommitOperationAdd, CommitOperationDelete

    calls = []
    class API:
        def repo_info(self, repo_id, **kwargs):
            assert repo_id == "owner/space"
            assert kwargs == {"repo_type": "space", "revision": "main"}
            return SimpleNamespace(sha="remote-parent")

        def list_repo_files(self, repo_id, **kwargs):
            assert kwargs["revision"] == "remote-parent"
            return [
                "README.md", "src/package/app.py", "src/package/deleted.py",
                ".gitattributes", "data/user.csv", "custom-notes.md", "src-backup/keep.py",
            ]

        def create_commit(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(oid="published")

    result = publisher.publish(
        repository=repository, revision="HEAD", repo_id="owner/space", token="fake", api=API(),
    )
    assert result.oid == "published"
    assert len(calls) == 1
    call = calls[0]
    assert call["parent_commit"] == "remote-parent"
    assert call["revision"] == "main"
    assert call["repo_type"] == "space"
    assert "v1.0.7" in call["commit_message"]
    assert git(repository, "rev-parse", "HEAD") in call["commit_description"]
    additions = {op.path_in_repo: op.path_or_fileobj for op in call["operations"]
                 if isinstance(op, CommitOperationAdd)}
    deletions = [op.path_in_repo for op in call["operations"]
                 if isinstance(op, CommitOperationDelete)]
    assert deletions == ["src/package/deleted.py"]
    assert additions["README.md"].startswith(b"---\nsdk: docker\n")
    assert not {"data/user.csv", ".gitattributes", "custom-notes.md"} & additions.keys()


@pytest.mark.parametrize("token", [None, "", "   "])
def test_missing_credential_performs_no_git_or_network_operations(monkeypatch, token):
    def unexpected(*args, **kwargs):
        pytest.fail("Deployment attempted work before validating its credential")
    monkeypatch.setattr(publisher, "source_snapshot", unexpected)
    with pytest.raises(ValueError, match="authentication"):
        publisher.publish(
            repository=Path("/nonexistent"), revision="HEAD", repo_id="owner/space", token=token,
        )


def test_dry_run_needs_no_credential_or_network(repository, monkeypatch, capsys):
    monkeypatch.setattr(publisher, "REPOSITORY", repository)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    publisher.main(["--dry-run"])
    output = capsys.readouterr().out
    assert '"version": "1.0.7"' in output
    assert "src/package/app.py" in output
    assert "scratch/private.txt" not in output


def test_wait_requires_finished_build_and_healthy_expected_version(monkeypatch):
    states = iter([
        ("RUNNING", "old-commit"), ("RUNNING_BUILDING", "new-commit"),
        ("RUNNING", "new-commit"), ("RUNNING", "new-commit"),
    ])
    responses = iter([
        {"version": "1.0.7"}, {"status": "ok"},
        {"version": "1.0.7"}, {"status": "ok"},
        {"version": "1.0.6"}, {"status": "ok"},
        {"version": "1.0.7"}, {"status": "ok"},
    ])
    probes = []
    def get_json(url):
        probes.append(url)
        return next(responses)
    monkeypatch.setattr(publisher, "read_app_json", get_json)
    monkeypatch.setattr(publisher.time, "sleep", lambda seconds: None)
    def runtime(repo):
        stage, commit = next(states)
        return SimpleNamespace(stage=stage, raw={"sha": commit})
    api = SimpleNamespace(get_space_runtime=runtime)
    publisher.wait_for_deployment(
        repo_id="owner/space", version="1.0.7", app_url="https://app.example/",
        expected_commit="new-commit", token="fake", api=api,
    )
    assert probes == ["https://app.example/api/version", "https://app.example/health"] * 4


@pytest.mark.parametrize("stage", ["BUILD_ERROR", "RUNTIME_ERROR", "CONFIG_ERROR"])
def test_wait_fails_immediately_on_space_errors(stage):
    api = SimpleNamespace(get_space_runtime=lambda repo: SimpleNamespace(
        stage=stage, raw={"sha": "new-commit"},
    ))
    with pytest.raises(RuntimeError, match=stage):
        publisher.wait_for_deployment(
            repo_id="owner/space", version="1.0.7", app_url="https://app.example",
            expected_commit="new-commit", token="fake", api=api,
        )


def test_wait_times_out_instead_of_accepting_healthy_old_version(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(publisher.time, "monotonic", lambda: clock[0])
    def sleep(seconds):
        clock[0] += seconds
    monkeypatch.setattr(publisher.time, "sleep", sleep)
    monkeypatch.setattr(publisher, "read_app_json", lambda url: (
        {"version": "1.0.6"} if url.endswith("/api/version") else {"status": "ok"}
    ))
    api = SimpleNamespace(get_space_runtime=lambda repo: SimpleNamespace(
        stage="RUNNING", raw={"sha": "new-commit"},
    ))
    with pytest.raises(TimeoutError, match="did not serve SRHarness 1.0.7"):
        publisher.wait_for_deployment(
            repo_id="owner/space", version="1.0.7", app_url="https://app.example",
            expected_commit="new-commit", token="fake", timeout=30, api=api,
        )


@pytest.mark.parametrize("event,version,expected", [
    ("push", "1.0.7", "false"),
    ("push", "1.0.8", "true"),
    ("workflow_dispatch", "1.0.7", "true"),
])
def test_workflow_publishes_only_version_changes_or_manual_dispatch(
    repository, monkeypatch, event, version, expected,
):
    import os
    import sys
    import yaml

    workflow_path = MODULE_PATH.parents[2] / ".github/workflows/publish-huggingface.yml"
    workflow = yaml.load(workflow_path.read_text(), Loader=yaml.BaseLoader)
    step = next(s for s in workflow["jobs"]["changes"]["steps"] if s.get("id") == "changes")
    script = "\n".join(step["run"].splitlines()[1:-1])
    before = git(repository, "rev-parse", "HEAD")
    (repository / "pyproject.toml").write_text(f'[project]\nversion = "{version}"\n')
    output = repository / "github-output"
    subprocess.run(
        [sys.executable, "-c", script], cwd=repository, check=True,
        env={**os.environ, "GITHUB_EVENT_NAME": event, "BEFORE": before,
             "GITHUB_OUTPUT": str(output)},
    )
    assert f"publish={expected}" in output.read_text().splitlines()


def test_wait_does_not_fail_on_previous_deployments_build_error(monkeypatch):
    states = iter([("BUILD_ERROR", "old-commit"), ("RUNNING", "new-commit")])
    def runtime(repo):
        stage, commit = next(states)
        return SimpleNamespace(stage=stage, raw={"sha": commit})
    monkeypatch.setattr(publisher.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(publisher, "read_app_json", lambda url: (
        {"version": "1.0.7"} if url.endswith("/api/version") else {"status": "ok"}
    ))
    publisher.wait_for_deployment(
        repo_id="owner/space", version="1.0.7", expected_commit="new-commit",
        app_url="https://app.example", token="fake",
        api=SimpleNamespace(get_space_runtime=runtime),
    )


def test_cli_uses_oidc_credential_without_persistent_secret(monkeypatch, capsys):
    import huggingface_hub

    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setenv("HF_OIDC_RESOURCE", "spaces/owner/space")
    monkeypatch.setattr(huggingface_hub, "get_token", lambda: "temporary-oidc-credential")
    calls = []
    def publish(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(oid="new-commit")
    monkeypatch.setattr(publisher, "publish", publish)
    monkeypatch.setattr(publisher, "source_snapshot", lambda *args: ("source", "1.0.7", {}))
    monkeypatch.setattr(publisher, "wait_for_deployment", lambda **kwargs: calls.append(kwargs))

    publisher.main(["--repo-id", "owner/space", "--app-url", "https://app.example"])

    assert len(calls) == 2
    assert all(call["token"] == "temporary-oidc-credential" for call in calls)
    assert calls[1]["expected_commit"] == "new-commit"
    assert "temporary-oidc-credential" not in capsys.readouterr().out


def test_oidc_failure_stops_before_publishing(monkeypatch):
    import huggingface_hub

    monkeypatch.setenv("HF_OIDC_RESOURCE", "spaces/owner/space")
    def reject():
        raise RuntimeError("Trusted Publisher claims did not match")
    def unexpected(**kwargs):
        pytest.fail("Publishing attempted after failed authentication")
    monkeypatch.setattr(huggingface_hub, "get_token", reject)
    monkeypatch.setattr(publisher, "publish", unexpected)
    with pytest.raises(RuntimeError, match="claims did not match"):
        publisher.main([])


def test_wait_recovers_network_errors_without_legacy_httpx(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "httpx", None)
    monkeypatch.setattr(publisher.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(publisher, "read_app_json", lambda url: (
        {"version": "1.0.7"} if url.endswith("/api/version") else {"status": "ok"}
    ))
    attempts = []
    def runtime(repo):
        attempts.append(repo)
        if len(attempts) == 1:
            raise OSError("Transient transport error")
        return SimpleNamespace(stage="RUNNING", raw={"sha": "new-commit"})
    publisher.wait_for_deployment(
        repo_id="owner/space", version="1.0.7", expected_commit="new-commit",
        app_url="https://app.example", token="fake",
        api=SimpleNamespace(get_space_runtime=runtime),
    )
    assert len(attempts) == 2
