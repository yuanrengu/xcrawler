"""Tests grouped by responsibility from the former monolithic suite."""

import csv
import json
from contextlib import closing
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


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

class TestVisualizeMain:
    """测试可视化主流程的依赖、退出码和输出格式。"""

    @staticmethod
    def _args(tmp_path, output_format="png"):
        return SimpleNamespace(
            user="alice",
            cache_dir=str(tmp_path),
            output=str(tmp_path / "charts"),
            format=output_format,
            include_sensitive_events=False,
        )

    def test_missing_raw_data_returns_failure(self, tmp_path, monkeypatch):
        import visualize

        monkeypatch.setattr(visualize, "parse_args", lambda: self._args(tmp_path))
        monkeypatch.setattr(visualize, "load_data", lambda username, cache_dir: {"raw": None})

        assert visualize.main() == 1

    def test_missing_matplotlib_returns_failure(self, tmp_path, monkeypatch, capsys):
        import visualize

        monkeypatch.setattr(visualize, "parse_args", lambda: self._args(tmp_path))
        monkeypatch.setattr(visualize, "load_data", lambda username, cache_dir: {"raw": [{"id": "1"}]})
        monkeypatch.setattr(visualize, "MATPLOTLIB_AVAILABLE", False)

        assert visualize.main() == 1
        assert "python3 -m pip install -e '.[viz]'" in capsys.readouterr().out

    @pytest.mark.parametrize("output_format, expected_html_calls", [("png", 0), ("html", 1)])
    def test_format_controls_html_report(self, tmp_path, monkeypatch, output_format, expected_html_calls):
        import visualize

        monkeypatch.setattr(visualize, "parse_args", lambda: self._args(tmp_path, output_format))
        monkeypatch.setattr(visualize, "load_data", lambda username, cache_dir: {
            "raw": [{"id": "1"}],
            "translated": [],
            "behavior": {},
            "profile": {},
        })
        monkeypatch.setattr(visualize, "MATPLOTLIB_AVAILABLE", True)
        monkeypatch.setattr(visualize, "chart_hourly_heatmap", lambda *args: "hourly.png")
        monkeypatch.setattr(visualize, "chart_weekday_bar", lambda *args: "weekday.png")
        generate_html = MagicMock(return_value="report.html")
        monkeypatch.setattr(visualize, "generate_html_report", generate_html)

        assert visualize.main() == 0
        assert generate_html.call_count == expected_html_calls

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

class TestAnalyzeNetworkMain:
    """测试网络分析的失败退出语义。"""

    @staticmethod
    def _args(tmp_path):
        return SimpleNamespace(
            user="alice",
            cache_dir=str(tmp_path),
            output=str(tmp_path / "charts"),
            top=20,
            storage_backend="json",
            sqlite_path=None,
        )

    def test_missing_raw_data_returns_failure(self, tmp_path, monkeypatch):
        import analyze_network

        monkeypatch.setattr(analyze_network, "parse_args", lambda: self._args(tmp_path))

        assert analyze_network.main() == 1

    def test_missing_matplotlib_returns_failure_before_run_creation(self, tmp_path, monkeypatch, capsys):
        import analyze_network

        (tmp_path / "alice_raw_tweets.json").write_text('[{"id": "1"}]', encoding="utf-8")
        monkeypatch.setattr(analyze_network, "parse_args", lambda: self._args(tmp_path))
        monkeypatch.setattr(analyze_network, "MATPLOTLIB_AVAILABLE", False)
        create_run = MagicMock()
        monkeypatch.setattr(analyze_network, "create_analysis_run", create_run)

        assert analyze_network.main() == 1
        create_run.assert_not_called()
        assert "python3 -m pip install -e '.[viz]'" in capsys.readouterr().out

    def test_chart_failure_is_recorded(self, tmp_path, monkeypatch):
        import analyze_network

        (tmp_path / "alice_raw_tweets.json").write_text(
            '[{"id":"1","text":"#python","entities":{}}]', encoding="utf-8"
        )
        monkeypatch.setattr(analyze_network, "parse_args", lambda: self._args(tmp_path))
        monkeypatch.setattr(analyze_network, "MATPLOTLIB_AVAILABLE", True)
        monkeypatch.setattr(analyze_network, "chart_hashtag_bar", MagicMock(side_effect=OSError("disk full")))

        assert analyze_network.main() == 1
        runs = json.loads((tmp_path / "analysis_runs.json").read_text(encoding="utf-8"))
        assert runs[-1]["status"] == "failed"
        assert runs[-1]["error_type"] == "OSError"

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

    def test_main_ml_preflight_checks_both_optional_modules(self):
        import main

        with patch("main.modules_available", return_value=False) as available:
            assert main.ml_analysis_available() is False

        available.assert_called_once_with("sentence_transformers", "sklearn")

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

    def test_missing_matplotlib_returns_failure_before_provider_creation(self, tmp_path, monkeypatch, capsys):
        import analyze_sentiment

        records = [
            {
                "tweet_id": str(index),
                "original": f"original {index}",
                "translated": f"translated {index}",
                "detected_language": "en",
                "created_at": "2024-01-01T00:00:00Z",
            }
            for index in range(5)
        ]
        (tmp_path / "alice_translated.json").write_text(json.dumps(records), encoding="utf-8")
        monkeypatch.setattr(analyze_sentiment, "parse_args", lambda: SimpleNamespace(
            user="alice",
            cache_dir=str(tmp_path),
            output=str(tmp_path / "charts"),
            top=10,
            storage_backend="json",
            sqlite_path=None,
        ))
        monkeypatch.setattr(analyze_sentiment, "MATPLOTLIB_AVAILABLE", False)
        create_provider = MagicMock()
        monkeypatch.setattr(analyze_sentiment, "create_provider", create_provider)

        assert analyze_sentiment.main() == 1
        create_provider.assert_not_called()
        assert "python3 -m pip install -e '.[viz]'" in capsys.readouterr().out

    def test_provider_initialization_failure_is_recorded(self, tmp_path, monkeypatch):
        import analyze_sentiment

        records = [
            {
                "tweet_id": str(index),
                "original": f"original {index}",
                "translated": f"translated {index}",
                "detected_language": "en",
                "created_at": "2024-01-01T00:00:00Z",
            }
            for index in range(5)
        ]
        (tmp_path / "alice_translated.json").write_text(json.dumps(records), encoding="utf-8")
        monkeypatch.setattr(analyze_sentiment, "parse_args", lambda: SimpleNamespace(
            user="alice",
            cache_dir=str(tmp_path),
            output=str(tmp_path / "charts"),
            top=10,
            storage_backend="json",
            sqlite_path=None,
        ))
        monkeypatch.setattr(analyze_sentiment, "MATPLOTLIB_AVAILABLE", True)
        monkeypatch.setattr(analyze_sentiment, "create_provider", MagicMock(side_effect=RuntimeError("missing key")))

        assert analyze_sentiment.main() == 1
        runs = json.loads((tmp_path / "analysis_runs.json").read_text(encoding="utf-8"))
        assert runs[-1]["status"] == "failed"
        assert runs[-1]["error_type"] == "RuntimeError"

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
