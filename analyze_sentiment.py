"""
情感分析脚本
对翻译后的推文进行情感打分（正/中/负），生成趋势图
"""
import os
import json
import argparse
from datetime import datetime, timedelta
from collections import Counter, defaultdict

from dotenv import load_dotenv
from xcrawler.llm.provider import DeepSeekProvider
from xcrawler.services.analysis_runs import complete_analysis_run, create_analysis_run, partial_analysis_run, record_analysis_run
from xcrawler.services.records import normalize_translated_tweets
from xcrawler.storage.json_store import JsonStore
from xcrawler.utils import cli_validation
_ = load_dotenv()

TARGET_USERNAME = os.getenv("TARGET_USERNAME", "MiracleHe")
CACHE_DIR = "cache"


def parse_sentiment_response(response: str, expected_count: int) -> list[str]:
    """Parse a fully numbered sentiment response."""
    import re

    lines = [line.strip() for line in response.splitlines() if line.strip()]
    if not lines:
        return []

    parsed: dict[int, str] = {}
    for line in lines:
        match = re.match(r"^(?:\[(\d+)\]|(\d+)[\.\):：])\s*[\.\):：]?\s*(positive|neutral|negative)\s*$", line, re.I)
        if not match:
            return []
        idx = int(match.group(1) or match.group(2))
        sentiment = match.group(3).lower()
        if idx < 1 or idx > expected_count or idx in parsed:
            return []
        parsed[idx] = sentiment

    if set(parsed) != set(range(1, expected_count + 1)):
        return []
    return [parsed[i] for i in range(1, expected_count + 1)]


def parse_args():
    parser = argparse.ArgumentParser(description="推文情感分析：批量打分 + 趋势图")
    parser.add_argument("-u", "--user", help="目标用户名")
    parser.add_argument("--cache-dir", help=f"缓存目录（默认 {CACHE_DIR}）")
    parser.add_argument("--output", help="输出目录（默认 cache/charts）")
    parser.add_argument("--top", type=cli_validation.positive_int, default=10, help="显示 Top N 正/负面推文")
    return parser.parse_args()


def batch_sentiment(texts: list[str], llm, model: str) -> tuple[list[str], dict[str, int]]:
    """批量情感打分：positive / neutral / negative"""
    BATCH = 20
    results = ["unknown"] * len(texts)
    stats = {"batches": 0, "failed_batches": 0, "total_tokens": 0}

    for start in range(0, len(texts), BATCH):
        stats["batches"] += 1
        batch = texts[start:start + BATCH]
        numbered = "\n".join(f"[{i+1}] {t}" for i, t in enumerate(batch))

        prompt = f"""对以下 {len(batch)} 条推文做情感分类。
每行输出一个结果，格式为 [编号] positive/neutral/negative。
只输出结果，不要解释。

推文：
{numbered}"""

        try:
            r = llm.chat([{"role": "user", "content": prompt}], model=model, temperature=0)
            if r.total_tokens is not None:
                stats["total_tokens"] += r.total_tokens
            parsed = parse_sentiment_response(r.content, len(batch))
            if len(parsed) != len(batch):
                stats["failed_batches"] += 1
                print("   ⚠️ 批次情感分析响应不完整，标记为 unknown")
                continue
            for idx, sentiment in enumerate(parsed):
                results[start + idx] = sentiment
        except Exception as e:
            stats["failed_batches"] += 1
            print(f"   ⚠️ 批次情感分析失败: {e}")

    return results, stats


def create_provider():
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("未检测到 DEEPSEEK_API_KEY，无法执行情感分析")
    return DeepSeekProvider(
        api_key=api_key,
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    )


def chart_sentiment_timeline(translated_data, sentiments, output_dir, username, tz_offset):
    """生成情感时间趋势图"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    # 按月聚合
    monthly = defaultdict(lambda: Counter())
    for item, sent in zip(translated_data, sentiments):
        try:
            dt = datetime.strptime(item["created_at"], "%Y-%m-%dT%H:%M:%S.%fZ")
        except ValueError:
            try:
                dt = datetime.strptime(item["created_at"], "%Y-%m-%dT%H:%M:%SZ")
            except:
                continue
        month_key = dt.strftime("%Y-%m")
        monthly[month_key][sent] += 1

    if not monthly:
        return None

    months = sorted(monthly.keys())
    pos_counts = [monthly[m].get("positive", 0) for m in months]
    neg_counts = [monthly[m].get("negative", 0) for m in months]
    neu_counts = [monthly[m].get("neutral", 0) for m in months]

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(months, pos_counts, color='#4CAF50', label='Positive')
    ax.bar(months, neu_counts, bottom=pos_counts, color='#9E9E9E', label='Neutral')
    bottom2 = [p + n for p, n in zip(pos_counts, neu_counts)]
    ax.bar(months, neg_counts, bottom=bottom2, color='#F44336', label='Negative')
    ax.set_xlabel('Month')
    ax.set_ylabel('Tweets')
    ax.set_title(f'@{username} - Sentiment Timeline')
    ax.legend()
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()

    path = os.path.join(output_dir, f"{username}_sentiment.png")
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"   ✅ 情感趋势图: {path}")
    return path


def chart_sentiment_pie(sentiments, output_dir, username):
    """生成情感分布饼图"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    counts = Counter(sentiments)
    labels = ['Positive', 'Neutral', 'Negative', 'Unknown']
    sizes = [counts.get('positive', 0), counts.get('neutral', 0), counts.get('negative', 0), counts.get('unknown', 0)]
    colors = ['#4CAF50', '#9E9E9E', '#F44336', '#BDBDBD']

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.pie(sizes, labels=labels, autopct='%1.1f%%', colors=colors, startangle=90)
    ax.set_title(f'@{username} - Sentiment Distribution')

    plt.tight_layout()
    path = os.path.join(output_dir, f"{username}_sentiment_pie.png")
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"   ✅ 情感分布图: {path}")
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
    print(f"😊 情感分析: @{TARGET_USERNAME}")
    print("=" * 60 + "\n")

    # 加载翻译数据
    translated_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_translated.json")
    if not os.path.exists(translated_file):
        print(f"❌ 找不到翻译文件: {translated_file}")
        print("   请先运行 main.py")
        return

    with open(translated_file, 'r', encoding='utf-8') as f:
        translated_data = normalize_translated_tweets(json.load(f))

    sentiment_inputs = [item for item in translated_data if item.get("translated")]
    texts = [item["translated"] for item in sentiment_inputs]
    print(f"📂 已加载 {len(texts)} 条翻译文本\n")

    if len(texts) < 5:
        print("⚠️ 数据量过少，无法有效分析")
        return

    # 初始化 LLM
    provider = create_provider()
    model = os.getenv("LLM_MODEL", "deepseek-chat")
    store = JsonStore(CACHE_DIR)
    run = create_analysis_run(
        username=TARGET_USERNAME,
        analysis_type="sentiment",
        model=model,
        params={"top": args.top},
        input_range={"translated_records": len(translated_data), "texts": len(texts), "batch_size": 20},
        config={"provider": provider.name},
    )

    print("📋 执行计划:")
    print(f"   输入文本: {len(texts)} 条")
    print(f"   预计 LLM 批次: {(len(texts) + 19) // 20} 批")
    print("   失败策略: 失败或未解析项标记为 unknown，不计入 neutral")
    print()

    # 批量情感打分
    print(f"🧠 批量情感打分（{len(texts)} 条）...")
    sentiments, run_stats = batch_sentiment(texts, provider, model)
    run.llm_calls = run_stats["batches"]
    run.failed_batches = run_stats["failed_batches"]
    run.total_tokens = run_stats["total_tokens"] or None

    # 统计
    counts = Counter(sentiments)
    total = len(sentiments)
    print(f"\n📊 情感分布:")
    print(f"   ✅ Positive: {counts.get('positive', 0)} ({counts.get('positive', 0)/total*100:.1f}%)")
    print(f"   😐 Neutral:  {counts.get('neutral', 0)} ({counts.get('neutral', 0)/total*100:.1f}%)")
    print(f"   ❌ Negative: {counts.get('negative', 0)} ({counts.get('negative', 0)/total*100:.1f}%)")
    if counts.get("unknown", 0):
        print(f"   ⚠️ Unknown:  {counts.get('unknown', 0)} ({counts.get('unknown', 0)/total*100:.1f}%)")

    # Top 正面/负面推文
    pos_tweets = [(item, s) for item, s in zip(sentiment_inputs, sentiments) if s == "positive"]
    neg_tweets = [(item, s) for item, s in zip(sentiment_inputs, sentiments) if s == "negative"]

    if pos_tweets:
        print(f"\n😊 Top {min(args.top, len(pos_tweets))} 正面推文:")
        for item, _ in pos_tweets[:args.top]:
            t = item["translated"]
            print(f"   • {t[:60]}{'...' if len(t) > 60 else ''}")

    if neg_tweets:
        print(f"\n😔 Top {min(args.top, len(neg_tweets))} 负面推文:")
        for item, _ in neg_tweets[:args.top]:
            t = item["translated"]
            print(f"   • {t[:60]}{'...' if len(t) > 60 else ''}")

    # 生成图表
    print(f"\n🎨 生成图表...")
    tz_offset = float(os.getenv("TIMEZONE_OFFSET", "9"))
    chart_sentiment_timeline(sentiment_inputs, sentiments, output_dir, TARGET_USERNAME, tz_offset)
    chart_sentiment_pie(sentiments, output_dir, TARGET_USERNAME)

    # 保存结果
    result = {
        "username": TARGET_USERNAME,
        "analysis_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "total": total,
        "distribution": dict(counts),
        "positive_ratio": round(counts.get("positive", 0) / total, 3),
        "negative_ratio": round(counts.get("negative", 0) / total, 3),
        "unknown_ratio": round(counts.get("unknown", 0) / total, 3),
        "failed_batches": run_stats["failed_batches"],
        "items": [
            {
                "tweet_id": item.get("tweet_id"),
                "created_at": item.get("created_at"),
                "sentiment": sentiment,
                "translated": item.get("translated", ""),
            }
            for item, sentiment in zip(sentiment_inputs, sentiments)
        ],
    }
    result_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_sentiment.json")
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    if run_stats["failed_batches"]:
        record_analysis_run(store, partial_analysis_run(run, failed_batches=run_stats["failed_batches"]))
    else:
        record_analysis_run(store, complete_analysis_run(run))
    print(f"\n💾 结果已保存: {result_file}")

    print("\n" + "=" * 60)
    print("✅ 情感分析完成！")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
