from __future__ import annotations

import hashlib
from typing import Any

from xcrawler.models import TranslatedTweet


def make_translated_tweet(
    *,
    tweet_id: str | None,
    original: str,
    translated: str,
    detected_language: str,
    created_at: str,
    config_fingerprint: str | None = None,
) -> dict[str, Any]:
    result = TranslatedTweet(
        tweet_id=tweet_id,
        original=original,
        translated=translated,
        detected_language=detected_language,
        created_at=created_at,
    ).to_dict()
    result["source_fingerprint"] = translation_source_fingerprint(original)
    if config_fingerprint:
        result["config_fingerprint"] = config_fingerprint
    return result


def translation_source_fingerprint(original: str) -> str:
    return hashlib.sha256(original.encode("utf-8")).hexdigest()[:16]


def translation_record_is_current(record: dict[str, Any], original: str, config_fingerprint: str) -> bool:
    recorded_source = record.get("source_fingerprint") or translation_source_fingerprint(
        str(record.get("original", ""))
    )
    recorded_config = record.get("config_fingerprint")
    translated = record.get("translated")
    return (
        recorded_source == translation_source_fingerprint(original)
        and recorded_config == config_fingerprint
        and isinstance(translated, str)
        and bool(translated.strip())
    )


def normalize_translated_tweet(data: dict[str, Any]) -> dict[str, Any]:
    result = TranslatedTweet.from_dict(data).to_dict()
    result["source_fingerprint"] = data.get("source_fingerprint") or translation_source_fingerprint(result["original"])
    if data.get("config_fingerprint"):
        result["config_fingerprint"] = data["config_fingerprint"]
    return result


def normalize_translated_tweets(data: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not data:
        return []
    return [normalize_translated_tweet(item) for item in data]
