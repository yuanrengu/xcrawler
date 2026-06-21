from __future__ import annotations

from typing import Any

from xcrawler.models import TranslatedTweet


def make_translated_tweet(
    *,
    tweet_id: str | None,
    original: str,
    translated: str,
    detected_language: str,
    created_at: str,
) -> dict[str, Any]:
    return TranslatedTweet(
        tweet_id=tweet_id,
        original=original,
        translated=translated,
        detected_language=detected_language,
        created_at=created_at,
    ).to_dict()


def normalize_translated_tweet(data: dict[str, Any]) -> dict[str, Any]:
    return TranslatedTweet.from_dict(data).to_dict()


def normalize_translated_tweets(data: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not data:
        return []
    return [normalize_translated_tweet(item) for item in data]
