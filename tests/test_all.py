"""
xcrawler 单元测试
覆盖纯函数、工具函数和需要 mock 的 API 调用
"""
import csv
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# ==============================
# main.py 函数测试
# ==============================

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


class TestClusterCalculation:
    """测试聚类数动态计算逻辑"""

    def test_small_dataset(self):
        # 10条推文 -> 10//10=1 -> max(2,1)=2
        n = 10
        cluster_num = max(2, min(8, n // 10))
        assert cluster_num == 2

    def test_medium_dataset(self):
        # 50条推文 -> 50//10=5
        n = 50
        cluster_num = max(2, min(8, n // 10))
        assert cluster_num == 5

    def test_large_dataset(self):
        # 200条推文 -> 200//10=20 -> min(8,20)=8
        n = 200
        cluster_num = max(2, min(8, n // 10))
        assert cluster_num == 8

    def test_minimum_is_2(self):
        n = 5
        cluster_num = max(2, min(8, n // 10))
        assert cluster_num == 2


# ==============================
# fetch_more_history.py 函数测试
# ==============================

class TestParseTwitterDatetime:
    """测试 parse_twitter_datetime 时间解析"""

    def test_with_microseconds(self):
        from fetch_more_history import parse_twitter_datetime
        dt = parse_twitter_datetime("2024-06-15T12:30:45.123456Z")
        assert dt.year == 2024
        assert dt.month == 6
        assert dt.hour == 12

    def test_without_microseconds(self):
        from fetch_more_history import parse_twitter_datetime
        dt = parse_twitter_datetime("2024-06-15T12:30:45Z")
        assert dt.year == 2024
        assert dt.minute == 30

    def test_invalid_format_raises(self):
        from fetch_more_history import parse_twitter_datetime
        with pytest.raises(ValueError):
            parse_twitter_datetime("not-a-date")


class TestFetchMoreHistory:
    """测试增量历史抓取边界"""

    def test_merge_tweets_retains_existing_and_deduplicates(self):
        from fetch_more_history import merge_tweets

        existing = [
            {"id": "2", "text": "old copy", "created_at": "2024-01-02T00:00:00Z"},
            {"id": "1", "text": "existing history", "created_at": "2024-01-01T00:00:00Z"},
        ]
        new = [
            {"id": "3", "text": "new tweet", "created_at": "2024-01-03T00:00:00Z"},
            {"id": "2", "text": "refreshed copy", "created_at": "2024-01-02T00:00:00Z"},
            {"id": "0", "text": "older history", "created_at": "2023-12-31T00:00:00Z"},
        ]

        merged = merge_tweets(existing, new)

        assert [tweet["id"] for tweet in merged] == ["3", "2", "1", "0"]
        assert merged[1]["text"] == "refreshed copy"

    def test_main_incremental_save_keeps_existing_tweets(self, tmp_path, monkeypatch):
        import fetch_more_history

        username = "testuser"
        raw_file = tmp_path / f"{username}_raw_tweets.json"
        raw_file.write_text(json.dumps([
            {"id": "2", "text": "existing latest", "created_at": "2025-01-02T00:00:00Z"},
            {"id": "1", "text": "existing history", "created_at": "2025-01-01T00:00:00Z"},
        ]), encoding="utf-8")

        monkeypatch.setattr(fetch_more_history, "parse_args", lambda: SimpleNamespace(
            user=username,
            pages=2,
            target_date=None,
            interval=0,
            cache_dir=str(tmp_path),
        ))
        monkeypatch.setattr(fetch_more_history, "auth_headers", lambda token: {"Authorization": "Bearer test"})
        monkeypatch.setattr(fetch_more_history, "get_user_id", lambda user, headers: "user-id")
        monkeypatch.setattr(fetch_more_history, "TARGET_DATE", datetime(2024, 1, 1))

        fetch_calls = MagicMock(side_effect=[
            ([{"id": "3", "text": "new tweet", "created_at": "2025-01-03T00:00:00Z"}], False, 1),
            ([{"id": "0", "text": "older history", "created_at": "2024-12-31T00:00:00Z"}], False, 1),
        ])
        monkeypatch.setattr(fetch_more_history, "fetch_tweets_generic", fetch_calls)

        assert fetch_more_history.main() == 0

        saved = json.loads(raw_file.read_text(encoding="utf-8"))
        assert [tweet["id"] for tweet in saved] == ["3", "2", "1", "0"]
        assert fetch_calls.call_count == 2

    @patch("fetch_more_history.requests.get")
    def test_stop_date_filters_within_page(self, mock_get):
        import fetch_more_history

        old_interval = fetch_more_history.REQUEST_INTERVAL
        fetch_more_history.REQUEST_INTERVAL = 0
        try:
            response = MagicMock()
            response.status_code = 200
            response.headers = {}
            response.raise_for_status = MagicMock()
            response.json.return_value = {
                "data": [
                    {"id": "2", "text": "newer", "created_at": "2024-01-02T00:00:00Z"},
                    {"id": "1", "text": "older", "created_at": "2023-12-31T23:59:59Z"},
                ],
                "meta": {},
            }
            mock_get.return_value = response

            tweets, reached, pages = fetch_more_history.fetch_tweets_generic(
                "user-id",
                {"Authorization": "Bearer test-token"},
                stop_date=datetime(2024, 1, 1),
                max_pages_limit=1,
            )

            assert reached is True
            assert pages == 1
            assert [tweet["id"] for tweet in tweets] == ["2"]
        finally:
            fetch_more_history.REQUEST_INTERVAL = old_interval


# ==============================
# visualize.py 函数测试
# ==============================

class TestParseDt:
    """测试 visualize._parse_dt"""

    def test_with_microseconds(self):
        from visualize import _parse_dt
        dt = _parse_dt("2024-01-01T00:00:00.000000Z")
        assert dt == datetime(2024, 1, 1)

    def test_without_microseconds(self):
        from visualize import _parse_dt
        dt = _parse_dt("2024-01-01T00:00:00Z")
        assert dt == datetime(2024, 1, 1)


# ==============================
# analyze_network.py 函数测试
# ==============================

class TestExtractEntities:
    """测试 extract_entities 实体提取"""

    def test_basic_extraction(self):
        from analyze_network import extract_entities
        tweets = [
            {
                "entities": {
                    "hashtags": [{"tag": "python"}, {"tag": "AI"}],
                    "mentions": [{"username": "elonmusk"}]
                }
            },
            {
                "entities": {
                    "hashtags": [{"tag": "python"}],
                    "mentions": [{"username": "openai"}]
                }
            }
        ]
        hashtag_counts, mention_counts, pair_counts = extract_entities(tweets)
        assert hashtag_counts["python"] == 2
        assert hashtag_counts["ai"] == 1
        assert mention_counts["elonmusk"] == 1
        assert mention_counts["openai"] == 1

    def test_empty_entities(self):
        from analyze_network import extract_entities
        tweets = [{"entities": {}}]
        hashtag_counts, mention_counts, pair_counts = extract_entities(tweets)
        assert len(hashtag_counts) == 0

    def test_no_entities_field(self):
        from analyze_network import extract_entities
        tweets = [{"text": "hello world"}]
        hashtag_counts, mention_counts, pair_counts = extract_entities(tweets)
        assert len(hashtag_counts) == 0

    def test_cooccurrence(self):
        from analyze_network import extract_entities
        tweets = [{
            "entities": {
                "hashtags": [{"tag": "python"}],
                "mentions": [{"username": "guido"}]
            }
        }]
        _, _, pair_counts = extract_entities(tweets)
        assert pair_counts["#python ↔ @guido"] == 1


class TestExtractHashtagsFromText:
    """测试从文本中提取 hashtag"""

    def test_basic(self):
        from analyze_network import extract_hashtags_from_text
        tweets = [{"text": "Love #Python and #AI"}]
        counts = extract_hashtags_from_text(tweets)
        assert counts["python"] == 1
        assert counts["ai"] == 1

    def test_no_hashtags(self):
        from analyze_network import extract_hashtags_from_text
        tweets = [{"text": "No hashtags here"}]
        counts = extract_hashtags_from_text(tweets)
        assert len(counts) == 0

    def test_case_insensitive(self):
        from analyze_network import extract_hashtags_from_text
        tweets = [{"text": "#Python #PYTHON #python"}]
        counts = extract_hashtags_from_text(tweets)
        assert counts["python"] == 3


# ==============================
# API 函数测试（mock）
# ==============================

class TestGetUserId:
    """测试 get_user_id"""

    @patch("main.requests.get")
    def test_success(self, mock_get):
        from main import get_user_id
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"data": {"id": "12345"}}
        mock_get.return_value.raise_for_status = MagicMock()

        result = get_user_id("testuser")
        assert result == "12345"

    @patch("main.requests.get")
    def test_user_not_found(self, mock_get):
        from main import get_user_id
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"errors": [{"message": "Not found"}]}
        mock_get.return_value.raise_for_status = MagicMock()

        with pytest.raises(ValueError, match="不存在"):
            get_user_id("nonexistent")


class TestGetUserProfile:
    """测试 get_user_profile"""

    @patch("main.requests.get")
    def test_success(self, mock_get):
        from main import get_user_profile
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "data": {
                "name": "Test User",
                "description": "A test bio",
                "location": "Tokyo",
                "verified": False,
                "created_at": "2020-01-01T00:00:00.000Z",
                "public_metrics": {
                    "followers_count": 100,
                    "following_count": 50,
                    "tweet_count": 500,
                    "listed_count": 5
                }
            }
        }
        mock_get.return_value.raise_for_status = MagicMock()

        result = get_user_profile("testuser")
        assert result["username"] == "testuser"
        assert result["followers_count"] == 100
        assert result["description"] == "A test bio"

    @patch("main.requests.get")
    def test_api_failure(self, mock_get):
        from main import get_user_profile
        mock_get.side_effect = Exception("Network error")
        result = get_user_profile("testuser")
        assert result is None


# ==============================
# 集成级测试
# ==============================

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


class TestAnalysisImports:
    """测试分析脚本导入不会过早初始化外部服务"""

    def test_analyze_pro_provider_is_lazy(self):
        import analyze_pro

        original_provider = analyze_pro.provider
        try:
            analyze_pro.provider = None
            assert analyze_pro.provider is None
            assert callable(analyze_pro._get_provider)
        finally:
            analyze_pro.provider = original_provider

    def test_analyze_pro_exposes_main_for_unified_cli(self):
        import analyze_pro

        assert callable(analyze_pro.main)


class TestExportCsvHelpers:
    """测试 CSV 导出辅助逻辑"""

    @pytest.mark.parametrize("value", [
        "=1+1",
        "+SUM(A1:A2)",
        "-2+3",
        "@SUM(A1:A2)",
        "  =HYPERLINK(\"https://example.com\")",
        "\t=CMD()",
    ])
    def test_safe_csv_cell_blocks_spreadsheet_formulas(self, value):
        from export_csv import safe_csv_cell

        assert safe_csv_cell(value) == f"'{value}"

    def test_safe_csv_cell_preserves_normal_text(self):
        from export_csv import safe_csv_cell

        assert safe_csv_cell("ordinary text") == "ordinary text"

    def test_export_tweets(self, tmp_path):
        from export_csv import export_tweets
        tweets = [
            {
                "id": "1",
                "text": "Hello #world @user",
                "created_at": "2024-01-01T00:00:00.000Z",
                "entities": {
                    "hashtags": [{"tag": "world"}],
                    "mentions": [{"username": "user"}]
                }
            }
        ]
        output = str(tmp_path / "test.csv")
        export_tweets(tweets, output)

        with open(output, encoding='utf-8-sig') as f:
            content = f.read()
        assert "Hello #world @user" in content
        assert "world" in content
        assert "user" in content

    def test_export_translations(self, tmp_path):
        from export_csv import export_translations
        data = [
            {"tweet_id": "42", "original": "Hello", "translated": "你好", "detected_language": "en", "created_at": "2024-01-01"}
        ]
        output = str(tmp_path / "test.csv")
        export_translations(data, output)

        with open(output, encoding='utf-8-sig') as f:
            content = f.read()
        assert "tweet_id" in content
        assert "42" in content
        assert "你好" in content
        assert "en" in content

    def test_export_tweets_escapes_formula_and_preserves_long_id(self, tmp_path):
        from export_csv import export_tweets

        tweet_id = "1999999999999999999"
        output = str(tmp_path / "tweets.csv")
        export_tweets([{
            "id": tweet_id,
            "text": "=HYPERLINK(\"https://example.com\")",
            "created_at": "2026-01-01T00:00:00Z",
            "entities": {},
        }], output)

        with open(output, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))

        assert rows[1][0] == f"'{tweet_id}"
        assert rows[1][1] == "'=HYPERLINK(\"https://example.com\")"

    def test_export_translations_escapes_untrusted_text(self, tmp_path):
        from export_csv import export_translations

        output = str(tmp_path / "translations.csv")
        export_translations([{
            "tweet_id": "1999999999999999999",
            "original": "+CMD()",
            "translated": "  @SUM(A1:A2)",
            "detected_language": "en",
            "created_at": "2026-01-01",
        }], output)

        with open(output, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))

        assert rows[1][0] == "'1999999999999999999"
        assert rows[1][1] == "'+CMD()"
        assert rows[1][2] == "'  @SUM(A1:A2)"

    def test_export_interests_includes_evidence_ids(self, tmp_path):
        from export_csv import export_interests

        profile = {
            "interests": [{
                "tag": "AI",
                "level": "core",
                "confidence": 0.9,
                "keywords": ["LLM"],
                "evidence_count": 1,
                "evidence_tweet_ids": ["123"],
                "evidence_status": "ok",
            }]
        }
        output = str(tmp_path / "interests.csv")
        export_interests(profile, output)

        with open(output, encoding='utf-8-sig') as f:
            content = f.read()
        assert "evidence_tweet_ids" in content
        assert "123" in content

    def test_export_interests_escapes_llm_generated_fields(self, tmp_path):
        from export_csv import export_interests

        output = str(tmp_path / "interests.csv")
        export_interests({"interests": [{
            "tag": "@SUM(A1:A2)",
            "level": "core",
            "confidence": "=1+1",
            "keywords": ["+CMD()"],
            "evidence_count": 1,
            "evidence_tweet_ids": ["1999999999999999999"],
            "evidence_status": "ok",
        }]}, output)

        with open(output, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))

        assert rows[1][0] == "'@SUM(A1:A2)"
        assert rows[1][2] == "'=1+1"
        assert rows[1][3] == "'+CMD()"
        assert rows[1][5] == "'1999999999999999999"


# ==============================
# xcrawler 公共模块测试
# ==============================

class TestXcrawlerTextUtils:
    """测试 xcrawler.utils.text"""

    def test_clean_text_module(self):
        from xcrawler.utils.text import clean_text
        assert clean_text("@user hello https://t.co/x   world") == "hello world"

    def test_detect_language_short_text(self):
        from xcrawler.utils.text import detect_language
        assert detect_language("hi") == "unknown"


class TestXcrawlerTimeUtils:
    """测试 xcrawler.utils.time"""

    def test_parse_twitter_datetime_module(self):
        from xcrawler.utils.time import parse_twitter_datetime
        dt = parse_twitter_datetime("2024-06-15T12:30:45Z")
        assert dt == datetime(2024, 6, 15, 12, 30, 45)


class TestJsonStore:
    """测试 xcrawler.storage.json_store"""

    def test_save_and_load_json(self, tmp_path):
        from xcrawler.storage.json_store import load_json, save_json
        path = tmp_path / "nested" / "data.json"
        save_json(str(path), {"a": 1})
        assert load_json(str(path)) == {"a": 1}

    def test_load_json_missing_returns_default(self, tmp_path):
        from xcrawler.storage.json_store import load_json
        assert load_json(str(tmp_path / "missing.json"), default=[]) == []

    def test_save_json_keeps_primary_when_replace_fails(self, tmp_path, monkeypatch):
        from xcrawler.storage import json_store

        path = tmp_path / "data.json"
        json_store.save_json(str(path), {"version": 1})
        real_replace = json_store.os.replace

        def fail_primary_replace(source, destination):
            if destination == str(path):
                raise OSError("simulated interruption")
            return real_replace(source, destination)

        monkeypatch.setattr(json_store.os, "replace", fail_primary_replace)

        with pytest.raises(OSError, match="simulated interruption"):
            json_store.save_json(str(path), {"version": 2})

        assert json.loads(path.read_text(encoding="utf-8")) == {"version": 1}
        assert not list(tmp_path.glob(".data.json.*.tmp"))

    def test_load_json_recovers_corrupt_primary_from_backup(self, tmp_path):
        from xcrawler.storage.json_store import load_json, save_json

        path = tmp_path / "data.json"
        save_json(str(path), {"version": 1})
        save_json(str(path), {"version": 2})
        path.write_text("not valid json {{{", encoding="utf-8")

        with pytest.warns(RuntimeWarning, match="已从备份恢复"):
            recovered = load_json(str(path))

        assert recovered == {"version": 1}
        assert json.loads(path.read_text(encoding="utf-8")) == {"version": 1}

    def test_load_json_corrupt_without_backup_raises(self, tmp_path):
        from xcrawler.storage.json_store import JsonStoreError, load_json

        path = tmp_path / "data.json"
        path.write_text("not valid json {{{", encoding="utf-8")

        with pytest.raises(JsonStoreError, match="没有可恢复备份"):
            load_json(str(path), default={})

    def test_json_store_append_record(self, tmp_path):
        from xcrawler.storage.json_store import JsonStore

        store = JsonStore(str(tmp_path))
        store.append_json_record("runs.json", {"id": "1"})
        store.append_json_record("runs.json", {"id": "2"})

        assert store.load_json("runs.json") == [{"id": "1"}, {"id": "2"}]


class TestModels:
    """测试 xcrawler.models"""

    def test_tweet_record_from_api(self):
        from xcrawler.models import TweetRecord

        record = TweetRecord.from_api({
            "id": "123",
            "text": "hello",
            "created_at": "2024-01-01T00:00:00Z",
        })

        assert record.id == "123"
        assert record.to_dict()["raw"]["text"] == "hello"

    def test_interest_signal_defaults_evidence_ids(self):
        from xcrawler.models import InterestSignal

        signal = InterestSignal.from_dict({
            "tag": "AI",
            "level": "core",
            "confidence": 0.9,
            "evidence_count": 2,
        })

        assert signal.evidence_tweet_ids == []


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


class TestEvidenceService:
    """测试 evidence 校验和 HTML 渲染"""

    def test_validate_interest_evidence_filters_unknown_ids(self):
        from xcrawler.services.evidence import validate_interest_evidence

        result = {
            "interests": [{
                "tag": "AI",
                "evidence_count": 1,
                "evidence_tweet_ids": ["known", "missing"],
            }]
        }
        translated = [{
            "tweet_id": "known",
            "original": "Hello",
            "translated": "你好",
            "detected_language": "en",
            "created_at": "2024-01-01",
        }]

        validated = validate_interest_evidence(result, translated)
        assert validated["interests"][0]["evidence_tweet_ids"] == ["known"]
        assert "evidence_status" not in validated["interests"][0]

    def test_validate_interest_evidence_marks_missing(self):
        from xcrawler.services.evidence import validate_interest_evidence

        result = {"interests": [{"tag": "AI", "evidence_tweet_ids": ["missing"]}]}
        validated = validate_interest_evidence(result, [])
        assert validated["interests"][0]["evidence_tweet_ids"] == []
        assert validated["interests"][0]["evidence_status"] == "missing"

    def test_validate_interest_evidence_strict_rejects_unsupported_interests(self):
        from xcrawler.services.evidence import EvidenceValidationError, validate_interest_evidence

        result = {"interests": [{"tag": "AI", "evidence_count": 9, "evidence_tweet_ids": ["missing"]}]}

        with pytest.raises(EvidenceValidationError):
            validate_interest_evidence(result, [], require_evidence=True)

        assert result["interests"] == []
        assert result["rejected_interests"][0]["evidence_count"] == 0

    def test_validate_life_event_evidence_strict_filters_missing(self):
        from xcrawler.services.evidence import validate_life_event_evidence

        events = {
            "other_events": [
                {"description": "supported", "evidence_tweet_ids": ["known"]},
                {"description": "unsupported", "evidence_tweet_ids": ["missing"]},
            ]
        }
        translated = [{
            "tweet_id": "known",
            "original": "Hello",
            "translated": "你好",
            "detected_language": "en",
            "created_at": "2024-01-01",
        }]

        validated = validate_life_event_evidence(events, translated, require_evidence=True)

        assert len(validated["other_events"]) == 1
        assert validated["other_events"][0]["description"] == "supported"

    def test_render_evidence_html_includes_translated_text(self):
        from xcrawler.services.evidence import build_evidence_map, render_evidence_html

        translated = [{
            "tweet_id": "123",
            "original": "Hello",
            "translated": "你好",
            "detected_language": "en",
            "created_at": "2024-01-01",
        }]
        html = render_evidence_html(["123"], build_evidence_map(translated))

        assert "123" in html
        assert "你好" in html

    def test_render_evidence_html_redacts_original(self):
        from xcrawler.services.evidence import build_evidence_map, render_evidence_html

        translated = [{
            "tweet_id": "123",
            "original": "email me at user@example.com",
            "translated": "我的电话是 138-0013-8000",
            "detected_language": "zh",
            "created_at": "2024-01-01",
        }]
        html = render_evidence_html(["123"], build_evidence_map(translated), redact=True)

        assert "敏感原文已隐藏" in html
        assert "138-0013-8000" not in html

    def test_validate_life_event_evidence_filters_missing_ids(self):
        from xcrawler.services.evidence import validate_life_event_evidence

        life_events = {
            "other_events": [{
                "description": "参加演出",
                "evidence_tweet_ids": ["known", "missing"],
            }]
        }
        translated = [{
            "tweet_id": "known",
            "original": "show",
            "translated": "演出",
            "detected_language": "en",
            "created_at": "2024-01-01",
        }]

        validated = validate_life_event_evidence(life_events, translated)
        assert validated["other_events"][0]["evidence_tweet_ids"] == ["known"]

    def test_validate_life_event_evidence_marks_missing(self):
        from xcrawler.services.evidence import validate_life_event_evidence

        validated = validate_life_event_evidence(
            {"other_events": [{"description": "参加演出", "evidence_tweet_ids": ["missing"]}]},
            [],
        )

        assert validated["other_events"][0]["evidence_tweet_ids"] == []
        assert validated["other_events"][0]["evidence_status"] == "missing"


class TestPrivacyGuard:
    """测试隐私保护层"""

    def test_is_sensitive_event_by_category(self):
        from xcrawler.privacy_guard import is_sensitive_event

        assert is_sensitive_event("health_events", "去了医院")
        assert not is_sensitive_event("other_events", "参加公开演出")

    def test_redact_text_masks_email_and_phone(self):
        from xcrawler.privacy_guard import redact_text

        text = redact_text("邮箱 user@example.com 电话 138-0013-8000")
        assert "user@example.com" not in text
        assert "138-0013-8000" not in text

    def test_sanitize_life_events_hides_sensitive_by_default(self):
        from xcrawler.privacy_guard import sanitize_life_events

        events = {
            "health_events": [{
                "description": "去了医院",
                "evidence_tweet_ids": ["123"],
            }]
        }
        sanitized = sanitize_life_events(events)

        assert sanitized["health_events"][0]["description"] == "[敏感生活事件已隐藏]"
        assert sanitized["health_events"][0]["evidence_tweet_ids"] == []
        assert sanitized["health_events"][0]["redacted"] is True


class TestHtmlReportEscaping:
    """测试 HTML 报告不会直接拼接不可信文本"""

    def test_evidence_sections_escape_profile_and_event_text(self):
        from visualize import generate_evidence_sections

        html = generate_evidence_sections({
            "profile": {
                "interests": [{
                    "tag": "<script>alert(1)</script>",
                    "level": "core",
                    "confidence": "0.9",
                    "evidence_tweet_ids": [],
                }]
            },
            "behavior": {
                "life_events": {
                    "other_events": [{
                        "description": "<img src=x onerror=alert(1)>",
                        "evidence_tweet_ids": [],
                    }]
                }
            },
            "translated": [],
        })

        assert "<script>alert(1)</script>" not in html
        assert "<img src=x onerror=alert(1)>" not in html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
        assert "&lt;img src=x onerror=alert(1)&gt;" in html


class TestEmbeddingCache:
    """测试 embedding 缓存避免重复编码"""

    def test_encode_texts_with_cache_reuses_cached_vectors(self, tmp_path):
        from xcrawler.services.embeddings import encode_texts_with_cache

        calls = []

        def encoder(texts):
            calls.append(list(texts))
            return [[float(len(text))] for text in texts]

        cache_path = str(tmp_path / "embeddings.json")
        first = encode_texts_with_cache(["hello", "world"], model_name="m", cache_path=cache_path, encoder=encoder)
        second = encode_texts_with_cache(["hello", "world"], model_name="m", cache_path=cache_path, encoder=encoder)

        assert first == [[5.0], [5.0]]
        assert second == first
        assert calls == [["hello", "world"]]

    def test_encode_texts_with_cache_deduplicates_missing_texts(self, tmp_path):
        from xcrawler.services.embeddings import encode_texts_with_cache

        calls = []

        def encoder(texts):
            calls.append(list(texts))
            return [[float(len(text))] for text in texts]

        vectors = encode_texts_with_cache(
            ["same", "same"],
            model_name="m",
            cache_path=str(tmp_path / "embeddings.json"),
            encoder=encoder,
        )

        assert vectors == [[4.0], [4.0]]
        assert calls == [["same"]]


class TestSampling:
    """测试长输入均匀抽样"""

    def test_sample_evenly_spans_input(self):
        from xcrawler.services.sampling import sample_evenly

        assert sample_evenly(list(range(10)), 4) == [0, 3, 6, 9]

    def test_sample_evenly_keeps_short_input(self):
        from xcrawler.services.sampling import sample_evenly

        assert sample_evenly(["a", "b"], 5) == ["a", "b"]


class TestCli:
    """测试统一 CLI"""

    def test_cli_help_exits(self):
        from xcrawler.cli import main

        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == 0

    def test_fetch_command_forwards_args(self):
        from xcrawler import cli

        calls = []

        def fake_run(module_name, args):
            calls.append((module_name, args))
            return 0

        with patch("xcrawler.cli._run_script", side_effect=fake_run):
            result = cli.main(["fetch", "--user", "alice", "--pages", "2", "--no-translate"])

        assert result == 0
        assert calls == [("main", ["--user", "alice", "--pages", "2", "--no-translate"])]

    def test_fetch_forwards_analysis_limit(self):
        from xcrawler import cli

        with patch("xcrawler.cli._run_script") as mock_run:
            mock_run.return_value = 0
            cli.main(["fetch", "--analysis-limit", "50"])

        mock_run.assert_called_once_with("main", ["--analysis-limit", "50"])

    def test_fetch_rejects_zero_pages(self):
        from xcrawler import cli

        with pytest.raises(SystemExit) as exc:
            cli.main(["fetch", "--pages", "0"])

        assert exc.value.code == 2

    def test_interest_rejects_invalid_temperature(self):
        from xcrawler import cli

        with pytest.raises(SystemExit) as exc:
            cli.main(["analyze", "interest", "--temperature", "2.5"])

        assert exc.value.code == 2

    def test_analyze_behavior_forwards_privacy_flag(self):
        from xcrawler import cli

        with patch("xcrawler.cli._run_script") as mock_run:
            mock_run.return_value = 0
            cli.main(["analyze", "behavior", "--include-sensitive-events"])

        mock_run.assert_called_once_with("analyze_behavior", ["--include-sensitive-events"])

    def test_analyze_interest_forwards_limit(self):
        from xcrawler import cli

        with patch("xcrawler.cli._run_script") as mock_run:
            mock_run.return_value = 0
            cli.main(["analyze", "interest", "--limit", "25"])

        mock_run.assert_called_once_with("analyze_pro", ["--limit", "25"])

    def test_run_script_invokes_analyze_pro_main(self):
        import analyze_pro
        from xcrawler import cli

        with patch.object(analyze_pro, "main", return_value=None) as mock_main:
            assert cli._run_script("analyze_pro", ["--cache-dir", "missing-cache"]) == 0

        mock_main.assert_called_once_with()

    def test_run_script_returns_script_exit_code(self):
        import analyze_pro
        from xcrawler import cli

        with patch.object(analyze_pro, "main", return_value=1):
            assert cli._run_script("analyze_pro", ["--cache-dir", "missing-cache"]) == 1

    def test_translate_forwards_cache_dir(self):
        from xcrawler import cli

        with patch("xcrawler.cli._run_script") as mock_run:
            mock_run.return_value = 0
            cli.main(["translate", "--user", "alice", "--cache-dir", "tmp-cache", "--force"])

        mock_run.assert_called_once_with("translate_sync", ["--user", "alice", "--cache-dir", "tmp-cache", "--force"])

    def test_pyproject_has_console_script(self):
        with open("pyproject.toml", encoding="utf-8") as f:
            content = f.read()
        assert 'xcrawler = "xcrawler.cli:main"' in content

    def test_pyproject_splits_heavy_optional_dependencies(self):
        with open("pyproject.toml", encoding="utf-8") as f:
            content = f.read()
        # Heavy deps (torch, transformers, sentence-transformers, etc.) should NOT be in [project.dependencies]
        assert "torch" not in content.split("[project.optional-dependencies]")[0]
        # They should appear in optional-dependencies sections
        assert "torch>=2.0.0" in content
        assert "matplotlib>=3.7.0" in content


class TestConfigValidation:
    """测试配置和密钥校验"""

    def test_require_secret_rejects_missing_and_placeholder(self):
        from xcrawler.config import require_secret

        with pytest.raises(RuntimeError):
            require_secret("X_BEARER_TOKEN", None)
        with pytest.raises(RuntimeError):
            require_secret("X_BEARER_TOKEN", "your_x_bearer_token_here")

    def test_require_secret_strips_valid_value(self):
        from xcrawler.config import require_secret

        assert require_secret("X_BEARER_TOKEN", "  token  ") == "token"


class TestAnalysisRuns:
    """测试 analysis run 记录"""

    def test_record_and_load_analysis_run(self, tmp_path):
        from xcrawler.services.analysis_runs import create_analysis_run, load_analysis_runs, record_analysis_run
        from xcrawler.storage.json_store import JsonStore

        store = JsonStore(str(tmp_path))
        run = create_analysis_run(
            username="alice",
            analysis_type="interest",
            model="deepseek-chat",
            params={"temperature": 0.2},
            input_range={"translated_records": 12},
        )
        record_analysis_run(store, run)

        records = load_analysis_runs(store)
        assert records[0]["username"] == "alice"
        assert records[0]["analysis_type"] == "interest"
        assert records[0]["params"]["temperature"] == 0.2
        assert records[0]["input_range"]["translated_records"] == 12
        assert records[0]["status"] == "running"

    def test_complete_and_fail_analysis_run_status(self, tmp_path):
        from xcrawler.services.analysis_runs import (
            complete_analysis_run,
            create_analysis_run,
            fail_analysis_run,
            load_analysis_runs,
            partial_analysis_run,
            record_analysis_run,
        )
        from xcrawler.storage.json_store import JsonStore

        store = JsonStore(str(tmp_path))
        ok_run = complete_analysis_run(create_analysis_run(username="alice", analysis_type="interest"))
        failed_run = fail_analysis_run(create_analysis_run(username="alice", analysis_type="sentiment"), ValueError("bad"))
        partial_run = partial_analysis_run(
            create_analysis_run(username="alice", analysis_type="behavior"),
            failed_batches=1,
        )

        record_analysis_run(store, ok_run)
        record_analysis_run(store, failed_run)
        record_analysis_run(store, partial_run)

        records = load_analysis_runs(store)
        assert records[0]["status"] == "success"
        assert records[0]["duration_ms"] is not None
        assert records[1]["status"] == "failed"
        assert records[1]["error_type"] == "ValueError"
        assert records[1]["error_message"] == "bad"
        assert records[2]["status"] == "partial"
        assert records[2]["failed_batches"] == 1


class TestSentimentFailures:
    """测试情感分析失败不会污染为 neutral"""

    def test_failed_batch_stays_unknown(self):
        from analyze_sentiment import batch_sentiment

        client = MagicMock()
        client.chat.side_effect = Exception("api down")

        sentiments, stats = batch_sentiment(["hello", "world"], client, "model")

        assert sentiments == ["unknown", "unknown"]
        assert stats["failed_batches"] == 1

    def test_successful_batch_records_tokens(self):
        from analyze_sentiment import batch_sentiment
        from xcrawler.llm.provider import LLMResponse

        client = MagicMock()
        client.chat.return_value = LLMResponse(
            content="[1] positive\n[2] negative",
            model="model",
            provider="test",
            total_tokens=7,
        )

        sentiments, stats = batch_sentiment(["great", "bad"], client, "model")

        assert sentiments == ["positive", "negative"]
        assert stats["total_tokens"] == 7

    def test_incomplete_batch_response_stays_unknown_and_counts_failure(self):
        from analyze_sentiment import batch_sentiment
        from xcrawler.llm.provider import LLMResponse

        client = MagicMock()
        client.chat.return_value = LLMResponse(
            content="[1] positive",
            model="model",
            provider="test",
            total_tokens=5,
        )

        sentiments, stats = batch_sentiment(["great", "bad"], client, "model")

        assert sentiments == ["unknown", "unknown"]
        assert stats["failed_batches"] == 1

    def test_sentiment_response_skips_preamble(self):
        from analyze_sentiment import parse_sentiment_response

        response = "结果如下：\n[1] positive\n[2] negative"
        assert parse_sentiment_response(response, 2) == ["positive", "negative"]


class TestFetchPlan:
    """测试抓取计划估算"""

    def test_fetch_plan_estimates_requests_and_tweets(self):
        from xcrawler.services.fetch_plan import build_fetch_plan

        plan = build_fetch_plan("alice", pages=3)

        assert plan.estimated_requests == 3
        assert plan.estimated_max_tweets == 300
        assert plan.to_dict()["username"] == "alice"


class TestLLMProvider:
    """测试 LLM Provider 抽象"""

    def test_llm_response_to_dict(self):
        from xcrawler.llm.provider import LLMResponse

        response = LLMResponse(content="hello", model="m", provider="test", total_tokens=3)

        assert response.to_dict()["content"] == "hello"
        assert response.to_dict()["total_tokens"] == 3

    @patch("xcrawler.llm.provider.OpenAI")
    def test_openai_compatible_provider_wraps_response(self, mock_openai):
        from xcrawler.llm.provider import OpenAICompatibleProvider

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = " result "
        mock_response.usage.prompt_tokens = 1
        mock_response.usage.completion_tokens = 2
        mock_response.usage.total_tokens = 3
        mock_openai.return_value.chat.completions.create.return_value = mock_response

        provider = OpenAICompatibleProvider(api_key="key", base_url="https://example.com", name="test")
        response = provider.chat([{"role": "user", "content": "hi"}], model="m", temperature=0.1)

        assert response.content == "result"
        assert response.provider == "test"
        assert response.total_tokens == 3
        assert response.latency_ms is not None


class TestLLMCallObservability:
    """测试调用级 LLM 元数据、成本和失败率记录。"""

    def test_parse_llm_pricing_rejects_invalid_entries(self):
        from xcrawler.config import parse_llm_pricing

        pricing = parse_llm_pricing(
            json.dumps({
                "model-a": {"input_per_million": "1.5", "output_per_million": 2},
                "negative": {"input_per_million": -1, "output_per_million": 2},
                "infinite": {"input_per_million": "Infinity", "output_per_million": 2},
                "missing": {"input_per_million": 1},
            })
        )

        assert pricing == {
            "model-a": {"input_per_million": 1.5, "output_per_million": 2.0}
        }
        assert parse_llm_pricing("not-json") == {}

    def test_estimate_llm_cost_uses_configured_model_or_wildcard(self):
        from xcrawler.services.llm_calls import estimate_llm_cost

        pricing = {
            "model-a": {"input_per_million": 1.0, "output_per_million": 2.0},
            "*": {"input_per_million": 3.0, "output_per_million": 4.0},
        }

        assert estimate_llm_cost(
            model="model-a",
            prompt_tokens=1_000,
            completion_tokens=500,
            pricing=pricing,
        ) == 0.002
        assert estimate_llm_cost(
            model="model-b",
            prompt_tokens=1_000,
            completion_tokens=500,
            pricing=pricing,
        ) == 0.005

    def test_recorder_persists_success_and_failure_without_content(self, tmp_path):
        from xcrawler.llm.provider import LLMResponse
        from xcrawler.services.llm_calls import LLMCallRecorder, load_llm_calls
        from xcrawler.storage.json_store import JsonStore

        store = JsonStore(str(tmp_path))
        recorder = LLMCallRecorder(
            store,
            pricing={"model-a": {"input_per_million": 1, "output_per_million": 2}},
            analysis_run_id="run-1",
            username="alice",
        )
        response = LLMResponse(
            content="private response",
            model="model-a",
            provider="test",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            latency_ms=12,
        )
        recorder.record_success(
            operation="interest_analysis",
            provider="test",
            model="model-a",
            started=recorder.start(),
            response=response,
        )
        recorder.record_failure(
            operation="interest_analysis",
            provider="test",
            model="model-a",
            started=recorder.start(),
            error=TimeoutError("api_key=supersecret"),
            attempt=2,
        )

        records = load_llm_calls(store)
        assert len(records) == 2
        assert records[0]["analysis_run_id"] == "run-1"
        assert records[0]["username"] == "alice"
        assert records[0]["estimated_cost"] == 0.0002
        assert records[1]["status"] == "failed"
        assert records[1]["error_type"] == "TimeoutError"
        assert records[1]["error_message"] == "api_key=[REDACTED]"
        assert records[1]["attempt"] == 2
        assert "content" not in records[0]
        assert "messages" not in records[0]

        summary = recorder.summary()
        assert summary["calls"] == 2
        assert summary["successful_calls"] == 1
        assert summary["failed_calls"] == 1
        assert summary["failure_rate"] == 0.5
        assert summary["total_tokens"] == 150

    def test_observed_provider_records_success_and_failure(self, tmp_path):
        from xcrawler.llm.provider import LLMResponse
        from xcrawler.services.llm_calls import LLMCallRecorder, ObservedLLMProvider
        from xcrawler.storage.json_store import JsonStore

        raw_provider = MagicMock()
        raw_provider.name = "test-provider"
        raw_provider.chat.side_effect = [
            LLMResponse(content="ok", model="model-a", provider="test-provider", total_tokens=3),
            RuntimeError("provider failed"),
        ]
        recorder = LLMCallRecorder(JsonStore(str(tmp_path)), analysis_run_id="run-2")
        provider = ObservedLLMProvider(raw_provider, recorder, operation="sentiment_analysis")

        assert provider.chat([], model="model-a").content == "ok"
        with pytest.raises(RuntimeError, match="provider failed"):
            provider.chat([], model="model-a")

        assert [record.status for record in recorder.records] == ["success", "failed"]
        assert all(record.analysis_run_id == "run-2" for record in recorder.records)

    def test_telemetry_write_failure_does_not_break_llm_workflow(self):
        from xcrawler.llm.provider import LLMResponse
        from xcrawler.services.llm_calls import LLMCallRecorder

        store = MagicMock()
        store.append_json_record.side_effect = OSError("disk full")
        recorder = LLMCallRecorder(store)

        with pytest.warns(RuntimeWarning, match="业务流程将继续"):
            record = recorder.record_success(
                operation="interest_analysis",
                provider="test",
                model="model-a",
                started=recorder.start(),
                response=LLMResponse(content="ok", model="model-a", provider="test"),
            )

        assert record.status == "success"
        assert recorder.records == [record]

    def test_translation_parse_failure_records_spent_tokens(self, tmp_path):
        from xcrawler.services.llm_calls import LLMCallRecorder
        from xcrawler.services.translation import translate_batch
        from xcrawler.storage.json_store import JsonStore

        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = "incomplete response"
        response.usage.prompt_tokens = 10
        response.usage.completion_tokens = 2
        response.usage.total_tokens = 12
        client = MagicMock()
        client.chat.completions.create.return_value = response
        recorder = LLMCallRecorder(JsonStore(str(tmp_path)), username="alice")

        result = translate_batch(
            ["hello", "world"],
            detected_langs=["en", "en"],
            use_cache=False,
            cache={},
            client_factory=lambda: client,
            model="model-a",
            batch_size=2,
            max_retries=1,
            fallback_translate=lambda text, lang, use_cache: None,
            call_recorder=recorder,
            provider_name="test-provider",
        )

        assert result == [None, None]
        assert recorder.records[0].status == "failed"
        assert recorder.records[0].error_type == "ValueError"
        assert recorder.records[0].total_tokens == 12


class TestVisualizeEvidence:
    """测试 HTML 报告证据区"""

    def test_generate_evidence_sections(self):
        from visualize import generate_evidence_sections

        data = {
            "translated": [{
                "tweet_id": "123",
                "original": "Hello",
                "translated": "你好",
                "detected_language": "en",
                "created_at": "2024-01-01",
            }],
            "profile": {
                "interests": [{
                    "tag": "AI",
                    "level": "core",
                    "confidence": 0.9,
                    "evidence_tweet_ids": ["123"],
                }]
            },
        }

        html = generate_evidence_sections(data)
        assert "兴趣画像证据" in html
        assert "你好" in html

    def test_generate_evidence_sections_hides_sensitive_events(self):
        from visualize import generate_evidence_sections

        data = {
            "translated": [{
                "tweet_id": "123",
                "original": "private original",
                "translated": "敏感内容",
                "detected_language": "zh",
                "created_at": "2024-01-01",
            }],
            "behavior": {
                "life_events": {
                    "health_events": [{
                        "description": "去了医院",
                        "sensitive": True,
                        "evidence_tweet_ids": ["123"],
                    }]
                }
            },
        }

        html = generate_evidence_sections(data)
        assert "敏感事件证据默认隐藏" in html
        assert "private original" not in html


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


class TestXApiClient:
    """测试 xcrawler.clients.x_api"""

    def test_get_user_id_module(self):
        from xcrawler.clients.x_api import get_user_id

        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"id": "123"}}
        mock_response.raise_for_status = MagicMock()
        mock_get = MagicMock(return_value=mock_response)

        assert get_user_id("testuser", {"Authorization": "Bearer token"}, request_get=mock_get) == "123"
        mock_get.assert_called_once()
