from __future__ import annotations

"""
数据可视化脚本
从缓存数据生成图表：24小时热力图、语言分布、兴趣标签、时间趋势
"""
import argparse
import html
import os
from collections import Counter
from datetime import datetime, timedelta

from xcrawler.config import load_config
from xcrawler.services.evidence import build_evidence_map, render_evidence_html
from xcrawler.storage.json_store import load_json
from xcrawler.utils.optional_dependencies import print_missing_optional_dependency
from xcrawler.utils.time import parse_twitter_datetime

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


def _parse_dt(dt_str: str) -> datetime:
    """解析 Twitter 时间戳，兼容有/无微秒"""
    return parse_twitter_datetime(dt_str)


def parse_args():
    parser = argparse.ArgumentParser(description="数据可视化：生成分析图表")
    parser.add_argument("-u", "--user", help="目标用户名")
    parser.add_argument("--cache-dir", help=f"缓存目录（默认 {CACHE_DIR}）")
    parser.add_argument("--output", help="输出目录（默认 cache/charts）")
    parser.add_argument(
        "--format",
        choices=["png", "html"],
        default="html",
        help="输出格式：png 仅生成图表，html 生成图表和 HTML 报告（默认）",
    )
    parser.add_argument("--include-sensitive-events", action="store_true",
                        help="在 HTML 报告中展示敏感事件证据。默认隐藏。")
    return parser.parse_args()


def load_data(username, cache_dir):
    """加载分析所需的数据"""
    raw_file = os.path.join(cache_dir, f"{username}_raw_tweets.json")
    translated_file = os.path.join(cache_dir, f"{username}_translated.json")
    behavior_file = os.path.join(cache_dir, f"{username}_behavior.json")
    profile_file = os.path.join(cache_dir, f"{username}_interest_profile.json")

    data = {}
    for key, path in [("raw", raw_file), ("translated", translated_file),
                       ("behavior", behavior_file), ("profile", profile_file)]:
        data[key] = load_json(path)
    return data


def chart_hourly_heatmap(raw_tweets, output_dir, username):
    """生成24小时发推热力图"""
    tz_offset = _config.timezone_offset

    hour_counts = Counter()
    weekday_counts = Counter()

    for tweet in raw_tweets:
        if "created_at" not in tweet:
            continue
        dt_utc = _parse_dt(tweet["created_at"])
        dt_local = dt_utc + timedelta(hours=tz_offset)
        hour_counts[dt_local.hour] += 1
        weekday_counts[dt_local.weekday()] += 1

    # 24小时柱状图
    fig, ax = plt.subplots(figsize=(12, 5))
    hours = list(range(24))
    counts = [hour_counts.get(h, 0) for h in hours]
    colors = ['#2196F3' if c > 0 else '#E0E0E0' for c in counts]
    max_c = max(counts) if counts else 1
    colors = [plt.cm.Blues(c / max_c) if c > 0 else '#E0E0E0' for c in counts]

    ax.bar(hours, counts, color=colors, edgecolor='white', linewidth=0.5)
    ax.set_xlabel('Hour', fontsize=12)
    ax.set_ylabel('Tweets', fontsize=12)
    ax.set_title(f'@{username} - 24h Tweet Distribution (UTC+{int(tz_offset)})', fontsize=14)
    ax.set_xticks(hours)
    ax.set_xticklabels([f'{h:02d}' for h in hours])
    ax.grid(axis='y', alpha=0.3)

    # 标注高峰
    if counts:
        top3 = sorted(range(24), key=lambda h: hour_counts.get(h, 0), reverse=True)[:3]
        for h in top3:
            if hour_counts.get(h, 0) > 0:
                ax.annotate(f'{hour_counts[h]}', xy=(h, hour_counts[h]),
                           ha='center', va='bottom', fontweight='bold', color='#D32F2F')

    plt.tight_layout()
    path = os.path.join(output_dir, f"{username}_hourly.png")
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"   ✅ 24小时分布图: {path}")
    return path


def chart_weekday_bar(raw_tweets, output_dir, username):
    """生成星期分布柱状图"""
    tz_offset = _config.timezone_offset
    weekday_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    weekday_counts = Counter()

    for tweet in raw_tweets:
        if "created_at" not in tweet:
            continue
        dt_utc = _parse_dt(tweet["created_at"])
        dt_local = dt_utc + timedelta(hours=tz_offset)
        weekday_counts[dt_local.weekday()] += 1

    fig, ax = plt.subplots(figsize=(8, 5))
    counts = [weekday_counts.get(i, 0) for i in range(7)]
    colors = ['#42A5F5' if i < 5 else '#FF7043' for i in range(7)]

    ax.bar(weekday_names, counts, color=colors, edgecolor='white')
    ax.set_ylabel('Tweets', fontsize=12)
    ax.set_title(f'@{username} - Weekday vs Weekend', fontsize=14)
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    path = os.path.join(output_dir, f"{username}_weekday.png")
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"   ✅ 星期分布图: {path}")
    return path


def chart_language_pie(translated_data, output_dir, username):
    """生成语言分布饼图"""
    lang_counts = Counter()
    lang_names = {
        "ja": "Japanese", "en": "English", "zh-cn": "Chinese", "zh": "Chinese",
        "ko": "Korean", "es": "Spanish", "fr": "French", "unknown": "Unknown"
    }

    for item in translated_data:
        lang = item.get("detected_language", "unknown")
        lang_counts[lang] += 1

    if not lang_counts:
        return None

    labels = [lang_names.get(l, l) for l in lang_counts.keys()]
    sizes = list(lang_counts.values())
    colors = plt.cm.Set3(range(len(labels)))

    fig, ax = plt.subplots(figsize=(8, 6))
    wedges, texts, autotexts = ax.pie(sizes, labels=labels, autopct='%1.1f%%',
                                       colors=colors, startangle=90)
    ax.set_title(f'@{username} - Language Distribution', fontsize=14)

    plt.tight_layout()
    path = os.path.join(output_dir, f"{username}_language.png")
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"   ✅ 语言分布图: {path}")
    return path


def chart_interest_tags(profile_data, output_dir, username):
    """生成兴趣标签条形图"""
    if not profile_data or "interests" not in profile_data:
        return None

    interests = profile_data["interests"]
    if not interests:
        return None

    tags = [i["tag"] for i in interests]
    confidences = [i.get("confidence", 0.5) for i in interests]
    levels = [i.get("level", "peripheral") for i in interests]
    colors = ['#1976D2' if l == "core" else '#90CAF9' for l in levels]

    fig, ax = plt.subplots(figsize=(10, 5))
    y_pos = range(len(tags))
    ax.barh(y_pos, confidences, color=colors, edgecolor='white')
    ax.set_yticks(y_pos)
    ax.set_yticklabels(tags, fontsize=11)
    ax.set_xlabel('Confidence', fontsize=12)
    ax.set_title(f'@{username} - Interest Profile', fontsize=14)
    ax.set_xlim(0, 1)
    ax.grid(axis='x', alpha=0.3)

    plt.tight_layout()
    path = os.path.join(output_dir, f"{username}_interests.png")
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"   ✅ 兴趣画像图: {path}")
    return path


def generate_evidence_sections(data, include_sensitive_events=False):
    """生成兴趣和生活事件的证据 HTML。"""
    translated_data = data.get("translated") or []
    evidence_map = build_evidence_map(translated_data)

    sections = []
    profile = data.get("profile") or {}
    interests = profile.get("interests", [])
    if interests:
        rows = []
        for interest in interests:
            tag = html.escape(str(interest.get("tag", "")))
            level = html.escape(str(interest.get("level", "")))
            confidence = html.escape(str(interest.get("confidence", "")))
            status = html.escape(str(interest.get("evidence_status", "ok")))
            ids = interest.get("evidence_tweet_ids", [])
            rows.append(
                f'<section class="evidence-item">'
                f'<h3>{tag} <span class="meta">{level} / confidence={confidence} / evidence={status}</span></h3>'
                f'{render_evidence_html(ids, evidence_map)}'
                f'</section>'
            )
        sections.append('<div class="panel"><h2>兴趣画像证据</h2>' + "\n".join(rows) + "</div>")

    behavior = data.get("behavior") or {}
    life_events = behavior.get("life_events", {})
    if life_events:
        rows = []
        for category, events in life_events.items():
            for event in events or []:
                if isinstance(event, dict):
                    description = html.escape(str(event.get("description", "")))
                    ids = event.get("evidence_tweet_ids", [])
                    sensitive = bool(event.get("sensitive"))
                else:
                    description = html.escape(str(event))
                    ids = []
                    sensitive = False
                safe_category = html.escape(str(category))
                redact = sensitive and not include_sensitive_events
                note = '<p class="empty">敏感事件证据默认隐藏；使用 --include-sensitive-events 可显示。</p>' if redact else ""
                rows.append(
                    f'<section class="evidence-item">'
                    f'<h3>{safe_category}: {description}</h3>'
                    f'{note}{render_evidence_html(ids, evidence_map, redact=redact)}'
                    f'</section>'
                )
        if rows:
            sections.append('<div class="panel"><h2>生活事件证据</h2>' + "\n".join(rows) + "</div>")

    return "\n".join(sections)


def generate_html_report(username, chart_paths, output_dir, data=None, include_sensitive_events=False):
    """生成 HTML 报告"""
    safe_username = html.escape(str(username))
    charts_html = ""
    for name, path in chart_paths:
        if path and os.path.exists(path):
            rel_path = os.path.basename(path)
            safe_name = html.escape(str(name))
            safe_rel_path = html.escape(rel_path, quote=True)
            charts_html += f'<div class="chart"><h3>{safe_name}</h3><img src="{safe_rel_path}" alt="{safe_name}"></div>\n'
    evidence_html = generate_evidence_sections(data or {}, include_sensitive_events=include_sensitive_events)

    report_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>@{safe_username} Twitter Analysis Report</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; background: #f5f5f5; }}
  h1 {{ color: #1976D2; border-bottom: 2px solid #1976D2; padding-bottom: 10px; }}
  .chart, .panel {{ background: white; border-radius: 8px; padding: 20px; margin: 20px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
  .chart img {{ max-width: 100%; height: auto; }}
  .meta {{ color: #666; font-size: 14px; }}
  .evidence-item {{ border-top: 1px solid #eee; padding-top: 12px; margin-top: 12px; }}
  code {{ background: #f1f3f4; padding: 2px 4px; border-radius: 4px; }}
  details summary {{ cursor: pointer; color: #1976D2; }}
  .empty {{ color: #999; }}
</style>
</head>
<body>
<h1>📊 @{safe_username} Twitter Analysis Report</h1>
<p class="meta">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
{charts_html}
{evidence_html}
</body>
</html>"""

    path = os.path.join(output_dir, f"{username}_report.html")
    with open(path, 'w', encoding='utf-8') as f:
        f.write(report_html)
    print(f"   ✅ HTML 报告: {path}")
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
    print(f"📊 数据可视化: @{TARGET_USERNAME}")
    print(f"📁 输出目录: {output_dir}")
    print("=" * 60 + "\n")

    data = load_data(TARGET_USERNAME, CACHE_DIR)

    if not data.get("raw"):
        print("❌ 找不到原始推文数据，请先运行 main.py")
        return 1

    if not MATPLOTLIB_AVAILABLE:
        print_missing_optional_dependency("matplotlib", "viz", feature="可视化报告")
        return 1

    print("🎨 生成图表...")
    chart_paths = []

    p = chart_hourly_heatmap(data["raw"], output_dir, TARGET_USERNAME)
    chart_paths.append(("24h Tweet Distribution", p))

    p = chart_weekday_bar(data["raw"], output_dir, TARGET_USERNAME)
    chart_paths.append(("Weekday vs Weekend", p))

    if data.get("translated"):
        p = chart_language_pie(data["translated"], output_dir, TARGET_USERNAME)
        chart_paths.append(("Language Distribution", p))

    if data.get("profile"):
        p = chart_interest_tags(data["profile"], output_dir, TARGET_USERNAME)
        chart_paths.append(("Interest Profile", p))

    report_path = None
    if args.format == "html":
        print()
        report_path = generate_html_report(
            TARGET_USERNAME,
            chart_paths,
            output_dir,
            data,
            include_sensitive_events=args.include_sensitive_events,
        )

    print("\n" + "=" * 60)
    print(f"✅ 可视化完成！共生成 {len(chart_paths)} 张图表")
    if report_path:
        print(f"📄 报告: {report_path}")
    print("=" * 60 + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
