from __future__ import annotations

import os

from xcrawler.storage.base import Storage
from xcrawler.storage.json_store import JsonStore
from xcrawler.storage.sqlite_store import SQLiteStore

STORAGE_BACKENDS = ("json", "sqlite")


def create_store(
    cache_dir: str,
    *,
    backend: str = "json",
    sqlite_path: str | None = None,
) -> Storage:
    if not isinstance(backend, str):
        raise ValueError(f"Unsupported storage backend: {backend!r}")
    normalized_backend = backend.strip().lower()
    if normalized_backend == "json":
        return JsonStore(cache_dir)
    if normalized_backend == "sqlite":
        path = os.path.expanduser(sqlite_path or os.path.join(cache_dir, "xcrawler.db"))
        return SQLiteStore(path)
    raise ValueError(f"Unsupported storage backend: {backend}. Expected one of: {', '.join(STORAGE_BACKENDS)}")
