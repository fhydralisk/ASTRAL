"""Operating-system sandbox boundary tests."""

import numpy as np
import pytest

from sr_harness import AgentContext
from sr_harness.runtime.sandbox import (
    SandboxExecutionError,
    SandboxRunner,
    _context_array_snapshot,
)


def test_worker_output_protocol_rejects_symbolic_links():
    runner = SandboxRunner()
    program = """
import inspect
import os

frame = inspect.currentframe()
while frame is not None and "output_root" not in frame.f_locals:
    frame = frame.f_back
output_root = frame.f_locals["output_root"]
os.symlink("result.json", output_root / "arrays.json")
"""
    with pytest.raises(SandboxExecutionError, match="not a regular file"):
        runner.run(program)


def test_worker_cannot_start_child_process():
    runner = SandboxRunner()
    program = """
import subprocess

try:
    subprocess.run(["/bin/true"], check=True)
except PermissionError:
    print("blocked")
"""
    result = runner.run(program)
    assert result.exit_code == 0
    assert result.stdout.strip() == "blocked"
    assert result.duration_seconds >= 0
    assert result.cpu_seconds > 0
    assert result.peak_memory_bytes > 0


def test_worker_cannot_open_network_socket_or_read_host_files():
    runner = SandboxRunner()
    program = """
import socket

blocked = []
try:
    socket.socket()
except PermissionError:
    blocked.append("network")
try:
    open("/etc/passwd").read()
except PermissionError:
    blocked.append("filesystem")
print(",".join(blocked))
"""

    result = runner.run(program)

    assert result.exit_code == 0
    assert result.stdout.strip() == "network,filesystem"


def test_context_array_snapshot_is_reused_until_data_revision_changes():
    context = AgentContext(
        data={"x": np.arange(5.0), "y": np.arange(5.0)}, target="y"
    )

    first = _context_array_snapshot(context)
    second = _context_array_snapshot(context)
    context.args.data_revision += 1
    third = _context_array_snapshot(context)

    assert second is first
    assert third is not first
    assert third.root != first.root
