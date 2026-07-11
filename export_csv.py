from __future__ import annotations

"""
CSV 导出工具
将缓存数据导出为 CSV 格式，方便 Excel 打开
"""
import argparse
import csv
import os

from xcrawler.config import load_config
from xcrawler.services.records import normalize_translated_tweets
from xcrawler.storage.json_store import load_json
from xcrawler.utils import cli_validation

_config = load_config()

TARGET_USERNAME = _config.target_username
CACHE_DIR = _config.cache_dir

DANGEROUS_CSV_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


def safe_csv_cell(value, *, force_text: bool = False) -> str:
    """Return a spreadsheet-safe cell value.

    A leading apostrophe prevents Excel-compatible applications from evaluating
    untrusted values as formulas. ``force_text`` also protects long tweet IDs
    from numeric precision loss.
    """
    if value is None:
        return ""
    text = str(value)
    candidate = text.lstrip()
    if text and (force_text or text.startswith(DANGEROUS_CSV_PREFIXES) or candidate.startswith(DANGEROUS_CSV_PREFIXES)):
        return f"'{text}"
    return text


def _csv_writer(file_obj):
    return csv.writer(file_obj, quoting=csv.QUOTE_ALL, lineterminator="\n")


def parse_args():
    parser = argparse.ArgumentParser(description="将分析数据导出为 CSV")
    parser.add_argument("-u", "--user", type=cli_validation.x_username, help="目标用户名")
    parser.add_argument("--cache-dir", help=f"缓存目录（默认 {CACHE_DIR}）")
    parser.add_argument("--output", help="输出目录（默认 cache/csv）")
    parser.add_argument("--type", choices=["all", "tweets", "translations", "interests"],
                        default="all", help="导出类型（默认 all）")
    return parser.parse_args()


def export_tweets(raw_tweets, output_path):
    """导出原始推文"""
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = _csv_writer(f)
        writer.writerow(["id", "text", "created_at", "hashtags", "mentions"])
        for t in raw_tweets:
            entities = t.get("entities", {})
            tags = ", ".join(ht.get("tag", "") for ht in entities.get("hashtags", []))
            mentions = ", ".join(m.get("username", "") for m in entities.get("mentions", []))
            writer.writerow([
                safe_csv_cell(t.get("id", ""), force_text=True),
                safe_csv_cell(t.get("text", "").replace("\n", " ")),
                safe_csv_cell(t.get("created_at", "")),
                safe_csv_cell(tags),
                safe_csv_cell(mentions),
            ])
    print(f"   ✅ 推文导出: {output_path} ({len(raw_tweets)} 条)")


def export_translations(translated_data, output_path):
    """导出翻译数据"""
    translated_data = normalize_translated_tweets(translated_data)
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = _csv_writer(f)
        writer.writerow(["tweet_id", "original", "translated", "detected_language", "created_at"])
        for item in translated_data:
            writer.writerow([
                safe_csv_cell(item.get("tweet_id", ""), force_text=True),
                safe_csv_cell(item.get("original", "").replace("\n", " ")),
                safe_csv_cell(item.get("translated", "").replace("\n", " ")),
                safe_csv_cell(item.get("detected_language", "")),
                safe_csv_cell(item.get("created_at", "")),
            ])
    print(f"   ✅ 翻译导出: {output_path} ({len(translated_data)} 条)")


def export_interests(profile_data, output_path):
    """导出兴趣画像"""
    if not profile_data or "interests" not in profile_data:
        print("   ⚠️ 无兴趣画像数据")
        return

    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = _csv_writer(f)
        writer.writerow(["tag", "level", "confidence", "keywords", "evidence_count", "evidence_tweet_ids", "evidence_status"])
        for interest in profile_data.get("interests", []):
            writer.writerow([
                safe_csv_cell(interest.get("tag", "")),
                safe_csv_cell(interest.get("level", "")),
                safe_csv_cell(interest.get("confidence", "")),
                safe_csv_cell(", ".join(interest.get("keywords", []))),
                safe_csv_cell(interest.get("evidence_count", 0)),
                safe_csv_cell(", ".join(interest.get("evidence_tweet_ids", [])), force_text=True),
                safe_csv_cell(interest.get("evidence_status", "")),
            ])
    print(f"   ✅ 兴趣导出: {output_path}")


def main():
    global TARGET_USERNAME, CACHE_DIR

    args = parse_args()
    if args.user:
        TARGET_USERNAME = args.user
    if args.cache_dir:
        CACHE_DIR = args.cache_dir
    output_dir = args.output or os.path.join(CACHE_DIR, "csv")
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60)
    print(f"📤 CSV 导出: @{TARGET_USERNAME}")
    print(f"📁 输出目录: {output_dir}")
    print("=" * 60 + "\n")

    exported = 0

    if args.type in ("all", "tweets"):
        raw_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_raw_tweets.json")
        raw_tweets = load_json(raw_file)
        if raw_tweets is not None:
            export_tweets(raw_tweets, os.path.join(output_dir, f"{TARGET_USERNAME}_tweets.csv"))
            exported += 1
        else:
            print("   ⚠️ 未找到原始推文文件")

    if args.type in ("all", "translations"):
        trans_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_translated.json")
        translated_data = load_json(trans_file)
        if translated_data is not None:
            export_translations(translated_data, os.path.join(output_dir, f"{TARGET_USERNAME}_translations.csv"))
            exported += 1
        else:
            print("   ⚠️ 未找到翻译文件")

    if args.type in ("all", "interests"):
        profile_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_interest_profile.json")
        profile_data = load_json(profile_file)
        if profile_data is not None:
            export_interests(profile_data, os.path.join(output_dir, f"{TARGET_USERNAME}_interests.csv"))
            exported += 1
        else:
            print("   ⚠️ 未找到兴趣画像文件")

    print("\n" + "=" * 60)
    if exported:
        print(f"✅ 导出完成！共 {exported} 个文件")
    else:
        print("⚠️ 没有可导出的数据")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
