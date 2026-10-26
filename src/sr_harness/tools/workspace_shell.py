# Copyright (c) 2026-present, Yumeow. Licensed under the MIT License.
"""Restricted shell-like command execution tool confined to the active workspace."""

from __future__ import annotations

import argparse
import gzip
import logging
import os
import re
import shlex
import shutil
import stat
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Never

from ..runtime.workspace import Workspace
from .base_tool import BaseTool, ToolMetadata
from .code_executor import LimitedWriter
from ..utils import log_exception

_logger = logging.getLogger(f"sr_harness.{__name__}")

# WorkspaceShellTool 支持的命令白名单
ALLOWED_COMMANDS = {
    "ls", "cat", "head", "tail", "wc", "grep",
    "sort", "cut", "cp", "mv", "rm", "mkdir",
    "gunzip", "gzip", "unzip", "tar",
}


class CommandParseError(ValueError):
    """Exception raised when a workspace shell command violates syntax or argument rules."""


class CommandArgumentParser(argparse.ArgumentParser):
    """Non-exiting :class:`argparse.ArgumentParser` subclass that raises :class:`CommandParseError` on invalid flags."""

    def __init__(self, command: str):
        """Initialize the parser for a single restricted shell command.

        Args:
            command: Command name used in error messages.
        """
        super().__init__(prog=command, add_help=False, allow_abbrev=False, exit_on_error=False)

    def error(self, message: str) -> Never:
        """Raise :class:`CommandParseError` instead of printing to stderr and exiting.

        Args:
            message: Error message produced by :mod:`argparse`.

        Raises:
            CommandParseError: Always raised with ``"<command>: <message>"``.
        """
        raise CommandParseError(f"{self.prog}: {message}")

    def exit(self, status: int = 0, message: str | None = None) -> Never:
        """Raise :class:`CommandParseError` instead of terminating the Python process.

        Args:
            status: Exit status code.
            message: Optional error message.

        Raises:
            CommandParseError: Always raised when :mod:`argparse` attempts to exit.
        """
        raise CommandParseError(message or f"{self.prog}: invalid arguments")


@BaseTool.register("workspace_shell")
class WorkspaceShellTool(BaseTool):
    """Tool for inspecting and manipulating workspace files with a safe, restricted POSIX-like command subset."""

    metadata = ToolMetadata(name="workspace_shell")

    DEFAULT_OUTPUT_LIMIT_BYTES = 64 * 1024
    MAX_OUTPUT_LIMIT_BYTES = 1024 * 1024

    @classmethod
    def get_doc(cls) -> dict[str, str]:
        """Return runtime skill documentation for ``workspace-shell``.

        Returns:
            dict[str, str]: Skill metadata, supported command syntax, and pipeline examples.
        """
        return {
            "name": "workspace-shell",
            "description": (
                "Inspect and modify workspace files with a safe, restricted shell-like "
                "command language."
            ),
            "content": (
                "# Workspace Shell\n\n"
                "`workspace_shell` implements a small command language in Python. It does not "
                "start a system shell or execute operating-system commands. Use it to inspect, "
                "filter, copy, move, remove, and unpack files in the current workspace.\n\n"
                "## Syntax\n\n"
                "- Separate arguments with whitespace. Single quotes, double quotes, and "
                "backslash escapes follow POSIX shell lexical rules.\n"
                "- Join supported commands with `|`. A pipeline passes each command's text "
                "output to the next command in memory; spaces around `|` are optional.\n"
                "- Short flags may be combined or separated: `ls -la`, `ls -al`, "
                "`ls -l -a`, and `ls -a -l` are equivalent. Options and operands may usually "
                "be interspersed. Use `--` before a path beginning with `-`.\n"
                "- Use workspace-relative paths. Registered mounts can be read through their "
                "workspace names; other symbolic links escaping the workspace are rejected.\n"
                "- Redirection and other shell operators (`>`, `<`, `;`, `&&`, `||`, `&`) are "
                "not supported. There is no globbing, variable or tilde expansion, command "
                "substitution, background execution, or invocation of unlisted commands.\n\n"
                "## Supported commands\n\n"
                "```text\n"
                "ls [-a|--all] [-l] [-L|--dereference] [PATH ...]\n"
                "cat [-n|--number] [FILE ...]\n"
                "head [-n N|--lines N|-N] [FILE]\n"
                "tail [-n N|--lines N|-N] [FILE]\n"
                "wc [-l] [-w] [-c] [-m] [FILE ...]\n"
                "grep [-i|--ignore-case] [-v|--invert-match] [-n|--line-number]\n"
                "     [-c|--count] [-F|--fixed-strings] PATTERN [FILE]\n"
                "sort [-r|--reverse] [-n|--numeric-sort] [-u|--unique] [FILE]\n"
                "cut [-d DELIMITER|--delimiter DELIMITER] -f FIELDS [FILE]\n"
                "cp [-r|-R|--recursive] [-f|--force] SOURCE DESTINATION\n"
                "mv [-f|--force] SOURCE DESTINATION\n"
                "rm [-r|-R|--recursive] [-f|--force] PATH ...\n"
                "mkdir [-p|--parents] DIRECTORY ...\n"
                "gzip [-k|--keep] [-f|--force] FILE\n"
                "gunzip [-k|--keep] [-f|--force] FILE\n"
                "unzip [-d DIRECTORY|--directory DIRECTORY] FILE\n"
                "tar (-x|--extract) [-z|--gzip] (-f FILE|--file FILE)\n"
                "    [-C DIRECTORY|--directory DIRECTORY]\n"
                "```\n\n"
                "`grep` performs fixed-string matching; `-F` is accepted for familiar grep "
                "syntax. `cut -f` accepts comma-separated, one-based field numbers. `tar` only "
                "supports extraction and accepts grouped flags such as `-xf` and `-xzf`. When "
                "a text-processing command has no file operand, it reads the previous pipeline "
                "stage. `ls -L` reports linked entries using their targets only when workspace "
                "read access allows it; it does not grant access to other host paths.\n\n"
                "## Examples\n\n"
                "```text\n"
                "ls -la\n"
                "cat 'experiment 1.csv' | head -5\n"
                "cat data.csv|grep -i result|wc -l\n"
                "cut data.csv -d, -f1,3 | sort -u\n"
                "mkdir -p results/archive\n"
                "cp -r results results-copy\n"
                "tar -xzf results.tar.gz -C results/archive\n"
                "cat -- -notes\n"
                "```"
            ),
        }

    def execute(
        self,
        command: str,
        output_limit_bytes: int = DEFAULT_OUTPUT_LIMIT_BYTES,
    ) -> Dict[str, Any]:
        """Run a restricted shell command or ``|`` pipeline inside the workspace directory.

        Supports ``ls``, ``cat``, ``head``, ``tail``, ``wc``, ``grep``, ``sort``, ``cut``, ``cp``,
        ``mv``, ``rm``, ``mkdir``, ``gunzip``, ``gzip``, ``unzip``, and ``tar`` (extract only).
        Common forms include ``ls -laL`` and ``head -n 20`` (or ``head -20``).
        All paths must stay within the workspace root; shell redirection (``>``, ``<``), chaining
        (``;``, ``&&``, ``||``), globbing, and unlisted commands are rejected. Call ``read_skill``
        with ``"workspace-shell"`` for full flag syntax.

        Args:
            command: Command or ``|``-connected pipeline string, e.g., ``"ls -la"``, ``"cat data.csv | head -n 5"``, or ``"unzip archive.zip -d raw"``.
            output_limit_bytes: Maximum stdout size in bytes retained per pipeline stage (1024-1048576, default 65536).

        Returns:
            Dict[str, Any]: Command execution status, ``stdout``, ``stderr``, and ``exit_code``.
        """
        if self.context.workspace is None:
            return self._error("Workspace not initialized.")
        output_limit_bytes = self._bounded_output_limit(output_limit_bytes)

        try:
            pipeline = self._parse_pipeline(command)
        except CommandParseError as exc:
            return self._error(f"Command parse error: {exc}")

        stdin_text = ""
        for tokens in pipeline:
            try:
                result = self._execute_tokens(tokens, stdin_text)
                if not result.get("success", False):
                    return result
                stdin_text = self._limit_output(result.get("stdout", ""), output_limit_bytes)
            except Exception as e:
                rendered = shlex.join(tokens)
                _logger.error(f"Error executing command segment '{rendered}': {log_exception(e)}")
                return self._error(
                    f"Error executing command segment '{rendered}', ask human for help: "
                    f"{self._safe_exception_text(e)}"
                )
        return self._ok(stdin_text)

    @classmethod
    def format_result_dict(cls, result: Dict[str, Any]) -> str:
        """Format workspace command stdout, stderr, or failure details for the Agent.

        Args:
            result: Result dictionary returned by :meth:`execute`.

        Returns:
            str: Command output or error message.
        """
        if not result.get("success", False):
            detail = result.get("error") or result.get("stderr") or "No error detail was provided."
            return f"Command failed: {detail}"
        parts = []
        if result.get("stdout"):
            parts.append(result["stdout"])
        if result.get("stderr"):
            parts.append(f"Command stderr:\n{result['stderr']}")
        return (
            "\n".join(parts) if parts else "Command completed successfully and produced no output."
        )

    def execute_single(self, command: str, stdin_text: str = "") -> Dict[str, Any]:
        """Execute a single command segment (without pipes) given optional stdin text.

        Args:
            command: Single command string without ``|`` operators.
            stdin_text: Input text piped from a preceding command segment.

        Returns:
            Dict[str, Any]: Command execution status, ``stdout``, ``stderr``, and ``exit_code``.
        """
        if self.context.workspace is None:
            return self._error("Workspace not initialized.")
        try:
            parts = shlex.split(command)
        except ValueError as e:
            return self._error(f"Command parse error: {e}")
        return self._execute_tokens(parts, stdin_text)

    @staticmethod
    def _parse_pipeline(command: str) -> list[list[str]]:
        """Parse the deliberately small shell-like language into a pipeline AST.

        Quotes and backslash escapes follow POSIX shell lexical rules, but the only
        executable operator is a single pipe.  Shell evaluation, expansion,
        redirection, conditionals, command substitution, and background jobs are
        intentionally outside this language.
        """
        try:
            lexer = shlex.shlex(command, posix=True, punctuation_chars="|&;<>")
            lexer.whitespace_split = True
            lexer.commenters = ""
            tokens = list(lexer)
        except ValueError as exc:
            raise CommandParseError(str(exc)) from exc

        pipeline: list[list[str]] = [[]]
        for token in tokens:
            if token == "|":
                if not pipeline[-1]:
                    raise CommandParseError("empty command before pipe")
                pipeline.append([])
            elif token and all(char in "|&;<>" for char in token):
                raise CommandParseError(f"operator {token!r} is not supported")
            else:
                pipeline[-1].append(token)
        if not pipeline[-1]:
            message = "empty command" if len(pipeline) == 1 else "empty command after pipe"
            raise CommandParseError(message)
        return pipeline

    def _execute_tokens(self, parts: list[str], stdin_text: str) -> Dict[str, Any]:
        if not parts:
            return self._error("Empty command.")

        cmd_name = parts[0]
        args = parts[1:]

        if cmd_name not in ALLOWED_COMMANDS:
            return self._error(
                f"Command '{cmd_name}' is not allowed. "
                f"Allowed: {', '.join(sorted(ALLOWED_COMMANDS))}"
            )

        handler = getattr(self, f"_cmd_{cmd_name}", None)
        if handler is None:
            return self._error(f"Command '{cmd_name}' is not implemented.")
        try:
            return handler(args, stdin_text)
        except CommandParseError as exc:
            return self._error(str(exc))

    @staticmethod
    def _ok(stdout: str) -> Dict[str, Any]:
        return {"success": True, "stdout": stdout, "stderr": "", "exit_code": 0}

    @staticmethod
    def _error(msg: str) -> Dict[str, Any]:
        return {"success": False, "stdout": "", "stderr": "", "error": msg, "exit_code": 1}

    @classmethod
    def _bounded_output_limit(cls, value: Any) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = cls.DEFAULT_OUTPUT_LIMIT_BYTES
        return max(1024, min(cls.MAX_OUTPUT_LIMIT_BYTES, parsed))

    @staticmethod
    def _limit_output(stdout: str, output_limit_bytes: int) -> str:
        writer = LimitedWriter(output_limit_bytes)
        writer.write(stdout)
        return writer.getvalue()

    @staticmethod
    def _parse_args(
        command: str,
        args: list[str],
        configure: Callable[[CommandArgumentParser], None],
    ) -> argparse.Namespace:
        parser = CommandArgumentParser(command)
        configure(parser)
        try:
            return parser.parse_intermixed_args(args)
        except (argparse.ArgumentError, CommandParseError) as exc:
            raise CommandParseError(f"{exc}\nSupported syntax: {parser.format_usage().strip()}") from exc

    def _read_text(self, path: Path) -> str:
        if not path.is_file():
            raise CommandParseError(f"Not a regular file: {path.name}")
        try:
            with self._workspace.safe_open(
                path, "r", encoding="utf-8", errors="replace"
            ) as f:
                return f.read()
        except OSError as exc:
            raise CommandParseError(
                f"Cannot read file: {self._safe_exception_text(exc)}"
            ) from exc

    @property
    def _workspace(self) -> Workspace:
        workspace = self.context.workspace
        if workspace is None:
            raise RuntimeError("Workspace not initialized.")
        return workspace

    def _safe_exception_text(self, error: BaseException) -> str:
        """Remove host workspace and mount locations from a user-visible error."""
        message = str(error)
        workspace = self.context.workspace
        if workspace is None:
            return message
        replacements = [
            (workspace.path, "."),
            *(
                (source, os.fspath(logical.relative_to(workspace.path)))
                for logical, source in workspace.mount_map.items()
            ),
        ]
        for host_path, visible_path in sorted(
            replacements,
            key=lambda pair: len(os.fspath(pair[0])),
            reverse=True,
        ):
            message = message.replace(os.fspath(host_path), visible_path)
        return message

    def _copy_file(self, source: str | os.PathLike, destination: str) -> str:
        """Copy one regular file while enforcing safe source and destination access."""
        ws = self._workspace
        with ws.safe_open(source, "rb") as input_stream:
            with ws.open_for_write(destination, "wb") as output_stream:
                shutil.copyfileobj(input_stream, output_stream)
        return os.fspath(destination)

    @staticmethod
    def _reject_tree_symlinks(directory: str, names: list[str]) -> set[str]:
        """Reject recursive copies containing symbolic links instead of following them."""
        symbolic_links = [name for name in names if (Path(directory) / name).is_symlink()]
        if symbolic_links:
            raise ValueError(
                "recursive copies do not follow symbolic links: "
                + ", ".join(symbolic_links)
            )
        return set()

    @staticmethod
    def _find_tree_symlink(root: Path) -> Path | None:
        """Return the first symbolic link below a directory without following links."""
        for directory, directories, filenames in os.walk(root, followlinks=False):
            parent = Path(directory)
            for name in (*directories, *filenames):
                candidate = parent / name
                if candidate.is_symlink():
                    return candidate
        return None

    @staticmethod
    def _nonnegative_int(value: str) -> int:
        try:
            parsed = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("must be an integer") from exc
        if parsed < 0:
            raise argparse.ArgumentTypeError("must be non-negative")
        return parsed

    def _cmd_ls(self, args: list, stdin: str) -> Dict[str, Any]:
        ws = self._workspace
        def configure(parser):
            parser.add_argument("-a", "--all", action="store_true")
            parser.add_argument("-l", action="store_true", dest="long")
            parser.add_argument("-L", "--dereference", action="store_true")
            parser.add_argument("paths", nargs="*")

        options = self._parse_args("ls", args, configure)
        targets = options.paths or ["."]
        sections = []
        for target in targets:
            if (path := ws.resolve(target)) is None:
                return self._error(f"Invalid path: {target}")
            if not path.exists():
                return self._error(f"No such file or directory: {target}")
            if path.is_dir():
                entries = sorted(
                    (
                        entry
                        for entry in path.iterdir()
                        if options.all or not entry.name.startswith(".")
                    ),
                    key=lambda entry: entry.name,
                )
                names = []
                metadata = []
                for entry in entries:
                    if options.dereference and entry.is_symlink():
                        logical = str(Path(target) / entry.name)
                        resolved = ws.resolve(logical)
                        if resolved is None or not resolved.exists():
                            return self._error(f"Cannot dereference workspace entry: {logical}")
                        info = resolved.stat()
                        suffix = "/" if stat.S_ISDIR(info.st_mode) else ""
                    else:
                        info = entry.lstat()
                        suffix = "@" if entry.is_symlink() else "/" if entry.is_dir() else ""
                    names.append(entry.name + suffix)
                    metadata.append(info)
                if options.long:
                    rendered = []
                    for name, info in zip(names, metadata):
                        modified = datetime.fromtimestamp(info.st_mtime).strftime("%Y-%m-%d %H:%M")
                        rendered.append(
                            f"{stat.filemode(info.st_mode)} {info.st_size:>10} {modified} {name}"
                        )
                    output = "\n".join(rendered)
                else:
                    output = "\n".join(names)
                if len(targets) > 1:
                    sections.append(f"{target}:\n" + output)
                else:
                    sections.append(output)
            else:
                if options.long:
                    info = path.stat()
                    modified = datetime.fromtimestamp(info.st_mtime).strftime("%Y-%m-%d %H:%M")
                    sections.append(
                        f"{stat.filemode(info.st_mode)} {info.st_size:>10} {modified} {path.name}"
                    )
                else:
                    sections.append(path.name)
        return self._ok("\n\n".join(sections))

    def _cmd_cat(self, args: list, stdin: str) -> Dict[str, Any]:
        ws = self._workspace
        def configure(parser):
            parser.add_argument("-n", "--number", action="store_true")
            parser.add_argument("files", nargs="*")

        options = self._parse_args("cat", args, configure)
        if not options.files:
            text = stdin
            if options.number:
                text = "\n".join(
                    f"{index:6}\t{line}" for index, line in enumerate(text.splitlines(), 1)
                )
            return self._ok(text)
        parts: List[str] = []
        for arg in options.files:
            if (path := ws.resolve(arg)) is None:
                return self._error(f"Invalid path: {arg}")
            if not path.exists():
                return self._error(f"No such file: {arg}")
            try:
                parts.append(self._read_text(path))
            except Exception as e:
                return self._error(f"Cannot read file: {self._safe_exception_text(e)}")
        text = "".join(parts)
        if options.number:
            text = "\n".join(
                f"{index:6}\t{line}" for index, line in enumerate(text.splitlines(), 1)
            )
        return self._ok(text)

    def _cmd_head(self, args: list, stdin: str) -> Dict[str, Any]:
        ws = self._workspace
        normalized = [
            part
            for arg in args
            for part in (["-n", arg[1:]] if re.fullmatch(r"-\d+", arg) else [arg])
        ]

        def configure(parser):
            parser.add_argument("-n", "--lines", type=self._nonnegative_int, default=10)
            parser.add_argument("files", nargs="*")

        options = self._parse_args("head", normalized, configure)
        if len(options.files) > 1:
            return self._error("head: at most one file is supported")
        if options.files:
            path = ws.resolve(options.files[0])
            if path is None:
                return self._error(f"Invalid path: {options.files[0]}")
            if not path.exists():
                return self._error(f"No such file: {options.files[0]}")
            text = self._read_text(path)
        else:
            text = stdin
        lines = text.splitlines()[:options.lines]
        return self._ok("\n".join(lines))

    def _cmd_tail(self, args: list, stdin: str) -> Dict[str, Any]:
        ws = self._workspace
        normalized = [
            part
            for arg in args
            for part in (["-n", arg[1:]] if re.fullmatch(r"-\d+", arg) else [arg])
        ]

        def configure(parser):
            parser.add_argument("-n", "--lines", type=self._nonnegative_int, default=10)
            parser.add_argument("files", nargs="*")

        options = self._parse_args("tail", normalized, configure)
        if len(options.files) > 1:
            return self._error("tail: at most one file is supported")
        if options.files:
            path = ws.resolve(options.files[0])
            if path is None:
                return self._error(f"Invalid path: {options.files[0]}")
            if not path.exists():
                return self._error(f"No such file: {options.files[0]}")
            text = self._read_text(path)
        else:
            text = stdin
        lines = text.splitlines()[-options.lines:] if options.lines else []
        return self._ok("\n".join(lines))

    def _cmd_wc(self, args: list, stdin: str) -> Dict[str, Any]:
        ws = self._workspace
        def configure(parser):
            parser.add_argument("-l", "--lines", action="store_true")
            parser.add_argument("-w", "--words", action="store_true")
            parser.add_argument("-c", "--bytes", action="store_true")
            parser.add_argument("-m", "--chars", action="store_true")
            parser.add_argument("files", nargs="*")

        options = self._parse_args("wc", args, configure)
        selected = [options.lines, options.words, options.bytes, options.chars]
        enabled_counts = selected if any(selected) else [True, True, True, False]
        sources: list[tuple[str, str]] = []
        if options.files:
            for name in options.files:
                path = ws.resolve(name)
                if path is None:
                    return self._error(f"Invalid path: {name}")
                if not path.exists():
                    return self._error(f"No such file: {name}")
                sources.append((name, self._read_text(path)))
        else:
            sources.append(("", stdin))

        def counts(text: str) -> list[int]:
            values = [
                len(text.splitlines()),
                len(text.split()),
                len(text.encode("utf-8")),
                len(text),
            ]
            return [value for value, enabled in zip(values, enabled_counts) if enabled]

        output = [
            " ".join(map(str, counts(text))) + (f" {name}" if name else "")
            for name, text in sources
        ]
        if len(sources) > 1:
            totals = [sum(values) for values in zip(*(counts(text) for _, text in sources))]
            output.append(" ".join(map(str, totals)) + " total")
        return self._ok("\n".join(output))

    def _cmd_grep(self, args: list, stdin: str) -> Dict[str, Any]:
        ws = self._workspace
        def configure(parser):
            parser.add_argument("-i", "--ignore-case", action="store_true")
            parser.add_argument("-v", "--invert-match", action="store_true")
            parser.add_argument("-n", "--line-number", action="store_true")
            parser.add_argument("-c", "--count", action="store_true")
            parser.add_argument("-F", "--fixed-strings", action="store_true")
            parser.add_argument("pattern")
            parser.add_argument("files", nargs="*")

        options = self._parse_args("grep", args, configure)
        if len(options.files) > 1:
            return self._error("grep: at most one file is supported")
        if options.files:
            path = ws.resolve(options.files[0])
            if path is None:
                return self._error(f"Invalid path: {options.files[0]}")
            if not path.exists():
                return self._error(f"No such file: {options.files[0]}")
            text = self._read_text(path)
        else:
            text = stdin
        pattern = options.pattern.casefold() if options.ignore_case else options.pattern
        matched = []
        for number, line in enumerate(text.splitlines(), 1):
            searchable = line.casefold() if options.ignore_case else line
            include = pattern in searchable
            if include == options.invert_match:
                continue
            matched.append(
                f"{number}:{line}" if options.line_number and not options.count else line
            )
        return self._ok(str(len(matched)) if options.count else "\n".join(matched))

    def _cmd_sort(self, args: list, stdin: str) -> Dict[str, Any]:
        ws = self._workspace
        def configure(parser):
            parser.add_argument("-r", "--reverse", action="store_true")
            parser.add_argument("-n", "--numeric-sort", action="store_true")
            parser.add_argument("-u", "--unique", action="store_true")
            parser.add_argument("files", nargs="*")

        options = self._parse_args("sort", args, configure)
        if len(options.files) > 1:
            return self._error("sort: at most one file is supported")
        if options.files:
            path = ws.resolve(options.files[0])
            if path is None:
                return self._error(f"Invalid path: {options.files[0]}")
            if not path.exists():
                return self._error(f"No such file: {options.files[0]}")
            text = self._read_text(path)
        else:
            text = stdin
        lines = text.splitlines()
        if options.unique:
            lines = list(dict.fromkeys(lines))
        if options.numeric_sort:
            try:
                lines.sort(key=lambda line: float(line.strip()), reverse=options.reverse)
            except ValueError:
                return self._error("sort: non-numeric input with -n")
        else:
            lines.sort(reverse=options.reverse)
        return self._ok("\n".join(lines))

    def _cmd_cut(self, args: list, stdin: str) -> Dict[str, Any]:
        ws = self._workspace
        def configure(parser):
            parser.add_argument("-d", "--delimiter", default="\t")
            parser.add_argument("-f", "--fields", required=True)
            parser.add_argument("files", nargs="*")

        options = self._parse_args("cut", args, configure)
        if len(options.delimiter) != 1:
            return self._error("cut: delimiter must be a single character")
        if len(options.files) > 1:
            return self._error("cut: at most one file is supported")
        if options.files:
            path = ws.resolve(options.files[0])
            if path is None:
                return self._error(f"Invalid path: {options.files[0]}")
            if not path.exists():
                return self._error(f"No such file: {options.files[0]}")
            text = self._read_text(path)
        else:
            text = stdin
        # 解析字段索引（1-based）
        try:
            field_indices = [int(field) - 1 for field in options.fields.split(",")]
            if any(index < 0 for index in field_indices):
                raise ValueError
        except ValueError:
            return self._error(f"Invalid field specification: {options.fields}")
        output_lines = []
        for line in text.splitlines():
            parts = line.split(options.delimiter)
            selected = [parts[i] if i < len(parts) else "" for i in field_indices]
            output_lines.append(options.delimiter.join(selected))
        return self._ok("\n".join(output_lines))

    def _cmd_cp(self, args: list, stdin: str) -> Dict[str, Any]:
        ws = self._workspace
        def configure(parser):
            parser.add_argument("-r", "-R", "--recursive", action="store_true")
            parser.add_argument("-f", "--force", action="store_true")
            parser.add_argument("paths", nargs="+")

        options = self._parse_args("cp", args, configure)
        if len(options.paths) != 2:
            return self._error("cp: exactly one source and one destination are supported")
        source, destination = options.paths
        src_path = ws.resolve(source)
        dst_path = ws.resolve(destination)
        if src_path is None:
            return self._error(f"Invalid source path: {source}")
        if dst_path is None:
            return self._error(f"Invalid destination path: {destination}")
        if not src_path.exists():
            return self._error(f"No such file: {source}")
        if src_path.is_dir() and not options.recursive:
            return self._error(f"cp: omitting directory {source!r}; use -r")
        effective_destination = dst_path / src_path.name if dst_path.is_dir() else dst_path
        destination_name = str(
            Path(destination) / src_path.name if dst_path.is_dir() else Path(destination)
        )
        dst_path = ws.resolve(
            destination_name,
            access="remove" if effective_destination.exists() else "create",
        )
        if dst_path is None:
            return self._error(f"Invalid destination path: {destination}")
        if dst_path.exists() and os.path.samefile(src_path, dst_path):
            return self._error("cp: source and destination identify the same file")
        if src_path.is_dir():
            try:
                dst_path.relative_to(src_path)
            except ValueError:
                pass
            else:
                return self._error("cp: cannot copy a directory into itself")
        try:
            if src_path.is_dir():
                if dst_path.exists() and not options.force:
                    return self._error(f"cp: destination already exists: {destination}")
                ws.create_directory(destination_name, parents=True, exist_ok=options.force)
                for directory, directories, filenames in os.walk(src_path, followlinks=False):
                    parent = Path(directory)
                    symbolic_links = [
                        name for name in (*directories, *filenames)
                        if (parent / name).is_symlink()
                    ]
                    if symbolic_links:
                        raise ValueError(
                            "recursive copies do not follow symbolic links: "
                            + ", ".join(symbolic_links)
                        )
                    relative = parent.relative_to(src_path)
                    for name in directories:
                        child = Path(destination_name) / relative / name
                        ws.create_directory(str(child), parents=True, exist_ok=options.force)
                    for name in filenames:
                        child = Path(destination_name) / relative / name
                        self._copy_file(parent / name, str(child))
            else:
                self._copy_file(src_path, destination_name)
            return self._ok("")
        except Exception as e:
            return self._error(f"cp failed: {self._safe_exception_text(e)}")

    def _cmd_mv(self, args: list, stdin: str) -> Dict[str, Any]:
        ws = self._workspace
        def configure(parser):
            parser.add_argument("-f", "--force", action="store_true")
            parser.add_argument("paths", nargs="+")

        options = self._parse_args("mv", args, configure)
        if len(options.paths) != 2:
            return self._error("mv: exactly one source and one destination are supported")
        source, destination = options.paths
        src_path = ws.resolve(source, access="remove")
        destination_probe = ws.resolve(destination)
        destination_name = str(
            Path(destination) / src_path.name
            if src_path is not None and destination_probe is not None and destination_probe.is_dir()
            else Path(destination)
        )
        effective_probe = ws.resolve(destination_name)
        dst_path = ws.resolve(
            destination_name,
            access=(
                "remove" if effective_probe is not None and effective_probe.exists() else "create"
            ),
        )
        if src_path is None:
            return self._error(f"Invalid source path: {source}")
        if dst_path is None:
            return self._error(f"Invalid destination path: {destination}")
        if not src_path.exists():
            return self._error(f"No such file: {source}")
        if src_path == ws.path:
            return self._error("mv: refusing to move the workspace root")
        if dst_path.exists() and os.path.samefile(src_path, dst_path):
            return self._error("mv: source and destination identify the same file")
        if src_path.is_dir():
            try:
                dst_path.relative_to(src_path)
            except ValueError:
                pass
            else:
                return self._error("mv: cannot move a directory into itself")
        try:
            ws.move(source, destination_name, overwrite=options.force)
            return self._ok("")
        except Exception as e:
            return self._error(f"mv failed: {self._safe_exception_text(e)}")

    def _cmd_rm(self, args: list, stdin: str) -> Dict[str, Any]:
        ws = self._workspace
        def configure(parser):
            parser.add_argument("-r", "-R", "--recursive", action="store_true")
            parser.add_argument("-f", "--force", action="store_true")
            parser.add_argument("paths", nargs="+")

        options = self._parse_args("rm", args, configure)
        for name in options.paths:
            path = ws.resolve(name, access="remove")
            if path is None:
                return self._error(f"Invalid path: {name}")
            if path == ws.path:
                return self._error("rm: refusing to remove the workspace root")
            if not os.path.lexists(path):
                if options.force:
                    continue
                return self._error(f"No such file: {name}")
            try:
                ws.remove(name, recursive=options.recursive, missing_ok=options.force)
            except IsADirectoryError:
                return self._error(f"rm: cannot remove directory {name!r} without -r")
            except Exception as e:
                return self._error(f"rm failed: {self._safe_exception_text(e)}")
        return self._ok("")

    def _cmd_mkdir(self, args: list, stdin: str) -> Dict[str, Any]:
        ws = self._workspace
        def configure(parser):
            parser.add_argument("-p", "--parents", action="store_true")
            parser.add_argument("directories", nargs="+")

        options = self._parse_args("mkdir", args, configure)
        for name in options.directories:
            try:
                ws.create_directory(name, parents=options.parents, exist_ok=options.parents)
            except Exception as e:
                return self._error(f"mkdir failed: {self._safe_exception_text(e)}")
        return self._ok("")

    def _cmd_gunzip(self, args: list, stdin: str) -> Dict[str, Any]:
        ws = self._workspace
        def configure(parser):
            parser.add_argument("-k", "--keep", action="store_true")
            parser.add_argument("-f", "--force", action="store_true")
            parser.add_argument("file")

        options = self._parse_args("gunzip", args, configure)
        path = ws.resolve(options.file)
        if path is None:
            return self._error(f"Invalid path: {options.file}")
        if not path.exists():
            return self._error(f"No such file: {options.file}")
        output_name = (
            str(Path(options.file).with_suffix(""))
            if Path(options.file).suffix == ".gz"
            else str(Path(options.file).parent / (Path(options.file).name + ".out"))
        )
        output_probe = ws.resolve(output_name)
        out_path = ws.resolve(
            output_name,
            access="remove" if output_probe is not None and output_probe.exists() else "create",
        )
        remove_path = None if options.keep else ws.resolve(options.file, access="remove")
        if out_path is None or (not options.keep and remove_path is None):
            return self._error("gunzip: read-only workspace inputs cannot be modified")
        if out_path.exists() and os.path.samefile(path, out_path):
            return self._error("gunzip: input and output identify the same file")
        if out_path.exists() and not options.force:
            return self._error(f"gunzip: output already exists: {out_path.name}; use -f")
        try:
            with ws.safe_open(path, "rb") as f:
                with gzip.GzipFile(fileobj=f, mode="rb") as f_in:
                    with ws.open_for_write(output_name, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
            if remove_path is not None:
                ws.remove(options.file)
            return self._ok(f"Decompressed to {out_path.name}")
        except Exception as e:
            return self._error(f"gunzip failed: {self._safe_exception_text(e)}")

    def _cmd_gzip(self, args: list, stdin: str) -> Dict[str, Any]:
        ws = self._workspace
        def configure(parser):
            parser.add_argument("-k", "--keep", action="store_true")
            parser.add_argument("-f", "--force", action="store_true")
            parser.add_argument("file")

        options = self._parse_args("gzip", args, configure)
        path = ws.resolve(options.file)
        if path is None:
            return self._error(f"Invalid path: {options.file}")
        if not path.exists():
            return self._error(f"No such file: {options.file}")
        output_name = str(Path(options.file).parent / (Path(options.file).name + ".gz"))
        output_probe = ws.resolve(output_name)
        out_path = ws.resolve(
            output_name,
            access="remove" if output_probe is not None and output_probe.exists() else "create",
        )
        remove_path = None if options.keep else ws.resolve(options.file, access="remove")
        if out_path is None or (not options.keep and remove_path is None):
            return self._error("gzip: read-only workspace inputs cannot be modified")
        if out_path.exists() and os.path.samefile(path, out_path):
            return self._error("gzip: input and output identify the same file")
        if out_path.exists() and not options.force:
            return self._error(f"gzip: output already exists: {out_path.name}; use -f")
        try:
            with ws.safe_open(path, "rb") as f_in:
                with ws.open_for_write(output_name, "wb") as output_stream:
                    with gzip.GzipFile(fileobj=output_stream, mode="wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
            if remove_path is not None:
                ws.remove(options.file)
            return self._ok(f"Compressed to {out_path.name}")
        except Exception as e:
            return self._error(f"gzip failed: {self._safe_exception_text(e)}")

    def _cmd_unzip(self, args: list, stdin: str) -> Dict[str, Any]:
        ws = self._workspace
        import zipfile

        def configure(parser):
            parser.add_argument("-d", "--directory", default=".")
            parser.add_argument("file")

        options = self._parse_args("unzip", args, configure)
        path = ws.resolve(options.file)
        destination = ws.resolve(options.directory)
        if destination is not None and not destination.exists():
            destination = ws.resolve(options.directory, access="create")
        if path is None:
            return self._error(f"Invalid path: {options.file}")
        if destination is None:
            return self._error(f"Invalid destination path: {options.directory}")
        if not path.exists():
            return self._error(f"No such file: {options.file}")
        try:
            with ws.safe_open(path, "rb") as f:
                zf = zipfile.ZipFile(f, "r")
                with zf:
                    ws.create_directory(options.directory, parents=True, exist_ok=True)
                    for member in zf.infolist():
                        member_relative = Path(member.filename)
                        if member_relative.is_absolute() or ".." in member_relative.parts:
                            return self._error(f"Unsafe path in archive: {member.filename}")
                        logical_member = str(Path(options.directory) / member_relative)
                        if Path(logical_member) == Path(options.file):
                            return self._error(
                                f"Archive member would overwrite its source: {member.filename}"
                            )
                        mode = member.external_attr >> 16
                        if stat.S_ISLNK(mode):
                            return self._error(
                                f"Symbolic links are not allowed in archives: {member.filename}"
                            )
                        file_type = stat.S_IFMT(mode)
                        if file_type and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                            return self._error(
                                f"Special files are not allowed in archives: {member.filename}"
                            )
                        if member.is_dir():
                            ws.create_directory(logical_member, parents=True, exist_ok=True)
                        else:
                            parent = str(Path(logical_member).parent)
                            ws.create_directory(parent, parents=True, exist_ok=True)
                            with zf.open(member, "r") as input_stream:
                                with ws.open_for_write(logical_member, "wb") as output_stream:
                                    shutil.copyfileobj(input_stream, output_stream)
            return self._ok(f"Extracted to {options.directory}")
        except Exception as e:
            return self._error(f"unzip failed: {self._safe_exception_text(e)}")

    def _cmd_tar(self, args: list, stdin: str) -> Dict[str, Any]:
        ws = self._workspace
        import tarfile

        def configure(parser):
            parser.add_argument("-x", "--extract", action="store_true")
            parser.add_argument("-z", "--gzip", action="store_true")
            parser.add_argument("-f", "--file", required=True)
            parser.add_argument("-C", "--directory", default=".")

        options = self._parse_args("tar", args, configure)
        path = ws.resolve(options.file)
        destination = ws.resolve(options.directory)
        if destination is not None and not destination.exists():
            destination = ws.resolve(options.directory, access="create")
        if path is None:
            return self._error(f"Invalid path: {options.file}")
        if destination is None:
            return self._error(f"Invalid destination path: {options.directory}")
        if not path.exists():
            return self._error(f"No such file: {options.file}")
        if not options.extract:
            return self._error("Only tar extraction (-x) is supported.")
        mode = "r:gz" if options.gzip else "r:*"
        try:
            ws.create_directory(options.directory, parents=True, exist_ok=True)
            with ws.safe_open(path, "rb") as f:
                tf = tarfile.open(fileobj=f, mode=mode)
                with tf:
                    for member in tf.getmembers():
                        if not (member.isfile() or member.isdir()):
                            return self._error(
                                f"Links and special files are not allowed in archives: "
                                f"{member.name}"
                            )
                        member_relative = Path(member.name)
                        if member_relative.is_absolute() or ".." in member_relative.parts:
                            return self._error(f"Unsafe path in archive: {member.name}")
                        logical_member = str(Path(options.directory) / member_relative)
                        if Path(logical_member) == Path(options.file):
                            return self._error(
                                f"Archive member would overwrite its source: {member.name}"
                            )
                        if member.isdir():
                            ws.create_directory(logical_member, parents=True, exist_ok=True)
                        else:
                            parent = str(Path(logical_member).parent)
                            ws.create_directory(parent, parents=True, exist_ok=True)
                            input_stream = tf.extractfile(member)
                            if input_stream is None:
                                raise ValueError(f"Unable to read archive member: {member.name}")
                            with input_stream:
                                with ws.open_for_write(logical_member, "wb") as output_stream:
                                    shutil.copyfileobj(input_stream, output_stream)
            return self._ok(f"Extracted to {options.directory}")
        except Exception as e:
            return self._error(f"tar failed: {self._safe_exception_text(e)}")
