"""Publish a committed SRHarness source snapshot to a Hugging Face Docker Space."""
from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import time
import tomllib
from typing import Any
from urllib.request import urlopen


REPOSITORY = Path(__file__).resolve().parents[2]
SPACE_README = "deploy/huggingface/README.space.md"
SOURCE_PATHS = ("Dockerfile", ".dockerignore", "pyproject.toml", "LICENSE", "src", SPACE_README)


def source_snapshot(repository: Path, revision: str) -> tuple[str, str, dict[str, bytes]]:
    """Read only Git objects, excluding modified, staged and untracked local files."""
    commit = subprocess.check_output(
        ["git", "rev-parse", "--verify", "--end-of-options", f"{revision}^{{commit}}"],
        cwd=repository, text=True,
    ).strip()
    archive = subprocess.check_output(
        ["git", "archive", "--format=tar", commit, "--", *SOURCE_PATHS], cwd=repository,
    )
    files = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as source:
        for entry in source:
            if entry.isdir():
                continue
            if not entry.isfile():
                raise ValueError(f"Deployment source must be a regular file: {entry.name}")
            content = source.extractfile(entry)
            assert content is not None
            files[entry.name] = content.read()
    files["README.md"] = files.pop(SPACE_README)
    version = tomllib.loads(files["pyproject.toml"].decode("utf-8"))["project"]["version"]
    return commit, version, files


def publish(
    *, repository: Path, revision: str, repo_id: str, token: str | None, api: Any = None,
) -> Any:
    """Replace managed application files in one commit, preserving other Space files."""
    if not token or not token.strip():
        raise ValueError(
            "Hugging Face authentication is required; configure the Space Trusted Publisher for CI"
        )

    from huggingface_hub import CommitOperationAdd, CommitOperationDelete, HfApi

    commit, version, files = source_snapshot(repository, revision)
    client = api if api is not None else HfApi(token=token)
    parent = client.repo_info(repo_id, repo_type="space", revision="main").sha
    if not parent:
        raise ValueError("Could not determine the Space's current commit")
    remote_files = client.list_repo_files(repo_id, repo_type="space", revision=parent)
    operations = [
        CommitOperationAdd(path_in_repo=path, path_or_fileobj=content)
        for path, content in sorted(files.items())
    ]
    operations.extend(
        CommitOperationDelete(path_in_repo=path)
        for path in sorted(remote_files)
        if path.startswith("src/") and path not in files
    )
    return client.create_commit(
        repo_id=repo_id,
        repo_type="space",
        revision="main",
        parent_commit=parent,
        operations=operations,
        commit_message=f"Deploy SRHarness v{version} ({commit[:12]})",
        commit_description=f"Source commit: {commit}\nManaged files: Docker build files and src/.",
    )


def read_app_json(url: str) -> dict[str, Any]:
    """Probe a public app endpoint with a bounded request timeout."""
    with urlopen(url, timeout=10) as response:
        return json.load(response)


def wait_for_deployment(
    *, repo_id: str, version: str, expected_commit: str, app_url: str, token: str | None,
    timeout: float = 1200, poll_interval: float = 15, api: Any = None,
) -> None:
    """Wait for the build to finish and the public application to serve this version."""
    from huggingface_hub import HfApi

    client = api if api is not None else HfApi(token=token)
    deadline = time.monotonic() + timeout
    status = "No response yet"
    while time.monotonic() < deadline:
        try:
            runtime = client.get_space_runtime(repo_id)
            stage = runtime.stage
            running_commit = runtime.raw.get("sha")
            current_deployment = running_commit == expected_commit
            if current_deployment and stage in {
                "BUILD_ERROR", "RUNTIME_ERROR", "CONFIG_ERROR", "NO_APP_FILE",
            }:
                raise RuntimeError(f"Hugging Face deployment failed: {stage}")
            # The public requests also wake a sleeping Space.
            current = read_app_json(app_url.rstrip("/") + "/api/version").get("version")
            health = read_app_json(app_url.rstrip("/") + "/health").get("status")
            if current_deployment and stage == "RUNNING" and current == version and health == "ok":
                print(f"Deployment ready: {app_url} serves SRHarness {version}")
                return
            status = (f"Space stage={stage}, running commit={running_commit}, "
                      f"app version={current}, health={health}")
        except (OSError, ValueError) as error:
            status = f"Waiting for application responses ({type(error).__name__})"
        print(status, flush=True)
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(poll_interval, remaining))
    raise TimeoutError(f"Space did not serve SRHarness {version} within {timeout:g}s: {status}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    space_id = os.environ.get("HF_SPACE_ID") or "YuMeow/SRHarness"
    parser.add_argument("--repo-id", default=space_id, help="Target Hugging Face Space")
    parser.add_argument("--revision", default="HEAD", help="Committed source revision to deploy")
    parser.add_argument("--dry-run", action="store_true", help=(
        "List the source payload without credentials or network access"
    ))
    app_url = os.environ.get("HF_SPACE_URL") or "https://yumeow-srharness.hf.space"
    parser.add_argument("--app-url", default=app_url, help="Direct application URL to verify")
    parser.add_argument("--wait-timeout", type=float, default=1200, help=(
        "Maximum seconds to wait for the application to serve the deployed version"
    ))
    args = parser.parse_args(argv)
    if args.wait_timeout <= 0:
        parser.error("--wait-timeout must be positive")
    if args.dry_run:
        commit, version, files = source_snapshot(REPOSITORY, args.revision)
        print(json.dumps({
            "repo_id": args.repo_id, "commit": commit, "version": version, "files": sorted(files),
        }, indent=2))
        return
    from huggingface_hub import get_token

    try:
        token = get_token()
        result = publish(
            repository=REPOSITORY, revision=args.revision, repo_id=args.repo_id,
            token=token,
        )
    except ValueError as error:
        parser.error(str(error))
    print(f"Published source to {args.repo_id}: {result.oid}", flush=True)
    _, version, _ = source_snapshot(REPOSITORY, args.revision)
    wait_for_deployment(
        repo_id=args.repo_id, version=version, expected_commit=result.oid, app_url=args.app_url,
        token=token, timeout=args.wait_timeout,
    )


if __name__ == "__main__":
    main()
