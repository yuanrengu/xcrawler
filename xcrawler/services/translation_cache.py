from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from xcrawler.storage.json_store import update_json
from xcrawler.utils.text import usable_translation

TRANSLATION_CACHE_SCHEMA_VERSION = 2
TRANSLATION_PROMPT_VERSION = "social-media-zh-v1"
DEFAULT_TARGET_LANGUAGE = "zh-CN"


class _CacheEntries(dict[str, Any]):
    """JSON-compatible entries with process-local changes, never serialized."""

    def __init__(self, entries: dict[str, Any] | None = None):
        super().__init__(entries or {})
        self.pending: dict[str, Any] = {}

    def __setitem__(self, key: str, value: Any) -> None:
        super().__setitem__(key, value)
        self.pending[key] = value


@dataclass(frozen=True)
class TranslationCacheContext:
    provider: str
    model: str
    target_language: str = DEFAULT_TARGET_LANGUAGE
    prompt_version: str = TRANSLATION_PROMPT_VERSION

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()[:16]


def new_translation_cache(*, legacy_entries: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "version": TRANSLATION_CACHE_SCHEMA_VERSION,
        "entries": _CacheEntries(),
        "legacy_entries": dict(legacy_entries or {}),
    }


def normalize_translation_cache(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return new_translation_cache()

    if data.get("version") == TRANSLATION_CACHE_SCHEMA_VERSION:
        entries = data.get("entries")
        legacy_entries = data.get("legacy_entries")
        return {
            "version": TRANSLATION_CACHE_SCHEMA_VERSION,
            "entries": entries if isinstance(entries, _CacheEntries) else _CacheEntries(
                entries if isinstance(entries, dict) else None
            ),
            "legacy_entries": (
                {str(key): value for key, value in legacy_entries.items() if isinstance(value, str)}
                if isinstance(legacy_entries, dict)
                else {}
            ),
        }

    # Version 1 was a plain {source_text: translated_text} mapping. Preserve it
    # for manual recovery, but do not reuse entries whose provider/model/prompt
    # provenance is unknown.
    legacy_entries = {
        str(key): value
        for key, value in data.items()
        if isinstance(key, str) and isinstance(value, str)
    }
    return new_translation_cache(legacy_entries=legacy_entries)


def ensure_translation_cache(cache: dict[str, Any]) -> dict[str, Any]:
    if cache.get("version") != TRANSLATION_CACHE_SCHEMA_VERSION:
        normalized = normalize_translation_cache(cache)
        cache.clear()
        cache.update(normalized)
    else:
        entries = cache.get("entries")
        if not isinstance(entries, _CacheEntries):
            cache["entries"] = _CacheEntries(entries if isinstance(entries, dict) else None)
        if not isinstance(cache.get("legacy_entries"), dict):
            cache["legacy_entries"] = {}
    return cache


def _cache_key(text: str, context: TranslationCacheContext) -> str:
    payload = f"{context.canonical_json()}\0{text}".encode()
    return hashlib.sha256(payload).hexdigest()


def get_cached_translation(
    cache: dict[str, Any],
    text: str,
    context: TranslationCacheContext,
) -> str | None:
    cache = ensure_translation_cache(cache)
    entry = cache["entries"].get(_cache_key(text, context))
    if not isinstance(entry, dict):
        return None
    if entry.get("context") != context.to_dict():
        return None
    translated = entry.get("translated")
    return translated if isinstance(translated, str) and usable_translation(translated) else None


def set_cached_translation(
    cache: dict[str, Any],
    text: str,
    translated: str,
    context: TranslationCacheContext,
) -> None:
    if not usable_translation(translated):
        raise ValueError("不能缓存空白译文")
    cache = ensure_translation_cache(cache)
    cache["entries"][_cache_key(text, context)] = {
        "translated": translated,
        "context": context.to_dict(),
    }


def persist_translation_cache(path: str, cache: dict[str, Any]) -> None:
    """Commit local translations only; loaded entries cannot overwrite corrections."""
    incoming = normalize_translation_cache(cache)
    entries = incoming["entries"]
    changes = dict(entries.pending)

    def merge(current: Any) -> dict[str, Any]:
        result = normalize_translation_cache(current)
        for section in ("entries", "legacy_entries"):
            # Preserve imports/migrations without overwriting an existing value.
            for key, value in incoming[section].items():
                result[section].setdefault(key, value)
        result["entries"].update(changes)
        return result

    saved = update_json(path, merge, default={})
    # Only acknowledge changes after a successful commit. Refresh stale entries
    # so subsequent batches also use corrections made by other processes.
    entries.clear()
    entries.update(saved["entries"])
    entries.pending.clear()


def translation_cache_entry_count(
    cache: dict[str, Any],
    context: TranslationCacheContext | None = None,
) -> int:
    cache = ensure_translation_cache(cache)
    if context is None:
        return len(cache["entries"])
    expected_context = context.to_dict()
    return sum(
        1
        for entry in cache["entries"].values()
        if isinstance(entry, dict) and entry.get("context") == expected_context
    )


def legacy_translation_cache_entry_count(cache: dict[str, Any]) -> int:
    cache = ensure_translation_cache(cache)
    return len(cache["legacy_entries"])
