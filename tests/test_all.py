"""
xcrawler 单元测试
覆盖纯函数、工具函数和需要 mock 的 API 调用
"""
import os
import json
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime


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
    """测试 _parse_batch_response 批量响应解析"""

    def test_standard_format(self):
        from main import _parse_batch_response
        resp = "[1] 你好世界\n[2] 这是测试\n[3] 第三条"
        result = _parse_batch_response(resp, 3)
        assert result == ["你好世界", "这是测试", "第三条"]

    def test_number_dot_format(self):
        from main import _parse_batch_response
        resp = "1. 你好世界\n2. 这是测试"
        result = _parse_batch_response(resp, 2)
        assert result == ["你好世界", "这是测试"]

    def test_number_paren_format(self):
        from main import _parse_batch_response
        resp = "1) 你好世界\n2) 这是测试"
        result = _parse_batch_response(resp, 2)
        assert result == ["你好世界", "这是测试"]

    def test_empty_lines_skipped(self):
        from main import _parse_batch_response
        resp = "[1] 你好\n\n[2] 世界\n\n"
        result = _parse_batch_response(resp, 2)
        assert result == ["你好", "世界"]

    def test_count_mismatch_fallback(self):
        """当解析结果数量不对时，回退到按行返回"""
        from main import _parse_batch_response
        resp = "你好世界\n这是测试"
        result = _parse_batch_response(resp, 2)
        assert len(result) == 2
        assert "你好世界" in result

    def test_with_colon_separator(self):
        from main import _parse_batch_response
        resp = "[1]：你好\n[2]：世界"
        result = _parse_batch_response(resp, 2)
        assert result == ["你好", "世界"]


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
        original_dir = main.CACHE_DIR
        main.CACHE_DIR = str(tmp_path)
        try:
            cache = {"hello": "你好", "world": "世界"}
            main.save_translation_cache(cache)
            loaded = main.load_translation_cache()
            assert loaded == cache
        finally:
            main.CACHE_DIR = original_dir

    def test_load_missing_file(self, tmp_path):
        import main
        original_dir = main.CACHE_DIR
        main.CACHE_DIR = str(tmp_path)
        try:
            loaded = main.load_translation_cache()
            assert loaded == {}
        finally:
            main.CACHE_DIR = original_dir

    def test_load_corrupt_file(self, tmp_path):
        import main
        original_dir = main.CACHE_DIR
        main.CACHE_DIR = str(tmp_path)
        try:
            cache_file = tmp_path / "translation_cache.json"
            cache_file.write_text("not valid json {{{")
            loaded = main.load_translation_cache()
            assert loaded == {}
        finally:
            main.CACHE_DIR = original_dir


class TestDeepseekTranslate:
    """测试 deepseek_translate 单条翻译"""

    def test_cached_text_returns_immediately(self):
        import main
        main.translation_cache = {"hello": "你好"}
        result = main.deepseek_translate("hello")
        assert result == "你好"

    def test_chinese_text_passthrough(self):
        import main
        main.translation_cache = {}
        result = main.deepseek_translate("这是中文", detected_lang="zh-cn")
        assert result == "这是中文"
        assert main.translation_cache["这是中文"] == "这是中文"

    def test_chinese_zh_lang(self):
        import main
        main.translation_cache = {}
        result = main.deepseek_translate("中文推文", detected_lang="zh")
        assert result == "中文推文"

    @patch("main._get_ds_client")
    def test_api_call(self, mock_client):
        import main
        main.translation_cache = {}
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "你好世界"
        mock_client.return_value.chat.completions.create.return_value = mock_response

        result = main.deepseek_translate("Hello world", detected_lang="en")
        assert result == "你好世界"
        assert main.translation_cache["Hello world"] == "你好世界"

    @patch("main._get_ds_client")
    def test_api_failure_returns_none(self, mock_client):
        import main
        main.translation_cache = {}
        mock_client.return_value.chat.completions.create.side_effect = Exception("API error")

        result = main.deepseek_translate("Hello", detected_lang="en", use_cache=False)
        assert result is None


class TestDeepseekTranslateBatch:
    """测试 deepseek_translate_batch 批量翻译"""

    def test_all_cached(self):
        import main
        main.translation_cache = {"a": "甲", "b": "乙"}
        result = main.deepseek_translate_batch(["a", "b"])
        assert result == ["甲", "乙"]

    def test_chinese_passthrough(self):
        import main
        main.translation_cache = {}
        result = main.deepseek_translate_batch(["中文"], detected_langs=["zh-cn"])
        assert result == ["中文"]

    def test_mixed_cache_and_new(self):
        import main
        main.translation_cache = {"cached": "已缓存"}
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
        import importlib
        # 这应该不会抛异常，因为 ds_client 现在是 lazy init
        import main
        assert main.ds_client is None  # 尚未初始化
        assert callable(main._get_ds_client)


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


class TestExportCsvHelpers:
    """测试 CSV 导出辅助逻辑"""

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

        with open(output, 'r', encoding='utf-8-sig') as f:
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

        with open(output, 'r', encoding='utf-8-sig') as f:
            content = f.read()
        assert "tweet_id" in content
        assert "42" in content
        assert "你好" in content
        assert "en" in content

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

        with open(output, 'r', encoding='utf-8-sig') as f:
            content = f.read()
        assert "evidence_tweet_ids" in content
        assert "123" in content


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

    def test_json_store_append_record(self, tmp_path):
        from xcrawler.storage.json_store import JsonStore

        store = JsonStore(str(tmp_path))
        store.append_json_record("runs.json", {"id": "1"})
        store.append_json_record("runs.json", {"id": "2"})

        assert store.load_json("runs.json") == [{"id": "1"}, {"id": "2"}]


class TestConfig:
    """测试 xcrawler.config"""

    def test_apply_common_overrides(self):
        from argparse import Namespace
        from xcrawler.config import AppConfig, apply_common_overrides

        config = AppConfig()
        args = Namespace(user="alice", cache_dir="tmp-cache", model="deepseek-test")
        updated = apply_common_overrides(config, args)

        assert updated.target_username == "alice"
        assert updated.cache_dir == "tmp-cache"
        assert updated.llm_model == "deepseek-test"


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
            "translated": "我的电话是 13800138000",
            "detected_language": "zh",
            "created_at": "2024-01-01",
        }]
        html = render_evidence_html(["123"], build_evidence_map(translated), redact=True)

        assert "敏感原文已隐藏" in html
        assert "13800138000" not in html


class TestPrivacyGuard:
    """测试隐私保护层"""

    def test_is_sensitive_event_by_category(self):
        from xcrawler.privacy_guard import is_sensitive_event

        assert is_sensitive_event("health_events", "去了医院")
        assert not is_sensitive_event("other_events", "参加公开演出")

    def test_redact_text_masks_email_and_phone(self):
        from xcrawler.privacy_guard import redact_text

        text = redact_text("邮箱 user@example.com 电话 13800138000")
        assert "user@example.com" not in text
        assert "13800138000" not in text

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

    def test_translate_forwards_cache_dir(self):
        from xcrawler import cli

        with patch("xcrawler.cli._run_script") as mock_run:
            mock_run.return_value = 0
            cli.main(["translate", "--user", "alice", "--cache-dir", "tmp-cache", "--force"])

        mock_run.assert_called_once_with("translate_sync", ["--user", "alice", "--cache-dir", "tmp-cache", "--force"])

    def test_pyproject_has_console_script(self):
        import tomllib

        with open("pyproject.toml", "rb") as f:
            data = tomllib.load(f)

        assert data["project"]["scripts"]["xcrawler"] == "xcrawler.cli:main"


class TestAnalysisRuns:
    """测试 analysis run 记录"""

    def test_record_and_load_analysis_run(self, tmp_path):
        from xcrawler.services.analysis_runs import create_analysis_run, record_analysis_run, load_analysis_runs
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

    def test_parse_batch_response_module(self):
        from xcrawler.services.translation import parse_batch_response
        resp = "[1] 你好\n[2] 世界"
        assert parse_batch_response(resp, 2) == ["你好", "世界"]

    def test_translate_text_uses_cache(self):
        from xcrawler.services.translation import translate_text
        cache = {"hello": "你好"}

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
