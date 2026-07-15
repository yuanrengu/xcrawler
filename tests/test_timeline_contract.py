"""Contract and property tests for X timeline pagination responses."""

from unittest.mock import MagicMock, patch

import pytest
import requests
from hypothesis import given
from hypothesis import strategies as st

from xcrawler.clients.x_api import TimelinePageError, validate_timeline_page_response


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"errors": {}}, "errors 数据结构无效"),
        ({"errors": [{"message": "denied"}]}, "API errors"),
        ({"data": [], "meta": []}, "meta 数据结构无效"),
        ({"data": [], "meta": {"next_token": 123}}, "next_token 数据结构无效"),
        ({"data": [], "meta": {"next_token": "   "}}, "next_token 数据结构无效"),
        ({"meta": {}}, "响应缺少 data"),
        ({"data": {}, "meta": {}}, "data 数据结构无效"),
        ({"data": [], "meta": {"next_token": "more"}}, "分页状态不一致"),
    ],
)
def test_invalid_timeline_payloads_are_rejected(payload, message):
    with pytest.raises(TimelinePageError, match=message):
        validate_timeline_page_response(payload, page_number=3)


def test_first_page_network_failure_never_returns_a_partial_result():
    from xcrawler.clients.x_api import TweetFetchError, fetch_user_tweets_with_status

    request_get = MagicMock(side_effect=requests.exceptions.Timeout("first page timeout"))
    with patch("xcrawler.clients.x_api.time.sleep"), pytest.raises(TweetFetchError, match="第 1 页网络错误"):
        fetch_user_tweets_with_status("user-id", {}, 2, request_get=request_get, max_retries=2)

    assert request_get.call_count == 2


@given(
    tweets=st.lists(
        st.fixed_dictionaries({"id": st.text(min_size=1), "text": st.text()}),
        min_size=1,
        max_size=20,
    ),
    next_token=st.one_of(st.none(), st.text(min_size=1).filter(lambda value: bool(value.strip()))),
)
def test_valid_non_empty_pages_round_trip_without_mutation(tweets, next_token):
    payload = {"data": tweets, "meta": {}}
    if next_token is not None:
        payload["meta"]["next_token"] = next_token

    result = validate_timeline_page_response(payload, page_number=1)

    assert result.tweets == tweets
    assert result.next_token == next_token


@given(
    extra_meta=st.dictionaries(
        st.text(min_size=1).filter(lambda key: key not in {"result_count", "next_token"}),
        st.integers() | st.text() | st.booleans() | st.none(),
        max_size=5,
    )
)
def test_explicit_empty_page_without_token_is_complete(extra_meta):
    result = validate_timeline_page_response(
        {"meta": {"result_count": 0, **extra_meta}},
        page_number=1,
    )

    assert result.tweets == []
    assert result.next_token is None


@given(token=st.text(min_size=1).filter(lambda value: bool(value.strip())))
def test_full_fetch_rejects_any_repeated_pagination_token(token):
    from xcrawler.clients.x_api import TweetFetchError, fetch_user_tweets_with_status

    responses = []
    for tweet_id in ("1", "2"):
        response = MagicMock(status_code=200, headers={})
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "data": [{"id": tweet_id, "text": "tweet"}],
            "meta": {"next_token": token},
        }
        responses.append(response)

    with patch("xcrawler.clients.x_api.time.sleep"), pytest.raises(TweetFetchError, match="重复 next_token"):
        fetch_user_tweets_with_status("user-id", {}, 2, request_get=MagicMock(side_effect=responses))
