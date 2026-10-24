"""Unified command-line entry point for SRHarness."""
from __future__ import annotations
import argparse
import importlib

__all__ = ["entrypoint"]


COMMANDS = {
    "run": ("run", "Launch the SRHarness interactive workbench."),
    "synthetic": ("synthetic", "Run SRHarness on a synthetic symbolic-regression problem."),
    "benchmark": ("benchmark", "Evaluate SRHarness and baseline algorithms on LLM-SRBench."),
    "tool": ("tool", "Inspect or invoke an SRHarness tool."),
}


class _CommandParser(argparse.ArgumentParser):
    def __init__(self, *args, module_name: str | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._module_name = module_name
        self._is_configured = module_name is None

    def parse_known_args(self, args=None, namespace=None):
        if not self._is_configured:
            self._is_configured = True
            module = importlib.import_module(f"{__package__}.{self._module_name}")
            module.setup_parser(self)
        return super().parse_known_args(args, namespace)


def setup_parser(parser: argparse.ArgumentParser | None = None) -> argparse.ArgumentParser:
    """Build the top-level ``sr-harness`` CLI argument parser and register all subcommands.

    Args:
        parser: Optional existing :class:`argparse.ArgumentParser` to populate.

    Returns:
        argparse.ArgumentParser: Configured top-level argument parser.
    """
    if parser is None:
        parser = argparse.ArgumentParser(prog="sr-harness", description="SRHarness command-line interface.")

    subparsers = parser.add_subparsers(
        dest="command",
        metavar="COMMAND",
        parser_class=_CommandParser,
    )
    for name, (module_name, help_text) in COMMANDS.items():
        subparsers.add_parser(name, help=help_text, module_name=module_name)
    return parser


def main(args: argparse.Namespace) -> int:
    """Dispatch parsed CLI arguments to the selected subcommand handler.

    Args:
        args: Parsed command-line arguments from :func:`setup_parser`.

    Returns:
        int: Process exit code (``0`` on success, non-zero on failure).
    """
    module_name = COMMANDS[args.command][0]
    module = importlib.import_module(f"{__package__}.{module_name}")
    return module.main(args)


def entrypoint() -> int:
    """Parse ``sys.argv`` and execute the ``sr-harness`` command-line entry point.

    Returns:
        int: Process exit code returned by the active subcommand.
    """
    parser = setup_parser()
    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return 0
    return main(args)
