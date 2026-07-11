"""
增量抓取脚本
功能：
1. 抓取比现有数据更新的推文（Forward Fetching）
2. 抓取比现有数据更早的推文（Backward Fetching），直到到达 TARGET_DATE
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime

import requests

from xcrawler.clients import x_api
from xcrawler.clients.x_api import auth_headers
from xcrawler.config import load_config
from xcrawler.paths import ensure_dir
from xcrawler.services.tweets import merge_tweets
from xcrawler.storage.json_store import JsonStoreError, load_json, save_json
from xcrawler.utils import cli_validation
from xcrawler.utils.time import parse_twitter_datetime

_config = load_config()

# 配置
X_BEARER_TOKEN = _config.x_bearer_token
TARGET_USERNAME = _config.target_username
CACHE_DIR = _config.cache_dir
MAX_PAGES = 10

TARGET_DATE = _config.target_date

REQUEST_INTERVAL = 3
MAX_RETRIES = 3
MAX_RATE_LIMIT_WAIT = 60


class FetchError(RuntimeError):
    """抓取未能成功完成，不应将其视为“没有新数据”。"""


def parse_args():
    parser = argparse.ArgumentParser(description="智能增量抓取：双向同步（新推文 + 历史补全）")
    parser.add_argument("-u", "--user", type=cli_validation.x_username, help="目标用户名")
    parser.add_argument("--pages", type=cli_validation.positive_int, help=f"最大抓取页数（默认 {MAX_PAGES}）")
    parser.add_argument("--target-date", help="历史抓取目标日期，格式 YYYY-MM-DD")
    parser.add_argument("--interval", type=cli_validation.non_negative_int, help=f"请求间隔秒数（默认 {REQUEST_INTERVAL}）")
    parser.add_argument("--cache-dir", help=f"缓存目录（默认 {CACHE_DIR}）")
    return parser.parse_args()


def get_user_id(username, headers):
    """获取用户ID"""
    return x_api.get_user_id(username, headers, request_get=requests.get)


def fetch_tweets_generic(
    user_id,
    headers,
    since_id=None,
    until_id=None,
    stop_date=None,
    max_pages_limit=MAX_PAGES,
    description="抓取",
    max_retries=MAX_RETRIES,
):
    """
    通用抓取函数
    :param user_id: 用户ID
    :param headers: HTTP 请求头
    :param since_id: 获取比此ID更新的推文（向后/未来）
    :param until_id: 获取比此ID更早的推文（向前/历史）
    :param stop_date: 如果遇到早于此日期的推文，停止抓取 (仅用于 Backward 模式)
    :param max_pages_limit: 本次调用的最大页数限制
    :param description: 描述文本
    :return: (tweets_list, reached_stop_date, pages_fetched)
    """
    url = f"https://api.twitter.com/2/users/{user_id}/tweets"
    params = {
        "max_results": 100,
        "tweet.fields": "created_at,entities",
        "exclude": "retweets,replies"
    }
    
    if until_id:
        params["until_id"] = until_id
    if since_id:
        params["since_id"] = since_id

    all_tweets = []
    reached_target = False
    pages_fetched = 0
    
    print(f"🚀 {description} (最大页数限制: {max_pages_limit})...")
    if since_id:
        print(f"   📍 范围: ID {since_id} 之后 (新推文)")
    if until_id:
        print(f"   📍 范围: ID {until_id} 之前 (历史推文)")

    for page in range(max_pages_limit):
        response = None
        data = None
        for attempt in range(1, max_retries + 1):
            try:
                response = requests.get(url, headers=headers, params=params, timeout=10)
                if response.status_code == 429:
                    reset_time = response.headers.get("x-rate-limit-reset")
                    if reset_time is None:
                        wait_seconds = min(2 ** (attempt - 1), 8)
                    else:
                        try:
                            wait_seconds = max(0, int(float(reset_time)) - int(time.time()))
                        except (TypeError, ValueError) as error:
                            raise FetchError("API 限流重置时间无效") from error
                    if wait_seconds > MAX_RATE_LIMIT_WAIT:
                        raise FetchError(f"API 限流需等待 {wait_seconds} 秒，超过最大等待时间")
                    if attempt == max_retries:
                        raise FetchError(f"API 限流，重试 {max_retries} 次后仍未恢复")
                    print(f"⏳ API 限流，{wait_seconds} 秒后重试 ({attempt}/{max_retries})...")
                    time.sleep(wait_seconds)
                    continue

                response.raise_for_status()
                data = response.json()
                break
            except requests.exceptions.HTTPError as error:
                status = error.response.status_code if error.response is not None else 0
                if status in (401, 403):
                    raise FetchError(f"认证失败（HTTP {status}），请检查 X_BEARER_TOKEN") from error
                retryable = status >= 500 or status == 0
                if not retryable or attempt == max_retries:
                    raise FetchError(f"第 {page + 1} 页 HTTP 错误（{status or 'unknown'}）") from error
                delay = min(2 ** (attempt - 1), 8)
                print(f"⚠️ 第 {page + 1} 页 HTTP {status}，{delay} 秒后重试 ({attempt}/{max_retries})...")
                time.sleep(delay)
            except requests.exceptions.RequestException as error:
                if attempt == max_retries:
                    raise FetchError(f"第 {page + 1} 页网络错误，重试 {max_retries} 次后仍失败") from error
                delay = min(2 ** (attempt - 1), 8)
                print(f"⚠️ 第 {page + 1} 页网络错误，{delay} 秒后重试 ({attempt}/{max_retries})...")
                time.sleep(delay)
            except (json.JSONDecodeError, ValueError) as error:
                if attempt == max_retries:
                    raise FetchError(f"第 {page + 1} 页响应解析失败") from error
                delay = min(2 ** (attempt - 1), 8)
                print(f"⚠️ 第 {page + 1} 页响应解析失败，{delay} 秒后重试 ({attempt}/{max_retries})...")
                time.sleep(delay)

        if response is None or data is None:
            raise FetchError(f"第 {page + 1} 页未能获取有效响应")

        try:
            
            page_tweets = data.get("data", [])
            if not page_tweets:
                print(f"📭 第 {page + 1} 页无数据 (本批次结束)")
                break

            kept_tweets = page_tweets
            if stop_date:
                kept_tweets = []
                for tweet in page_tweets:
                    tweet_dt = parse_twitter_datetime(tweet["created_at"])
                    if tweet_dt >= stop_date:
                        kept_tweets.append(tweet)
                    else:
                        reached_target = True

            all_tweets.extend(kept_tweets)
            pages_fetched += 1
            
            # 获取本页最早时间
            oldest_in_page = parse_twitter_datetime(page_tweets[-1]["created_at"])
            kept_note = f"，保留 {len(kept_tweets)} 条" if stop_date and len(kept_tweets) != len(page_tweets) else ""
            print(f"📄 第 {page + 1} 页: {len(page_tweets)}条{kept_note} | 最早: {oldest_in_page.strftime('%Y-%m-%d')} | 累计: {len(all_tweets)}条")
            
            # 仅在向历史抓取时检查日期停止条件
            if reached_target:
                print(f"✅ 已到达目标日期 {stop_date.strftime('%Y-%m-%d')}！")
                break
            
            # 检查剩余配额
            remaining = response.headers.get('x-rate-limit-remaining')
            if remaining:
               if int(remaining) % 10 == 0: # 减少日志输出
                    print(f"   剩余配额: {remaining} 次")
               if int(remaining) < 2:
                    print("⚠️ 配额即将耗尽，暂停抓取")
                    break
            
            # 获取下一页token
            token = data.get("meta", {}).get("next_token")
            if not token:
                print("✅ 已抓取该区间所有推文")
                break
            params["pagination_token"] = token
            
            time.sleep(REQUEST_INTERVAL)
            
        except (KeyError, TypeError, ValueError) as error:
            raise FetchError(f"第 {page + 1} 页推文数据结构无效") from error
    
    return all_tweets, reached_target, pages_fetched


def main():
    global TARGET_USERNAME, MAX_PAGES, TARGET_DATE, REQUEST_INTERVAL, CACHE_DIR

    args = parse_args()
    if args.user:
        TARGET_USERNAME = args.user
    if args.pages is not None:
        MAX_PAGES = args.pages
    if args.target_date:
        try:
            TARGET_DATE = datetime.strptime(args.target_date, "%Y-%m-%d")
        except ValueError:
            print(f"❌ --target-date 格式错误: {args.target_date}，必须为 YYYY-MM-DD")
            return 1
    if args.interval is not None:
        REQUEST_INTERVAL = args.interval
    if args.cache_dir:
        CACHE_DIR = args.cache_dir
    ensure_dir(CACHE_DIR)

    headers = auth_headers(_config.x_bearer_token)

    print("=" * 60)
    print(f"🎯 目标用户: {TARGET_USERNAME}")
    print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📊 每日最大抓取页数: {MAX_PAGES}")
    print("=" * 60 + "\n")
    print("📋 执行计划:")
    print(f"   预计最多请求: {MAX_PAGES} 页 / {MAX_PAGES * 100} 条")
    print(f"   请求间隔: {REQUEST_INTERVAL} 秒")
    print(f"   历史目标日期: {TARGET_DATE.strftime('%Y-%m-%d')}")
    print()
    
    # 1. 加载现有数据
    raw_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_raw_tweets.json")
    existing_tweets = []
    
    if os.path.exists(raw_file):
        try:
            existing_tweets = load_json(raw_file, default=[])
            if not isinstance(existing_tweets, list):
                raise JsonStoreError(f"原始推文文件必须是 JSON 数组: {raw_file}")
            print(f"💾 已加载现有数据: {len(existing_tweets)} 条")
        except JsonStoreError as error:
            print(f"❌ 无法安全加载现有数据: {error}")
            return 1
    else:
        print("⚠️ 未找到现有数据文件，将从头开始抓取")

    # 2. 获取用户ID
    try:
        user_id = get_user_id(TARGET_USERNAME, headers)
        print(f"✅ 用户 ID: {user_id}\n")
    except Exception as e:
        print(f"❌ 无法获取用户ID: {e}")
        return 1

    # 确定 ID 边界
    newest_id = None
    oldest_id = None
    oldest_date = None

    if existing_tweets:
        # 按ID排序（字符串ID可以字典序排序，但Twitter ID是大致随时间递增的数字）
        # 安全起见，按 created_at 排序
        existing_tweets.sort(key=lambda t: t.get("created_at", ""), reverse=True)
        
        newest_tweet = existing_tweets[0]
        oldest_tweet = existing_tweets[-1]
        
        newest_id = newest_tweet["id"]
        oldest_id = oldest_tweet["id"]
        oldest_date = parse_twitter_datetime(oldest_tweet["created_at"])
        
        print(f"📍 现有最新推文: {newest_tweet['created_at']} (ID: {newest_id})")
        print(f"📍 现有最早推文: {oldest_tweet['created_at']} (ID: {oldest_id})\n")

    # 共享配额
    remaining_pages_quota = MAX_PAGES

    # ==========================
    # 3. 阶段一：抓取新推文 (Forward)
    # ==========================
    new_tweets_forward = []
    print(f"🔄 剩余配额: {remaining_pages_quota} 页")
    
    if newest_id:
        print("📥 阶段一: 检查新发布的推文...")
        try:
            tweets, _, pages_used = fetch_tweets_generic(
                user_id, headers,
                since_id=newest_id,
                max_pages_limit=remaining_pages_quota,
                description="抓取最新推文",
            )
        except FetchError as error:
            print(f"❌ 新推文抓取失败: {error}")
            return 1
        remaining_pages_quota -= pages_used
        
        if tweets:
            print(f"✅ 发现 {len(tweets)} 条新推文！")
            new_tweets_forward = tweets
        else:
            print("✅ 没有发现更新的推文")
        print("-" * 30 + "\n")
    else:
        # 如果没有现有数据，这步跳过，直接进入历史抓取（或视为全量抓取）
        print("📥 阶段一: 无现有数据，跳过增量更新，直接开始全量抓取...\n")

    # ==========================
    # 4. 阶段二：抓取历史推文 (Backward)
    # ==========================
    new_tweets_backward = []
    # 判断是否还需要抓取历史
    need_history = True
    if oldest_date and oldest_date <= TARGET_DATE:
        print(f"✅ 现有数据已涵盖到目标日期 {TARGET_DATE.strftime('%Y-%m-%d')}，跳过历史抓取")
        need_history = False
    elif newest_id is None:
        # 如果是第一次抓取，不需要 untill_id
        pass 
    
    if remaining_pages_quota <= 0:
        print(f"⚠️ 配额已用完 ({MAX_PAGES} 页)，跳过历史抓取")
        need_history = False

    if need_history:
        print(f"📥 阶段二: 补充历史推文... (剩余配额: {remaining_pages_quota} 页)")
        try:
            tweets, reached, pages_used = fetch_tweets_generic(
                user_id, headers,
                until_id=oldest_id,  # 从已知最早的往前
                stop_date=TARGET_DATE,
                max_pages_limit=remaining_pages_quota,
                description="抓取历史推文",
            )
        except FetchError as error:
            print(f"❌ 历史推文抓取失败: {error}")
            return 1
        new_tweets_backward = tweets
        remaining_pages_quota -= pages_used
        
        if tweets:
            print(f"✅ 抓取到 {len(tweets)} 条历史推文")
        else:
            print("⚠️ 未能抓取到更多历史推文 (可能已达API限制或无更多数据)")
        print("-" * 30 + "\n")

    # ==========================
    # 5. 合并与保存
    # ==========================
    all_new_tweets = new_tweets_forward + new_tweets_backward
    
    if all_new_tweets:
        print(f"📊 总计新增抓取: {len(all_new_tweets)} 条")
        
        # 合并已有和新增数据，避免增量抓取覆盖历史记录。
        final_list = merge_tweets(existing_tweets, all_new_tweets)

        print(f"💾 保存总推文数: {len(final_list)} 条")
        
        # 写入文件
        save_json(raw_file, final_list)
            
        print(f"✅ 数据已更新至: {raw_file}")
        
    else:
        print("🎉 数据已是最新，无需更新")

    print("\n" + "=" * 60)
    print("✅ 所有任务完成！")
    print("=" * 60)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
