from __future__ import annotations

import time
from typing import Callable

import requests

from xcrawler.config import require_secret


RequestGet = Callable[..., requests.Response]


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
    except Exception:
        return None


def fetch_user_tweets(
    user_id: str,
    headers: dict[str, str],
    max_pages: int,
    request_get: RequestGet = requests.get,
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
            response = request_get(url, headers=headers, params=params, timeout=10)

            if response.status_code == 429:
                reset_time = response.headers.get("x-rate-limit-reset")
                if reset_time:
                    wait_seconds = int(reset_time) - int(time.time())
                    if wait_seconds > 0:
                        print(f"⏳ API 限流，需等待 {wait_seconds // 60} 分 {wait_seconds % 60} 秒...")
                        print("💡 提示：X API 有严格的频率限制，请稍后再试")
                        if page == 0:
                            raise Exception(f"API 限流，请等待 {wait_seconds // 60} 分钟后再运行")
                        break
                else:
                    print("⚠️ API 限流（429），建议等待 15 分钟后重试")
                    if page == 0:
                        raise Exception("API 限流，请等待 15 分钟后再运行")
                    break

            response.raise_for_status()
            data = response.json()

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

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                print("⚠️ API 限流，请稍后重试")
            else:
                print(f"⚠️ 第 {page + 1} 页抓取失败: {str(e)}")
            if page == 0:
                raise Exception(f"首页抓取失败: {str(e)}")
            break
        except requests.exceptions.RequestException as e:
            print(f"⚠️ 第 {page + 1} 页抓取失败: {str(e)}")
            if page == 0:
                raise Exception(f"首页抓取失败: {str(e)}")
            break

    return tweets
