from __future__ import annotations

import os
import stat
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TextIO

from xcrawler.utils.cli_validation import validate_x_username

PRIVATE_DIR_MODE = 0o700
PRIVATE_FILE_MODE = 0o600


class UnsafePathError(ValueError):
    """Raised when a managed path could escape or redirect local private data."""


def reject_symlink(path: str, *, label: str = "文件") -> None:
    """Reject symlinked managed files while still allowing a symlinked root directory."""
    if os.path.lexists(path) and os.path.islink(path):
        raise UnsafePathError(f"拒绝使用符号链接{label}: {path}")


def _warn_if_directory_is_shared(path: str) -> None:
    if os.name != "posix":
        return
    mode = stat.S_IMODE(os.stat(path).st_mode)
    if mode & 0o077:
        warnings.warn(
            f"目录权限可能暴露本地数据（当前 {mode:#05o}，建议 0o700）: {path}",
            RuntimeWarning,
            stacklevel=3,
        )


def ensure_private_dir(path: str, *, warn_existing: bool = True) -> str:
    """Create a private directory without changing a pre-existing directory's mode."""
    existed = os.path.isdir(path)
    missing: list[str] = []
    candidate = os.path.abspath(path)
    while not os.path.lexists(candidate):
        missing.append(candidate)
        parent = os.path.dirname(candidate)
        if parent == candidate:
            break
        candidate = parent
    os.makedirs(path, mode=PRIVATE_DIR_MODE, exist_ok=True)
    if os.name == "posix" and not existed:
        for created in reversed(missing):
            os.chmod(created, PRIVATE_DIR_MODE)
    elif existed and warn_existing:
        _warn_if_directory_is_shared(path)
    return path


def ensure_dir(path: str) -> str:
    """Backward-compatible alias for private cache/output directory creation."""
    return ensure_private_dir(path)


def protect_private_file(path: str) -> str:
    """Apply private permissions to an existing managed file without following links."""
    reject_symlink(path)
    if os.name == "posix" and os.path.exists(path):
        os.chmod(path, PRIVATE_FILE_MODE, follow_symlinks=False)
    return path


def prepare_private_output(path: str) -> str:
    parent = os.path.dirname(os.path.abspath(path))
    ensure_private_dir(parent)
    reject_symlink(path, label="输出文件")
    return path


@contextmanager
def open_private_text(
    path: str,
    *,
    encoding: str = "utf-8",
    newline: str | None = None,
) -> Iterator[TextIO]:
    """Open a text output with 0600 permissions and no symlink following where supported."""
    prepare_private_output(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, PRIVATE_FILE_MODE)
    if os.name == "posix":
        os.fchmod(descriptor, PRIVATE_FILE_MODE)
    try:
        with os.fdopen(descriptor, "w", encoding=encoding, newline=newline) as output:
            yield output
    finally:
        protect_private_file(path)


def validate_managed_filename(name: str) -> str:
    if (
        not name
        or name in {".", ".."}
        or os.path.isabs(name)
        or os.sep in name
        or (os.altsep and os.altsep in name)
    ):
        raise UnsafePathError("存储键必须是单个非空文件名")
    return name


def cache_path(cache_dir: str, username: str, suffix: str) -> str:
    safe_username = validate_x_username(username)
    try:
        validate_managed_filename(suffix)
    except UnsafePathError as error:
        raise ValueError("缓存文件后缀必须是单个非空文件名") from error
    return os.path.join(cache_dir, f"{safe_username}_{suffix}")


def translation_cache_path(cache_dir: str) -> str:
    return os.path.join(cache_dir, "translation_cache.json")
