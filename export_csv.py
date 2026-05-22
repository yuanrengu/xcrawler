"""
CSV 导出工具
将缓存数据导出为 CSV 格式，方便 Excel 打开
"""
import os
import json
import csv
import argparse
from datetime import datetime

from dotenv import load_dotenv
_ = load_dotenv()

TARGET_USERNAME = os.getenv("TARGET_USERNAME", "MiracleHe")
CACHE_DIR = "cache"


def parse_args():
    parser = argparse.ArgumentParser(description="将分析数据导出为 CSV")
    parser.add_argument("-u", "--user", help="目标用户名")
    parser.add_argument("--cache-dir", help=f"缓存目录（默认 {CACHE_DIR}）")
    parser.add_argument("--output", help="输出目录（默认 cache/csv）")
    parser.add_argument("--type", choices=["all", "tweets", "translations", "interests"],
                        default="all", help="导出类型（默认 all）")
    return parser.parse_args()


def export_tweets(raw_tweets, output_path):
    """导出原始推文"""
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(["id", "text", "created_at", "hashtags", "mentions"])
        for t in raw_tweets:
            entities = t.get("entities", {})
            tags = ", ".join(ht.get("tag", "") for ht in entities.get("hashtags", []))
            mentions = ", ".join(m.get("username", "") for m in entities.get("mentions", []))
            writer.writerow([
                t.get("id", ""),
                t.get("text", "").replace("\n", " "),
                t.get("created_at", ""),
                tags,
                mentions
            ])
    print(f"   ✅ 推文导出: {output_path} ({len(raw_tweets)} 条)")


def export_translations(translated_data, output_path):
    """导出翻译数据"""
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(["original", "translated", "detected_language", "created_at"])
        for item in translated_data:
            writer.writerow([
                item.get("original", "").replace("\n", " "),
                item.get("translated", "").replace("\n", " "),
                item.get("detected_language", ""),
                item.get("created_at", "")
            ])
    print(f"   ✅ 翻译导出: {output_path} ({len(translated_data)} 条)")


def export_interests(profile_data, output_path):
    """导出兴趣画像"""
    if not profile_data or "interests" not in profile_data:
        print("   ⚠️ 无兴趣画像数据")
        return

    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(["tag", "level", "confidence", "keywords", "evidence_count"])
        for interest in profile_data.get("interests", []):
            writer.writerow([
                interest.get("tag", ""),
                interest.get("level", ""),
                interest.get("confidence", ""),
                ", ".join(interest.get("keywords", [])),
                interest.get("evidence_count", 0)
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
        if os.path.exists(raw_file):
            with open(raw_file, 'r', encoding='utf-8') as f:
                raw_tweets = json.load(f)
            export_tweets(raw_tweets, os.path.join(output_dir, f"{TARGET_USERNAME}_tweets.csv"))
            exported += 1
        else:
            print("   ⚠️ 未找到原始推文文件")

    if args.type in ("all", "translations"):
        trans_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_translated.json")
        if os.path.exists(trans_file):
            with open(trans_file, 'r', encoding='utf-8') as f:
                translated_data = json.load(f)
            export_translations(translated_data, os.path.join(output_dir, f"{TARGET_USERNAME}_translations.csv"))
            exported += 1
        else:
            print("   ⚠️ 未找到翻译文件")

    if args.type in ("all", "interests"):
        profile_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_interest_profile.json")
        if os.path.exists(profile_file):
            with open(profile_file, 'r', encoding='utf-8') as f:
                profile_data = json.load(f)
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
