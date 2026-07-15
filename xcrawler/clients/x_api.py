from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import requests

from xcrawler.clients.retry import RequestAttemptsError, request_json_with_retries
from xcrawler.config import require_secret

RequestGet = Callable[..., requests.Response]
MAX_FETCH_RETRIES = 3
MAX_RATE_LIMIT_WAIT = 60


class TweetFetchError(RuntimeError):
    """用户时间线未能完整抓取，返回的部分数据不应当作完整结果。"""


class TimelinePageError(ValueError):
    """X API 时间线页面不满足可安全分页的数据契约。"""


@dataclass(frozen=True)
class TimelinePageResult:
    tweets: list[dict]
    next_token: str | None


@dataclass(frozen=True)
class TweetFetchResult:
    tweets: list[dict]
    complete: bool
    stop_reason: str
    data_pages: int
    requests_used: int
    retries: int
    next_token: str | None = None


def validate_timeline_page_response(data: dict, *, page_number: int) -> TimelinePageResult:
    errors = data.get("errors")
    if errors is not None:
        if not isinstance(errors, list):
            raise TimelinePageError(f"第 {page_number} 页 errors 数据结构无效")
        if errors:
            raise TimelinePageError(f"第 {page_number} 页响应包含 API errors，无法确认抓取完整")

    meta = data.get("meta", {})
    if not isinstance(meta, dict):
        raise TimelinePageError(f"第 {page_number} 页 meta 数据结构无效")

    token = meta.get("next_token")
    if token is not None and (not isinstance(token, str) or not token.strip()):
        raise TimelinePageError(f"第 {page_number} 页 next_token 数据结构无效")

    if "data" not in data:
        if meta.get("result_count") == 0 and token is None:
            page_tweets = []
        else:
            raise TimelinePageError(f"第 {page_number} 页响应缺少 data，无法确认抓取完整")
    else:
        page_tweets = data["data"]
        if not isinstance(page_tweets, list):
            raise TimelinePageError(f"第 {page_number} 页 data 数据结构无效")

    if not page_tweets and token is not None:
        raise TimelinePageError(f"第 {page_number} 页无数据但仍包含 next_token，分页状态不一致")

    return TimelinePageResult(page_tweets, token)


def auth_headers(bearer_token: str | None) -> dict[str, str]:
    token = require_secret("X_BEARER_TOKEN", bearer_token, purpose="抓取公开推文")
    return {"Authorization": f"Bearer {token}"}


def get_user_id(username: str, headers: dict[str, str], request_get: RequestGet = requests.get) -> str:
    url = f"https://api.twitter.com/2/users/by/username/{username}"
    try:
        data = request_json_with_retries(
            url,
            headers=headers,
            params={},
            request_get=request_get,
            max_retries=MAX_FETCH_RETRIES,
            request_budget=MAX_FETCH_RETRIES,
            page_number=1,
        ).data
    except RequestAttemptsError as error:
        raise TweetFetchError(str(error)) from error

    if "data" not in data:
        raise ValueError(f"用户 '{username}' 不存在或无权访问")

    return data["data"]["id"]


def get_user_profile(
    username: str,
    headers: dict[str, str],
    request_get: RequestGet = requests.get,
) -> dict | None:
    url = f"https://api.twitter.com/2/users/by/username/{username}"
    params = {
        "user.fields": "description,public_metrics,created_at,profile_image_url,verified,location"
    }
    try:
        data = request_json_with_retries(
            url,
            headers=headers,
            params=params,
            request_get=request_get,
            max_retries=MAX_FETCH_RETRIES,
            request_budget=MAX_FETCH_RETRIES,
            page_number=1,
        ).data
        if "data" not in data:
            return None
        user = data["data"]
        metrics = user.get("public_metrics", {})
        return {
            "username": username,
            "name": user.get("name", ""),
            "description": user.get("description", ""),
            "location": user.get("location", ""),
            "verified": user.get("verified", False),
            "created_at": user.get("created_at", ""),
            "profile_image_url": user.get("profile_image_url", ""),
            "followers_count": metrics.get("followers_count", 0),
            "following_count": metrics.get("following_count", 0),
            "tweet_count": metrics.get("tweet_count", 0),
            "listed_count": metrics.get("listed_count", 0),
        }
    except (RequestAttemptsError, ValueError):
        return None


def fetch_user_tweets_with_status(
    user_id: str,
    headers: dict[str, str],
    max_pages: int,
    request_get: RequestGet = requests.get,
    max_retries: int = MAX_FETCH_RETRIES,
) -> TweetFetchResult:
    if max_pages < 1:
        raise ValueError("max_pages 必须大于等于 1")

    url = f"https://api.twitter.com/2/users/{user_id}/tweets"
    params = {
        "max_results": 100,
        "tweet.fields": "created_at,entities",
        "exclude": "retweets,replies",
    }

    tweets = []
    data_pages = 0
    requests_used = 0
    retries = 0
    seen_tokens: set[str] = set()
    next_token: str | None = None
    for page in range(max_pages):
        try:
            attempt_result = request_json_with_retries(
                url,
                headers=headers,
                params=params,
                request_get=request_get,
                max_retries=max_retries,
                request_budget=max_retries,
                page_number=page + 1,
                max_rate_limit_wait=MAX_RATE_LIMIT_WAIT,
            )
        except RequestAttemptsError as error:
            raise TweetFetchError(str(error)) from error
        requests_used += attempt_result.requests_used
        retries += attempt_result.retries
        response = attempt_result.response
        data = attempt_result.data

        try:
            page_result = validate_timeline_page_response(data, page_number=page + 1)
        except TimelinePageError as error:
            raise TweetFetchError(str(error)) from error
        page_tweets = page_result.tweets

        if not page_tweets:
            print(f"📭 第 {page + 1} 页无数据，停止抓取")
            return TweetFetchResult(
                tweets=tweets,
                complete=True,
                stop_reason="no_data",
                data_pages=data_pages,
                requests_used=requests_used,
                retries=retries,
            )

        tweets.extend(page_tweets)
        data_pages += 1
        print(f"📄 已抓取第 {page + 1} 页，本页 {len(page_tweets)} 条，累计 {len(tweets)} 条")

        remaining = response.headers.get("x-rate-limit-remaining")
        if remaining:
            print(f"   剩余配额: {remaining} 次")

        token = page_result.next_token
        if token is None:
            print("✅ 已抓取所有可用推文")
            return TweetFetchResult(
                tweets=tweets,
                complete=True,
                stop_reason="no_next_token",
                data_pages=data_pages,
                requests_used=requests_used,
                retries=retries,
            )
        if token in seen_tokens:
            raise TweetFetchError(f"第 {page + 1} 页出现重复 next_token，分页无法继续")
        seen_tokens.add(token)
        next_token = token
        params["pagination_token"] = token
        if page + 1 < max_pages:
            time.sleep(1)

    return TweetFetchResult(
        tweets=tweets,
        complete=False,
        stop_reason="page_limit",
        data_pages=data_pages,
        requests_used=requests_used,
        retries=retries,
        next_token=next_token,
    )


def fetch_user_tweets(
    user_id: str,
    headers: dict[str, str],
    max_pages: int,
    request_get: RequestGet = requests.get,
    max_retries: int = MAX_FETCH_RETRIES,
) -> list[dict]:
    """兼容旧调用方的列表返回值，但绝不把页数截断结果伪装成完整列表。"""
    result = fetch_user_tweets_with_status(
        user_id,
        headers,
        max_pages,
        request_get=request_get,
        max_retries=max_retries,
    )
    if not result.complete:
        raise TweetFetchError(
            f"抓取达到 {max_pages} 页上限但仍有下一页；请提高页数，或使用带状态的抓取接口"
        )
    return result.tweets
