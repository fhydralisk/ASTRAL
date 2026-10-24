# Copyright (c) 2026-present, Yumeow. Licensed under the MIT License.
"""Execute Python with only the active conversation workspace mounted writable."""

from __future__ import annotations

import json
from typing import Any, Dict

from ..runtime import get_sandbox_runner
from .base_tool import BaseTool, ToolMetadata
from .code_executor import CodeExecutorTool


@BaseTool.register("workspace_code_executor")
class WorkspaceCodeExecutorTool(CodeExecutorTool):
    """Tool for running sandboxed Python code with read/write access to the active workspace directory."""

    metadata = ToolMetadata(name="workspace_code_executor")

    def execute(
        self,
        program: str,
        timeout_seconds: int = CodeExecutorTool.DEFAULT_TIMEOUT_SECONDS,
        memory_limit_mb: int = CodeExecutorTool.DEFAULT_MEMORY_LIMIT_MB,
        output_limit_bytes: int = CodeExecutorTool.DEFAULT_OUTPUT_LIMIT_BYTES,
    ) -> Dict[str, Any]:
        """Execute Python code in an OS sandbox with the active workspace mounted as the working directory.

        1. Runs with ``cwd`` set to the workspace root so relative paths (e.g., ``open("data.csv")``, ``np.save("context.data/x.npy", arr)``) read and write workspace files directly.
        2. Also receives serialized ``context.data`` on ``sys.stdin`` (optional to read).
        3. Scientific Python libraries are available; access outside the workspace, networking, and subprocess creation are blocked.

        Args:
            program: Python source code to execute inside the workspace sandbox.
            timeout_seconds: Wall-clock timeout in seconds (1-120, default 30).
            memory_limit_mb: Maximum address-space memory in MB (64-4096, default 1024).
            output_limit_bytes: Maximum stdout/stderr capture size in bytes (1024-1048576, default 65536).

        Returns:
            Dict[str, Any]: Sandbox stdout, stderr, timing, and resource-usage metrics.
        """
        timeout_seconds = self.bounded_int(
            timeout_seconds, self.DEFAULT_TIMEOUT_SECONDS, 1, self.MAX_TIMEOUT_SECONDS
        )
        memory_limit_mb = self.bounded_int(
            memory_limit_mb, self.DEFAULT_MEMORY_LIMIT_MB, 64, self.MAX_MEMORY_LIMIT_MB
        )
        output_limit_bytes = self.bounded_int(
            output_limit_bytes, self.DEFAULT_OUTPUT_LIMIT_BYTES, 1024, self.MAX_OUTPUT_LIMIT_BYTES
        )
        stdin_text = json.dumps(self.serialization(self.context.data), ensure_ascii=False)
        workspace = self.context.workspace
        if workspace is None:
            raise RuntimeError("Workspace not initialized.")
        result = get_sandbox_runner().run(
            self.extract_code(program),
            stdin=stdin_text,
            workspace=workspace,
            timeout_seconds=timeout_seconds,
            memory_limit_mb=memory_limit_mb,
            output_limit_bytes=output_limit_bytes,
            interruption_event=getattr(self, "cancel_event", None),
        )
        if result.exit_code != 0:
            raise RuntimeError(result.stderr or f"Sandboxed program exited with {result.exit_code}")
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration": result.duration_seconds,
            "cpu_seconds": result.cpu_seconds,
            "peak_memory_bytes": result.peak_memory_bytes,
            "timeout_seconds": timeout_seconds,
            "memory_limit_mb": memory_limit_mb,
            "output_limit_bytes": output_limit_bytes,
        }
