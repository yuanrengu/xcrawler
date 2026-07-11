from __future__ import annotations

import os

from xcrawler.utils.cli_validation import validate_x_username


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def cache_path(cache_dir: str, username: str, suffix: str) -> str:
    safe_username = validate_x_username(username)
    if not suffix or os.path.isabs(suffix) or os.sep in suffix or (os.altsep and os.altsep in suffix):
        raise ValueError("缓存文件后缀必须是单个非空文件名")
    return os.path.join(cache_dir, f"{safe_username}_{suffix}")


def translation_cache_path(cache_dir: str) -> str:
    return os.path.join(cache_dir, "translation_cache.json")
