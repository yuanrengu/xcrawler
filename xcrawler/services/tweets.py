from __future__ import annotations

from datetime import datetime
from typing import Any

from xcrawler.utils.time import parse_twitter_datetime


def tweet_order_key(record: dict[str, Any]) -> tuple[datetime, int, str]:
    """Order by actual time then numeric ID; undated legacy translations sort last."""
    timestamp = record.get("created_at")
    parsed = parse_twitter_datetime(timestamp) if timestamp else datetime.min
    identity = str(record.get("id") or record.get("tweet_id") or "")
    return parsed, int(identity) if identity.isdecimal() else -1, identity


class TweetSchemaError(ValueError):
    """raw tweet 数据结构无效。"""


def validate_raw_tweets(data: Any, *, source: str = "raw tweets") -> list[dict[str, Any]]:
    if not isinstance(data, list):
        raise TweetSchemaError(f"{source} 必须是 JSON 数组")
    validated: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise TweetSchemaError(f"{source} 第 {index + 1} 条必须是 JSON 对象")
        tweet_id = item.get("id")
        if tweet_id is None or not str(tweet_id).strip():
            raise TweetSchemaError(f"{source} 第 {index + 1} 条缺少有效 id")
        if not isinstance(item.get("text"), str):
            raise TweetSchemaError(f"{source} 第 {index + 1} 条 text 必须是字符串")
        created_at = item.get("created_at")
        if not isinstance(created_at, str):
            raise TweetSchemaError(f"{source} 第 {index + 1} 条缺少有效 created_at")
        try:
            parse_twitter_datetime(created_at)
        except ValueError as error:
            raise TweetSchemaError(f"{source} 第 {index + 1} 条 created_at 无效") from error
        normalized_id = str(tweet_id)
        if normalized_id in seen_ids:
            raise TweetSchemaError(f"{source} 包含重复 id: {normalized_id}")
        seen_ids.add(normalized_id)
        validated.append(item)
    return validated


def merge_tweets(existing_tweets: list[dict[str, Any]], new_tweets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按推文 ID 去重合并，新记录覆盖同 ID 旧记录，并按时间倒序返回。"""
    validate_raw_tweets(existing_tweets, source="existing raw tweets")
    validate_raw_tweets(new_tweets, source="new raw tweets")
    records: dict[str, dict[str, Any]] = {}
    for tweet in [*existing_tweets, *new_tweets]:
        tweet_id = tweet.get("id")
        records[str(tweet_id)] = tweet
    return sorted(records.values(), key=tweet_order_key, reverse=True)


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
    return sorted(records.values(), key=tweet_order_key, reverse=True)
