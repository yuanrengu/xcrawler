from __future__ import annotations

from typing import Any


def merge_tweets(existing_tweets: list[dict[str, Any]], new_tweets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按推文 ID 去重合并，新记录覆盖同 ID 旧记录，并按时间倒序返回。"""
    records: dict[str, dict[str, Any]] = {}
    for tweet in [*existing_tweets, *new_tweets]:
        tweet_id = tweet.get("id")
        if tweet_id is None:
            continue
        records[str(tweet_id)] = tweet
    return sorted(records.values(), key=lambda tweet: tweet.get("created_at", ""), reverse=True)


def merge_translated_tweets(
    existing_records: list[dict[str, Any]],
    new_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """优先使用 tweet_id 合并译文，无 ID 旧数据使用原文作为兼容键。"""
    records: dict[tuple[str, str], dict[str, Any]] = {}
    for record in [*existing_records, *new_records]:
        tweet_id = record.get("tweet_id")
        key = ("id", str(tweet_id)) if tweet_id is not None else ("text", str(record.get("original", "")))
        records[key] = record
    return sorted(records.values(), key=lambda record: record.get("created_at", ""), reverse=True)
