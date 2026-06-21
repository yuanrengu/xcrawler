from __future__ import annotations

import html
from typing import Any

from xcrawler.services.records import normalize_translated_tweets


def build_evidence_map(translated_data: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    evidence = {}
    for item in normalize_translated_tweets(translated_data):
        tweet_id = item.get("tweet_id")
        if tweet_id:
            evidence[str(tweet_id)] = item
    return evidence


def validate_evidence_tweet_ids(ids: list[Any] | None, evidence_map: dict[str, dict[str, Any]]) -> list[str]:
    if not ids:
        return []

    valid = []
    seen = set()
    for item in ids:
        tweet_id = str(item)
        if tweet_id in evidence_map and tweet_id not in seen:
            valid.append(tweet_id)
            seen.add(tweet_id)
    return valid


def validate_interest_evidence(result: dict[str, Any], translated_data: list[dict[str, Any]] | None) -> dict[str, Any]:
    evidence_map = build_evidence_map(translated_data)
    interests = result.get("interests", []) if isinstance(result, dict) else []
    for interest in interests:
        if not isinstance(interest, dict):
            continue
        valid_ids = validate_evidence_tweet_ids(interest.get("evidence_tweet_ids"), evidence_map)
        interest["evidence_tweet_ids"] = valid_ids
        interest["evidence_count"] = max(int(interest.get("evidence_count", 0) or 0), len(valid_ids))
        if not valid_ids:
            interest["evidence_status"] = "missing"
    return result


def evidence_items(tweet_ids: list[str], evidence_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [evidence_map[tweet_id] for tweet_id in tweet_ids if tweet_id in evidence_map]


def render_evidence_html(tweet_ids: list[str], evidence_map: dict[str, dict[str, Any]]) -> str:
    items = evidence_items(tweet_ids, evidence_map)
    if not items:
        return '<p class="empty">暂无可追溯证据</p>'

    rows = []
    for item in items:
        tweet_id = html.escape(str(item.get("tweet_id") or ""))
        created_at = html.escape(item.get("created_at", ""))
        translated = html.escape(item.get("translated", ""))
        original = html.escape(item.get("original", ""))
        rows.append(
            "<li>"
            f"<code>{tweet_id}</code> <span class=\"meta\">{created_at}</span>"
            f"<p>{translated}</p>"
            f"<details><summary>原文</summary><p>{original}</p></details>"
            "</li>"
        )
    return "<ol>" + "\n".join(rows) + "</ol>"
