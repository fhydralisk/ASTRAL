"""Sandbox-backed proxies for user-authored ``BaseTool`` implementations."""

from __future__ import annotations

import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..core import AgentContext, ToolCallResult, ToolMetadata
from ..runtime.sandbox import (
    SandboxExecutionError,
    _context_array_snapshot,
    _run_sandbox_protocol,
)
from ..runtime.sandbox_context import sandbox_arguments
from .base_tool import BaseTool


def _context_payload(context: AgentContext) -> dict[str, Any]:
    """Serialize only data-independent context metadata for a sandbox worker."""
    evaluator = context.evaluator
    custom = getattr(type(evaluator), "CUSTOM_EVALUATOR", None)
    evaluator_payload = (
        {
            "kind": "custom",
            "source": custom["source"],
            "filename": Path(custom.get("file") or "custom_evaluator.py").name,
        }
        if isinstance(custom, dict) and isinstance(custom.get("source"), str)
        else {
            "kind": "graph" if type(evaluator).__name__ == "GraphEvaluator" else "default"
        }
    )
    return {
        "args": sandbox_arguments(context.args),
        "target": context.target,
        "variable_descriptions": context.variable_descriptions,
        "variable_axes": {name: list(axes) for name, axes in context.variable_axes.items()},
        "variable_structures": context.variable_structures,
        "relation_names": sorted(context.relation_names),
        "num_nodes": context.num_nodes,
        "evaluator": evaluator_payload,
    }


@lru_cache(maxsize=256)
def _inspect_source(source: str, filename: str) -> dict[str, Any]:
    """Inspect immutable tool source inside the OS sandbox."""
    result = _run_sandbox_protocol(
        operation="custom-tool",
        request={"action": "inspect", "source": source, "filename": filename},
        timeout_seconds=30,
        memory_limit_mb=2048,
        output_limit_bytes=64 * 1024,
    )
    return dict(result.payload)


class SandboxedCustomTool(BaseTool):
    """Proxy a user-authored tool into a fresh confined worker per invocation."""

    metadata = ToolMetadata(
        name="_sandboxed_custom_tool_proxy",
        description="Internal sandbox proxy for a user-authored tool.",
        parameters={},
    )

    SANDBOX_SOURCE: str
    SANDBOX_FILENAME: str
    source_path: Path

    def _sandbox_call(self, params: dict[str, Any]) -> dict[str, Any]:
        result = _run_sandbox_protocol(
            operation="custom-tool",
            request={
                "action": "execute",
                "source": self.SANDBOX_SOURCE,
                "filename": self.SANDBOX_FILENAME,
                "params": params,
                "context": _context_payload(self.context),
            },
            array_snapshot=_context_array_snapshot(self.context),
            timeout_seconds=120,
            memory_limit_mb=4096,
            output_limit_bytes=self.MAX_RESULT_STR_LENGTH,
            interruption_event=getattr(self, "cancel_event", None),
        )
        return dict(result.payload)

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Execute the custom tool in the OS sandbox."""
        return dict(self._sandbox_call(kwargs)["result"])

    def __call__(self, *args: Any, **kwargs: Any) -> ToolCallResult:
        """Execute and format the tool without importing its code in this process."""
        if args:
            raise TypeError("Sandboxed custom tools accept keyword arguments only")
        started = time.time()
        try:
            payload = self._sandbox_call(kwargs)
            result = payload["result"]
            if not isinstance(result, dict):
                raise TypeError("Custom tool execute() must return a dictionary")
            result_str = self.truncate_result_str(str(payload["result_str"]))
            return ToolCallResult(
                ok=True,
                result=result,
                result_str=result_str,
                meta_data={
                    "timestamp": started,
                    "execution_time": time.time() - started,
                    "tool": self.metadata.name,
                },
            )
        except Exception as exc:
            error = self.truncate_result_str(
                f"Error executing {self.metadata.name}:\n    {type(exc).__name__}: {exc}"
            )
            return ToolCallResult(
                ok=False,
                result={"error": error},
                result_str=error,
                meta_data={
                    "timestamp": started,
                    "execution_time": time.time() - started,
                    "tool": self.metadata.name,
                },
            )


def create_sandboxed_custom_tool(source: str, file: Path) -> type[BaseTool]:
    """Validate custom tool source and return a metadata-only proxy class."""
    try:
        metadata = _inspect_source(source, file.name)
    except SandboxExecutionError as exc:
        message = str(exc)
        if any(
            marker in message
            for marker in (
                "Custom tool must define exactly one",
                "Custom tools must not use @BaseTool.register",
                "Custom tool metadata.",
            )
        ):
            raise ValueError(message.split("\nTraceback", 1)[0]) from None
        raise
    tool_metadata = ToolMetadata(
        name=str(metadata["tool_name"]),
        description=str(metadata["description"]),
        parameters=dict(metadata["parameters"]),
    )
    return type(
        str(metadata["class_name"]),
        (SandboxedCustomTool,),
        {
            "__module__": __name__,
            "metadata": tool_metadata,
            "source_path": file.resolve(),
            "SANDBOX_SOURCE": source,
            "SANDBOX_FILENAME": file.name,
        },
    )
