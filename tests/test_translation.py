"""Tests grouped by responsibility from the former monolithic suite."""

import csv
import json
from contextlib import closing
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class TestCleanText:
    """测试 clean_text 文本清洗"""

    def test_remove_urls(self):
        from main import clean_text
        assert clean_text("hello https://t.co/abc world") == "hello world"

    def test_remove_mentions(self):
        from main import clean_text
        assert clean_text("hello @user world") == "hello world"

    def test_collapse_whitespace(self):
        from main import clean_text
        assert clean_text("hello   world\n\nfoo") == "hello world foo"

    def test_strip(self):
        from main import clean_text
        assert clean_text("  hello  ") == "hello"

    def test_combined(self):
        from main import clean_text
        result = clean_text("  @user check https://t.co/x this  ")
        assert result == "check this"

    def test_empty(self):
        from main import clean_text
        assert clean_text("") == ""

    def test_only_url(self):
        from main import clean_text
        assert clean_text("https://t.co/abc") == ""

class TestParseBatchResponse:
    """测试 parse_batch_response 批量响应解析"""

    def test_standard_format(self):
        from xcrawler.services.translation import parse_batch_response
        resp = "[1] 你好世界\n[2] 这是测试\n[3] 第三条"
        result = parse_batch_response(resp, 3)
        assert result == ["你好世界", "这是测试", "第三条"]

    def test_number_dot_format(self):
        from xcrawler.services.translation import parse_batch_response
        resp = "1. 你好世界\n2. 这是测试"
        result = parse_batch_response(resp, 2)
        assert result == ["你好世界", "这是测试"]

    def test_number_paren_format(self):
        from xcrawler.services.translation import parse_batch_response
        resp = "1) 你好世界\n2) 这是测试"
        result = parse_batch_response(resp, 2)
        assert result == ["你好世界", "这是测试"]

    def test_empty_lines_skipped(self):
        from xcrawler.services.translation import parse_batch_response
        resp = "[1] 你好\n\n[2] 世界\n\n"
        result = parse_batch_response(resp, 2)
        assert result == ["你好", "世界"]

    def test_count_mismatch_fallback(self):
        """当解析结果数量不对时，回退到按行返回"""
        from xcrawler.services.translation import parse_batch_response
        resp = "你好世界\n这是测试"
        result = parse_batch_response(resp, 2)
        assert len(result) == 2
        assert "你好世界" in result

    def test_with_colon_separator(self):
        from xcrawler.services.translation import parse_batch_response
        resp = "[1]：你好\n[2]：世界"
        result = parse_batch_response(resp, 2)
        assert result == ["你好", "世界"]

    def test_numbered_response_with_extra_text_is_invalid(self):
        from xcrawler.services.translation import parse_batch_response

        resp = "以下是翻译：\n[1] 你好\n[2] 世界"
        assert parse_batch_response(resp, 2) == []

class TestDetectLanguage:
    """测试 detect_language 语言检测"""

    def test_short_text_unknown(self):
        from main import detect_language
        assert detect_language("hi") == "unknown"

    def test_empty_text_unknown(self):
        from main import detect_language
        assert detect_language("") == "unknown"

    def test_chinese_if_langdetect_installed(self):
        from main import detect_language
        result = detect_language("这是一段足够长的中文文本用于检测语言")
        try:
            import langdetect
            assert result in ("zh-cn", "zh")
        except ImportError:
            assert result == "unknown"

    def test_english_if_langdetect_installed(self):
        from main import detect_language
        result = detect_language("This is a longer English text for detection")
        try:
            import langdetect
            assert result == "en"
        except ImportError:
            assert result == "unknown"

class TestTranslationCache:
    """测试翻译缓存读写"""

    def test_save_and_load(self, tmp_path):
        import main
        from xcrawler.services.translation_cache import TRANSLATION_CACHE_SCHEMA_VERSION

        original_dir = main.CACHE_DIR
        main.CACHE_DIR = str(tmp_path)
        try:
            cache = {"hello": "你好", "world": "世界"}
            main.save_translation_cache(cache)
            loaded = main.load_translation_cache()
            assert loaded["version"] == TRANSLATION_CACHE_SCHEMA_VERSION
            assert loaded["entries"] == {}
            assert loaded["legacy_entries"] == cache
        finally:
            main.CACHE_DIR = original_dir

    def test_load_missing_file(self, tmp_path):
        import main
        original_dir = main.CACHE_DIR
        main.CACHE_DIR = str(tmp_path)
        try:
            loaded = main.load_translation_cache()
            assert loaded == {"version": 2, "entries": {}, "legacy_entries": {}}
        finally:
            main.CACHE_DIR = original_dir

    def test_load_corrupt_file_without_backup_raises(self, tmp_path):
        import main
        from xcrawler.storage.json_store import JsonStoreError

        original_dir = main.CACHE_DIR
        main.CACHE_DIR = str(tmp_path)
        try:
            cache_file = tmp_path / "translation_cache.json"
            cache_file.write_text("not valid json {{{")
            with pytest.raises(JsonStoreError, match="没有可恢复备份"):
                main.load_translation_cache()
        finally:
            main.CACHE_DIR = original_dir

class TestTranslationCacheSchema:
    """测试版本化翻译缓存和配置隔离。"""

    def test_legacy_cache_is_preserved_but_not_reused(self):
        from xcrawler.services.translation_cache import (
            TranslationCacheContext,
            get_cached_translation,
            normalize_translation_cache,
        )

        cache = normalize_translation_cache({"hello": "你好"})
        context = TranslationCacheContext(provider="deepseek", model="deepseek-chat")

        assert cache["legacy_entries"] == {"hello": "你好"}
        assert cache["entries"] == {}
        assert get_cached_translation(cache, "hello", context) is None

    @pytest.mark.parametrize("changed_context", [
        {"provider": "openai", "model": "deepseek-chat"},
        {"provider": "deepseek", "model": "deepseek-reasoner"},
        {"provider": "deepseek", "model": "deepseek-chat", "target_language": "en"},
        {"provider": "deepseek", "model": "deepseek-chat", "prompt_version": "social-media-zh-v2"},
    ])
    def test_cache_misses_when_context_changes(self, changed_context):
        from xcrawler.services.translation_cache import (
            TranslationCacheContext,
            get_cached_translation,
            new_translation_cache,
            set_cached_translation,
        )

        original_context = TranslationCacheContext(provider="deepseek", model="deepseek-chat")
        cache = new_translation_cache()
        set_cached_translation(cache, "hello", "你好", original_context)

        assert get_cached_translation(cache, "hello", TranslationCacheContext(**changed_context)) is None
        assert get_cached_translation(cache, "hello", original_context) == "你好"

    def test_context_fingerprint_is_stable_and_configuration_specific(self):
        from xcrawler.services.translation_cache import TranslationCacheContext

        first = TranslationCacheContext(provider="deepseek", model="deepseek-chat")
        same = TranslationCacheContext(provider="deepseek", model="deepseek-chat")
        changed = TranslationCacheContext(provider="deepseek", model="deepseek-reasoner")

        assert first.fingerprint == same.fingerprint
        assert first.fingerprint != changed.fingerprint

    def test_malformed_current_schema_is_safely_normalized(self):
        from xcrawler.services.translation_cache import ensure_translation_cache

        cache = {"version": 2, "entries": [], "legacy_entries": None}

        assert ensure_translation_cache(cache) == {"version": 2, "entries": {}, "legacy_entries": {}}

class TestDeepseekTranslate:
    """测试 deepseek_translate 单条翻译"""

    def test_cached_text_returns_immediately(self):
        import main
        from xcrawler.services.translation_cache import new_translation_cache, set_cached_translation

        main.translation_cache = new_translation_cache()
        set_cached_translation(main.translation_cache, "hello", "你好", main._translation_cache_context())
        result = main.deepseek_translate("hello")
        assert result == "你好"

    def test_chinese_text_passthrough(self):
        import main
        from xcrawler.services.translation_cache import get_cached_translation, new_translation_cache

        main.translation_cache = new_translation_cache()
        result = main.deepseek_translate("这是中文", detected_lang="zh-cn")
        assert result == "这是中文"
        assert get_cached_translation(
            main.translation_cache,
            "这是中文",
            main._translation_cache_context(),
        ) == "这是中文"

    def test_chinese_zh_lang(self):
        import main
        from xcrawler.services.translation_cache import new_translation_cache

        main.translation_cache = new_translation_cache()
        result = main.deepseek_translate("中文推文", detected_lang="zh")
        assert result == "中文推文"

    @patch("main._get_ds_client")
    def test_api_call(self, mock_client):
        import main
        from xcrawler.services.translation_cache import get_cached_translation, new_translation_cache

        main.translation_cache = new_translation_cache()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "你好世界"
        mock_client.return_value.chat.completions.create.return_value = mock_response

        result = main.deepseek_translate("Hello world", detected_lang="en")
        assert result == "你好世界"
        assert get_cached_translation(
            main.translation_cache,
            "Hello world",
            main._translation_cache_context(),
        ) == "你好世界"

    @patch("main._get_ds_client")
    def test_api_failure_returns_none(self, mock_client):
        import main
        from xcrawler.services.translation_cache import new_translation_cache

        main.translation_cache = new_translation_cache()
        mock_client.return_value.chat.completions.create.side_effect = Exception("API error")

        result = main.deepseek_translate("Hello", detected_lang="en", use_cache=False)
        assert result is None

class TestDeepseekTranslateBatch:
    """测试 deepseek_translate_batch 批量翻译"""

    @pytest.fixture(autouse=True)
    def isolated_checkpoint_cache(self, tmp_path, monkeypatch):
        import main

        monkeypatch.setattr(main, "CACHE_DIR", str(tmp_path))

    def test_all_cached(self):
        import main
        from xcrawler.services.translation_cache import new_translation_cache, set_cached_translation

        main.translation_cache = new_translation_cache()
        context = main._translation_cache_context()
        set_cached_translation(main.translation_cache, "a", "甲", context)
        set_cached_translation(main.translation_cache, "b", "乙", context)
        result = main.deepseek_translate_batch(["a", "b"])
        assert result == ["甲", "乙"]

    def test_chinese_passthrough(self):
        import main
        from xcrawler.services.translation_cache import new_translation_cache

        main.translation_cache = new_translation_cache()
        result = main.deepseek_translate_batch(["中文"], detected_langs=["zh-cn"])
        assert result == ["中文"]

    def test_mixed_cache_and_new(self):
        import main
        from xcrawler.services.translation_cache import new_translation_cache, set_cached_translation

        main.translation_cache = new_translation_cache()
        set_cached_translation(main.translation_cache, "cached", "已缓存", main._translation_cache_context())
        with patch("main._get_ds_client") as mock_client:
            mock_resp = MagicMock()
            mock_resp.choices = [MagicMock()]
            mock_resp.choices[0].message.content = "[1] 新翻译"
            mock_client.return_value.chat.completions.create.return_value = mock_resp

            result = main.deepseek_translate_batch(["cached", "new text"], detected_langs=["zh", "en"])
            assert result[0] == "已缓存"
            assert result[1] == "新翻译"

    def test_batch_size_must_be_positive(self):
        from xcrawler.services.translation import translate_batch

        with pytest.raises(ValueError, match="batch_size"):
            translate_batch(
                ["hello"],
                detected_langs=["en"],
                use_cache=False,
                cache={},
                client_factory=lambda: None,
                model="m",
                batch_size=0,
                max_retries=1,
                fallback_translate=lambda text, lang, use_cache: None,
            )

    def test_malformed_batch_response_falls_back_without_caching_bad_lines(self):
        from xcrawler.services.translation import translate_batch

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "以下是翻译：\n[1] 你好\n[2] 世界"
        client = MagicMock()
        client.chat.completions.create.return_value = mock_response
        cache = {}
        fallback = MagicMock(side_effect=lambda text, lang, use_cache: f"fallback:{text}")
        metrics = {}

        result = translate_batch(
            ["hello", "world"],
            detected_langs=["en", "en"],
            use_cache=True,
            cache=cache,
            client_factory=lambda: client,
            model="m",
            batch_size=2,
            max_retries=1,
            fallback_translate=fallback,
            metrics=metrics,
        )

        assert result == ["fallback:hello", "fallback:world"]
        assert cache["entries"] == {}
        assert cache["legacy_entries"] == {}
        assert metrics["failed_batches"] == 1

class TestTranslateSyncImport:
    """测试 translate_sync.py 能否正常 import"""

    def test_import_succeeds(self):
        """验证 import main 不会因缺少 API key 而崩溃"""
        # 这应该不会抛异常，因为 ds_client 现在是 lazy init
        import main
        assert main.ds_client is None  # 尚未初始化
        assert callable(main._get_ds_client)

    def test_sync_adds_duplicate_text_when_tweet_id_is_new(self, tmp_path):
        import sys

        import translate_sync

        username = "alice"
        raw_file = tmp_path / f"{username}_raw_tweets.json"
        translated_file = tmp_path / f"{username}_translated.json"
        raw_file.write_text(json.dumps([
            {"id": "1", "text": "Same text", "created_at": "2024-01-02T00:00:00Z"},
            {"id": "2", "text": "Same text", "created_at": "2024-01-01T00:00:00Z"},
        ]), encoding="utf-8")
        translated_file.write_text(json.dumps([
            {
                "tweet_id": "1",
                "original": "Same text",
                "translated": "同样的文本",
                "detected_language": "en",
                "created_at": "2024-01-02T00:00:00Z",
            }
        ]), encoding="utf-8")

        old_argv = sys.argv[:]
        old_cache_dir = translate_sync.CACHE_DIR
        old_username = translate_sync.TARGET_USERNAME
        try:
            sys.argv = ["translate_sync.py", "--user", username, "--cache-dir", str(tmp_path)]
            with patch("translate_sync.translate_batch", return_value=["同样的文本", "同样的文本"]) as mock_batch, \
                 patch("translate_sync.detect_language", return_value="en"), \
                 patch("xcrawler.storage.json_store.save_json"):
                translate_sync.main()

            data = json.loads(translated_file.read_text(encoding="utf-8"))
            assert {item["tweet_id"] for item in data} == {"1", "2"}
            mock_batch.assert_called_once()
        finally:
            sys.argv = old_argv
            translate_sync.CACHE_DIR = old_cache_dir
            translate_sync.TARGET_USERNAME = old_username

    def test_force_partial_failure_keeps_original_translation_file(self, tmp_path, monkeypatch):
        import sys

        import translate_sync

        raw = [
            {"id": "1", "text": "first long text", "created_at": "2024-01-02T00:00:00Z"},
            {"id": "2", "text": "second long text", "created_at": "2024-01-01T00:00:00Z"},
        ]
        original = [
            {
                "tweet_id": "1",
                "original": "first long text",
                "translated": "旧译文一",
                "detected_language": "en",
                "created_at": "2024-01-02T00:00:00Z",
            },
            {
                "tweet_id": "2",
                "original": "second long text",
                "translated": "旧译文二",
                "detected_language": "en",
                "created_at": "2024-01-01T00:00:00Z",
            },
        ]
        raw_file = tmp_path / "alice_raw_tweets.json"
        translated_file = tmp_path / "alice_translated.json"
        raw_file.write_text(json.dumps(raw), encoding="utf-8")
        translated_file.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(sys, "argv", [
            "translate_sync.py", "--user", "alice", "--cache-dir", str(tmp_path), "--force",
        ])
        monkeypatch.setattr(translate_sync, "translate_batch", MagicMock(return_value=["新译文一", None]))
        monkeypatch.setattr(translate_sync, "detect_language", lambda text: "en")

        assert translate_sync.main() == 1
        assert json.loads(translated_file.read_text(encoding="utf-8")) == original
        assert translated_file.with_suffix(".json.bak").exists()

    def test_non_force_all_fail_returns_failure(self, tmp_path, monkeypatch):
        import sys

        import translate_sync

        raw = [{"id": "1", "text": "first long text", "created_at": "2024-01-02T00:00:00Z"}]
        (tmp_path / "alice_raw_tweets.json").write_text(json.dumps(raw), encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["translate_sync.py", "--user", "alice", "--cache-dir", str(tmp_path)])
        monkeypatch.setattr(translate_sync, "translate_batch", MagicMock(return_value=[None]))
        monkeypatch.setattr(translate_sync, "detect_language", lambda text: "en")

        assert translate_sync.main() == 1
        assert not (tmp_path / "alice_translated.json").exists()

    def test_changed_source_text_for_existing_id_is_retranslated(self, tmp_path, monkeypatch):
        import sys

        import translate_sync

        raw = [{"id": "1", "text": "updated long text", "created_at": "2024-01-02T00:00:00Z"}]
        translated = [{
            "tweet_id": "1",
            "original": "previous long text",
            "translated": "旧译文",
            "detected_language": "en",
            "created_at": "2024-01-02T00:00:00Z",
        }]
        (tmp_path / "alice_raw_tweets.json").write_text(json.dumps(raw), encoding="utf-8")
        (tmp_path / "alice_translated.json").write_text(json.dumps(translated), encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["translate_sync.py", "--user", "alice", "--cache-dir", str(tmp_path)])
        translate_batch_mock = MagicMock(return_value=["新译文"])
        monkeypatch.setattr(translate_sync, "translate_batch", translate_batch_mock)
        monkeypatch.setattr(translate_sync, "detect_language", lambda text: "en")

        assert translate_sync.main() == 0
        translate_batch_mock.assert_called_once()
        saved = json.loads((tmp_path / "alice_translated.json").read_text(encoding="utf-8"))
        assert len(saved) == 1
        updated = saved[0]
        assert updated["original"] == "updated long text"
        assert updated["source_fingerprint"]
        assert updated["config_fingerprint"]

class TestXcrawlerTextUtils:
    """测试 xcrawler.utils.text"""

    def test_clean_text_module(self):
        from xcrawler.utils.text import clean_text
        assert clean_text("@user hello https://t.co/x   world") == "hello world"

    def test_detect_language_short_text(self):
        from xcrawler.utils.text import detect_language
        assert detect_language("hi") == "unknown"

class TestTranslationRecords:
    """测试 translated tweet 兼容层"""

    def test_make_translated_tweet_includes_tweet_id(self):
        from xcrawler.services.records import make_translated_tweet

        record = make_translated_tweet(
            tweet_id="123",
            original="Hello",
            translated="你好",
            detected_language="en",
            created_at="2024-01-01",
        )

        assert record["tweet_id"] == "123"
        assert record["translated"] == "你好"

    def test_normalize_old_translated_tweet_adds_tweet_id_none(self):
        from xcrawler.services.records import normalize_translated_tweets

        records = normalize_translated_tweets([
            {"original": "Hello", "translated": "你好", "detected_language": "en", "created_at": "2024-01-01"}
        ])

        assert records[0]["tweet_id"] is None
        assert records[0]["original"] == "Hello"

class TestTranslationService:
    """测试 xcrawler.services.translation"""

    def testparse_batch_response_module(self):
        from xcrawler.services.translation import parse_batch_response
        resp = "[1] 你好\n[2] 世界"
        assert parse_batch_response(resp, 2) == ["你好", "世界"]

    def test_translate_text_uses_cache(self):
        from xcrawler.services.translation import translate_text
        from xcrawler.services.translation_cache import (
            TranslationCacheContext,
            new_translation_cache,
            set_cached_translation,
        )

        context = TranslationCacheContext(provider="test", model="test")
        cache = new_translation_cache()
        set_cached_translation(cache, "hello", "你好", context)

        def fail_client():
            raise AssertionError("cached text should not call client")

        assert translate_text(
            "hello",
            detected_lang="en",
            use_cache=True,
            cache=cache,
            client_factory=fail_client,
            model="test",
            max_retries=1,
            cache_context=context,
        ) == "你好"

    def test_translate_batch_records_usage_metrics(self):
        from xcrawler.services.translation import translate_batch

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "[1] 你好"
        mock_response.usage.total_tokens = 11
        client = MagicMock()
        client.chat.completions.create.return_value = mock_response
        metrics = {"llm_calls": 0, "total_tokens": 0, "failed_batches": 0}

        result = translate_batch(
            ["hello"],
            detected_langs=["en"],
            use_cache=False,
            cache={},
            client_factory=lambda: client,
            model="test",
            batch_size=1,
            max_retries=1,
            fallback_translate=lambda text, lang, use_cache: None,
            metrics=metrics,
        )

        assert result == ["你好"]
        assert metrics["llm_calls"] == 1
        assert metrics["total_tokens"] == 11

    def test_translate_batch_records_cache_hits_misses_and_fingerprint(self):
        from xcrawler.services.translation import translate_batch
        from xcrawler.services.translation_cache import (
            TranslationCacheContext,
            new_translation_cache,
            set_cached_translation,
        )

        context = TranslationCacheContext(provider="deepseek", model="test")
        cache = new_translation_cache()
        set_cached_translation(cache, "cached", "已缓存", context)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "[1] 新翻译"
        client = MagicMock()
        client.chat.completions.create.return_value = mock_response
        metrics = {}

        result = translate_batch(
            ["cached", "new"],
            detected_langs=["en", "en"],
            use_cache=True,
            cache=cache,
            client_factory=lambda: client,
            model="test",
            batch_size=10,
            max_retries=1,
            fallback_translate=lambda text, lang, use_cache: None,
            metrics=metrics,
            cache_context=context,
        )

        assert result == ["已缓存", "新翻译"]
        assert metrics["cache_hits"] == 1
        assert metrics["cache_misses"] == 1
        assert metrics["cache_fingerprint"] == context.fingerprint

    def test_force_mode_bypasses_old_entry_and_rebuilds_cache(self):
        from xcrawler.services.translation import translate_batch
        from xcrawler.services.translation_cache import (
            TranslationCacheContext,
            get_cached_translation,
            new_translation_cache,
            set_cached_translation,
        )

        context = TranslationCacheContext(provider="deepseek", model="test")
        cache = new_translation_cache()
        set_cached_translation(cache, "hello", "旧翻译", context)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "[1] 新翻译"
        client = MagicMock()
        client.chat.completions.create.return_value = mock_response
        metrics = {}

        result = translate_batch(
            ["hello"],
            detected_langs=["en"],
            use_cache=False,
            cache=cache,
            client_factory=lambda: client,
            model="test",
            batch_size=1,
            max_retries=1,
            fallback_translate=lambda text, lang, use_cache: None,
            metrics=metrics,
            cache_context=context,
            cache_results=True,
        )

        assert result == ["新翻译"]
        assert get_cached_translation(cache, "hello", context) == "新翻译"
        assert metrics["cache_bypassed"] == 1
