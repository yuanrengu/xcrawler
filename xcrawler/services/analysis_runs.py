from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from xcrawler.models import AnalysisRun
from xcrawler.storage.base import Storage


ANALYSIS_RUNS_KEY = "analysis_runs.json"


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


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
    return run


def record_analysis_run(store: Storage, run: AnalysisRun) -> None:
    store.append_json_record(ANALYSIS_RUNS_KEY, run.to_dict())


def load_analysis_runs(store: Storage) -> list[dict[str, Any]]:
    return store.load_json(ANALYSIS_RUNS_KEY, default=[])
