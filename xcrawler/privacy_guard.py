from __future__ import annotations

import re
from typing import Any


SENSITIVE_EVENT_CATEGORIES = {
    "birthday_mentions",
    "relationship_events",
    "health_events",
    "travel_relocation",
    "major_purchases",
}

SENSITIVE_KEYWORDS = {
    "健康": ["生病", "医院", "手术", "抑郁", "焦虑", "受伤", "康复", "药"],
    "感情": ["恋爱", "分手", "约会", "结婚", "离婚", "表白"],
    "财务": ["买房", "买车", "贷款", "工资", "收入", "欠款", "负债"],
    "位置": ["住址", "搬家", "搬到", "地址", "小区", "宿舍"],
    "联系方式": ["电话", "手机号", "邮箱", "微信", "Line", "WhatsApp"],
    "未成年人": ["未成年", "小孩", "孩子", "儿童", "学生"],
}


def is_sensitive_event(category: str, description: str = "") -> bool:
    if category in SENSITIVE_EVENT_CATEGORIES:
        return True
    return any(keyword in description for keywords in SENSITIVE_KEYWORDS.values() for keyword in keywords)


def redact_text(text: str) -> str:
    redacted = re.sub(r"[\w\.-]+@[\w\.-]+\.\w+", "[邮箱已隐藏]", text)
    # 要求至少一个分隔符（- 或空格），避免匹配纯数字 ID
    redacted = re.sub(r"(?<!\d)(?:\(\d{2,4}\)[\s\-]?)?\d{3,4}(?:[\s\-]\d{3,4}){1,2}(?!\d)", "[电话已隐藏]", redacted)
    redacted = re.sub(r"(住址|地址|小区|宿舍)[:：]?\s*\S+", r"\1[已隐藏]", redacted)
    return redacted


def redact_record(record: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(record)
    if "original" in redacted:
        redacted["original"] = "[敏感原文已隐藏]"
    if "translated" in redacted:
        redacted["translated"] = redact_text(redacted["translated"])
    return redacted


def sanitize_life_events(life_events: dict[str, list[Any]], include_sensitive: bool = False) -> dict[str, list[dict[str, Any]]]:
    sanitized: dict[str, list[dict[str, Any]]] = {}

    for category, events in (life_events or {}).items():
        sanitized_events = []
        for event in events or []:
            event_dict = dict(event) if isinstance(event, dict) else {"description": str(event)}
            event_dict.setdefault("evidence_tweet_ids", [])
            event_dict.setdefault("confidence", None)

            sensitive = bool(event_dict.get("sensitive")) or is_sensitive_event(category, event_dict.get("description", ""))
            event_dict["sensitive"] = sensitive

            if sensitive and not include_sensitive:
                event_dict["description"] = "[敏感生活事件已隐藏]"
                event_dict["evidence_tweet_ids"] = []
                event_dict["redacted"] = True

            sanitized_events.append(event_dict)
        sanitized[category] = sanitized_events

    return sanitized
