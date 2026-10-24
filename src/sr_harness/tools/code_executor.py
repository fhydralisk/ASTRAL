# Copyright (c) 2026-present, Yumeow. Licensed under the MIT License.
"""Execute data-only Python programs in an operating-system sandbox."""

from __future__ import annotations

import io
import json
from typing import Any, Dict

from ..runtime import get_sandbox_runner
from ..utils import bounded_value
from .base_tool import BaseTool, ToolMetadata


class LimitedWriter(io.StringIO):
    """In-memory string buffer that truncates writes beyond a fixed character limit."""

    SUFFIX = "...[truncated]"

    def __init__(self, limit: int):
        """Initialize a bounded string buffer.

        Args:
            limit: Maximum number of characters retained before truncation.
        """
        super().__init__()
        self.limit = limit

    def write(self, text: str) -> int:
        """Append ``text`` up to the configured buffer limit, adding a truncation suffix if exceeded.

        Args:
            text: String chunk to append.

        Returns:
            int: Length of ``text`` passed by the caller.
        """
        remaining = self.limit - self.tell() - len(self.SUFFIX)
        if remaining <= 0:
            return len(text)
        if len(text) > remaining:
            super().write(text[:remaining])
            super().write(self.SUFFIX)
            return len(text)
        return super().write(text)


@BaseTool.register("code_executor")
class CodeExecutorTool(BaseTool):
    """Tool for running isolated, data-only Python analysis scripts in an OS sandbox."""

    metadata = ToolMetadata(name="code_executor")
    DEFAULT_TIMEOUT_SECONDS = 30
    DEFAULT_MEMORY_LIMIT_MB = 1024
    DEFAULT_OUTPUT_LIMIT_BYTES = 64 * 1024
    MAX_TIMEOUT_SECONDS = 120
    MAX_MEMORY_LIMIT_MB = 4096
    MAX_OUTPUT_LIMIT_BYTES = 1024 * 1024

    def execute(
        self,
        program: str,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB,
        output_limit_bytes: int = DEFAULT_OUTPUT_LIMIT_BYTES,
    ) -> Dict[str, Any]:
        """Execute a Python snippet in an isolated OS sandbox with the dataset piped via ``stdin``.

        Use this tool for custom statistical tests, transformations, or exploratory checks not
        covered by built-in analysis tools:
        1. Load the dataset via ``import sys, json; data_dict = json.loads(sys.stdin.read())``.
        2. Print concise results with ``print(...)`` (only stdout/stderr are returned).
        3. Scientific Python packages (``numpy``, ``scipy``, ``scikit-learn``, ``sympy``, ``pandas``)
           are pre-installed; filesystem writes outside the sandbox, network access, and subprocesses
           are blocked.

        Args:
            program: Python code to run. Read ``sys.stdin`` as JSON to inspect ``context.data``.
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
        result = get_sandbox_runner().run(
            self.extract_code(program),
            stdin=stdin_text,
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

    @classmethod
    def format_result_dict(cls, result: Dict[str, Any]) -> str:
        """Format sandbox stdout, stderr, and execution duration for the Agent.

        Args:
            result: Result dictionary returned by :meth:`execute`.

        Returns:
            str: Formatted program output and runtime duration.
        """
        parts = []
        if result["stdout"]:
            parts.append(result["stdout"].rstrip())
        if result["stderr"]:
            parts.append(f"Program stderr:\n{result['stderr'].rstrip()}")
        if not parts:
            parts.append("Program completed successfully and printed no output.")
        parts.append(f"(Execution duration: {result['duration']:.3f} seconds.)")
        return "\n".join(parts)

    @classmethod
    def extract_code(cls, code: str) -> str:
        """Strip optional Markdown code fences (e.g. ````python ... ````) from a code string.

        Args:
            code: Raw code string or Markdown-fenced code block.

        Returns:
            str: Extracted Python source code.
        """
        raw_code = str(code).strip()
        if "```python" in raw_code:
            return raw_code.split("```python")[-1].split("```")[0].strip()
        if "```" not in raw_code:
            return raw_code
        parts = raw_code.split("```")
        if len(parts) <= 1:
            return raw_code
        potential_code = parts[1]
        if "\n" not in potential_code:
            return potential_code.strip()
        first_line, rest = potential_code.split("\n", 1)
        return rest.strip() if first_line.strip().isalpha() else potential_code.strip()

    @classmethod
    def serialization(cls, value: Any) -> Any:
        """Recursively convert NumPy arrays, scalars, and containers into JSON-serializable objects.

        Args:
            value: Arbitrary context data value to serialize.

        Returns:
            Any: JSON-serializable Python primitive, list, or dict.
        """
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(key): cls.serialization(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [cls.serialization(item) for item in value]
        if hasattr(value, "tolist"):
            return cls.serialization(value.tolist())
        if hasattr(value, "item"):
            return cls.serialization(value.item())
        raise TypeError(f"unsupported data type {type(value).__name__}")

    @classmethod
    def bounded_int(cls, value: Any, default: int, minimum: int, maximum: int) -> int:
        """Coerce ``value`` to an integer clamped within ``[minimum, maximum]``.

        Args:
            value: Input value to coerce and clamp.
            default: Fallback integer used when ``value`` cannot be converted.
            minimum: Inclusive lower bound.
            maximum: Inclusive upper bound.

        Returns:
            int: Clamped integer value.
        """
        return bounded_value(value, min=minimum, max=maximum, default=default, converter=int)
