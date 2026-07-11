from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from xcrawler.models import AnalysisRun
from xcrawler.storage.base import Storage
from xcrawler.storage.keys import ANALYSIS_RUNS_KEY


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _duration_ms(started_at: str | None, completed_at: str | None) -> int | None:
    started = _parse_iso(started_at)
    completed = _parse_iso(completed_at)
    if not started or not completed:
        return None
    return max(0, int((completed - started).total_seconds() * 1000))


def create_analysis_run(
    *,
    username: str,
    analysis_type: str,
    model: str | None = None,
    params: dict[str, Any] | None = None,
    input_range: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> AnalysisRun:
    return AnalysisRun(
        id=str(uuid4()),
        username=username,
        analysis_type=analysis_type,
        model=model,
        started_at=utc_now_iso(),
        params=params or {},
        input_range=input_range or {},
        config=config or {},
    )


def complete_analysis_run(run: AnalysisRun) -> AnalysisRun:
    run.completed_at = utc_now_iso()
    run.status = "success"
    run.duration_ms = _duration_ms(run.started_at, run.completed_at)
    return run


def fail_analysis_run(run: AnalysisRun, error: BaseException | str) -> AnalysisRun:
    run.completed_at = utc_now_iso()
    run.status = "failed"
    run.duration_ms = _duration_ms(run.started_at, run.completed_at)
    if isinstance(error, BaseException):
        run.error_type = type(error).__name__
        run.error_message = str(error)
    else:
        run.error_type = "Error"
        run.error_message = error
    return run


def partial_analysis_run(run: AnalysisRun, *, failed_batches: int = 0) -> AnalysisRun:
    run.completed_at = utc_now_iso()
    run.status = "partial"
    run.failed_batches = failed_batches
    run.duration_ms = _duration_ms(run.started_at, run.completed_at)
    return run


def record_analysis_run(store: Storage, run: AnalysisRun) -> None:
    store.append_json_record(ANALYSIS_RUNS_KEY, run.to_dict())


def record_failed_analysis_run(store: Storage, run: AnalysisRun, error: BaseException | str) -> None:
    """尽最大努力记录失败，不覆盖原始业务异常。"""
    try:
        record_analysis_run(store, fail_analysis_run(run, error))
    except Exception:
        return


def load_analysis_runs(store: Storage) -> list[dict[str, Any]]:
    return store.load_json(ANALYSIS_RUNS_KEY, default=[])
