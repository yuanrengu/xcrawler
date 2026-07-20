from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import warnings
from typing import Any

from xcrawler.storage.base import Storage

logger = logging.getLogger(__name__)


class JsonStoreError(RuntimeError):
    """Raised when persisted JSON cannot be read or recovered safely."""


def _read_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _atomic_copy(source: str, destination: str) -> None:
    parent = os.path.dirname(destination) or "."
    os.makedirs(parent, exist_ok=True)
    temp_path: str | None = None
    try:
        with open(source, "rb") as source_file, tempfile.NamedTemporaryFile(
            "wb",
            dir=parent,
            prefix=f".{os.path.basename(destination)}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = temp_file.name
            shutil.copyfileobj(source_file, temp_file)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, destination)
        temp_path = None
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def load_json(path: str, default: Any = None) -> Any:
    if not os.path.exists(path):
        logger.debug("JSON load miss path=%s", path)
        return default
    logger.debug("JSON load path=%s", path)
    try:
        return _read_json(path)
    except (json.JSONDecodeError, UnicodeDecodeError) as primary_error:
        backup_path = f"{path}.bak"
        if not os.path.exists(backup_path):
            raise JsonStoreError(f"JSON 文件损坏且没有可恢复备份: {path}") from primary_error
        try:
            recovered = _read_json(backup_path)
            _atomic_copy(backup_path, path)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as backup_error:
            raise JsonStoreError(f"JSON 文件及其备份均无法读取: {path}") from backup_error
        warnings.warn(f"JSON 文件已从备份恢复: {path}", RuntimeWarning, stacklevel=2)
        return recovered
    except OSError as error:
        raise JsonStoreError(f"无法读取 JSON 文件: {path}") from error


def save_json(path: str, data: Any, *, indent: int = 2, create_backup: bool = True) -> None:
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)
    logger.debug("JSON save path=%s create_backup=%s", path, create_backup)

    # Serialize to a temporary file before touching the current good version.
    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=parent,
            prefix=f".{os.path.basename(path)}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = temp_file.name
            json.dump(data, temp_file, ensure_ascii=False, indent=indent)
            temp_file.flush()
            os.fsync(temp_file.fileno())

        if create_backup and os.path.exists(path):
            try:
                _read_json(path)
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                # Preserve the last valid backup when the primary is already corrupt.
                pass
            else:
                _atomic_copy(path, f"{path}.bak")

        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def replace_json_files_atomically(updates: dict[str, Any], *, indent: int = 2) -> None:
    """先完整序列化所有文件，再统一替换；任一替换失败时回滚已替换文件。"""
    logger.debug("JSON transaction begin files=%s", list(updates))
    pending: dict[str, str] = {}
    rollback: dict[str, str | None] = {}
    replaced: list[str] = []
    try:
        for path, data in updates.items():
            parent = os.path.dirname(path) or "."
            os.makedirs(parent, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=parent,
                prefix=f".{os.path.basename(path)}.",
                suffix=".pending",
                delete=False,
            ) as temp_file:
                json.dump(data, temp_file, ensure_ascii=False, indent=indent)
                temp_file.flush()
                os.fsync(temp_file.fileno())
                pending[path] = temp_file.name

        for path in updates:
            if not os.path.exists(path):
                rollback[path] = None
                continue
            parent = os.path.dirname(path) or "."
            with tempfile.NamedTemporaryFile(
                "wb",
                dir=parent,
                prefix=f".{os.path.basename(path)}.",
                suffix=".rollback",
                delete=False,
            ) as backup_file:
                rollback[path] = backup_file.name
                with open(path, "rb") as source_file:
                    shutil.copyfileobj(source_file, backup_file)
                backup_file.flush()
                os.fsync(backup_file.fileno())
            _atomic_copy(path, f"{path}.bak")

        for path, temp_path in pending.items():
            os.replace(temp_path, path)
            pending[path] = ""
            replaced.append(path)
        logger.debug("JSON transaction committed files=%s", replaced)
    except Exception:
        logger.debug("JSON transaction rollback files=%s", replaced, exc_info=True)
        for path in reversed(replaced):
            backup_path = rollback.get(path)
            if backup_path:
                os.replace(backup_path, path)
                rollback[path] = None
            elif os.path.exists(path):
                os.unlink(path)
        raise
    finally:
        for temp_path in pending.values():
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
        for backup_path in rollback.values():
            if backup_path and os.path.exists(backup_path):
                os.unlink(backup_path)


class JsonStore(Storage):
    """JSON-file store rooted at a cache directory."""

    def __init__(self, root_dir: str):
        self.root_dir = root_dir

    def path_for(self, key: str) -> str:
        return os.path.join(self.root_dir, key)

    def load_json(self, key: str, default: Any = None) -> Any:
        return load_json(self.path_for(key), default=default)

    def save_json(self, key: str, data: Any) -> None:
        save_json(self.path_for(key), data)

    def append_json_record(self, key: str, record: dict[str, Any]) -> None:
        records = self.load_json(key, default=[])
        if not isinstance(records, list):
            records = []
        records.append(record)
        self.save_json(key, records)
