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
from xcrawler.services.records import normalize_translated_tweets
_ = load_dotenv()

TARGET_USERNAME = os.getenv("TARGET_USERNAME", "MiracleHe")
CACHE_DIR = "cache"


def parse_args():
    parser = argparse.ArgumentParser(description="推文情感分析：批量打分 + 趋势图")
    parser.add_argument("-u", "--user", help="目标用户名")
    parser.add_argument("--cache-dir", help=f"缓存目录（默认 {CACHE_DIR}）")
    parser.add_argument("--output", help="输出目录（默认 cache/charts）")
    parser.add_argument("--top", type=int, default=10, help="显示 Top N 正/负面推文")
    return parser.parse_args()


def batch_sentiment(texts: list[str], client, model: str) -> list[str]:
    """批量情感打分：positive / neutral / negative"""
    import re

    BATCH = 20
    results = ["neutral"] * len(texts)

    for start in range(0, len(texts), BATCH):
        batch = texts[start:start + BATCH]
        numbered = "\n".join(f"[{i+1}] {t}" for i, t in enumerate(batch))

        prompt = f"""对以下 {len(batch)} 条推文做情感分类。
每行输出一个结果，格式为 [编号] positive/neutral/negative。
只输出结果，不要解释。

推文：
{numbered}"""

        try:
            r = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )
            response = r.choices[0].message.content.strip()
            for line in response.split("\n"):
                line = line.strip()
                m = re.match(r'^\[?(\d+)\]?\s*[\.:：]?\s*(positive|neutral|negative)', line, re.I)
                if m:
                    idx = int(m.group(1)) - 1
                    if 0 <= idx < len(batch):
                        results[start + idx] = m.group(2).lower()
        except Exception as e:
            print(f"   ⚠️ 批次情感分析失败: {e}")

    return results


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
    labels = ['Positive', 'Neutral', 'Negative']
    sizes = [counts.get('positive', 0), counts.get('neutral', 0), counts.get('negative', 0)]
    colors = ['#4CAF50', '#9E9E9E', '#F44336']

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
    from openai import OpenAI
    client = OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    )
    model = os.getenv("LLM_MODEL", "deepseek-chat")

    # 批量情感打分
    print(f"🧠 批量情感打分（{len(texts)} 条）...")
    sentiments = batch_sentiment(texts, client, model)

    # 统计
    counts = Counter(sentiments)
    total = len(sentiments)
    print(f"\n📊 情感分布:")
    print(f"   ✅ Positive: {counts.get('positive', 0)} ({counts.get('positive', 0)/total*100:.1f}%)")
    print(f"   😐 Neutral:  {counts.get('neutral', 0)} ({counts.get('neutral', 0)/total*100:.1f}%)")
    print(f"   ❌ Negative: {counts.get('negative', 0)} ({counts.get('negative', 0)/total*100:.1f}%)")

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
    chart_sentiment_timeline(translated_data, sentiments, output_dir, TARGET_USERNAME, tz_offset)
    chart_sentiment_pie(sentiments, output_dir, TARGET_USERNAME)

    # 保存结果
    result = {
        "username": TARGET_USERNAME,
        "analysis_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "total": total,
        "distribution": dict(counts),
        "positive_ratio": round(counts.get("positive", 0) / total, 3),
        "negative_ratio": round(counts.get("negative", 0) / total, 3),
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
    print(f"\n💾 结果已保存: {result_file}")

    print("\n" + "=" * 60)
    print("✅ 情感分析完成！")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
