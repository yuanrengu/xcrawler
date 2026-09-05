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
