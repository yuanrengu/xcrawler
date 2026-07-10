from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass
class TweetRecord:
    id: str
    text: str
    created_at: str
    lang: str | None = None
    raw: dict[str, Any] | None = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> TweetRecord:
        return cls(
            id=str(data.get("id", "")),
            text=data.get("text", ""),
            created_at=data.get("created_at", ""),
            lang=data.get("lang"),
            raw=data,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TranslatedTweet:
    tweet_id: str | None
    original: str
    translated: str
    detected_language: str
    created_at: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TranslatedTweet:
        return cls(
            tweet_id=data.get("tweet_id"),
            original=data.get("original", ""),
            translated=data.get("translated", ""),
            detected_language=data.get("detected_language", ""),
            created_at=data.get("created_at", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InterestSignal:
    tag: str
    level: Literal["core", "peripheral"]
    confidence: float
    keywords: list[str] = field(default_factory=list)
    evidence_count: int = 0
    evidence_tweet_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InterestSignal:
        return cls(
            tag=data.get("tag", ""),
            level=data.get("level", "peripheral"),
            confidence=float(data.get("confidence", 0)),
            keywords=list(data.get("keywords", [])),
            evidence_count=int(data.get("evidence_count", 0)),
            evidence_tweet_ids=list(data.get("evidence_tweet_ids", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LifeEvent:
    category: str
    description: str
    confidence: float | None = None
    sensitive: bool = False
    evidence_tweet_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LifeEvent:
        return cls(
            category=data.get("category", ""),
            description=data.get("description", ""),
            confidence=data.get("confidence"),
            sensitive=data.get("sensitive", False),
            evidence_tweet_ids=list(data.get("evidence_tweet_ids", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnalysisRun:
    id: str
    username: str
    analysis_type: str
    model: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    status: Literal["running", "success", "failed", "partial"] = "running"
    params: dict[str, Any] = field(default_factory=dict)
    input_range: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    duration_ms: int | None = None
    error_type: str | None = None
    error_message: str | None = None
    llm_calls: int = 0
    total_tokens: int | None = None
    failed_batches: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LLMCallRecord:
    id: str
    operation: str
    provider: str
    model: str
    started_at: str
    completed_at: str
    status: Literal["success", "failed"]
    analysis_run_id: str | None = None
    username: str | None = None
    attempt: int = 1
    latency_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost: float | None = None
    error_type: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
