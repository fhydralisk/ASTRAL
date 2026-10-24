"""Minimal Linux ``openat2`` bindings for path-constrained file access."""

from __future__ import annotations

import ctypes
import errno
import os
import platform
from pathlib import Path

_LIBC = ctypes.CDLL(None, use_errno=True)
_SYS_OPENAT2 = {"x86_64": 437, "aarch64": 437}
_RESOLVE_NO_MAGICLINKS = 0x02
_RESOLVE_NO_SYMLINKS = 0x04
_RESOLVE_BENEATH = 0x08


class _OpenHow(ctypes.Structure):
    _fields_ = [
        ("flags", ctypes.c_uint64),
        ("mode", ctypes.c_uint64),
        ("resolve", ctypes.c_uint64),
    ]


def open_beneath(
    root: Path,
    relative_path: str | Path,
    *,
    disallow_symlinks: bool = False,
    flags: int = os.O_RDONLY | os.O_CLOEXEC,
) -> int:
    """Atomically open ``relative_path`` beneath ``root`` using Linux ``openat2(RESOLVE_BENEATH)``.

    Prevents ``..`` traversal and symlinks that resolve outside ``root`` at the
    kernel system-call boundary.

    Args:
        root: Trusted root directory path.
        relative_path: Path relative to ``root`` to open.
        disallow_symlinks: If ``True``, also set ``RESOLVE_NO_SYMLINKS`` to reject all symlinks.
        flags: POSIX ``os.open`` flags (defaults to ``os.O_RDONLY | os.O_CLOEXEC``).

    Returns:
        int: Open OS file descriptor owned by the caller.
    """
    syscall_number = _SYS_OPENAT2.get(platform.machine())
    if syscall_number is None:
        raise OSError(errno.ENOSYS, "openat2 is unsupported on this architecture")
    root_fd = os.open(root, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        resolve = _RESOLVE_BENEATH | _RESOLVE_NO_MAGICLINKS
        if disallow_symlinks:
            resolve |= _RESOLVE_NO_SYMLINKS
        how = _OpenHow(flags=flags, mode=0, resolve=resolve)
        result = int(
            _LIBC.syscall(
                syscall_number,
                root_fd,
                ctypes.c_char_p(os.fsencode(relative_path or ".")),
                ctypes.byref(how),
                ctypes.sizeof(how),
            )
        )
        if result < 0:
            code = ctypes.get_errno()
            if code in {errno.EXDEV, errno.ELOOP}:
                raise PermissionError(
                    errno.EACCES,
                    "Path resolves outside its authorized root",
                    relative_path,
                )
            raise OSError(code, os.strerror(code), relative_path)
        return result
    finally:
        os.close(root_fd)
