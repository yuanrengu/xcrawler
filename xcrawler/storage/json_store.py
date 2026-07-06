from __future__ import annotations

import json
import os
from typing import Any

from xcrawler.storage.base import Storage


def load_json(path: str, default: Any = None) -> Any:
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path: str, data: Any, *, indent: int = 2) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)


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
