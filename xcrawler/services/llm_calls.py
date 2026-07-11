from __future__ import annotations

import re
import warnings
from datetime import datetime, timezone
from math import isfinite
from time import perf_counter
from typing import Any
from uuid import uuid4

from xcrawler.models import LLMCallRecord
from xcrawler.storage.base import Storage
from xcrawler.storage.keys import LLM_CALLS_KEY


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def estimate_llm_cost(
    *,
    model: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    pricing: dict[str, dict[str, float]] | None,
) -> float | None:
    """Estimate call cost from a user-supplied per-million-token price table."""
    if prompt_tokens is None or completion_tokens is None or not pricing:
        return None
    rates = pricing.get(model) or pricing.get("*")
    if not rates:
        return None
    try:
        input_rate = float(rates["input_per_million"])
        output_rate = float(rates["output_per_million"])
    except (KeyError, TypeError, ValueError):
        return None
    if not isfinite(input_rate) or not isfinite(output_rate) or input_rate < 0 or output_rate < 0:
        return None
    return round((prompt_tokens * input_rate + completion_tokens * output_rate) / 1_000_000, 10)


class LLMCallRecorder:
    """Persist metadata for each LLM attempt without storing prompts or responses."""

    def __init__(
        self,
        store: Storage,
        *,
        pricing: dict[str, dict[str, float]] | None = None,
        analysis_run_id: str | None = None,
        username: str | None = None,
    ):
        self.store = store
        self.pricing = pricing or {}
        self.analysis_run_id = analysis_run_id
        self.username = username
        self.records: list[LLMCallRecord] = []

    def _persist(self, record: LLMCallRecord) -> None:
        self.records.append(record)
        try:
            self.store.append_json_record(LLM_CALLS_KEY, record.to_dict())
        except Exception as error:
            warnings.warn(
                f"LLM 调用记录写入失败，业务流程将继续: {error}",
                RuntimeWarning,
                stacklevel=2,
            )

    def start(self) -> tuple[str, float]:
        return _utc_now_iso(), perf_counter()

    def record_success(
        self,
        *,
        operation: str,
        provider: str,
        model: str,
        started: tuple[str, float],
        response: object,
        attempt: int = 1,
    ) -> LLMCallRecord:
        prompt_tokens, completion_tokens, total_tokens = _extract_usage(response)
        latency_ms = _extract_latency(response)
        if latency_ms is None:
            latency_ms = max(0, int((perf_counter() - started[1]) * 1000))
        record = LLMCallRecord(
            id=str(uuid4()),
            analysis_run_id=self.analysis_run_id,
            username=self.username,
            operation=operation,
            provider=provider,
            model=model,
            started_at=started[0],
            completed_at=_utc_now_iso(),
            status="success",
            attempt=attempt,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost=estimate_llm_cost(
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                pricing=self.pricing,
            ),
        )
        self._persist(record)
        return record

    def record_failure(
        self,
        *,
        operation: str,
        provider: str,
        model: str,
        started: tuple[str, float],
        error: BaseException,
        attempt: int = 1,
        response: object | None = None,
    ) -> LLMCallRecord:
        prompt_tokens, completion_tokens, total_tokens = _extract_usage(response) if response is not None else (None, None, None)
        record = LLMCallRecord(
            id=str(uuid4()),
            analysis_run_id=self.analysis_run_id,
            username=self.username,
            operation=operation,
            provider=provider,
            model=model,
            started_at=started[0],
            completed_at=_utc_now_iso(),
            status="failed",
            attempt=attempt,
            latency_ms=max(0, int((perf_counter() - started[1]) * 1000)),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost=estimate_llm_cost(
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                pricing=self.pricing,
            ),
            error_type=type(error).__name__,
            error_message=_safe_error_message(error),
        )
        self._persist(record)
        return record

    def summary(self) -> dict[str, int | float]:
        return summarize_llm_calls([record.to_dict() for record in self.records])


def _extract_usage(response: object) -> tuple[int | None, int | None, int | None]:
    usage = getattr(response, "usage", None)
    source = usage if usage is not None else response
    prompt_tokens = getattr(source, "prompt_tokens", None)
    completion_tokens = getattr(source, "completion_tokens", None)
    total_tokens = getattr(source, "total_tokens", None)
    if not isinstance(total_tokens, int) and isinstance(prompt_tokens, int) and isinstance(completion_tokens, int):
        total_tokens = prompt_tokens + completion_tokens
    return (
        prompt_tokens if isinstance(prompt_tokens, int) else None,
        completion_tokens if isinstance(completion_tokens, int) else None,
        total_tokens if isinstance(total_tokens, int) else None,
    )


def _safe_error_message(error: BaseException, *, limit: int = 1000) -> str:
    message = str(error)
    message = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}", "sk-[REDACTED]", message)
    message = re.sub(
        r"(?i)(authorization|bearer|api[_ -]?key)([\s:=\"']+)([^\s,;\"']+)",
        r"\1\2[REDACTED]",
        message,
    )
    return message[:limit]


def _extract_latency(response: object) -> int | None:
    latency_ms = getattr(response, "latency_ms", None)
    return latency_ms if isinstance(latency_ms, int) else None


class ObservedLLMProvider:
    """Add durable call telemetry to any provider implementing the LLMProvider protocol."""

    def __init__(self, provider: Any, recorder: LLMCallRecorder, *, operation: str):
        self.provider = provider
        self.recorder = recorder
        self.operation = operation
        self.name = provider.name

    def chat(self, messages: list[dict[str, str]], *, model: str, temperature: float = 0.0):
        started = self.recorder.start()
        try:
            response = self.provider.chat(messages, model=model, temperature=temperature)
        except Exception as error:
            self.recorder.record_failure(
                operation=self.operation,
                provider=self.name,
                model=model,
                started=started,
                error=error,
            )
            raise
        self.recorder.record_success(
            operation=self.operation,
            provider=getattr(response, "provider", self.name),
            model=getattr(response, "model", model),
            started=started,
            response=response,
        )
        return response


def load_llm_calls(store: Storage) -> list[dict[str, Any]]:
    records = store.load_json(LLM_CALLS_KEY, default=[])
    return [record for record in records if isinstance(record, dict)] if isinstance(records, list) else []


def summarize_llm_calls(
    records: list[dict[str, Any]],
    *,
    analysis_run_id: str | None = None,
) -> dict[str, int | float]:
    selected = [
        record
        for record in records
        if analysis_run_id is None or record.get("analysis_run_id") == analysis_run_id
    ]
    failures = sum(record.get("status") == "failed" for record in selected)
    successes = sum(record.get("status") == "success" for record in selected)
    total = len(selected)
    return {
        "calls": total,
        "successful_calls": successes,
        "failed_calls": failures,
        "failure_rate": round(failures / total, 4) if total else 0.0,
        "prompt_tokens": sum(record.get("prompt_tokens") or 0 for record in selected),
        "completion_tokens": sum(record.get("completion_tokens") or 0 for record in selected),
        "total_tokens": sum(record.get("total_tokens") or 0 for record in selected),
        "estimated_cost": round(sum(record.get("estimated_cost") or 0 for record in selected), 10),
    }
