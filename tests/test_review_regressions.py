"""Regression coverage for report privacy and analysis completion contracts."""

import copy
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from xcrawler.services.analysis_runs import load_analysis_runs
from xcrawler.storage.factory import create_store


def records(count):
    return [dict(tweet_id=str(i), original=f"original {i}", translated=f"译文 {i}",
                 created_at="2026-01-01T00:00:00Z", detected_language="en") for i in range(count)]


@pytest.mark.parametrize("event", [
    {"description": "健康详情", "sensitive": True, "evidence_tweet_ids": ["0"]},
    {"description": "健康详情", "evidence_tweet_ids": ["0"]},
    {"description": "健康详情", "sensitive": False, "evidence_tweet_ids": ["0"]},
    "健康详情",
])
def test_default_report_resanitizes_saved_events(event):
    from visualize import generate_evidence_sections

    data = {"translated": records(1), "behavior": {"life_events": {"health_events": [event]}}}
    original = copy.deepcopy(data)
    output = generate_evidence_sections(data)
    assert "健康详情" not in output
    assert "译文 0" not in output
    assert "original 0" not in output
    assert "<code>0</code>" not in output
    assert "敏感生活事件已隐藏" in output
    assert data == original
    explicit = generate_evidence_sections(data, include_sensitive_events=True)
    assert "健康详情" in explicit
    if isinstance(event, dict):
        assert "译文 0" in explicit
        assert "original 0" in explicit


def test_public_event_remains_visible():
    from visualize import generate_evidence_sections

    data = {"translated": records(1), "behavior": {"life_events": {
        "other_events": [{"description": "公开演出", "evidence_tweet_ids": ["0"]}]}}}
    assert "译文 0" in generate_evidence_sections(data)


def setup_interest(monkeypatch, tmp_path, backend, evidence_id="0"):
    import analyze_pro as module

    store = create_store(str(tmp_path), backend=backend)
    monkeypatch.setattr(module, "parse_args", lambda: SimpleNamespace(
        user="alice", model="fake", cache_dir=str(tmp_path), storage_backend=backend,
        sqlite_path=None, limit=2, temperature=0))
    monkeypatch.setattr(module, "load_translated_records", lambda *args: records(3))
    monkeypatch.setattr(module, "_get_provider", lambda: SimpleNamespace(name="fake"))
    analysis = MagicMock(return_value=({"interests": [{"tag": "演出", "evidence_tweet_ids": [evidence_id]}]}, 10))
    monkeypatch.setattr(module, "analyze_user_interest", analysis)
    return module, store, analysis


@pytest.mark.parametrize("backend", ["json", "sqlite"])
def test_interest_rejects_unsampled_evidence(tmp_path, monkeypatch, backend):
    module, store, analysis = setup_interest(monkeypatch, tmp_path, backend, evidence_id="1")
    assert module.main() == 1
    assert "tweet_id=1" not in "".join(analysis.call_args.args[0])
    runs = load_analysis_runs(store)
    assert len(runs) == 1
    assert runs[0]["status"] == "failed"
    assert not (tmp_path / "alice_interest_profile.json").exists()


@pytest.mark.parametrize("backend", ["json", "sqlite"])
@pytest.mark.parametrize("write_fails", [True, False])
def test_interest_records_terminal_state_after_result(tmp_path, monkeypatch, backend, write_fails):
    module, store, _ = setup_interest(monkeypatch, tmp_path, backend)
    original_save = module.save_analysis_result

    def save(result, *args):
        assert load_analysis_runs(store) == []
        if write_fails:
            raise OSError("disk full")
        original_save(result, *args)

    monkeypatch.setattr(module, "save_analysis_result", save)
    assert module.main() == (1 if write_fails else 0)
    runs = load_analysis_runs(store)
    assert len(runs) == 1
    assert runs[0]["status"] == ("failed" if write_fails else "success")
    assert runs[0]["input_range"]["sample_tweet_ids"] == ["0", "2"]
    if not write_fails:
        result = json.loads((tmp_path / "alice_interest_profile.json").read_text())
        assert result["sampling"]["sample_tweet_ids"] == ["0", "2"]


def test_interest_failure_record_does_not_mask_original_error(tmp_path, monkeypatch, capsys):
    module, _, _ = setup_interest(monkeypatch, tmp_path, "json")
    monkeypatch.setattr(module, "save_analysis_result", MagicMock(side_effect=OSError("disk full")))
    monkeypatch.setattr(module, "record_analysis_run", MagicMock(side_effect=RuntimeError("metadata unavailable")))
    # Fail the Storage method used by the best-effort failure recorder too.
    from xcrawler.storage.json_store import JsonStore
    monkeypatch.setattr(JsonStore, "append_json_record", MagicMock(side_effect=RuntimeError("metadata unavailable")))
    assert module.main() == 1
    assert "disk full" in capsys.readouterr().out


@pytest.mark.parametrize("failed_batches, code, status", [(0, 0, "success"), (1, 2, "partial"), (2, 1, "failed")])
def test_sentiment_completion_contract(tmp_path, monkeypatch, failed_batches, code, status):
    import analyze_sentiment as module

    (tmp_path / "alice_translated.json").write_text(json.dumps(records(21)))
    result_file = tmp_path / "alice_sentiment.json"
    result_file.write_text('{"previous": true}')
    monkeypatch.setattr(module, "parse_args", lambda: SimpleNamespace(
        user="alice", cache_dir=str(tmp_path), output=None, top=2, storage_backend="json", sqlite_path=None))
    monkeypatch.setattr(module, "MATPLOTLIB_AVAILABLE", True)
    monkeypatch.setattr(module, "create_provider", lambda: SimpleNamespace(name="fake"))
    labels = ["positive"] * 21 if not failed_batches else ["unknown"] * 20 + ["positive"]
    if failed_batches == 2:
        labels = ["unknown"] * 21
    monkeypatch.setattr(module, "batch_sentiment", lambda *args: (labels, {
        "batches": 2, "failed_batches": failed_batches, "total_tokens": 10}))
    chart = MagicMock()
    monkeypatch.setattr(module, "chart_sentiment_timeline", chart)
    monkeypatch.setattr(module, "chart_sentiment_pie", MagicMock())
    assert module.main() == code
    assert load_analysis_runs(create_store(str(tmp_path)))[0]["status"] == status
    saved = json.loads(result_file.read_text())
    if failed_batches == 2:
        assert saved == {"previous": True}
        chart.assert_not_called()
    else:
        assert saved["failed_batches"] == failed_batches
        assert saved["distribution"].get("unknown", 0) == (20 if failed_batches else 0)


@pytest.mark.parametrize("failure", ["none", "events", "summary", "both", "save"])
def test_behavior_samples_and_completion(tmp_path, monkeypatch, failure):
    import analyze_behavior as module
    from xcrawler.services.sampling import sample_evenly

    source = records(201)
    sampled = sample_evenly(source, 200)
    omitted = next(r["tweet_id"] for r in source if r not in sampled)
    (tmp_path / "alice_raw_tweets.json").write_text(json.dumps([
        {"id": "0", "text": "demo", "created_at": "2026-01-01T00:00:00Z"}]))
    (tmp_path / "alice_translated.json").write_text(json.dumps(source))
    monkeypatch.setattr(module, "parse_args", lambda: SimpleNamespace(
        user="alice", cache_dir=str(tmp_path), include_sensitive_events=False,
        storage_backend="json", sqlite_path=None))
    monkeypatch.setattr(module, "AI_AVAILABLE", True)
    monkeypatch.setattr(module, "_get_llm_provider", lambda: SimpleNamespace(name="fake"))

    def detect(items, **kwargs):
        assert [r["tweet_id"] for r in items] == [r["tweet_id"] for r in sampled]
        if failure in ("events", "both"):
            return None
        return {"other_events": [
            {"description": "未提供的证据", "evidence_tweet_ids": [omitted]},
            {"description": "公开演出", "evidence_tweet_ids": ["0"]}]}

    monkeypatch.setattr(module, "detect_life_events", detect)
    monkeypatch.setattr(module, "generate_behavior_summary", lambda *args, **kwargs:
                        "无法生成总结" if failure in ("summary", "both") else "有效总结")
    if failure == "save":
        monkeypatch.setattr(module, "save_json", MagicMock(side_effect=OSError("disk full")))
    code = 1 if failure == "save" else 0 if failure == "none" else 2
    assert module.main() == code
    runs = load_analysis_runs(create_store(str(tmp_path)))
    assert len(runs) == 1
    assert runs[0]["status"] == {0: "success", 1: "failed", 2: "partial"}[code]
    if failure != "save":
        result = json.loads((tmp_path / "alice_behavior.json").read_text())
        assert omitted not in result["sampling"]["sample_tweet_ids"]
        assert "未提供的证据" not in json.dumps(result, ensure_ascii=False)
