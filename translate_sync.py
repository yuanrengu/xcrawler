import os
import json
import shutil
import argparse

from xcrawler.clients.llm import create_openai_client
from xcrawler.config import load_config, require_secret
from xcrawler.paths import translation_cache_path, ensure_dir
from xcrawler.services.records import make_translated_tweet, normalize_translated_tweets
from xcrawler.services.translation import translate_batch, translate_text
from xcrawler.storage.json_store import load_json, save_json
from xcrawler.utils.text import clean_text, detect_language

_config = load_config()

CACHE_DIR = _config.cache_dir
LLM_MODEL = _config.llm_model
TARGET_USERNAME = _config.target_username
BATCH_SIZE = 10


def load_data(username, cache_dir):
    """Load raw and translated data"""
    raw_file = os.path.join(cache_dir, f"{username}_raw_tweets.json")
    translated_file = os.path.join(cache_dir, f"{username}_translated.json")

    raw_tweets = []
    if os.path.exists(raw_file):
        with open(raw_file, "r", encoding="utf-8") as f:
            raw_tweets = json.load(f)

    translated_data = []
    if os.path.exists(translated_file):
        with open(translated_file, "r", encoding="utf-8") as f:
            translated_data = normalize_translated_tweets(json.load(f))

    return raw_tweets, translated_data, translated_file


def _make_client():
    return create_openai_client(
        api_key=require_secret("DEEPSEEK_API_KEY", _config.deepseek_api_key, purpose="翻译同步"),
        base_url=_config.deepseek_base_url,
    )


def main():
    args = argparse.ArgumentParser(description="翻译同步/重翻工具")
    args.add_argument("-u", "--user", help="目标用户名")
    args.add_argument("--cache-dir", help="缓存目录")
    args.add_argument("--force", action="store_true", help="强制重新翻译")
    args = args.parse_args()

    username = args.user or TARGET_USERNAME
    cache_dir = args.cache_dir or CACHE_DIR
    ensure_dir(cache_dir)

    print("=" * 60)
    print(f"🔄 翻译同步工具 (Translation Sync)")
    print(f"🎯 目标用户: {username}")
    print(f"📁 缓存目录: {cache_dir}")
    if args.force:
        print("⚠️  模式: 强制重新翻译 (Force Re-translation)")
    print("=" * 60 + "\n")

    # 1. Load data
    print("📂 加载数据...")
    raw_tweets, translated_data, translated_file_path = load_data(username, cache_dir)
    print(f"   原始推文: {len(raw_tweets)} 条")
    print(f"   已翻译推文: {len(translated_data)} 条")

    # Load translation cache from disk
    translation_cache = load_json(translation_cache_path(cache_dir), default={})
    if args.force:
        print("🧹 强制模式：忽略并清除内存中的翻译缓存")
        translation_cache = {}

    # 2. Identify tweets to process
    print("🔍 检查待翻译推文...")

    translated_tweet_ids = {
        str(item.get("tweet_id"))
        for item in translated_data
        if item.get("tweet_id") is not None
    }
    translated_texts_without_id = {
        item["original"]
        for item in translated_data
        if not item.get("tweet_id") and item.get("original")
    }

    to_process = []
    for t in raw_tweets:
        text = t.get("text", "")
        clean = clean_text(text)

        if len(clean) < 6:
            continue

        tweet_id = t.get("id")
        already_translated = (
            str(tweet_id) in translated_tweet_ids
            if tweet_id is not None
            else clean in translated_texts_without_id
        )

        if args.force or not already_translated:
            detected_lang = detect_language(clean)
            to_process.append({
                "tweet_id": tweet_id,
                "original": clean,
                "lang": detected_lang,
                "created_at": t.get("created_at", ""),
            })

    if not to_process:
        print("🎉 所有推文都已翻译，无需更新！")
        return

    print(f"📝 发现 {len(to_process)} 条推文需要翻译")

    # 3. 批量翻译
    use_cache_flag = not args.force

    if args.force:
        backup_path = translated_file_path + ".bak"
        if os.path.exists(translated_file_path):
            shutil.copy2(translated_file_path, backup_path)
            print(f"📋 已备份旧翻译文件: {backup_path}")
        print("⚠️  强制模式：将覆盖现有的翻译文件")
        translated_data = []

    print(f"🚀 批量翻译 {len(to_process)} 条推文（每批 {BATCH_SIZE} 条）...")

    all_texts = [item["original"] for item in to_process]
    all_langs = [item["lang"] for item in to_process]

    def _fallback(text, lang, use_cache):
        return translate_text(
            text,
            detected_lang=lang,
            use_cache=use_cache,
            cache=translation_cache,
            client_factory=_make_client,
            model=LLM_MODEL,
            max_retries=3,
        )

    batch_results = translate_batch(
        all_texts,
        detected_langs=all_langs,
        use_cache=use_cache_flag,
        cache=translation_cache,
        client_factory=_make_client,
        model=LLM_MODEL,
        batch_size=BATCH_SIZE,
        max_retries=3,
        fallback_translate=_fallback,
    )

    new_translations = []
    for i, item in enumerate(to_process):
        translated_text = batch_results[i]
        if translated_text:
            new_translations.append(make_translated_tweet(
                tweet_id=item["tweet_id"],
                original=item["original"],
                translated=translated_text,
                detected_language=item["lang"],
                created_at=item["created_at"],
            ))

    if new_translations:
        current_data = translated_data + new_translations
        current_data.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        print(f"\n💾 保存更新后的翻译数据 ({len(current_data)} 条)...")
        with open(translated_file_path, "w", encoding="utf-8") as f:
            json.dump(current_data, f, ensure_ascii=False, indent=2)

        # Save updated cache to disk
        save_json(translation_cache_path(cache_dir), translation_cache)

        if args.force:
            print(f"✅ 重新翻译完成！共处理 {len(new_translations)} 条")
        else:
            print(f"✅ 同步完成！新增翻译 {len(new_translations)} 条")
    else:
        print("\n⚠️ 未能生成有效翻译")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    raise SystemExit(main() or 0)
