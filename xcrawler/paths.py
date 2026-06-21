from __future__ import annotations

import os


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def cache_path(cache_dir: str, username: str, suffix: str) -> str:
    return os.path.join(cache_dir, f"{username}_{suffix}")


def translation_cache_path(cache_dir: str) -> str:
    return os.path.join(cache_dir, "translation_cache.json")
