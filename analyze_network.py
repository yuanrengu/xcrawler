from __future__ import annotations

import argparse
import os
import re
from collections import Counter
from datetime import datetime

from xcrawler.config import load_config
from xcrawler.services.analysis_runs import (
    complete_analysis_run,
    create_analysis_run,
    record_analysis_run,
    record_failed_analysis_run,
)
from xcrawler.storage.factory import STORAGE_BACKENDS, create_store
from xcrawler.storage.json_store import load_json, save_json
from xcrawler.utils import cli_validation
from xcrawler.utils.optional_dependencies import print_missing_optional_dependency

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

_config = load_config()

TARGET_USERNAME = _config.target_username
CACHE_DIR = _config.cache_dir


def parse_args():
    parser = argparse.ArgumentParser(description="Hashtag / Mention 网络分析")
    parser.add_argument("-u", "--user", type=cli_validation.x_username, help="目标用户名")
    parser.add_argument("--cache-dir", help=f"缓存目录（默认 {CACHE_DIR}）")
    parser.add_argument("--top", type=cli_validation.positive_int, default=20, help="显示 Top N 结果（默认 20）")
    parser.add_argument("--output", help="输出目录（默认 cache/charts）")
    parser.add_argument("--storage", "--storage-backend", dest="storage_backend", choices=STORAGE_BACKENDS,
                        default=_config.storage_backend, help="运行元数据存储后端（默认 json）")
    parser.add_argument("--sqlite-path", default=_config.sqlite_path, help="SQLite 数据库路径")
    return parser.parse_args()


def extract_entities(raw_tweets):
    """从推文中提取 hashtags 和 mentions"""
    hashtag_counts = Counter()
    mention_counts = Counter()
    hashtag_mention_pairs = Counter()  # 共现关系

    for tweet in raw_tweets:
        entities = tweet.get("entities", {})
        hashtags_in_tweet = []
        mentions_in_tweet = []

        # 提取 hashtags
        for ht in entities.get("hashtags", []):
            tag = ht.get("tag", "").lower()
            if tag:
                hashtag_counts[tag] += 1
                hashtags_in_tweet.append(tag)

        # 提取 mentions
        for mention in entities.get("mentions", []):
            username = mention.get("username", "").lower()
            if username:
                mention_counts[username] += 1
                mentions_in_tweet.append(username)

        # 共现：同一条推文中的 hashtag-mention 对
        for ht in hashtags_in_tweet:
            for mn in mentions_in_tweet:
                pair = f"#{ht} ↔ @{mn}"
                hashtag_mention_pairs[pair] += 1

    return hashtag_counts, mention_counts, hashtag_mention_pairs


def extract_hashtags_from_text(raw_tweets):
    """从推文文本中提取 hashtag（entities 可能为空时的后备方案）"""
    hashtag_counts = Counter()
    for tweet in raw_tweets:
        text = tweet.get("text", "")
        tags = re.findall(r'#(\w+)', text)
        for tag in tags:
            hashtag_counts[tag.lower()] += 1
    return hashtag_counts


def print_stats(hashtag_counts, mention_counts, pair_counts, top_n):
    """打印统计结果"""
    print("🏷️  Top Hashtags:")
    if hashtag_counts:
        for tag, count in hashtag_counts.most_common(top_n):
            bar = "█" * min(count, 30)
            print(f"   #{tag:20s} {count:4d}  {bar}")
    else:
        print("   (无数据)")

    print()
    print("👤 Top Mentions:")
    if mention_counts:
        for user, count in mention_counts.most_common(top_n):
            bar = "█" * min(count, 30)
            print(f"   @{user:20s} {count:4d}  {bar}")
    else:
        print("   (无数据)")

    if pair_counts:
        print()
        print("🔗 Top Hashtag-Mention Pairs:")
        for pair, count in pair_counts.most_common(min(10, top_n)):
            print(f"   {pair:40s} {count:3d}")


def chart_hashtag_bar(hashtag_counts, output_dir, username, top_n=20):
    """生成 hashtag 柱状图"""
    top = hashtag_counts.most_common(top_n)
    if not top:
        return None

    tags = [f"#{t}" for t, _ in top]
    counts = [c for _, c in top]

    fig, ax = plt.subplots(figsize=(10, max(5, len(tags) * 0.4)))
    y_pos = range(len(tags))
    ax.barh(y_pos, counts, color='#1976D2', edgecolor='white')
    ax.set_yticks(y_pos)
    ax.set_yticklabels(tags, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlabel('Frequency', fontsize=12)
    ax.set_title(f'@{username} - Top {top_n} Hashtags', fontsize=14)
    ax.grid(axis='x', alpha=0.3)

    plt.tight_layout()
    path = os.path.join(output_dir, f"{username}_hashtags.png")
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"   ✅ Hashtag 柱状图: {path}")
    return path


def chart_mention_bar(mention_counts, output_dir, username, top_n=20):
    """生成 mention 柱状图"""
    top = mention_counts.most_common(top_n)
    if not top:
        return None

    users = [f"@{u}" for u, _ in top]
    counts = [c for _, c in top]

    fig, ax = plt.subplots(figsize=(10, max(5, len(users) * 0.4)))
    y_pos = range(len(users))
    ax.barh(y_pos, counts, color='#FF7043', edgecolor='white')
    ax.set_yticks(y_pos)
    ax.set_yticklabels(users, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlabel('Frequency', fontsize=12)
    ax.set_title(f'@{username} - Top {top_n} Mentions', fontsize=14)
    ax.grid(axis='x', alpha=0.3)

    plt.tight_layout()
    path = os.path.join(output_dir, f"{username}_mentions.png")
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"   ✅ Mention 柱状图: {path}")
    return path


def save_results(username, hashtag_counts, mention_counts, pair_counts, cache_dir):
    """保存分析结果到 JSON"""
    result = {
        "username": username,
        "analysis_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "hashtags": dict(hashtag_counts.most_common(100)),
        "mentions": dict(mention_counts.most_common(100)),
        "hashtag_mention_pairs": dict(pair_counts.most_common(50))
    }

    path = os.path.join(cache_dir, f"{username}_network.json")
    save_json(path, result)
    print(f"\n💾 结果已保存: {path}")
    return path


def main():
    global TARGET_USERNAME, CACHE_DIR

    args = parse_args()
    if args.user:
        TARGET_USERNAME = args.user
    if args.cache_dir:
        CACHE_DIR = args.cache_dir
    output_dir = args.output or os.path.join(CACHE_DIR, "charts")
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60)
    print(f"🏷️  Hashtag / Mention 网络分析: @{TARGET_USERNAME}")
    print("=" * 60 + "\n")

    # 加载数据
    raw_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_raw_tweets.json")
    raw_tweets = load_json(raw_file)
    if raw_tweets is None:
        print(f"❌ 找不到原始推文: {raw_file}")
        print("   请先运行 main.py 抓取数据")
        return 1

    if not MATPLOTLIB_AVAILABLE:
        print_missing_optional_dependency("matplotlib", "viz", feature="网络分析图表")
        return 1

    model = _config.llm_model
    store = create_store(CACHE_DIR, backend=args.storage_backend, sqlite_path=args.sqlite_path)
    run = create_analysis_run(
        username=TARGET_USERNAME,
        analysis_type="network",
        model=model,
        input_range={"raw_tweets": len(raw_tweets)},
    )

    try:
        print(f"📂 已加载 {len(raw_tweets)} 条推文\n")

        print("🔍 提取 Hashtags 和 Mentions...")
        hashtag_counts, mention_counts, pair_counts = extract_entities(raw_tweets)

        if not hashtag_counts:
            print("   ⚠️ entities 字段为空，从文本中提取 hashtag...")
            hashtag_counts = extract_hashtags_from_text(raw_tweets)

        print()
        print_stats(hashtag_counts, mention_counts, pair_counts, args.top)

        print("\n🎨 生成图表...")
        chart_hashtag_bar(hashtag_counts, output_dir, TARGET_USERNAME, args.top)
        chart_mention_bar(mention_counts, output_dir, TARGET_USERNAME, args.top)

        save_results(TARGET_USERNAME, hashtag_counts, mention_counts, pair_counts, CACHE_DIR)
        record_analysis_run(store, complete_analysis_run(run))
    except Exception as error:
        record_failed_analysis_run(store, run, error)
        print(f"❌ 网络分析失败: {error}")
        return 1

    print("\n" + "=" * 60)
    print("✅ 分析完成！")
    print(f"   Hashtags: {len(hashtag_counts)} 个")
    print(f"   Mentions: {len(mention_counts)} 个")
    print(f"   Pairs: {len(pair_counts)} 个")
    print("=" * 60 + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
