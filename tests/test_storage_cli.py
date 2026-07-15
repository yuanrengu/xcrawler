"""Tests grouped by responsibility from the former monolithic suite."""

import csv
import json
from contextlib import closing
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


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

    def test_atomic_json_bundle_rolls_back_when_second_replace_fails(self, tmp_path, monkeypatch):
        from xcrawler.storage import json_store

        raw_path = tmp_path / "raw.json"
        translated_path = tmp_path / "translated.json"
        raw_path.write_text('{"version":"old-raw"}', encoding="utf-8")
        translated_path.write_text('{"version":"old-translated"}', encoding="utf-8")
        real_replace = json_store.os.replace

        def fail_second_pending_replace(source, destination):
            if destination == str(translated_path) and str(source).endswith(".pending"):
                raise OSError("disk full")
            return real_replace(source, destination)

        monkeypatch.setattr(json_store.os, "replace", fail_second_pending_replace)

        with pytest.raises(OSError, match="disk full"):
            json_store.replace_json_files_atomically({
                str(raw_path): {"version": "new-raw"},
                str(translated_path): {"version": "new-translated"},
            })

        assert json.loads(raw_path.read_text(encoding="utf-8")) == {"version": "old-raw"}
        assert json.loads(translated_path.read_text(encoding="utf-8")) == {"version": "old-translated"}
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

class TestSQLiteStore:
    """测试可选 SQLite 元数据存储。"""

    def test_factory_keeps_json_default_and_builds_sqlite(self, tmp_path):
        from xcrawler.storage.factory import create_store
        from xcrawler.storage.json_store import JsonStore
        from xcrawler.storage.sqlite_store import SQLiteStore

        json_store = create_store(str(tmp_path))
        sqlite_store = create_store(str(tmp_path), backend="SQLITE")

        assert isinstance(json_store, JsonStore)
        assert isinstance(sqlite_store, SQLiteStore)
        assert sqlite_store.path == str(tmp_path / "xcrawler.db")
        assert (tmp_path / "xcrawler.db").exists()

    def test_generic_json_contract_is_compatible(self, tmp_path):
        from xcrawler.storage.sqlite_store import SQLiteStore

        store = SQLiteStore(str(tmp_path / "metadata.db"))
        assert store.load_json("missing.json", default={"missing": True}) == {"missing": True}

        store.save_json("settings.json", {"language": "zh"})
        assert store.load_json("settings.json") == {"language": "zh"}

        store.append_json_record("events.json", {"id": "1"})
        store.append_json_record("events.json", {"id": "2"})
        assert store.load_json("events.json") == [{"id": "1"}, {"id": "2"}]

    def test_analysis_runs_are_structured_and_queryable(self, tmp_path):
        from xcrawler.services.analysis_runs import create_analysis_run, load_analysis_runs, record_analysis_run
        from xcrawler.storage.sqlite_store import SQLiteStore

        store = SQLiteStore(str(tmp_path / "metadata.db"))
        first = create_analysis_run(username="alice", analysis_type="interest", model="model-a")
        second = create_analysis_run(username="bob", analysis_type="sentiment", model="model-b")
        record_analysis_run(store, first)
        record_analysis_run(store, second)

        assert [record["id"] for record in load_analysis_runs(store)] == [first.id, second.id]
        assert store.query_analysis_runs(username="alice")[0]["id"] == first.id
        assert store.query_analysis_runs(analysis_type="sentiment", limit=1)[0]["id"] == second.id
        with pytest.raises(ValueError, match="limit"):
            store.query_analysis_runs(limit=0)

    def test_llm_call_can_precede_run_and_remains_queryable(self, tmp_path):
        from xcrawler.llm.provider import LLMResponse
        from xcrawler.services.analysis_runs import create_analysis_run, record_analysis_run
        from xcrawler.services.llm_calls import LLMCallRecorder, summarize_llm_calls
        from xcrawler.storage.sqlite_store import SQLiteStore

        store = SQLiteStore(str(tmp_path / "metadata.db"))
        run = create_analysis_run(username="alice", analysis_type="interest", model="model-a")
        recorder = LLMCallRecorder(store, analysis_run_id=run.id, username="alice")
        recorder.record_success(
            operation="interest_analysis",
            provider="test",
            model="model-a",
            started=recorder.start(),
            response=LLMResponse(
                content="private response",
                model="model-a",
                provider="test",
                prompt_tokens=7,
                completion_tokens=3,
                total_tokens=10,
            ),
        )
        record_analysis_run(store, run)

        calls = store.query_llm_calls(analysis_run_id=run.id, status="success")
        assert len(calls) == 1
        assert calls[0]["total_tokens"] == 10
        assert summarize_llm_calls(calls)["total_tokens"] == 10
        assert store.query_analysis_runs(username="alice")[0]["id"] == run.id

    def test_replace_records_rolls_back_on_invalid_input(self, tmp_path):
        from xcrawler.storage.sqlite_store import ANALYSIS_RUNS_KEY, SQLiteStore, SQLiteStoreError

        store = SQLiteStore(str(tmp_path / "metadata.db"))
        original = [{"id": "run-1", "username": "alice"}]
        store.save_json(ANALYSIS_RUNS_KEY, original)

        with pytest.raises(SQLiteStoreError):
            store.save_json(ANALYSIS_RUNS_KEY, [{"id": "run-2"}, {"username": "missing-id"}])

        assert store.load_json(ANALYSIS_RUNS_KEY) == original

    def test_file_database_enables_wal_and_expected_indexes(self, tmp_path):
        import sqlite3

        from xcrawler.storage.sqlite_store import SQLiteStore

        path = tmp_path / "nested" / "metadata.db"
        SQLiteStore(str(path))

        with closing(sqlite3.connect(path)) as connection:
            journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
            indexes = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index' AND name LIKE 'idx_%'"
                )
            }

        assert journal_mode == "wal"
        assert "idx_analysis_runs_username_started" in indexes
        assert "idx_llm_calls_run_started" in indexes

    def test_unknown_schema_version_is_not_silently_overwritten(self, tmp_path):
        import sqlite3

        from xcrawler.storage.sqlite_store import SQLiteStore, SQLiteStoreError

        path = tmp_path / "future.db"
        with closing(sqlite3.connect(path)) as connection:
            connection.execute(
                "CREATE TABLE store_metadata (metadata_key TEXT PRIMARY KEY, metadata_value TEXT NOT NULL)"
            )
            connection.execute("INSERT INTO store_metadata VALUES ('schema_version', '99')")
            connection.commit()

        with pytest.raises(SQLiteStoreError, match="schema version"):
            SQLiteStore(str(path))

        with closing(sqlite3.connect(path)) as connection:
            version = connection.execute(
                "SELECT metadata_value FROM store_metadata WHERE metadata_key = 'schema_version'"
            ).fetchone()[0]
            created_tables = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
        assert version == "99"
        assert created_tables == {"store_metadata"}

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

    def test_fetch_forwards_explicit_replace(self):
        from xcrawler import cli

        with patch("xcrawler.cli._run_script") as mock_run:
            mock_run.return_value = 0
            cli.main(["fetch", "--replace"])

        mock_run.assert_called_once_with("main", ["--replace"])

    def test_fetch_forwards_analysis_limit(self):
        from xcrawler import cli

        with patch("xcrawler.cli._run_script") as mock_run:
            mock_run.return_value = 0
            cli.main(["fetch", "--analysis-limit", "50"])

        mock_run.assert_called_once_with("main", ["--analysis-limit", "50"])

    def test_fetch_forwards_sqlite_options(self):
        from xcrawler import cli

        with patch("xcrawler.cli._run_script") as mock_run:
            mock_run.return_value = 0
            cli.main(["fetch", "--storage", "sqlite", "--sqlite-path", "state/xcrawler.db"])

        mock_run.assert_called_once_with(
            "main",
            ["--storage", "sqlite", "--sqlite-path", "state/xcrawler.db"],
        )

    def test_fetch_rejects_zero_pages(self):
        from xcrawler import cli

        with pytest.raises(SystemExit) as exc:
            cli.main(["fetch", "--pages", "0"])

        assert exc.value.code == 2

    @pytest.mark.parametrize("username", ["../escape", "bad/name", "name-with-dash", "a" * 16])
    def test_cli_rejects_invalid_x_username(self, username):
        from xcrawler.cli import main

        with pytest.raises(SystemExit) as exc:
            main(["report", "--user", username])

        assert exc.value.code == 2

    def test_cli_normalizes_leading_at_in_username(self):
        from xcrawler import cli

        with patch("xcrawler.cli._run_script") as mock_run:
            mock_run.return_value = 0
            cli.main(["report", "--user", "@alice"])

        mock_run.assert_called_once_with("visualize", ["--user", "alice"])

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

    def test_report_forwards_explicit_format(self):
        from xcrawler import cli

        with patch("xcrawler.cli._run_script") as mock_run:
            mock_run.return_value = 0
            cli.main(["report", "--format", "png"])

        mock_run.assert_called_once_with("visualize", ["--format", "png"])

    def test_demo_forwards_output(self):
        from xcrawler import cli

        with patch("xcrawler.cli._run_script") as mock_run:
            mock_run.return_value = 0
            cli.main(["demo", "--output", "sample-output"])

        mock_run.assert_called_once_with("xcrawler.demo", ["--output", "sample-output"])

    def test_demo_generates_local_report_without_external_calls(self, tmp_path):
        from xcrawler.demo import generate_demo

        report = generate_demo(str(tmp_path))

        assert report == str(tmp_path / "xcrawler_demo_report.html")
        assert (tmp_path / "xcrawler_demo_raw_tweets.json").exists()
        assert "Trustworthy AI" in (tmp_path / "xcrawler_demo_report.html").read_text(encoding="utf-8")

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

class TestPathValidation:
    """测试用户名派生路径不能逃逸缓存目录。"""

    def test_cache_path_accepts_valid_username(self, tmp_path):
        from xcrawler.paths import cache_path

        assert cache_path(str(tmp_path), "alice_1", "raw.json") == str(tmp_path / "alice_1_raw.json")

    @pytest.mark.parametrize("username", ["../escape", "bad/name", "a" * 16])
    def test_cache_path_rejects_invalid_username(self, tmp_path, username):
        from xcrawler.paths import cache_path

        with pytest.raises(ValueError, match="X 用户名"):
            cache_path(str(tmp_path), username, "raw.json")

    @pytest.mark.parametrize("suffix", ["", "../raw.json", "/tmp/raw.json"])
    def test_cache_path_rejects_unsafe_suffix(self, tmp_path, suffix):
        from xcrawler.paths import cache_path

        with pytest.raises(ValueError, match="文件后缀"):
            cache_path(str(tmp_path), "alice", suffix)

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

    def test_load_config_reads_storage_settings(self, monkeypatch):
        from xcrawler.config import load_config

        monkeypatch.setenv("STORAGE_BACKEND", "SQLITE")
        monkeypatch.setenv("SQLITE_PATH", "state/xcrawler.db")

        config = load_config()

        assert config.storage_backend == "sqlite"
        assert config.sqlite_path == "state/xcrawler.db"

    @pytest.mark.parametrize("name,value", [
        ("TARGET_DATE", "2024/01/01"),
        ("TIMEZONE_OFFSET", "tomorrow"),
        ("TIMEZONE_OFFSET", "25"),
        ("STORAGE_BACKEND", "postgres"),
        ("TARGET_USERNAME", "../escape"),
    ])
    def test_load_config_rejects_invalid_environment_values(self, monkeypatch, name, value):
        from xcrawler.config import ConfigError, load_config

        monkeypatch.setenv(name, value)

        with pytest.raises(ConfigError):
            load_config()

    def test_load_config_reads_cache_dir(self, monkeypatch):
        from xcrawler.config import load_config

        monkeypatch.setenv("CACHE_DIR", "state/cache")

        assert load_config().cache_dir == "state/cache"
