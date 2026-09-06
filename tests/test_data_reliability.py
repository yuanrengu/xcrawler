"""Regressions for business updates and invalid translation persistence."""

import json
import multiprocessing
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from xcrawler.services.translation import translate_text
from xcrawler.services.translation_cache import (
    TranslationCacheContext,
    get_cached_translation,
    new_translation_cache,
    normalize_translation_cache,
    persist_translation_cache,
    set_cached_translation,
)
from xcrawler.storage.json_store import load_json, replace_json_files_atomically, save_json, update_json


def _merge_worker(path, worker, barrier):
    barrier.wait(timeout=10)
    for index in range(10):
        update_json(path, lambda current: [*current, [worker, index]], default=[], lock_timeout=10)


def test_compound_updates_preserve_all_processes(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    barrier = ctx.Barrier(3)
    path = str(tmp_path / "records.json")
    processes = [ctx.Process(target=_merge_worker, args=(path, worker, barrier)) for worker in range(3)]
    try:
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=20)
            assert process.exitcode == 0
        assert {tuple(row) for row in load_json(path)} == {(w, i) for w in range(3) for i in range(10)}
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)


def test_update_failure_preserves_old_document(tmp_path):
    path = str(tmp_path / "data.json")
    save_json(path, [1])
    with pytest.raises(TypeError):
        update_json(path, lambda current: [*current, object()])
    assert load_json(path) == [1]
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("failure", ["serialize", "fsync"])
def test_transaction_failure_cleans_pending_files(tmp_path, monkeypatch, failure):
    import xcrawler.storage.json_store as storage

    path = str(tmp_path / "data.json")
    save_json(path, [1])
    if failure == "fsync":
        monkeypatch.setattr(storage.os, "fsync", MagicMock(side_effect=OSError("disk full")))
    with pytest.raises((TypeError, OSError)):
        replace_json_files_atomically({path: [object()] if failure == "serialize" else [2]})
    assert json.loads((tmp_path / "data.json").read_text()) == [1]
    assert not list(tmp_path.glob("*.pending"))


def test_independent_cache_snapshots_are_merged(tmp_path):
    path = str(tmp_path / "cache.json")
    context = TranslationCacheContext(provider="test", model="m")
    first, second = new_translation_cache(), new_translation_cache()
    set_cached_translation(first, "first", "第一", context)
    set_cached_translation(second, "second", "第二", context)
    persist_translation_cache(path, first)
    persist_translation_cache(path, second)
    result = load_json(path)
    assert get_cached_translation(result, "first", context) == "第一"
    assert get_cached_translation(result, "second", context) == "第二"


def test_blank_translation_retries_and_repairs_existing_cache(monkeypatch):
    import xcrawler.services.translation as translation

    monkeypatch.setattr(translation.time, "sleep", lambda delay: None)
    context = TranslationCacheContext(provider="test", model="m")
    cache = new_translation_cache()
    set_cached_translation(cache, "hello", "old", context)
    next(iter(cache["entries"].values()))["translated"] = "  "
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])
        for text in ["  ", "你好"]
    ]
    result = translate_text(
        "hello", detected_lang="en", use_cache=True, cache=cache,
        client_factory=lambda: client, model="m", max_retries=2, cache_context=context,
    )
    assert result == "你好"
    assert client.chat.completions.create.call_count == 2
    assert get_cached_translation(cache, "hello", context) == "你好"


def test_blank_translation_is_never_cached():
    cache = new_translation_cache()
    with pytest.raises(ValueError, match="空白"):
        set_cached_translation(cache, "hello", "\n ", TranslationCacheContext(provider="test", model="m"))
    assert cache["entries"] == {}


def test_embedding_encoder_does_not_overwrite_concurrent_additions(tmp_path):
    from xcrawler.services.embeddings import encode_texts_with_cache

    path = str(tmp_path / "embeddings.json")

    def encoder(texts):
        encode_texts_with_cache(["second"], model_name="m", cache_path=path, encoder=lambda _: [[2.0]])
        return [[1.0]]

    encode_texts_with_cache(["first"], model_name="m", cache_path=path, encoder=encoder)
    no_call = MagicMock(side_effect=AssertionError("cached vectors should be reused"))
    assert encode_texts_with_cache(
        ["first", "second"], model_name="m", cache_path=path, encoder=no_call
    ) == [[1.0], [2.0]]


def test_sync_preserves_translation_written_while_model_runs(tmp_path, monkeypatch):
    import sys

    import translate_sync

    raw = {"id": "1", "text": "hello long text", "created_at": "2026-01-01T00:00:00Z"}
    save_json(str(tmp_path / "alice_raw_tweets.json"), [raw])
    path = str(tmp_path / "alice_translated.json")
    other = {"tweet_id": "2", "original": "other", "translated": "其他", "created_at": raw["created_at"]}

    def translate(*args, **kwargs):
        save_json(path, [other])
        return ["你好"]

    monkeypatch.setattr(sys, "argv", ["translate_sync", "-u", "alice", "--cache-dir", str(tmp_path)])
    monkeypatch.setattr(translate_sync, "translate_batch", translate)
    monkeypatch.setattr(translate_sync, "detect_language", lambda text: "en")
    assert translate_sync.main() == 0
    assert {record["tweet_id"] for record in load_json(path)} == {"1", "2"}


@pytest.mark.parametrize("normalize", [False, True])
def test_stale_cache_never_reverts_another_process_correction(tmp_path, normalize):
    path = str(tmp_path / "cache.json")
    context = TranslationCacheContext(provider="test", model="m")
    seed = new_translation_cache()
    set_cached_translation(seed, "same", "旧译文", context)
    persist_translation_cache(path, seed)
    stale = load_json(path)
    if normalize:
        stale = normalize_translation_cache(stale)
    corrected = normalize_translation_cache(load_json(path))
    set_cached_translation(corrected, "same", "新译文", context)
    persist_translation_cache(path, corrected)
    set_cached_translation(stale, "other", "其他", context)
    persist_translation_cache(path, stale)
    saved = load_json(path)
    assert get_cached_translation(saved, "same", context) == "新译文"
    assert get_cached_translation(stale, "same", context) == "新译文"
    assert get_cached_translation(saved, "other", context) == "其他"
    # After committing, this process must not replay its earlier correction.
    set_cached_translation(corrected, "other", "再次修正", context)
    persist_translation_cache(path, corrected)
    persist_translation_cache(path, stale)
    assert get_cached_translation(load_json(path), "other", context) == "再次修正"
    assert set(saved) == {"version", "entries", "legacy_entries"}


def test_failed_cache_commit_retains_pending_changes(tmp_path, monkeypatch):
    import xcrawler.services.translation_cache as service

    path = str(tmp_path / "cache.json")
    context = TranslationCacheContext(provider="test", model="m")
    cache = new_translation_cache()
    set_cached_translation(cache, "same", "旧译文", context)
    persist_translation_cache(path, cache)
    set_cached_translation(cache, "same", "修正", context)
    with monkeypatch.context() as scoped:
        scoped.setattr(service, "update_json", MagicMock(side_effect=OSError("disk full")))
        with pytest.raises(OSError):
            persist_translation_cache(path, cache)
    assert get_cached_translation(load_json(path), "same", context) == "旧译文"
    persist_translation_cache(path, cache)
    assert get_cached_translation(load_json(path), "same", context) == "修正"


@pytest.mark.parametrize("create_concurrently", [False, True])
def test_replace_no_translate_checks_existence_after_acquiring_both_locks(tmp_path, monkeypatch, create_concurrently):
    from contextlib import contextmanager

    import main
    import xcrawler.storage.json_store as storage

    raw_path = str(tmp_path / "alice_raw_tweets.json")
    trans_path = str(tmp_path / "alice_translated.json")
    raw = [{"id": "new", "text": "new long text", "created_at": "2026-01-01T00:00:00Z"}]
    real_locks = storage.file_locks
    acquired = []

    @contextmanager
    def interleaved_locks(paths, **kwargs):
        acquired.append(set(paths))
        if create_concurrently:
            save_json(trans_path, [{"tweet_id": "old", "original": "old", "translated": "旧"}])
        with real_locks(paths, **kwargs):
            yield

    monkeypatch.setattr(storage, "file_locks", interleaved_locks)
    options = SimpleNamespace(
        user="alice", pages=1, batch_size=1, model=None, cache_dir=str(tmp_path),
        analysis_limit=100, no_translate=True, replace=True, storage_backend="json", sqlite_path=None,
    )
    for name in ("CACHE_DIR", "TARGET_USERNAME", "MAX_PAGES", "BATCH_SIZE", "ANALYSIS_LIMIT",
                 "translation_cache", "translation_metrics", "llm_call_recorder"):
        monkeypatch.setattr(main, name, getattr(main, name))
    monkeypatch.setattr(main, "parse_args", lambda: options)
    monkeypatch.setattr(main, "validate_runtime_config", lambda **kwargs: None)
    monkeypatch.setattr(main, "get_user_id", lambda username: "uid")
    monkeypatch.setattr(main, "get_user_profile", lambda username: None)
    monkeypatch.setattr(main, "fetch_tweets", lambda uid: main.x_api.TweetFetchResult(
        raw, True, "no_next_token", 1, 1, 0,
    ))
    assert main.main() == 0
    assert acquired == [{raw_path, trans_path}]
    assert load_json(raw_path) == raw
    if create_concurrently:
        assert load_json(trans_path) == []
    else:
        assert not (tmp_path / "alice_translated.json").exists()
