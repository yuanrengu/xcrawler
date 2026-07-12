from __future__ import annotations

import time
from collections.abc import Callable

import requests

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
    response = request_get(url, headers=headers, timeout=10)
    response.raise_for_status()
    data = response.json()

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
        response = request_get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
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
    except (requests.exceptions.RequestException, ValueError):
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
        data = None
        response = None
        for attempt in range(1, max_retries + 1):
            try:
                response = request_get(url, headers=headers, params=params, timeout=10)
                if response.status_code == 429:
                    reset_time = response.headers.get("x-rate-limit-reset")
                    if reset_time is None:
                        wait_seconds = min(2 ** (attempt - 1), 8)
                    else:
                        try:
                            wait_seconds = max(0, int(float(reset_time)) - int(time.time()))
                        except (TypeError, ValueError) as error:
                            raise TweetFetchError("API 限流重置时间无效") from error
                    if wait_seconds > MAX_RATE_LIMIT_WAIT:
                        raise TweetFetchError(f"API 限流需等待 {wait_seconds} 秒，超过最大等待时间")
                    if attempt == max_retries:
                        raise TweetFetchError(f"API 限流，重试 {max_retries} 次后仍未恢复")
                    print(f"⏳ API 限流，{wait_seconds} 秒后重试 ({attempt}/{max_retries})...")
                    time.sleep(wait_seconds)
                    continue

                response.raise_for_status()
                data = response.json()
                break
            except requests.exceptions.HTTPError as error:
                status = error.response.status_code if error.response is not None else 0
                retryable = status >= 500 or status == 0
                if status in (401, 403) or not retryable or attempt == max_retries:
                    raise TweetFetchError(f"第 {page + 1} 页 HTTP 错误（{status or 'unknown'}）") from error
                delay = min(2 ** (attempt - 1), 8)
                print(f"⚠️ 第 {page + 1} 页 HTTP {status}，{delay} 秒后重试 ({attempt}/{max_retries})...")
                time.sleep(delay)
            except requests.exceptions.RequestException as error:
                if attempt == max_retries:
                    raise TweetFetchError(f"第 {page + 1} 页网络错误，重试 {max_retries} 次后仍失败") from error
                delay = min(2 ** (attempt - 1), 8)
                print(f"⚠️ 第 {page + 1} 页网络错误，{delay} 秒后重试 ({attempt}/{max_retries})...")
                time.sleep(delay)
            except ValueError as error:
                if attempt == max_retries:
                    raise TweetFetchError(f"第 {page + 1} 页响应解析失败") from error
                delay = min(2 ** (attempt - 1), 8)
                print(f"⚠️ 第 {page + 1} 页响应解析失败，{delay} 秒后重试 ({attempt}/{max_retries})...")
                time.sleep(delay)

        if response is None or data is None:
            raise TweetFetchError(f"第 {page + 1} 页未能获取有效响应")

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
