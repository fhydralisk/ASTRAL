# Copyright (c) 2026-present, Yumeow. Licensed under the MIT License.
"""Command-line gateway for ASTRAL tools."""
from __future__ import annotations

import json
import argparse
import numpy as np
import sr_harness.tools
from pathlib import Path
from typing import Any
from sr_harness.core import AgentContext
from sr_harness.tools import BaseTool


def load_json_text(text: str) -> dict[str, Any]:
    """Parse a JSON object string from the CLI and verify that the root value is a ``dict``.

    Args:
        text: Raw JSON string representing tool parameters.

    Returns:
        dict[str, Any]: Parsed parameter dictionary.

    Raises:
        ValueError: If ``text`` is not valid JSON or does not decode to a dictionary.
    """
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("Tool params must be a JSON object.")
    return value


def load_params(params: str | None = None, params_file: str | None = None) -> dict[str, Any]:
    """Load and merge tool invocation parameters from ``--params-file`` and/or ``--params``.

    When both are provided, ``--params-file`` is loaded first and keys in ``--params``
    override matching keys from the file.

    Args:
        params: Optional inline JSON object string.
        params_file: Optional path to a JSON file containing tool parameters.

    Returns:
        dict[str, Any]: Merged tool parameter dictionary.
    """
    loaded: dict[str, Any] = {}
    if params_file:
        loaded |= load_json_text(Path(params_file).read_text(encoding="utf-8"))
    if params:
        loaded |= load_json_text(params)
    return loaded


def decode_npz_value(value: np.ndarray) -> Any:
    """Unpack a scalar or array entry loaded from a ``.npz`` archive into a native Python or NumPy value.

    Args:
        value: Array entry read from :func:`numpy.load`.

    Returns:
        Any: Unwrapped Python scalar, dictionary, or NumPy array.
    """
    if value.shape == ():
        return value.item()
    return value


def load_context(path: str | Path, target: str | None = None) -> AgentContext:
    """Construct an :class:`~sr_harness.core.AgentContext` from a ``context.npz`` archive for standalone tool execution.

    Args:
        path: Path to the ``.npz`` archive containing dataset arrays and optional metadata.
        target: Optional target variable name overriding the archive's stored target.

    Returns:
        AgentContext: Populated context ready for tool initialization.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Context file not found: {path}")

    with np.load(path, allow_pickle=True) as archive:
        context = {key: decode_npz_value(archive[key]) for key in archive.files}

    if target is not None:
        context["target"] = target

    if "data" in context:
        data = context["data"]
        if not isinstance(data, dict):
            raise ValueError('context.npz field "data" must contain a dict[str, np.ndarray].')
        if "target" not in context:
            raise ValueError('context.npz with a "data" field must also contain a "target" field.')
        context["target"] = str(context["target"])
        return AgentContext(data=data, target=str(context["target"]))

    if "target" not in context:
        raise ValueError(
            'context.npz must either contain fields "data" and "target", '
            'or contain a scalar "target" naming the target variable.'
        )

    target_name = str(context["target"])
    data = {
        key: value
        for key, value in context.items()
        if key != "target" and isinstance(value, np.ndarray)
    }
    if target_name not in data:
        raise ValueError(
            f'Target variable "{target_name}" is not present as an array field in context.npz.'
        )
    return AgentContext(data=data, target=target_name)


def setup_parser(parser: argparse.ArgumentParser | None = None) -> argparse.ArgumentParser:
    """Configure CLI arguments for ``sr-harness tool`` (``list``, ``schema``, and ``call``).

    Args:
        parser: Optional existing :class:`argparse.ArgumentParser` to populate.

    Returns:
        argparse.ArgumentParser: Configured argument parser.
    """
    if parser is None:
        parser = argparse.ArgumentParser(
            prog="astral tool",
            description="Run ASTRAL tools from the command line.",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        )
    else:
        parser.description = "Run ASTRAL tools from the command line."
        parser.formatter_class = argparse.ArgumentDefaultsHelpFormatter
    subparsers = parser.add_subparsers(dest="tool_command", required=True)

    list_parser = subparsers.add_parser("list", help="List registered tool names.")
    list_parser.add_argument("--json", action="store_true", help="Output tool names as JSON.")

    schema_parser = subparsers.add_parser("schema", help="Print a tool schema.")
    schema_parser.add_argument("tool", nargs="?", help="Tool name. Omit to print all schemas.")

    call_parser = subparsers.add_parser("call", help="Call one registered tool.")
    call_parser.add_argument("tool", help="Tool name.")
    call_parser.add_argument("--context", default="context.npz", help=(
        "Path to context.npz containing BaseTool context fields."
    ))
    call_parser.add_argument("--target", default=None, help="Override context target name.")
    call_parser.add_argument("--params", default=None, help=(
        'Tool parameters as a JSON object, e.g. \'{"f": "sin(x1)"}\'.'
    ))
    call_parser.add_argument("--params-file", default=None, help="JSON file with tool parameters.")
    return parser


def tool_class(name: str) -> type[BaseTool]:
    """Look up a registered :class:`~sr_harness.tools.BaseTool` subclass by name.

    Args:
        name: Registered tool name.

    Returns:
        type[BaseTool]: Matching tool class.

    Raises:
        ValueError: If ``name`` is not registered.
    """
    return BaseTool.create(name, create_instance=False)


def main(args: argparse.Namespace) -> int:
    """Execute the ``sr-harness tool`` subcommand (``list``, ``schema``, or ``call``).

    Args:
        args: Parsed command-line arguments.

    Returns:
        int: Process exit code (``0`` on success, ``1`` when a called tool returns ``ok=False``).
    """
    if args.tool_command == "list":
        if args.json:
            print(json.dumps(list(BaseTool.REGISTRY_DICT), indent=2, ensure_ascii=False))
        else:
            for idx, (name, tool_cls) in enumerate(BaseTool.REGISTRY_DICT.items()):
                description = (tool_cls.metadata.description or "").strip()
                print(f"[{idx:02d}] {name}: {description}")
    elif args.tool_command == "schema":
        schema = tool_class(args.tool).to_dict() if args.tool else BaseTool.to_tool_list()
        print(json.dumps(schema, indent=2, ensure_ascii=False))
    elif args.tool_command == "call":
        tool_cls = tool_class(args.tool)
        context = load_context(args.context, target=args.target)
        params = load_params(args.params, args.params_file)
        result = tool_cls(context=context)(**params)
        print(result.result_str)
        if not result.ok:
            return 1
    else:
        raise ValueError(f"Unknown tool command: {args.tool_command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(setup_parser().parse_args()))
