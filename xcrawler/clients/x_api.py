from __future__ import annotations

import time
from collections.abc import Callable

import requests

from xcrawler.clients.retry import RequestAttemptsError, request_json_with_retries
from xcrawler.config import require_secret

RequestGet = Callable[..., requests.Response]
MAX_FETCH_RETRIES = 3
MAX_RATE_LIMIT_WAIT = 60


class TweetFetchError(RuntimeError):
    """用户时间线未能完整抓取，返回的部分数据不应当作完整结果。"""


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


def fetch_user_tweets(
    user_id: str,
    headers: dict[str, str],
    max_pages: int,
    request_get: RequestGet = requests.get,
    max_retries: int = MAX_FETCH_RETRIES,
) -> list[dict]:
    url = f"https://api.twitter.com/2/users/{user_id}/tweets"
    params = {
        "max_results": 100,
        "tweet.fields": "created_at,entities",
        "exclude": "retweets,replies",
    }

    tweets = []
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
        response = attempt_result.response
        data = attempt_result.data

        page_tweets = data.get("data", [])
        if not page_tweets:
            print(f"📭 第 {page + 1} 页无数据，停止抓取")
            break

        tweets.extend(page_tweets)
        print(f"📄 已抓取第 {page + 1} 页，本页 {len(page_tweets)} 条，累计 {len(tweets)} 条")

        remaining = response.headers.get("x-rate-limit-remaining")
        if remaining:
            print(f"   剩余配额: {remaining} 次")

        token = data.get("meta", {}).get("next_token")
        if not token:
            print("✅ 已抓取所有可用推文")
            break
        params["pagination_token"] = token
        time.sleep(1)

    return tweets
