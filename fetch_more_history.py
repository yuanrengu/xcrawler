"""
增量抓取脚本
功能：
1. 抓取比现有数据更新的推文（Forward Fetching）
2. 抓取比现有数据更早的推文（Backward Fetching），直到到达 TARGET_DATE
"""
from __future__ import annotations

import argparse
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime

import requests

from xcrawler.clients import x_api
from xcrawler.clients.retry import RequestAttemptsError, request_json_with_retries
from xcrawler.clients.x_api import auth_headers
from xcrawler.config import load_config
from xcrawler.paths import ensure_dir
from xcrawler.services.tweets import merge_tweets, validate_raw_tweets
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

    def __init__(self, message: str, *, requests_used: int = 0, retries: int = 0, stop_reason: str = "error"):
        super().__init__(message)
        self.requests_used = requests_used
        self.retries = retries
        self.stop_reason = stop_reason


@dataclass
class FetchBatchResult:
    tweets: list[dict]
    reached_target: bool
    data_pages: int
    requests_used: int
    retries: int
    stop_reason: str
    complete: bool
    has_more: bool
    can_continue: bool = True

    def to_dict(self) -> dict:
        result = asdict(self)
        result["tweet_count"] = len(self.tweets)
        result.pop("tweets")
        return result


def parse_args():
    parser = argparse.ArgumentParser(description="智能增量抓取：双向同步（新推文 + 历史补全）")
    parser.add_argument("-u", "--user", type=cli_validation.x_username, help="目标用户名")
    parser.add_argument(
        "--pages",
        type=cli_validation.positive_int,
        help=f"本次 HTTP 请求预算（Forward/Backward/重试共享，默认 {MAX_PAGES}）",
    )
    parser.add_argument("--target-date", help="历史抓取目标日期，格式 YYYY-MM-DD")
    parser.add_argument("--interval", type=cli_validation.non_negative_int, help=f"请求间隔秒数（默认 {REQUEST_INTERVAL}）")
    parser.add_argument("--cache-dir", help=f"缓存目录（默认 {CACHE_DIR}）")
    return parser.parse_args()


def get_user_id(username, headers):
    """获取用户ID"""
    return x_api.get_user_id(username, headers, request_get=requests.get)


def save_fetch_status(
    cache_dir: str,
    username: str,
    *,
    status: str,
    forward: FetchBatchResult | None = None,
    backward: FetchBatchResult | None = None,
    error: str | None = None,
    error_requests: int = 0,
    error_retries: int = 0,
    error_stop_reason: str | None = None,
    has_more_override: bool | None = None,
) -> None:
    phase_results = [result for result in (forward, backward) if result is not None]
    known_has_more = any(result.has_more for result in phase_results)
    has_more: bool | None
    if has_more_override is not None:
        has_more = has_more_override
    elif known_has_more:
        has_more = True
    elif error is not None:
        has_more = None
    else:
        has_more = False
    save_json(
        os.path.join(cache_dir, f"{username}_fetch_status.json"),
        {
            "username": username,
            "mode": "incremental",
            "status": status,
            "complete": status == "success",
            "has_more": has_more,
            "completed_at": datetime.now().isoformat(timespec="seconds"),
            "forward": forward.to_dict() if forward else None,
            "backward": backward.to_dict() if backward else None,
            "forward_complete": forward.complete if forward else None,
            "backward_complete": backward.complete if backward else None,
            "requests_used": (forward.requests_used if forward else 0) + (
                backward.requests_used if backward else 0
            ) + error_requests,
            "data_pages": (forward.data_pages if forward else 0) + (
                backward.data_pages if backward else 0
            ),
            "retries": (forward.retries if forward else 0) + (backward.retries if backward else 0) + error_retries,
            "error": error,
            "error_stop_reason": error_stop_reason,
        },
    )


def fetch_tweets_generic(
    user_id,
    headers,
    since_id=None,
    until_id=None,
    stop_date=None,
    max_pages_limit=MAX_PAGES,
    description="抓取",
    max_retries=MAX_RETRIES,
    request_budget=None,
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
    :return: 结构化抓取结果，区分数据页、真实请求、重试和停止原因
    """
    url = f"https://api.twitter.com/2/users/{user_id}/tweets"
    params = {
        "max_results": 100,
        "tweet.fields": "created_at,entities",
        "exclude": "retweets,replies",
    }
    
    if until_id:
        params["until_id"] = until_id
    if since_id:
        params["since_id"] = since_id

    if max_pages_limit < 1:
        raise ValueError("max_pages_limit 必须大于等于 1")

    all_tweets = []
    reached_target = False
    data_pages = 0
    requests_used = 0
    retries = 0
    request_budget = request_budget if request_budget is not None else max_pages_limit * max_retries
    if request_budget < 1:
        raise ValueError("request_budget 必须大于等于 1")
    seen_tokens: set[str] = set()
    next_token: str | None = None
    
    print(f"🚀 {description} (最大页数限制: {max_pages_limit})...")
    if since_id:
        print(f"   📍 范围: ID {since_id} 之后 (新推文)")
    if until_id:
        print(f"   📍 范围: ID {until_id} 之前 (历史推文)")

    page = 0
    while data_pages < max_pages_limit and requests_used < request_budget:
        try:
            attempt_result = request_json_with_retries(
                url,
                headers=headers,
                params=params,
                request_get=requests.get,
                max_retries=max_retries,
                request_budget=request_budget - requests_used,
                page_number=page + 1,
                max_rate_limit_wait=MAX_RATE_LIMIT_WAIT,
                sleep=time.sleep,
            )
        except RequestAttemptsError as error:
            raise FetchError(
                str(error),
                requests_used=requests_used + error.requests_used,
                retries=retries + error.retries,
                stop_reason=error.stop_reason,
            ) from error
        requests_used += attempt_result.requests_used
        retries += attempt_result.retries
        response = attempt_result.response
        data = attempt_result.data

        try:
            page_result = x_api.validate_timeline_page_response(data, page_number=page + 1)
            page_tweets = page_result.tweets
            if not page_tweets:
                print(f"📭 第 {page + 1} 页无数据 (本批次结束)")
                return FetchBatchResult(
                    tweets=all_tweets,
                    reached_target=reached_target,
                    data_pages=data_pages,
                    requests_used=requests_used,
                    retries=retries,
                    stop_reason="no_data",
                    complete=True,
                    has_more=False,
                )

            page_tweets = validate_raw_tweets(page_tweets, source=f"X API page {page + 1}")

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
            data_pages += 1
            
            # 获取本页最早时间
            oldest_in_page = parse_twitter_datetime(page_tweets[-1]["created_at"])
            kept_note = f"，保留 {len(kept_tweets)} 条" if stop_date and len(kept_tweets) != len(page_tweets) else ""
            print(f"📄 第 {page + 1} 页: {len(page_tweets)}条{kept_note} | 最早: {oldest_in_page.strftime('%Y-%m-%d')} | 累计: {len(all_tweets)}条")
            
            # 仅在向历史抓取时检查日期停止条件
            if reached_target:
                print(f"✅ 已到达目标日期 {stop_date.strftime('%Y-%m-%d')}！")
                return FetchBatchResult(
                    tweets=all_tweets,
                    reached_target=True,
                    data_pages=data_pages,
                    requests_used=requests_used,
                    retries=retries,
                    stop_reason="target_date",
                    complete=True,
                    has_more=False,
                )

            token = page_result.next_token
            if token is None:
                print("✅ 已抓取该区间所有推文")
                return FetchBatchResult(
                    tweets=all_tweets,
                    reached_target=False,
                    data_pages=data_pages,
                    requests_used=requests_used,
                    retries=retries,
                    stop_reason="no_next_token",
                    complete=True,
                    has_more=False,
                )
            if token in seen_tokens:
                raise FetchError(
                    f"第 {page + 1} 页出现重复 next_token，分页无法继续",
                    requests_used=requests_used,
                    retries=retries,
                    stop_reason="pagination_token_cycle",
                )
            seen_tokens.add(token)
            next_token = token

            # 检查剩余配额
            remaining = response.headers.get("x-rate-limit-remaining")
            if remaining:
                remaining_count = int(remaining)
                if remaining_count % 10 == 0:  # 减少日志输出
                    print(f"   剩余配额: {remaining} 次")
                if remaining_count < 2:
                    print("⚠️ 配额即将耗尽，暂停抓取")
                    return FetchBatchResult(
                        tweets=all_tweets,
                        reached_target=False,
                        data_pages=data_pages,
                        requests_used=requests_used,
                        retries=retries,
                        stop_reason="rate_limit_low",
                        can_continue=False,
                        complete=False,
                        has_more=True,
                    )

            params["pagination_token"] = token
            page += 1

            if data_pages < max_pages_limit and requests_used < request_budget:
                time.sleep(REQUEST_INTERVAL)

        except x_api.TimelinePageError as error:
            raise FetchError(
                str(error),
                requests_used=requests_used,
                retries=retries,
                stop_reason="invalid_response",
            ) from error
        except FetchError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise FetchError(
                f"第 {page + 1} 页推文数据结构无效",
                requests_used=requests_used,
                retries=retries,
                stop_reason="invalid_response",
            ) from error

    stop_reason = "request_budget" if requests_used >= request_budget else "page_limit"
    return FetchBatchResult(
        tweets=all_tweets,
        reached_target=reached_target,
        data_pages=data_pages,
        requests_used=requests_used,
        retries=retries,
        stop_reason=stop_reason,
        complete=False,
        has_more=next_token is not None,
    )


def main():
    global TARGET_USERNAME, MAX_PAGES, TARGET_DATE, REQUEST_INTERVAL, CACHE_DIR

    args = parse_args()
    if args.user:
        TARGET_USERNAME = args.user
    if args.pages is not None:
        MAX_PAGES = args.pages
    if args.cache_dir:
        CACHE_DIR = args.cache_dir
    ensure_dir(CACHE_DIR)
    if args.target_date:
        try:
            TARGET_DATE = datetime.strptime(args.target_date, "%Y-%m-%d")
        except ValueError:
            message = f"--target-date 格式错误: {args.target_date}，必须为 YYYY-MM-DD"
            print(f"❌ {message}")
            save_fetch_status(
                CACHE_DIR,
                TARGET_USERNAME,
                status="failed",
                error=message,
                error_stop_reason="invalid_target_date",
            )
            return 1
    if args.interval is not None:
        REQUEST_INTERVAL = args.interval

    try:
        headers = auth_headers(_config.x_bearer_token)
    except RuntimeError as error:
        print(f"❌ 配置错误: {error}")
        save_fetch_status(
            CACHE_DIR,
            TARGET_USERNAME,
            status="failed",
            error=str(error),
            error_stop_reason="missing_secret",
        )
        return 1

    print("=" * 60)
    print(f"🎯 目标用户: {TARGET_USERNAME}")
    print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📊 本次 HTTP 请求预算: {MAX_PAGES}")
    print("=" * 60 + "\n")
    print("📋 执行计划:")
    print(f"   最多 HTTP 请求: {MAX_PAGES} 次（包含重试）")
    print(f"   理论最大数据量: {MAX_PAGES * 100} 条（无重试且每页满载时）")
    print(f"   请求间隔: {REQUEST_INTERVAL} 秒")
    print(f"   历史目标日期: {TARGET_DATE.strftime('%Y-%m-%d')}")
    print()
    
    # 1. 加载现有数据
    raw_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_raw_tweets.json")
    existing_tweets = []
    
    if os.path.exists(raw_file):
        try:
            existing_tweets = validate_raw_tweets(load_json(raw_file, default=[]), source=raw_file)
            print(f"💾 已加载现有数据: {len(existing_tweets)} 条")
        except (JsonStoreError, ValueError) as error:
            print(f"❌ 无法安全加载现有数据: {error}")
            save_fetch_status(
                CACHE_DIR,
                TARGET_USERNAME,
                status="failed",
                error=str(error),
                error_stop_reason="invalid_existing_data",
            )
            return 1
    else:
        print("⚠️ 未找到现有数据文件，将从头开始抓取")

    # 2. 获取用户ID
    try:
        user_id = get_user_id(TARGET_USERNAME, headers)
        print(f"✅ 用户 ID: {user_id}\n")
    except Exception as error:
        print(f"❌ 无法获取用户ID: {error}")
        save_fetch_status(
            CACHE_DIR,
            TARGET_USERNAME,
            status="failed",
            error=str(error),
            error_stop_reason="user_lookup_failed",
        )
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
    forward_result = None
    backward_result = None
    print(f"🔄 剩余配额: {remaining_pages_quota} 页")
    
    if newest_id:
        print("📥 阶段一: 检查新发布的推文...")
        try:
            forward_result = fetch_tweets_generic(
                user_id, headers,
                since_id=newest_id,
                max_pages_limit=remaining_pages_quota,
                request_budget=remaining_pages_quota,
                description="抓取最新推文",
            )
        except FetchError as error:
            print(f"❌ 新推文抓取失败: {error}")
            save_fetch_status(
                CACHE_DIR,
                TARGET_USERNAME,
                status="failed",
                error=str(error),
                error_requests=error.requests_used,
                error_retries=error.retries,
                error_stop_reason=error.stop_reason,
            )
            return 1
        remaining_pages_quota -= forward_result.requests_used
        tweets = forward_result.tweets
        
        if tweets:
            print(f"✅ 发现 {len(tweets)} 条新推文！")
            new_tweets_forward = tweets
            existing_tweets = merge_tweets(existing_tweets, new_tweets_forward)
            save_json(raw_file, existing_tweets)
            print(f"💾 Forward 阶段已安全保存: {len(existing_tweets)} 条")
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
    history_required = not (oldest_date and oldest_date <= TARGET_DATE)
    need_history = history_required
    if oldest_date and oldest_date <= TARGET_DATE:
        print(f"✅ 现有数据已涵盖到目标日期 {TARGET_DATE.strftime('%Y-%m-%d')}，跳过历史抓取")
        need_history = False

    if remaining_pages_quota <= 0:
        print(f"⚠️ 配额已用完 ({MAX_PAGES} 页)，跳过历史抓取")
        need_history = False
    if forward_result and not forward_result.can_continue:
        print(f"⚠️ Forward 阶段因 {forward_result.stop_reason} 停止，跳过历史抓取")
        need_history = False

    if need_history:
        print(f"📥 阶段二: 补充历史推文... (剩余配额: {remaining_pages_quota} 页)")
        try:
            backward_result = fetch_tweets_generic(
                user_id, headers,
                until_id=oldest_id,  # 从已知最早的往前
                stop_date=TARGET_DATE,
                max_pages_limit=remaining_pages_quota,
                request_budget=remaining_pages_quota,
                description="抓取历史推文",
            )
        except FetchError as error:
            print(f"❌ 历史推文抓取失败: {error}")
            status = "partial" if forward_result is not None else "failed"
            save_fetch_status(
                CACHE_DIR,
                TARGET_USERNAME,
                status=status,
                forward=forward_result,
                error=str(error),
                error_requests=error.requests_used,
                error_retries=error.retries,
                error_stop_reason=error.stop_reason,
            )
            return 2 if status == "partial" else 1
        tweets = backward_result.tweets
        new_tweets_backward = tweets
        remaining_pages_quota -= backward_result.requests_used
        
        if tweets:
            print(f"✅ 抓取到 {len(tweets)} 条历史推文")
            existing_tweets = merge_tweets(existing_tweets, new_tweets_backward)
            save_json(raw_file, existing_tweets)
            print(f"💾 Backward 阶段已安全保存: {len(existing_tweets)} 条")
        else:
            print("⚠️ 未能抓取到更多历史推文 (可能已达API限制或无更多数据)")
        print("-" * 30 + "\n")

    history_skipped_incomplete = history_required and backward_result is None
    is_partial = bool(
        (forward_result and not forward_result.complete)
        or (backward_result and not backward_result.complete)
        or history_skipped_incomplete
    )
    if not new_tweets_forward and not new_tweets_backward:
        if is_partial:
            print("⚠️ 本次未保存新数据，但同步范围尚未完整")
        else:
            print("🎉 数据已是最新，无需更新")

    save_fetch_status(
        CACHE_DIR,
        TARGET_USERNAME,
        status="partial" if is_partial else "success",
        forward=forward_result,
        backward=backward_result,
        has_more_override=True if history_skipped_incomplete else None,
    )

    print("\n" + "=" * 60)
    print("✅ 所有任务完成！" if not is_partial else "⚠️ 本次在预算/配额边界停止，已记录 partial 状态")
    print("=" * 60)
    return 2 if is_partial else 0

if __name__ == "__main__":
    raise SystemExit(main())
