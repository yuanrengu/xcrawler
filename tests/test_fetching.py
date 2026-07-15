"""Tests grouped by responsibility from the former monolithic suite."""

import csv
import json
from contextlib import closing
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


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

    def test_merge_translations_retains_history_and_updates_matching_id(self):
        from xcrawler.services.tweets import merge_translated_tweets

        existing = [
            {"tweet_id": "1", "translated": "old", "created_at": "2024-01-01T00:00:00Z"},
            {"tweet_id": "0", "translated": "history", "created_at": "2023-01-01T00:00:00Z"},
        ]
        new = [{"tweet_id": "1", "translated": "new", "created_at": "2024-01-01T00:00:00Z"}]

        merged = merge_translated_tweets(existing, new)

        assert [item["tweet_id"] for item in merged] == ["1", "0"]
        assert merged[0]["translated"] == "new"

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
            fetch_more_history.FetchBatchResult(
                [{"id": "3", "text": "new tweet", "created_at": "2025-01-03T00:00:00Z"}],
                False, 1, 1, 0, "no_next_token", True, False,
            ),
            fetch_more_history.FetchBatchResult(
                [{"id": "0", "text": "older history", "created_at": "2024-12-31T00:00:00Z"}],
                False, 1, 1, 0, "no_next_token", True, False,
            ),
        ])
        monkeypatch.setattr(fetch_more_history, "fetch_tweets_generic", fetch_calls)

        assert fetch_more_history.main() == 0

        saved = json.loads(raw_file.read_text(encoding="utf-8"))
        assert [tweet["id"] for tweet in saved] == ["3", "2", "1", "0"]
        assert fetch_calls.call_count == 2
        status = json.loads((tmp_path / f"{username}_fetch_status.json").read_text(encoding="utf-8"))
        assert status["status"] == "success"
        assert status["complete"] is True
        assert status["has_more"] is False
        assert status["forward_complete"] is True
        assert status["backward_complete"] is True

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

            result = fetch_more_history.fetch_tweets_generic(
                "user-id",
                {"Authorization": "Bearer test-token"},
                stop_date=datetime(2024, 1, 1),
                max_pages_limit=1,
            )

            assert result.reached_target is True
            assert result.data_pages == 1
            assert result.requests_used == 1
            assert result.stop_reason == "target_date"
            assert result.complete is True
            assert result.has_more is False
            assert [tweet["id"] for tweet in result.tweets] == ["2"]
        finally:
            fetch_more_history.REQUEST_INTERVAL = old_interval

    @patch("fetch_more_history.time.sleep")
    @patch("fetch_more_history.requests.get")
    def test_network_failure_raises_after_retries(self, mock_get, mock_sleep):
        import requests

        import fetch_more_history

        mock_get.side_effect = requests.exceptions.Timeout("timed out")

        with pytest.raises(fetch_more_history.FetchError, match="第 1 页网络错误") as exc_info:
            fetch_more_history.fetch_tweets_generic(
                "user-id",
                {},
                max_pages_limit=1,
                max_retries=2,
            )

        assert mock_get.call_count == 2
        mock_sleep.assert_called_once_with(1)
        assert exc_info.value.requests_used == 2
        assert exc_info.value.retries == 1
        assert exc_info.value.stop_reason == "network_error"

    @patch("fetch_more_history.time.sleep")
    @patch("fetch_more_history.requests.get")
    def test_rate_limit_reset_in_past_retries_without_negative_sleep(self, mock_get, mock_sleep):
        import fetch_more_history

        limited = MagicMock(status_code=429, headers={"x-rate-limit-reset": "0"})
        success = MagicMock(status_code=200, headers={})
        success.raise_for_status = MagicMock()
        success.json.return_value = {"data": [], "meta": {}}
        mock_get.side_effect = [limited, success]

        result = fetch_more_history.fetch_tweets_generic(
            "user-id",
            {},
            max_pages_limit=1,
            max_retries=2,
        )

        assert result.tweets == []
        assert result.requests_used == 2
        assert result.retries == 1
        mock_sleep.assert_called_once_with(0)

    @patch("fetch_more_history.time.sleep")
    @patch("fetch_more_history.requests.get")
    def test_rate_limit_without_reset_header_uses_bounded_backoff(self, mock_get, mock_sleep):
        import fetch_more_history

        limited = MagicMock(status_code=429, headers={})
        success = MagicMock(status_code=200, headers={})
        success.raise_for_status = MagicMock()
        success.json.return_value = {"data": [], "meta": {}}
        mock_get.side_effect = [limited, success]

        result = fetch_more_history.fetch_tweets_generic(
            "user-id", {}, max_pages_limit=1, max_retries=2
        )
        assert result.tweets == []
        assert result.requests_used == 2
        assert result.retries == 1
        mock_sleep.assert_called_once_with(1)

    @patch("fetch_more_history.time.sleep")
    @patch("fetch_more_history.requests.get")
    def test_request_budget_with_next_token_is_partial(self, mock_get, mock_sleep):
        import fetch_more_history

        response = MagicMock(status_code=200, headers={})
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "data": [{"id": "1", "text": "tweet", "created_at": "2026-01-01T00:00:00Z"}],
            "meta": {"next_token": "more"},
        }
        mock_get.return_value = response

        result = fetch_more_history.fetch_tweets_generic(
            "user-id", {}, max_pages_limit=10, request_budget=1,
        )

        assert result.stop_reason == "request_budget"
        assert result.complete is False
        assert result.has_more is True
        assert result.requests_used == 1
        assert result.data_pages == 1
        mock_sleep.assert_not_called()

    @patch("fetch_more_history.time.sleep")
    @patch("fetch_more_history.requests.get")
    def test_data_page_limit_with_next_token_is_partial(self, mock_get, mock_sleep):
        import fetch_more_history

        response = MagicMock(status_code=200, headers={})
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "data": [{"id": "1", "text": "tweet", "created_at": "2026-01-01T00:00:00Z"}],
            "meta": {"next_token": "more"},
        }
        mock_get.return_value = response

        result = fetch_more_history.fetch_tweets_generic(
            "user-id", {}, max_pages_limit=1, request_budget=3,
        )

        assert result.stop_reason == "page_limit"
        assert result.complete is False
        assert result.has_more is True
        mock_sleep.assert_not_called()

    @patch("fetch_more_history.requests.get")
    def test_low_remaining_rate_limit_with_next_token_is_partial(self, mock_get):
        import fetch_more_history

        response = MagicMock(status_code=200, headers={"x-rate-limit-remaining": "1"})
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "data": [{"id": "1", "text": "tweet", "created_at": "2026-01-01T00:00:00Z"}],
            "meta": {"next_token": "more"},
        }
        mock_get.return_value = response

        result = fetch_more_history.fetch_tweets_generic(
            "user-id", {}, max_pages_limit=3, request_budget=3,
        )

        assert result.stop_reason == "rate_limit_low"
        assert result.can_continue is False
        assert result.complete is False
        assert result.has_more is True

    @patch("fetch_more_history.requests.get")
    def test_http_200_api_errors_raise_invalid_response(self, mock_get):
        import fetch_more_history

        response = MagicMock(status_code=200, headers={})
        response.raise_for_status = MagicMock()
        response.json.return_value = {"errors": [{"message": "partial failure"}]}
        mock_get.return_value = response

        with pytest.raises(fetch_more_history.FetchError, match="API errors") as exc_info:
            fetch_more_history.fetch_tweets_generic("user-id", {}, max_pages_limit=1)

        assert exc_info.value.stop_reason == "invalid_response"
        assert exc_info.value.requests_used == 1

    @patch("fetch_more_history.time.sleep")
    @patch("fetch_more_history.requests.get")
    def test_repeated_pagination_token_raises(self, mock_get, mock_sleep):
        import fetch_more_history

        responses = []
        for tweet_id in ("2", "1"):
            response = MagicMock(status_code=200, headers={})
            response.raise_for_status = MagicMock()
            response.json.return_value = {
                "data": [{"id": tweet_id, "text": "tweet", "created_at": "2026-01-01T00:00:00Z"}],
                "meta": {"next_token": "same-token"},
            }
            responses.append(response)
        mock_get.side_effect = responses

        with pytest.raises(fetch_more_history.FetchError, match="重复 next_token") as exc_info:
            fetch_more_history.fetch_tweets_generic(
                "user-id", {}, max_pages_limit=2, request_budget=2,
            )

        assert exc_info.value.stop_reason == "pagination_token_cycle"
        assert exc_info.value.requests_used == 2
        mock_sleep.assert_called_once_with(fetch_more_history.REQUEST_INTERVAL)

    def test_main_returns_failure_when_incremental_fetch_fails(self, tmp_path, monkeypatch):
        import fetch_more_history

        username = "alice"
        (tmp_path / f"{username}_raw_tweets.json").write_text(json.dumps([
            {"id": "1", "text": "existing", "created_at": "2025-01-01T00:00:00Z"},
        ]), encoding="utf-8")
        monkeypatch.setattr(fetch_more_history, "parse_args", lambda: SimpleNamespace(
            user=username,
            pages=1,
            target_date=None,
            interval=0,
            cache_dir=str(tmp_path),
        ))
        monkeypatch.setattr(fetch_more_history, "auth_headers", lambda token: {})
        monkeypatch.setattr(fetch_more_history, "get_user_id", lambda user, headers: "user-id")
        monkeypatch.setattr(
            fetch_more_history,
            "fetch_tweets_generic",
            MagicMock(side_effect=fetch_more_history.FetchError("api down")),
        )

        assert fetch_more_history.main() == 1

    def test_user_lookup_failure_replaces_stale_status(self, tmp_path, monkeypatch):
        import fetch_more_history

        status_path = tmp_path / "alice_fetch_status.json"
        status_path.write_text('{"status":"success","complete":true}', encoding="utf-8")
        monkeypatch.setattr(fetch_more_history, "parse_args", lambda: SimpleNamespace(
            user="alice", pages=1, target_date=None, interval=0, cache_dir=str(tmp_path),
        ))
        monkeypatch.setattr(fetch_more_history, "auth_headers", lambda token: {})
        monkeypatch.setattr(
            fetch_more_history,
            "get_user_id",
            MagicMock(side_effect=RuntimeError("lookup failed")),
        )

        assert fetch_more_history.main() == 1
        status = json.loads(status_path.read_text(encoding="utf-8"))
        assert status["status"] == "failed"
        assert status["complete"] is False
        assert status["error_stop_reason"] == "user_lookup_failed"

    def test_invalid_target_date_is_recorded_as_failed(self, tmp_path, monkeypatch):
        import fetch_more_history

        monkeypatch.setattr(fetch_more_history, "parse_args", lambda: SimpleNamespace(
            user="alice", pages=1, target_date="2026-99-99", interval=0, cache_dir=str(tmp_path),
        ))

        assert fetch_more_history.main() == 1
        status = json.loads((tmp_path / "alice_fetch_status.json").read_text(encoding="utf-8"))
        assert status["status"] == "failed"
        assert status["error_stop_reason"] == "invalid_target_date"

    def test_invalid_existing_data_is_recorded_as_failed(self, tmp_path, monkeypatch):
        import fetch_more_history

        (tmp_path / "alice_raw_tweets.json").write_text("{broken", encoding="utf-8")
        monkeypatch.setattr(fetch_more_history, "parse_args", lambda: SimpleNamespace(
            user="alice", pages=1, target_date=None, interval=0, cache_dir=str(tmp_path),
        ))
        monkeypatch.setattr(fetch_more_history, "auth_headers", lambda token: {})

        assert fetch_more_history.main() == 1
        status = json.loads((tmp_path / "alice_fetch_status.json").read_text(encoding="utf-8"))
        assert status["status"] == "failed"
        assert status["error_stop_reason"] == "invalid_existing_data"

    def test_backward_failure_keeps_forward_data_and_records_partial(self, tmp_path, monkeypatch):
        import fetch_more_history

        raw_file = tmp_path / "alice_raw_tweets.json"
        raw_file.write_text(json.dumps([
            {"id": "2", "text": "existing latest", "created_at": "2025-01-02T00:00:00Z"},
            {"id": "1", "text": "existing history", "created_at": "2025-01-01T00:00:00Z"},
        ]), encoding="utf-8")
        monkeypatch.setattr(fetch_more_history, "parse_args", lambda: SimpleNamespace(
            user="alice", pages=2, target_date=None, interval=0, cache_dir=str(tmp_path),
        ))
        monkeypatch.setattr(fetch_more_history, "auth_headers", lambda token: {})
        monkeypatch.setattr(fetch_more_history, "get_user_id", lambda user, headers: "user-id")
        monkeypatch.setattr(fetch_more_history, "TARGET_DATE", datetime(2024, 1, 1))
        monkeypatch.setattr(fetch_more_history, "fetch_tweets_generic", MagicMock(side_effect=[
            fetch_more_history.FetchBatchResult(
                [{"id": "3", "text": "new tweet", "created_at": "2025-01-03T00:00:00Z"}],
                False, 1, 1, 0, "no_next_token", True, False,
            ),
            fetch_more_history.FetchError("backward failed"),
        ]))

        assert fetch_more_history.main() == 2
        assert [item["id"] for item in json.loads(raw_file.read_text(encoding="utf-8"))] == ["3", "2", "1"]
        status = json.loads((tmp_path / "alice_fetch_status.json").read_text(encoding="utf-8"))
        assert status["status"] == "partial"
        assert status["complete"] is False
        assert status["has_more"] is None
        assert status["forward_complete"] is True
        assert status["backward_complete"] is None
        assert status["forward"]["requests_used"] == 1
        assert status["error"] == "backward failed"

    def test_first_fetch_backward_failure_is_failed_not_partial(self, tmp_path, monkeypatch):
        import fetch_more_history

        monkeypatch.setattr(fetch_more_history, "parse_args", lambda: SimpleNamespace(
            user="alice", pages=1, target_date=None, interval=0, cache_dir=str(tmp_path),
        ))
        monkeypatch.setattr(fetch_more_history, "auth_headers", lambda token: {})
        monkeypatch.setattr(fetch_more_history, "get_user_id", lambda user, headers: "user-id")
        monkeypatch.setattr(
            fetch_more_history,
            "fetch_tweets_generic",
            MagicMock(side_effect=fetch_more_history.FetchError("initial fetch failed")),
        )

        assert fetch_more_history.main() == 1
        status = json.loads((tmp_path / "alice_fetch_status.json").read_text(encoding="utf-8"))
        assert status["status"] == "failed"
        assert status["complete"] is False
        assert status["has_more"] is None

    def test_low_rate_limit_stops_before_backward_phase(self, tmp_path, monkeypatch):
        import fetch_more_history

        raw_file = tmp_path / "alice_raw_tweets.json"
        raw_file.write_text(json.dumps([
            {"id": "1", "text": "existing tweet", "created_at": "2025-01-01T00:00:00Z"},
        ]), encoding="utf-8")
        monkeypatch.setattr(fetch_more_history, "parse_args", lambda: SimpleNamespace(
            user="alice", pages=3, target_date=None, interval=0, cache_dir=str(tmp_path),
        ))
        monkeypatch.setattr(fetch_more_history, "auth_headers", lambda token: {})
        monkeypatch.setattr(fetch_more_history, "get_user_id", lambda user, headers: "user-id")
        monkeypatch.setattr(fetch_more_history, "TARGET_DATE", datetime(2024, 1, 1))
        fetch = MagicMock(return_value=fetch_more_history.FetchBatchResult(
            [], False, 1, 1, 0, "rate_limit_low", False, True, can_continue=False,
        ))
        monkeypatch.setattr(fetch_more_history, "fetch_tweets_generic", fetch)

        assert fetch_more_history.main() == 2
        assert fetch.call_count == 1
        status = json.loads((tmp_path / "alice_fetch_status.json").read_text(encoding="utf-8"))
        assert status["status"] == "partial"
        assert status["complete"] is False
        assert status["has_more"] is True
        assert status["forward_complete"] is False
        assert status["forward"]["stop_reason"] == "rate_limit_low"

    def test_history_skipped_after_forward_uses_partial_exit(self, tmp_path, monkeypatch):
        import fetch_more_history

        raw_file = tmp_path / "alice_raw_tweets.json"
        raw_file.write_text(json.dumps([
            {"id": "1", "text": "existing tweet", "created_at": "2025-01-01T00:00:00Z"},
        ]), encoding="utf-8")
        monkeypatch.setattr(fetch_more_history, "parse_args", lambda: SimpleNamespace(
            user="alice", pages=1, target_date=None, interval=0, cache_dir=str(tmp_path),
        ))
        monkeypatch.setattr(fetch_more_history, "auth_headers", lambda token: {})
        monkeypatch.setattr(fetch_more_history, "get_user_id", lambda user, headers: "user-id")
        monkeypatch.setattr(fetch_more_history, "TARGET_DATE", datetime(2024, 1, 1))
        monkeypatch.setattr(fetch_more_history, "fetch_tweets_generic", MagicMock(return_value=
            fetch_more_history.FetchBatchResult([], False, 0, 1, 0, "no_data", True, False)
        ))

        assert fetch_more_history.main() == 2
        status = json.loads((tmp_path / "alice_fetch_status.json").read_text(encoding="utf-8"))
        assert status["status"] == "partial"
        assert status["complete"] is False
        assert status["has_more"] is True
        assert status["forward_complete"] is True
        assert status["backward_complete"] is None

    def test_missing_secret_is_recorded_as_failed(self, tmp_path, monkeypatch):
        import fetch_more_history

        monkeypatch.setattr(fetch_more_history, "parse_args", lambda: SimpleNamespace(
            user="alice", pages=1, target_date=None, interval=0, cache_dir=str(tmp_path),
        ))
        monkeypatch.setattr(
            fetch_more_history,
            "auth_headers",
            MagicMock(side_effect=RuntimeError("missing X_BEARER_TOKEN")),
        )

        assert fetch_more_history.main() == 1
        status = json.loads((tmp_path / "alice_fetch_status.json").read_text(encoding="utf-8"))
        assert status["status"] == "failed"
        assert status["error_stop_reason"] == "missing_secret"

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

class TestFullFetchFailures:
    """测试全量抓取不会把中途失败当作完整结果。"""

    @patch("xcrawler.clients.x_api.time.sleep")
    def test_later_page_failure_raises_instead_of_returning_partial_data(self, mock_sleep):
        import requests

        from xcrawler.clients.x_api import TweetFetchError, fetch_user_tweets

        first = MagicMock(status_code=200, headers={})
        first.raise_for_status = MagicMock()
        first.json.return_value = {
            "data": [{"id": "1", "created_at": "2026-01-01T00:00:00Z"}],
            "meta": {"next_token": "next"},
        }
        request_get = MagicMock(side_effect=[
            first,
            requests.exceptions.Timeout("page 2 timeout"),
            requests.exceptions.Timeout("page 2 timeout"),
        ])

        with pytest.raises(TweetFetchError, match="第 2 页网络错误"):
            fetch_user_tweets("user-id", {}, 2, request_get=request_get, max_retries=2)

        assert request_get.call_count == 3
        assert mock_sleep.call_args_list[-1].args == (1,)

    @patch("xcrawler.clients.x_api.time.sleep")
    def test_page_limit_with_next_token_returns_partial_result(self, mock_sleep):
        from xcrawler.clients.x_api import fetch_user_tweets_with_status

        response = MagicMock(status_code=200, headers={})
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "data": [{"id": "1", "text": "tweet", "created_at": "2026-01-01T00:00:00Z"}],
            "meta": {"next_token": "still-more"},
        }

        result = fetch_user_tweets_with_status("user-id", {}, 1, request_get=MagicMock(return_value=response))

        assert [tweet["id"] for tweet in result.tweets] == ["1"]
        assert result.complete is False
        assert result.stop_reason == "page_limit"
        assert result.next_token == "still-more"
        assert result.data_pages == 1
        assert result.requests_used == 1
        mock_sleep.assert_not_called()

    def test_legacy_list_api_rejects_page_limit_partial(self):
        from xcrawler.clients.x_api import TweetFetchError, fetch_user_tweets

        response = MagicMock(status_code=200, headers={})
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "data": [{"id": "1", "text": "tweet", "created_at": "2026-01-01T00:00:00Z"}],
            "meta": {"next_token": "still-more"},
        }

        with pytest.raises(TweetFetchError, match="仍有下一页"):
            fetch_user_tweets("user-id", {}, 1, request_get=MagicMock(return_value=response))

    @patch("xcrawler.clients.x_api.time.sleep")
    def test_http_200_errors_on_later_page_raise(self, mock_sleep):
        from xcrawler.clients.x_api import TweetFetchError, fetch_user_tweets

        first = MagicMock(status_code=200, headers={})
        first.raise_for_status = MagicMock()
        first.json.return_value = {
            "data": [{"id": "1", "text": "tweet", "created_at": "2026-01-01T00:00:00Z"}],
            "meta": {"next_token": "next"},
        }
        second = MagicMock(status_code=200, headers={})
        second.raise_for_status = MagicMock()
        second.json.return_value = {"errors": [{"message": "partial failure"}]}
        request_get = MagicMock(side_effect=[first, second])

        with pytest.raises(TweetFetchError, match="API errors"):
            fetch_user_tweets("user-id", {}, 2, request_get=request_get)

        assert request_get.call_count == 2
        mock_sleep.assert_called_once_with(1)

    def test_malformed_meta_raises(self):
        from xcrawler.clients.x_api import TweetFetchError, fetch_user_tweets

        response = MagicMock(status_code=200, headers={})
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "data": [{"id": "1", "text": "tweet", "created_at": "2026-01-01T00:00:00Z"}],
            "meta": [],
        }

        with pytest.raises(TweetFetchError, match="meta 数据结构无效"):
            fetch_user_tweets("user-id", {}, 1, request_get=MagicMock(return_value=response))

    def test_empty_data_with_next_token_raises(self):
        from xcrawler.clients.x_api import TweetFetchError, fetch_user_tweets

        response = MagicMock(status_code=200, headers={})
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "data": [],
            "meta": {"result_count": 0, "next_token": "inconsistent"},
        }

        with pytest.raises(TweetFetchError, match="分页状态不一致"):
            fetch_user_tweets("user-id", {}, 1, request_get=MagicMock(return_value=response))

    @patch("xcrawler.clients.x_api.time.sleep")
    def test_repeated_next_token_raises(self, mock_sleep):
        from xcrawler.clients.x_api import TweetFetchError, fetch_user_tweets

        responses = []
        for tweet_id in ("1", "2"):
            response = MagicMock(status_code=200, headers={})
            response.raise_for_status = MagicMock()
            response.json.return_value = {
                "data": [{"id": tweet_id, "text": "tweet", "created_at": "2026-01-01T00:00:00Z"}],
                "meta": {"next_token": "same-token"},
            }
            responses.append(response)

        with pytest.raises(TweetFetchError, match="重复 next_token"):
            fetch_user_tweets("user-id", {}, 2, request_get=MagicMock(side_effect=responses))

        mock_sleep.assert_called_once_with(1)

    def test_replace_translation_failure_preserves_previous_snapshot(self, tmp_path, monkeypatch):
        import main

        old_raw = [{"id": "old", "text": "old tweet", "created_at": "2025-01-01T00:00:00Z"}]
        old_translated = [{
            "tweet_id": "old",
            "original": "old tweet",
            "translated": "旧译文",
            "detected_language": "en",
            "created_at": "2025-01-01T00:00:00Z",
        }]
        raw_path = tmp_path / "alice_raw_tweets.json"
        translated_path = tmp_path / "alice_translated.json"
        raw_path.write_text(json.dumps(old_raw, ensure_ascii=False), encoding="utf-8")
        translated_path.write_text(json.dumps(old_translated, ensure_ascii=False), encoding="utf-8")
        new_raw = [
            {"id": str(index), "text": f"long english tweet {index}", "created_at": "2026-01-01T00:00:00Z"}
            for index in range(10)
        ]
        args = SimpleNamespace(
            user="alice",
            pages=1,
            batch_size=10,
            model=None,
            cache_dir=str(tmp_path),
            analysis_limit=100,
            no_translate=False,
            replace=True,
            storage_backend="json",
            sqlite_path=None,
        )
        monkeypatch.setattr(main, "TARGET_USERNAME", main.TARGET_USERNAME)
        monkeypatch.setattr(main, "CACHE_DIR", main.CACHE_DIR)
        monkeypatch.setattr(main, "parse_args", lambda: args)
        monkeypatch.setattr(main, "validate_runtime_config", lambda **kwargs: None)
        monkeypatch.setattr(main, "get_user_id", lambda username: "uid")
        monkeypatch.setattr(main, "get_user_profile", lambda username: None)
        monkeypatch.setattr(main, "fetch_tweets", lambda user_id: main.x_api.TweetFetchResult(
            new_raw, True, "no_next_token", 1, 1, 0,
        ))
        monkeypatch.setattr(main, "deepseek_translate_batch", lambda texts, langs: [None] * len(texts))
        monkeypatch.setattr(main, "save_translation_cache", lambda cache: None)

        assert main.main() == 1
        assert json.loads(raw_path.read_text(encoding="utf-8")) == old_raw
        assert json.loads(translated_path.read_text(encoding="utf-8")) == old_translated

    def test_successful_translation_clears_stale_failure_list(self, tmp_path, monkeypatch):
        import main

        failed_path = tmp_path / "alice_failed.json"
        failed_path.write_text('[{"tweet_id":"old"}]', encoding="utf-8")
        raw = [{"id": "1", "text": "long english tweet", "created_at": "2026-01-01T00:00:00Z"}]
        args = SimpleNamespace(
            user="alice", pages=1, batch_size=10, model=None, cache_dir=str(tmp_path),
            analysis_limit=100, no_translate=False, replace=False, storage_backend="json", sqlite_path=None,
        )
        monkeypatch.setattr(main, "TARGET_USERNAME", main.TARGET_USERNAME)
        monkeypatch.setattr(main, "CACHE_DIR", main.CACHE_DIR)
        monkeypatch.setattr(main, "parse_args", lambda: args)
        monkeypatch.setattr(main, "validate_runtime_config", lambda **kwargs: None)
        monkeypatch.setattr(main, "get_user_id", lambda username: "uid")
        monkeypatch.setattr(main, "get_user_profile", lambda username: None)
        monkeypatch.setattr(main, "fetch_tweets", lambda user_id: main.x_api.TweetFetchResult(
            raw, True, "no_next_token", 1, 1, 0,
        ))
        monkeypatch.setattr(main, "deepseek_translate_batch", lambda texts, langs: ["新译文"])
        monkeypatch.setattr(main, "save_translation_cache", lambda cache: None)

        assert main.main() == 0
        assert json.loads(failed_path.read_text(encoding="utf-8")) == []

    def test_replace_no_translate_filters_stale_translations(self, tmp_path, monkeypatch):
        import main

        old_raw = [
            {"id": "old", "text": "old tweet", "created_at": "2025-01-01T00:00:00Z"},
            {"id": "keep", "text": "kept tweet", "created_at": "2025-01-02T00:00:00Z"},
        ]
        old_translated = [
            {"tweet_id": "old", "original": "old tweet", "translated": "old", "detected_language": "en", "created_at": "2025-01-01T00:00:00Z"},
            {"tweet_id": "keep", "original": "kept tweet", "translated": "keep", "detected_language": "en", "created_at": "2025-01-02T00:00:00Z"},
        ]
        new_raw = [
            {"id": "new", "text": "new tweet", "created_at": "2026-01-02T00:00:00Z"},
            {"id": "keep", "text": "kept tweet", "created_at": "2025-01-02T00:00:00Z"},
        ]
        raw_path = tmp_path / "alice_raw_tweets.json"
        translated_path = tmp_path / "alice_translated.json"
        raw_path.write_text(json.dumps(old_raw), encoding="utf-8")
        translated_path.write_text(json.dumps(old_translated), encoding="utf-8")
        args = SimpleNamespace(
            user="alice", pages=1, batch_size=10, model=None, cache_dir=str(tmp_path),
            analysis_limit=100, no_translate=True, replace=True, storage_backend="json", sqlite_path=None,
        )
        monkeypatch.setattr(main, "TARGET_USERNAME", main.TARGET_USERNAME)
        monkeypatch.setattr(main, "CACHE_DIR", main.CACHE_DIR)
        monkeypatch.setattr(main, "parse_args", lambda: args)
        monkeypatch.setattr(main, "validate_runtime_config", lambda **kwargs: None)
        monkeypatch.setattr(main, "get_user_id", lambda username: "uid")
        monkeypatch.setattr(main, "get_user_profile", lambda username: None)
        monkeypatch.setattr(main, "fetch_tweets", lambda user_id: main.x_api.TweetFetchResult(
            new_raw, True, "no_next_token", 1, 1, 0,
        ))

        assert main.main() == 0
        assert json.loads(raw_path.read_text(encoding="utf-8")) == new_raw
        retained = json.loads(translated_path.read_text(encoding="utf-8"))
        assert [item["tweet_id"] for item in retained] == ["keep"]

    def test_replace_page_limit_preserves_previous_snapshot(self, tmp_path, monkeypatch):
        import main

        old_raw = [{"id": "old", "text": "old tweet", "created_at": "2025-01-01T00:00:00Z"}]
        old_translated = [{
            "tweet_id": "old",
            "original": "old tweet",
            "translated": "旧译文",
            "detected_language": "en",
            "created_at": "2025-01-01T00:00:00Z",
        }]
        new_raw = [{"id": "new", "text": "new tweet", "created_at": "2026-01-01T00:00:00Z"}]
        raw_path = tmp_path / "alice_raw_tweets.json"
        translated_path = tmp_path / "alice_translated.json"
        raw_path.write_text(json.dumps(old_raw), encoding="utf-8")
        translated_path.write_text(json.dumps(old_translated, ensure_ascii=False), encoding="utf-8")
        args = SimpleNamespace(
            user="alice", pages=1, batch_size=10, model=None, cache_dir=str(tmp_path),
            analysis_limit=100, no_translate=False, replace=True, storage_backend="json", sqlite_path=None,
        )
        monkeypatch.setattr(main, "parse_args", lambda: args)
        monkeypatch.setattr(main, "validate_runtime_config", lambda **kwargs: None)
        monkeypatch.setattr(main, "get_user_id", lambda username: "uid")
        monkeypatch.setattr(main, "get_user_profile", lambda username: None)
        monkeypatch.setattr(main, "fetch_tweets", lambda user_id: main.x_api.TweetFetchResult(
            new_raw, False, "page_limit", 1, 1, 0, "still-more",
        ))
        translate = MagicMock()
        monkeypatch.setattr(main, "deepseek_translate_batch", translate)

        assert main.main() == 2
        assert json.loads(raw_path.read_text(encoding="utf-8")) == old_raw
        assert json.loads(translated_path.read_text(encoding="utf-8")) == old_translated
        translate.assert_not_called()

    def test_archive_page_limit_saves_partial_data_and_returns_two(self, tmp_path, monkeypatch):
        import main

        old_raw = [{"id": "old", "text": "old tweet", "created_at": "2025-01-01T00:00:00Z"}]
        new_raw = [{"id": "new", "text": "new tweet", "created_at": "2026-01-01T00:00:00Z"}]
        raw_path = tmp_path / "alice_raw_tweets.json"
        raw_path.write_text(json.dumps(old_raw), encoding="utf-8")
        args = SimpleNamespace(
            user="alice", pages=1, batch_size=10, model=None, cache_dir=str(tmp_path),
            analysis_limit=100, no_translate=True, replace=False, storage_backend="json", sqlite_path=None,
        )
        monkeypatch.setattr(main, "parse_args", lambda: args)
        monkeypatch.setattr(main, "validate_runtime_config", lambda **kwargs: None)
        monkeypatch.setattr(main, "get_user_id", lambda username: "uid")
        monkeypatch.setattr(main, "get_user_profile", lambda username: None)
        monkeypatch.setattr(main, "fetch_tweets", lambda user_id: main.x_api.TweetFetchResult(
            new_raw, False, "page_limit", 1, 1, 0, "still-more",
        ))

        assert main.main() == 2
        assert [tweet["id"] for tweet in json.loads(raw_path.read_text(encoding="utf-8"))] == ["new", "old"]

class TestRawTweetValidation:
    """测试 raw tweet 结构错误不会在合并时被静默丢弃。"""

    @pytest.mark.parametrize("record, message", [
        ({"text": "missing id", "created_at": "2026-01-01T00:00:00Z"}, "id"),
        ({"id": "1", "created_at": "2026-01-01T00:00:00Z"}, "text"),
        ({"id": "1", "text": "bad date", "created_at": "yesterday"}, "created_at"),
    ])
    def test_invalid_raw_record_is_rejected(self, record, message):
        from xcrawler.services.tweets import TweetSchemaError, validate_raw_tweets

        with pytest.raises(TweetSchemaError, match=message):
            validate_raw_tweets([record])

    def test_duplicate_raw_ids_are_rejected(self):
        from xcrawler.services.tweets import TweetSchemaError, validate_raw_tweets

        records = [
            {"id": "1", "text": "first", "created_at": "2026-01-01T00:00:00Z"},
            {"id": "1", "text": "second", "created_at": "2026-01-02T00:00:00Z"},
        ]
        with pytest.raises(TweetSchemaError, match="重复 id"):
            validate_raw_tweets(records)

class TestFetchPlan:
    """测试抓取计划估算"""

    def test_fetch_plan_estimates_requests_and_tweets(self):
        from xcrawler.services.fetch_plan import build_fetch_plan

        plan = build_fetch_plan("alice", pages=3)

        assert plan.estimated_requests == 3
        assert plan.estimated_max_tweets == 300
        assert plan.to_dict()["username"] == "alice"

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
