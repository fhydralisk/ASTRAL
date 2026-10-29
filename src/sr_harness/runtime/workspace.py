# Copyright (c) 2026-present, Yumeow. Licensed under the MIT License.
"""Persistent workspace management for interactive SRHarness sessions."""

from __future__ import annotations

import logging
import io
import os
import shutil
import stat
import ctypes
from collections.abc import Iterator
from pathlib import Path
from typing import IO, Literal

from ..utils.openat2 import open_beneath
from ..utils import log_exception

_logger = logging.getLogger(__name__)

_LIBC = ctypes.CDLL(None, use_errno=True) if os.name == "posix" else None
_RENAME_NOREPLACE = 1


class Workspace:
    """Manage a writable workspace with explicitly registered read-only inputs."""

    def __init__(
        self,
        path: str | Path,
        *,
        read_only: bool = False,
    ) -> None:
        """Create or open a workspace.

        Args:
            path: Existing or new workspace root. The caller owns the directory and
                decides where it is created and when it is removed.
        """
        self._path = Path(path).resolve()
        self._read_only = bool(read_only)
        if self._read_only:
            if not self._path.is_dir():
                raise FileNotFoundError(f"Read-only workspace does not exist: {self._path}")
        else:
            self._path.mkdir(parents=True, exist_ok=True)
        self._mount_map: dict[Path, Path] = {}
        self._readonly_mounts: set[Path] = set()
        self._lock_rules: dict[Path, bool] = {}
        _logger.info(f"Initialized workspace at {self._path}")

    @property
    def path(self) -> Path:
        """Return the workspace root."""
        return self._path

    @property
    def read_only(self) -> bool:
        """Return whether every workspace mutation is disabled."""
        return self._read_only

    @property
    def mount_map(self) -> dict[Path, Path]:
        """Return logical workspace mount points mapped to their host sources."""
        return dict(self._mount_map)

    def mount_mode(self, path: str | Path) -> Literal["read-only", "read-write"] | None:
        """Return the registered mount mode containing a logical workspace path.

        Args:
            path: Absolute or workspace-relative logical path.

        Returns:
            ``"read-only"`` or ``"read-write"`` for a mounted path, otherwise
            ``None``.
        """
        logical = Path(path)
        if not logical.is_absolute():
            logical = self._path / logical
        try:
            logical.relative_to(self._path)
        except ValueError:
            raise ValueError("Mount queries must refer to a logical workspace path") from None
        for root in (logical, *logical.parents):
            if root in self._mount_map:
                return "read-only" if root in self._readonly_mounts else "read-write"
            if root == self._path:
                break
        return None

    @property
    def lock_rules(self) -> dict[str, bool]:
        """Return explicit lock overrides keyed by workspace-relative paths."""
        return {
            str(path.relative_to(self._path)): locked
            for path, locked in self._lock_rules.items()
        }

    @property
    def has_locks(self) -> bool:
        """Return whether any path is effectively protected by a lock rule."""
        return any(self._lock_rules.values())

    def is_locked(self, path: str | Path) -> bool:
        """Return whether ``path`` is protected by a user lock rule or a read-only mount.

        Args:
            path: Absolute or workspace-relative path to check.

        Returns:
            bool: ``True`` if writing or deleting ``path`` is blocked by a lock rule.
        """
        logical = Path(path)
        if not logical.is_absolute():
            logical = self._path / logical
        try:
            logical.relative_to(self._path)
        except ValueError:
            raise ValueError("Lock queries must refer to a logical workspace path") from None
        for candidate in (logical, *logical.parents):
            if candidate == self._path.parent:
                break
            if candidate in self._lock_rules:
                return self._lock_rules[candidate]
            if candidate == self._path:
                break
        return False

    def contains_locked_paths(self, path: str | Path) -> bool:
        """Return whether ``path`` or any descendant inside its directory tree is explicitly locked.

        Args:
            path: Workspace-relative or absolute path to inspect.

        Returns:
            bool: ``True`` if ``path`` or any nested entry is locked.
        """
        logical = Path(path)
        if not logical.is_absolute():
            logical = self._path / logical
        try:
            logical.relative_to(self._path)
        except ValueError:
            raise ValueError("Lock queries must refer to a logical workspace path") from None
        return self.is_locked(logical) or any(
            locked and logical in rule.parents
            for rule, locked in self._lock_rules.items()
        )

    def set_locked(self, relative_path: str, locked: bool) -> Path:
        """Set an explicit lock rule on a workspace file or directory tree.

        Args:
            relative_path: Workspace-relative file or directory path.
            locked: Lock the path when true or explicitly unlock it when false.

        Returns:
            The affected workspace path.

        Raises:
            ValueError: If the path is invalid, missing, or belongs to a mounted input.
        """
        path = self.resolve(relative_path)
        if path is None or not path.exists():
            raise ValueError(f"File or directory not found: {relative_path}")
        logical = self._path / Path(relative_path)
        if self.mount_mode(logical) is not None:
            raise ValueError("Mounted inputs cannot be locked or unlocked")
        descendants = [rule for rule in self._lock_rules if logical in rule.parents]
        for rule in descendants:
            del self._lock_rules[rule]
        inherited = self.is_locked(logical.parent)
        if locked == inherited:
            self._lock_rules.pop(logical, None)
        else:
            self._lock_rules[logical] = locked
        self._apply_lock_permissions()
        return path

    def load_lock_rules(self, rules: dict[str, bool]) -> None:
        """Replace lock overrides from persisted workspace state.

        Args:
            rules: Workspace-relative paths mapped to explicit lock states.
        """
        parsed: dict[Path, bool] = {}
        for relative_path, locked in rules.items():
            if not isinstance(relative_path, str) or not isinstance(locked, bool):
                raise TypeError("Workspace lock rules must map path strings to booleans")
            requested = Path(relative_path)
            if requested.is_absolute() or not requested.parts or ".." in requested.parts:
                raise ValueError(f"Invalid workspace lock path: {relative_path!r}")
            logical = self._path / requested
            if not logical.exists() or logical.is_symlink() or self.mount_mode(logical) is not None:
                raise ValueError(f"Workspace lock path is unavailable: {relative_path!r}")
            parsed[logical] = locked
        self._lock_rules = parsed
        self._apply_lock_permissions()

    def _apply_lock_permissions(self) -> None:
        """Apply explicit lock rules through stable descriptors without following links."""
        if self._read_only:
            return
        if os.name != "posix":
            if self._lock_rules:
                raise OSError("Workspace lock enforcement requires Linux")
            return
        mount_roots = set(self._mount_map)
        paths = [self._path]
        for current_name, directory_names, file_names in os.walk(
            self._path,
            followlinks=False,
        ):
            current = Path(current_name)
            directory_names[:] = [
                name
                for name in directory_names
                if (current / name) not in mount_roots
                and not (current / name).is_symlink()
            ]
            paths.extend(current / name for name in directory_names)
            paths.extend(
                current / name
                for name in file_names
                if (current / name) not in mount_roots
                and not (current / name).is_symlink()
            )
        for path in reversed(paths):
            relative = path.relative_to(self._path)
            try:
                descriptor = open_beneath(
                    self._path,
                    relative,
                    disallow_symlinks=True,
                    flags=os.O_RDONLY | os.O_CLOEXEC,
                )
            except FileNotFoundError:
                continue
            try:
                mode = stat.S_IMODE(os.fstat(descriptor).st_mode)
                updated = mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
                if not self.is_locked(path):
                    updated |= stat.S_IWUSR
                os.fchmod(descriptor, updated)
            finally:
                os.close(descriptor)

    def resolve(
        self,
        relative_path: str,
        *,
        access: Literal["read", "write", "create", "remove"] = "read",
    ) -> Path | None:
        """Resolve a safe workspace-relative path.

        Args:
            relative_path: Relative path supplied by the caller.
            access: Intended operation. ``write`` changes existing content, ``create``
                adds a new entry, and ``remove`` deletes, moves, or replaces an
                existing entry.

        Returns:
            The resolved path, or ``None`` when the requested access is invalid.
        """
        if access not in {"read", "write", "create", "remove"}:
            raise ValueError(f"Unknown workspace access intent: {access}")
        if self._read_only and access != "read":
            return None
        if not relative_path:
            return self._path
        if os.path.isabs(relative_path):
            return None
        if len(relative_path) >= 2 and relative_path[0].isalpha() and relative_path[1] == ":":
            return None
        requested = Path(relative_path)
        if ".." in requested.parts:
            return None
        logical = self._path / requested
        if requested.parts:
            mount = self._path / requested.parts[0]
            if source := self._mount_map.get(mount):
                if access != "read" and mount in self._readonly_mounts:
                    return None
                if access == "remove" and len(requested.parts) == 1:
                    return None
                if source.is_file() and len(requested.parts) > 1:
                    return None
                candidate = (
                    (source / Path(*requested.parts[1:])).resolve()
                    if source.is_dir()
                    else source
                )
                try:
                    candidate.relative_to(source if source.is_dir() else source.parent)
                except ValueError:
                    return None
                return candidate
        if access != "read":
            logical_component = self._path
            for index, component in enumerate(requested.parts):
                logical_component /= component
                if logical_component.is_symlink():
                    if access == "remove" and index == len(requested.parts) - 1:
                        return None if self.is_locked(logical_component) else logical_component
                    return None
        candidate = logical.resolve()
        try:
            candidate.relative_to(self._path.resolve())
        except ValueError:
            return None
        if access != "read":
            if access == "create":
                probe = candidate.parent
                while not probe.exists() and probe != self._path:
                    probe = probe.parent
                logical_probe = self._path / probe.relative_to(self._path)
                if probe.exists() and self.is_locked(logical_probe):
                    return None
                return candidate
            if candidate.exists() and self.is_locked(logical):
                return None
            if access == "remove" and self.contains_locked_paths(logical):
                return None
            if not candidate.exists():
                probe = candidate.parent
                while not probe.exists() and probe != self._path:
                    probe = probe.parent
            else:
                probe = candidate
            logical_probe = self._path / probe.relative_to(self._path)
            if probe.exists() and self.is_locked(logical_probe):
                return None
        return candidate

    def safe_open(
        self,
        path: str | Path,
        mode: Literal["r", "rb"] = "r",
        *,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> IO:
        """Atomically open a file for reading inside the workspace or an authorized mount without escaping via symlinks.

        Args:
            path: Workspace-relative or mounted path to open.
            mode: Read mode (``"r"`` for text or ``"rb"`` for binary).
            encoding: Text encoding when ``mode == "r"``.
            errors: Encoding error handling strategy when ``mode == "r"``.

        Returns:
            IO: Open read-only file stream.
        """
        if mode not in {"r", "rb"}:
            raise ValueError("safe_open only supports 'r' and 'rb'")
        if mode == "rb" and (encoding is not None or errors is not None):
            raise ValueError("binary mode doesn't take an encoding or errors argument")
        requested = Path(path).expanduser()
        if not requested.is_absolute():
            requested = Path.cwd() / requested
        resolved = requested.resolve(strict=True)
        try:
            relative_path = resolved.relative_to(self._path)
        except ValueError:
            descriptor = None
        else:
            descriptor = open_beneath(self._path, relative_path)
        if descriptor is None:
            for source in self._mount_map.values():
                if source.is_file():
                    if resolved == source:
                        descriptor = open_beneath(
                            source.parent,
                            source.name,
                            disallow_symlinks=True,
                        )
                        break
                    continue
                try:
                    relative_path = resolved.relative_to(source)
                except ValueError:
                    continue
                descriptor = open_beneath(source, relative_path)
                break
        if descriptor is None:
            raise PermissionError(f"Path is outside the workspace: {path}")
        raw = io.FileIO(descriptor, mode="rb", closefd=True)
        if mode == "rb":
            return raw
        return io.TextIOWrapper(raw, encoding=encoding, errors=errors)

    def create_directory(
        self,
        relative_path: str,
        *,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> Path:
        """Create a directory without following mutable workspace symlinks.

        Args:
            relative_path: Workspace-relative directory path.
            parents: Create missing parent directories as needed.
            exist_ok: Do not fail if the final directory already exists.

        Returns:
            The logical path of the created directory.
        """
        requested = self._relative_mutation_path(relative_path)
        if requested == Path("."):
            if exist_ok:
                return self._path
            raise FileExistsError(relative_path)
        root, relative, logical = self._mutation_route(relative_path, access="create")
        components = relative.parts
        if not components:
            if exist_ok:
                return logical
            raise FileExistsError(relative_path)
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            for index, component in enumerate(components):
                final = index == len(components) - 1
                try:
                    os.mkdir(component, dir_fd=descriptor)
                except FileExistsError:
                    if final and not exist_ok:
                        raise
                    if not parents and not final:
                        raise
                if not final:
                    next_descriptor = os.open(
                        component,
                        os.O_RDONLY
                        | os.O_DIRECTORY
                        | os.O_CLOEXEC
                        | getattr(os, "O_NOFOLLOW", 0),
                        dir_fd=descriptor,
                    )
                    os.close(descriptor)
                    descriptor = next_descriptor
        finally:
            os.close(descriptor)
        return logical

    def open_for_write(
        self,
        relative_path: str,
        mode: Literal["w", "wb", "x", "xb"] = "w",
        *,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> IO:
        """Open a workspace file for writing without following symbolic links.

        Args:
            relative_path: Workspace-relative file path.
            mode: Truncating or exclusive text/binary write mode.
            encoding: Text encoding used by text modes.
            errors: Text encoding error strategy used by text modes.

        Returns:
            An open stream owned by the caller.
        """
        if mode not in {"w", "wb", "x", "xb"}:
            raise ValueError("open_for_write only supports 'w', 'wb', 'x', and 'xb'")
        existing = self.resolve(relative_path)
        access = "write" if existing is not None and existing.exists() else "create"
        _, parent_fd, name, _ = self._open_mutation_parent(relative_path, access=access)
        flags = os.O_WRONLY | os.O_CREAT | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
        flags |= os.O_EXCL if "x" in mode else os.O_TRUNC
        try:
            descriptor = os.open(name, flags, 0o666, dir_fd=parent_fd)
        finally:
            os.close(parent_fd)
        binary = os.fdopen(descriptor, "wb")
        if "b" in mode:
            if encoding is not None or errors is not None:
                binary.close()
                raise ValueError("binary mode doesn't take an encoding or errors argument")
            return binary
        import io
        return io.TextIOWrapper(binary, encoding=encoding, errors=errors)

    def replace_file(self, source: str | Path, destination: str) -> Path:
        """Atomically replace a writable workspace file with a staged temporary file.

        Args:
            source: Path to the caller-owned staging file.
            destination: Workspace-relative target file path.

        Returns:
            Path: Logical workspace path of the replaced file.
        """
        existing = self.resolve(destination)
        access = "write" if existing is not None and existing.exists() else "create"
        _, parent_fd, name, logical = self._open_mutation_parent(destination, access=access)
        try:
            os.replace(source, name, dst_dir_fd=parent_fd)
        finally:
            os.close(parent_fd)
        return logical

    def install(self, source: str | Path, destination: str) -> Path:
        """Atomically move a staged file or directory into the workspace without overwriting existing entries.

        Args:
            source: Path to the caller-owned staging file or directory.
            destination: Workspace-relative destination path.

        Returns:
            Path: Logical workspace path of the installed entry.
        """
        source = Path(source)
        if not source.is_absolute():
            source = Path.cwd() / source
        _, destination_fd, destination_name, logical = self._open_mutation_parent(
            destination,
            access="create",
        )
        try:
            self._rename_no_replace(
                getattr(os, "AT_FDCWD", -100),
                os.fspath(source),
                destination_fd,
                destination_name,
            )
        finally:
            os.close(destination_fd)
        return logical

    def move(self, source: str, destination: str, *, overwrite: bool = False) -> Path:
        """Move or rename a writable workspace entry while enforcing lock and mount boundaries.

        Args:
            source: Workspace-relative source path.
            destination: Workspace-relative destination path.
            overwrite: Whether to allow replacing an existing unlocked file at ``destination``.

        Returns:
            Path: Logical workspace path of the moved entry.
        """
        source_relative = self._relative_mutation_path(source)
        destination_relative = self._relative_mutation_path(destination)
        if source_relative == Path(".") or destination_relative == Path("."):
            raise ValueError("The workspace root cannot be moved or replaced")
        if source_relative in destination_relative.parents:
            raise ValueError("A directory cannot be moved inside itself")
        _, source_fd, source_name, _ = self._open_mutation_parent(source, access="remove")
        destination_probe = self.resolve(destination)
        destination_access = (
            "remove"
            if overwrite and destination_probe is not None and destination_probe.exists()
            else "create"
        )
        _, destination_fd, destination_name, destination_logical = self._open_mutation_parent(
            destination,
            access=destination_access,
        )
        try:
            if overwrite:
                os.rename(
                    source_name,
                    destination_name,
                    src_dir_fd=source_fd,
                    dst_dir_fd=destination_fd,
                )
            else:
                self._rename_no_replace(
                    source_fd,
                    source_name,
                    destination_fd,
                    destination_name,
                )
        finally:
            os.close(source_fd)
            os.close(destination_fd)
        return destination_logical

    def remove(self, relative_path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        """Delete a writable file or directory tree inside the workspace without following symlinks.

        Args:
            relative_path: Workspace-relative path to remove.
            recursive: Whether to recursively delete non-empty directories.
            missing_ok: If ``True``, do not raise when ``relative_path`` does not exist.
        """
        _, parent_fd, name, _ = self._open_mutation_parent(relative_path, access="remove")
        try:
            try:
                metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                if missing_ok:
                    return
                raise
            if stat.S_ISDIR(metadata.st_mode):
                if not recursive:
                    raise IsADirectoryError(relative_path)
                shutil.rmtree(name, dir_fd=parent_fd)
            else:
                os.unlink(name, dir_fd=parent_fd)
        finally:
            os.close(parent_fd)

    def _relative_mutation_path(self, relative_path: str) -> Path:
        if not relative_path:
            return Path(".")
        if os.path.isabs(relative_path):
            raise ValueError(f"Invalid workspace path: {relative_path}")
        if len(relative_path) >= 2 and relative_path[0].isalpha() and relative_path[1] == ":":
            raise ValueError(f"Invalid workspace path: {relative_path}")
        requested = Path(relative_path)
        if ".." in requested.parts:
            raise ValueError(f"Invalid workspace path: {relative_path}")
        return requested

    def _mutation_route(
        self,
        relative_path: str,
        *,
        access: Literal["write", "create", "remove"],
    ) -> tuple[Path, Path, Path]:
        if self._read_only:
            raise PermissionError("Workspace is read-only")
        requested = self._relative_mutation_path(relative_path)
        logical = self._path / requested
        if requested.parts and (mount := self._path / requested.parts[0]) in self._mount_map:
            if mount in self._readonly_mounts:
                raise PermissionError("Mounted input is read-only")
            if access == "remove" and len(requested.parts) == 1:
                raise PermissionError("A mounted workspace entry cannot be removed")
            source = self._mount_map[mount]
            if source.is_file():
                if len(requested.parts) != 1:
                    raise ValueError(f"Invalid mounted file path: {relative_path}")
                return source.parent, Path(source.name), logical
            return source, Path(*requested.parts[1:]), logical
        if access == "create":
            if self.is_locked(logical):
                raise PermissionError(f"Workspace path is locked: {relative_path}")
            probe = logical.parent
            while probe != self._path and not probe.exists():
                probe = probe.parent
            if self.is_locked(probe):
                raise PermissionError(f"Workspace path is locked: {relative_path}")
        else:
            if self.is_locked(logical):
                raise PermissionError(f"Workspace path is locked: {relative_path}")
            if access == "remove" and self.is_locked(logical.parent):
                raise PermissionError(
                    f"Workspace parent directory is locked: {relative_path}"
                )
            if access == "remove" and self.contains_locked_paths(logical):
                raise PermissionError(f"Workspace path contains locked entries: {relative_path}")
        return self._path, requested, logical

    def _open_mutation_parent(
        self,
        relative_path: str,
        *,
        access: Literal["write", "create", "remove"],
    ) -> tuple[Path, int, str, Path]:
        root, relative, logical = self._mutation_route(relative_path, access=access)
        if relative == Path(".") or not relative.name:
            raise ValueError("The workspace root cannot be modified")
        descriptor = open_beneath(
            root,
            relative.parent,
            disallow_symlinks=True,
            flags=os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC,
        )
        return root, descriptor, relative.name, logical

    @staticmethod
    def _rename_no_replace(source_fd: int, source: str, destination_fd: int, destination: str) -> None:
        result = _LIBC.renameat2(
            source_fd,
            os.fsencode(source),
            destination_fd,
            os.fsencode(destination),
            _RENAME_NOREPLACE,
        )
        if result != 0:
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code), destination)

    def mount(self, source: str | Path, *, readonly: bool = True) -> Path:
        """Expose a host file or directory through a registered link.

        Args:
            source: Existing host file or directory.
            readonly: Whether workspace operations and sandboxed code may modify it.

        Returns:
            The logical link inside the workspace.
        """
        if self._read_only:
            raise PermissionError("Workspace is read-only")
        source = Path(source).expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(f"Workspace input does not exist: {source}")
        destination = self._path / source.name
        if destination.is_symlink() and destination.resolve() == source:
            self._mount_map[destination] = source
            if readonly:
                self._readonly_mounts.add(destination)
            else:
                self._readonly_mounts.discard(destination)
            return destination
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(
                f"Workspace input name {destination.name!r} is already in use; "
                "rename one of the conflicting inputs."
            )
        try:
            os.symlink(source, destination, target_is_directory=source.is_dir())
            self._mount_map[destination] = source
            if readonly:
                self._readonly_mounts.add(destination)
        except Exception as exc:
            _logger.error(
                f"Failed to add {source} to workspace: "
                f"{log_exception(exc, with_traceback=False)}"
            )
            raise
        return destination

    def iter_files(self) -> Iterator[tuple[Path, Path]]:
        """Yield logical and resolved paths for every workspace file."""
        mounted = set(self._mount_map)
        for item in self._path.rglob("*"):
            if any(parent in mounted for parent in (item, *item.parents)):
                continue
            if item.is_symlink():
                continue
            if item.is_file():
                yield item.relative_to(self._path), item
        for logical, source in self._mount_map.items():
            prefix = Path(logical.name)
            if source.is_file():
                yield prefix, source
            else:
                for item in source.rglob("*"):
                    if item.is_file():
                        yield prefix / item.relative_to(source), item
