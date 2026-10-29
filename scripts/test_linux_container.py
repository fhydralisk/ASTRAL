"""Run from a disposable Harness container, not directly on a workstation.

The container installs pytest, drops to the production UID, and keeps every test
workspace/cache on its Linux /tmp filesystem instead of a Windows bind mount.
"""

import os
from pathlib import Path
import shutil
import subprocess
import sys

if not os.path.exists("/.dockerenv") or os.getuid() != 0:
    raise SystemExit("Run this helper as root inside a disposable Docker container")
subprocess.run([sys.executable, "-m", "pip", "install", "pytest"], check=True)
# Landlock tests must run on a native Linux filesystem. A Windows bind mount
# has different inode/mount semantics even when accessed from a Linux container.
source = Path(__file__).resolve().parents[1]
native = Path("/tmp/astral-test-source")
native.mkdir()
for name in ("src", "tests", "deploy", "scripts", ".github"):
    shutil.copytree(source / name, native / name, ignore=shutil.ignore_patterns("__pycache__"))
for name in ("pyproject.toml", "README.md", "Dockerfile", ".dockerignore", "LICENSE"):
    shutil.copyfile(source / name, native / name)
subprocess.run(["chown", "-R", "1000:1000", str(native)], check=True)
os.chdir(native)
os.setgroups([1000])
os.setgid(1000)
os.setuid(1000)
os.environ["HOME"] = "/tmp/astral-test-home"
os.makedirs(os.environ["HOME"], exist_ok=True)
import pytest  # noqa: E402 -- installed above, then imported after dropping privileges

raise SystemExit(
    pytest.main(
        [
            "--ignore=tests/playground",
            "--ignore=tests/deploy",
            "--basetemp=/tmp/astral-tests",
            "-o",
            "cache_dir=/tmp/astral-pytest-cache",
            "-o",
            "addopts=-m 'not slow and not paid'",
            "-q",
            "--maxfail=10",
            *sys.argv[1:],
        ]
    )
)
