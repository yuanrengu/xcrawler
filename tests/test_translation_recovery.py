"""Interrupted batches retain usable progress without committing partial snapshots."""

import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from xcrawler.services.records import translation_record_is_current
from xcrawler.services.translation import translate_batch
from xcrawler.services.translation_cache import (
    TranslationCacheContext,
    get_cached_translation,
    new_translation_cache,
    persist_translation_cache,
)
from xcrawler.storage.json_store import load_json, save_json


def response(text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


@pytest.mark.parametrize("command", ["fetch", "sync", "force"])
def test_command_checkpoints_before_interruption(tmp_path, monkeypatch, command):
    import main
    import translate_sync

    raw = [
        {"id": str(i), "text": f"long english text {i}", "created_at": "2026-01-01T00:00:00Z"}
        for i in range(2)
    ]
    raw_path = str(tmp_path / "alice_raw_tweets.json")
    translated_path = str(tmp_path / "alice_translated.json")
    old = [{"tweet_id": "old", "original": "old", "translated": "旧译文"}]
    save_json(raw_path, raw)
    save_json(translated_path, old)
    client = MagicMock()
    client.chat.completions.create.side_effect = [response("[1] 第一"), KeyboardInterrupt()]

    if command == "fetch":
        args = SimpleNamespace(
            user="alice", pages=1, batch_size=1, model=None, cache_dir=str(tmp_path),
            analysis_limit=100, no_translate=False, replace=True, storage_backend="json", sqlite_path=None,
        )
        monkeypatch.setattr(main, "parse_args", lambda: args)
        monkeypatch.setattr(main, "validate_runtime_config", lambda **kw: None)
        monkeypatch.setattr(main, "get_user_id", lambda username: "uid")
        monkeypatch.setattr(main, "get_user_profile", lambda username: None)
        monkeypatch.setattr(main, "fetch_tweets", lambda uid: main.x_api.TweetFetchResult(
            raw, True, "no_next_token", 1, 1, 0,
        ))
        monkeypatch.setattr(main, "_get_ds_client", lambda: client)
        monkeypatch.setattr(main, "detect_language", lambda text: "en")
        # main mutates its configured globals; restore them when the test ends.
        for name in ("CACHE_DIR", "TARGET_USERNAME", "BATCH_SIZE", "translation_cache", "llm_call_recorder"):
            monkeypatch.setattr(main, name, getattr(main, name))
        run = main.main
        context = main._translation_cache_context()
    else:
        argv = ["translate_sync", "-u", "alice", "--cache-dir", str(tmp_path)]
        if command == "force":
            argv.append("--force")
        monkeypatch.setattr(sys, "argv", argv)
        monkeypatch.setattr(translate_sync, "BATCH_SIZE", 1)
        monkeypatch.setattr(translate_sync, "_make_client", lambda: client)
        monkeypatch.setattr(translate_sync, "detect_language", lambda text: "en")
        run = translate_sync.main
        context = translate_sync._translation_cache_context()

    with pytest.raises(KeyboardInterrupt):
        run()
    assert load_json(raw_path) == raw
    assert load_json(translated_path) == old
    saved = load_json(str(tmp_path / "translation_cache.json"))
    assert get_cached_translation(saved, raw[0]["text"], context) == "第一"
    assert get_cached_translation(saved, raw[1]["text"], context) is None

    # A normal resumed batch uses the durable entry and calls the model only
    # for the unfinished item (force explicitly bypasses cache when requested).
    resumed = MagicMock()
    resumed.chat.completions.create.return_value = response("[1] 第二")
    result = translate_batch(
        [item["text"] for item in raw], detected_langs=["en", "en"], use_cache=True,
        cache=saved, client_factory=lambda: resumed, model=context.model, batch_size=1,
        max_retries=1, fallback_translate=lambda *args: None, cache_context=context,
    )
    assert result == ["第一", "第二"]
    resumed.chat.completions.create.assert_called_once()


def test_checkpoint_failure_does_not_retry_model():
    client = MagicMock()
    client.chat.completions.create.return_value = response("[1] 第一")
    checkpoint = MagicMock(side_effect=OSError("disk full"))
    with pytest.raises(OSError, match="disk full"):
        translate_batch(
            ["first", "second"], detected_langs=["en", "en"], use_cache=True,
            cache=new_translation_cache(), client_factory=lambda: client, model="m", batch_size=1,
            max_retries=3, fallback_translate=lambda *args: None, checkpoint=checkpoint,
        )
    client.chat.completions.create.assert_called_once()


def test_chinese_only_batch_is_checkpointed(tmp_path):
    cache = new_translation_cache()
    path = str(tmp_path / "cache.json")
    result = translate_batch(
        ["中文内容"], detected_langs=["zh"], use_cache=True, cache=cache,
        client_factory=MagicMock(side_effect=AssertionError("no model call expected")),
        model="m", batch_size=1, max_retries=1, fallback_translate=lambda *args: None,
        checkpoint=lambda: persist_translation_cache(path, cache),
    )
    assert result == ["中文内容"]
    assert load_json(path)["entries"]


@pytest.mark.parametrize("fingerprint, translated, expected", [
    (None, "旧译文", False), ("", "旧译文", False), ("old", "旧译文", False),
    ("current", "  ", False), ("current", "有效译文", True),
])
def test_translation_requires_known_matching_configuration(fingerprint, translated, expected):
    record = {"original": "hello", "translated": translated}
    if fingerprint is not None:
        record["config_fingerprint"] = fingerprint
    assert translation_record_is_current(record, "hello", "current") is expected


@pytest.mark.parametrize("success", [True, False])
def test_sync_revalidates_legacy_translation_and_preserves_it_on_failure(tmp_path, monkeypatch, success):
    import translate_sync

    raw = [{"id": "1", "text": "hello long text", "created_at": "2026-01-01T00:00:00Z"}]
    old = [{"tweet_id": "1", "original": raw[0]["text"], "translated": "旧译文"}]
    save_json(str(tmp_path / "alice_raw_tweets.json"), raw)
    path = str(tmp_path / "alice_translated.json")
    save_json(path, old)
    monkeypatch.setattr(sys, "argv", ["translate_sync", "-u", "alice", "--cache-dir", str(tmp_path)])
    translate = MagicMock(return_value=["新译文" if success else None])
    monkeypatch.setattr(translate_sync, "translate_batch", translate)
    monkeypatch.setattr(translate_sync, "detect_language", lambda text: "en")
    assert translate_sync.main() == (0 if success else 1)
    translate.assert_called_once()
    if success:
        result = load_json(path)[0]
        assert result["translated"] == "新译文"
        assert result["config_fingerprint"] == translate_sync._translation_cache_context().fingerprint
    else:
        assert json.loads((tmp_path / "alice_translated.json").read_text()) == old
