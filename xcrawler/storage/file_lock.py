from __future__ import annotations

import logging
import os
import stat
import threading
import time
from collections.abc import Iterator, Sequence
from contextlib import ExitStack, contextmanager

from xcrawler.paths import PRIVATE_FILE_MODE, UnsafePathError, ensure_private_dir, reject_symlink

logger = logging.getLogger(__name__)

DEFAULT_LOCK_TIMEOUT = 5.0
LOCK_POLL_INTERVAL = 0.05

_thread_locks: dict[str, threading.Lock] = {}
_thread_locks_guard = threading.Lock()


class FileLockTimeout(TimeoutError):
    """Raised when a managed file lock cannot be acquired before its deadline."""


def lock_path_for(target_path: str) -> str:
    return f"{target_path}.lock"


def _canonical_lock_path(target_path: str) -> str:
    return os.path.normcase(os.path.realpath(lock_path_for(target_path)))


def _thread_lock_for(target_path: str) -> threading.Lock:
    canonical_path = _canonical_lock_path(target_path)
    with _thread_locks_guard:
        return _thread_locks.setdefault(canonical_path, threading.Lock())


def _open_lock_file(target_path: str) -> tuple[int, str]:
    lock_path = lock_path_for(target_path)
    ensure_private_dir(os.path.dirname(os.path.abspath(lock_path)))
    reject_symlink(lock_path, label="锁文件")
    flags = os.O_RDWR | os.O_CREAT
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lock_path, flags, PRIVATE_FILE_MODE)
    try:
        opened_stat = os.fstat(descriptor)
        path_stat = os.lstat(lock_path)
        if (opened_stat.st_dev, opened_stat.st_ino) != (path_stat.st_dev, path_stat.st_ino):
            raise UnsafePathError(f"锁文件在打开时被替换: {lock_path}")
        if not stat.S_ISREG(opened_stat.st_mode) or opened_stat.st_nlink != 1:
            raise UnsafePathError(f"锁文件必须是普通文件: {lock_path}")
        if os.name == "posix":
            os.fchmod(descriptor, PRIVATE_FILE_MODE)
        elif opened_stat.st_size == 0:
            os.write(descriptor, b"\0")
    except Exception:
        os.close(descriptor)
        raise
    return descriptor, lock_path


def _try_acquire_os_lock(descriptor: int) -> bool:
    if os.name == "nt":
        import msvcrt

        os.lseek(descriptor, 0, os.SEEK_SET)
        try:
            getattr(msvcrt, "locking")(descriptor, getattr(msvcrt, "LK_NBLCK"), 1)
        except OSError:
            return False
        return True

    import fcntl

    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


def _release_os_lock(descriptor: int) -> None:
    if os.name == "nt":
        import msvcrt

        os.lseek(descriptor, 0, os.SEEK_SET)
        getattr(msvcrt, "locking")(descriptor, getattr(msvcrt, "LK_UNLCK"), 1)
        return

    import fcntl

    fcntl.flock(descriptor, fcntl.LOCK_UN)


def _remaining(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


@contextmanager
def file_lock(target_path: str, *, timeout: float = DEFAULT_LOCK_TIMEOUT) -> Iterator[str]:
    """Hold an exclusive thread/process lock associated with ``target_path``."""
    if timeout < 0:
        raise ValueError("lock timeout must be >= 0")

    deadline = time.monotonic() + timeout
    thread_lock = _thread_lock_for(target_path)
    if not thread_lock.acquire(timeout=_remaining(deadline)):
        raise FileLockTimeout(f"获取文件锁超时（{timeout:.3f}s）: {lock_path_for(target_path)}")

    descriptor: int | None = None
    acquired = False
    lock_path = lock_path_for(target_path)
    try:
        descriptor, lock_path = _open_lock_file(target_path)
        while True:
            if _try_acquire_os_lock(descriptor):
                acquired = True
                break
            remaining = _remaining(deadline)
            if remaining <= 0:
                raise FileLockTimeout(f"获取文件锁超时（{timeout:.3f}s）: {lock_path}")
            time.sleep(min(LOCK_POLL_INTERVAL, remaining))
        logger.debug("File lock acquired path=%s", lock_path)
        yield lock_path
    finally:
        if descriptor is not None:
            if acquired:
                _release_os_lock(descriptor)
            os.close(descriptor)
        thread_lock.release()
        if acquired:
            logger.debug("File lock released path=%s", lock_path)


@contextmanager
def file_locks(target_paths: Sequence[str], *, timeout: float = DEFAULT_LOCK_TIMEOUT) -> Iterator[None]:
    """Acquire multiple locks in a canonical order to prevent lock-order deadlocks."""
    if timeout < 0:
        raise ValueError("lock timeout must be >= 0")

    canonical_targets: dict[str, str] = {}
    for target_path in target_paths:
        canonical_targets.setdefault(_canonical_lock_path(target_path), target_path)

    deadline = time.monotonic() + timeout
    with ExitStack() as stack:
        for canonical_path in sorted(canonical_targets):
            target_path = canonical_targets[canonical_path]
            stack.enter_context(file_lock(target_path, timeout=_remaining(deadline)))
        yield
