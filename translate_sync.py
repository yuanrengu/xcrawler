from __future__ import annotations

import argparse
import os
import shutil

from xcrawler.clients.llm import create_openai_client
from xcrawler.config import load_config, require_secret
from xcrawler.paths import ensure_dir, translation_cache_path
from xcrawler.services.llm_calls import LLMCallRecorder
from xcrawler.services.records import (
    make_translated_tweet,
    normalize_translated_tweets,
    translation_record_is_current,
)
from xcrawler.services.translation import translate_batch, translate_text
from xcrawler.services.translation_cache import (
    TranslationCacheContext,
    legacy_translation_cache_entry_count,
    new_translation_cache,
    normalize_translation_cache,
    translation_cache_entry_count,
)
from xcrawler.services.tweets import merge_translated_tweets, validate_raw_tweets
from xcrawler.storage.factory import STORAGE_BACKENDS, create_store
from xcrawler.storage.json_store import load_json, save_json
from xcrawler.utils import cli_validation
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
        raw_tweets = validate_raw_tweets(load_json(raw_file, default=[]), source=raw_file)

    translated_data = []
    if os.path.exists(translated_file):
        translated_data = normalize_translated_tweets(load_json(translated_file, default=[]))

    return raw_tweets, translated_data, translated_file


def _make_client():
    return create_openai_client(
        api_key=require_secret("DEEPSEEK_API_KEY", _config.deepseek_api_key, purpose="翻译同步"),
        base_url=_config.deepseek_base_url,
    )


def _translation_cache_context() -> TranslationCacheContext:
    return TranslationCacheContext(provider="deepseek", model=LLM_MODEL)


def main():
    args = argparse.ArgumentParser(description="翻译同步/重翻工具")
    args.add_argument("-u", "--user", type=cli_validation.x_username, help="目标用户名")
    args.add_argument("--cache-dir", help="缓存目录")
    args.add_argument("--force", action="store_true", help="强制重新翻译")
    args.add_argument("--storage", "--storage-backend", dest="storage_backend", choices=STORAGE_BACKENDS,
                      default=_config.storage_backend, help="运行元数据存储后端（默认 json）")
    args.add_argument("--sqlite-path", default=_config.sqlite_path, help="SQLite 数据库路径")
    args = args.parse_args()

    username = args.user or TARGET_USERNAME
    cache_dir = args.cache_dir or CACHE_DIR
    ensure_dir(cache_dir)
    call_recorder = LLMCallRecorder(
        create_store(cache_dir, backend=args.storage_backend, sqlite_path=args.sqlite_path),
        pricing=_config.llm_pricing,
        username=username,
    )

    print("=" * 60)
    print("🔄 翻译同步工具 (Translation Sync)")
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
    translation_cache = normalize_translation_cache(load_json(translation_cache_path(cache_dir), default={}))
    cache_context = _translation_cache_context()
    metrics: dict[str, int | str] = {
        "cache_hits": 0,
        "cache_misses": 0,
        "cache_bypassed": 0,
        "cache_fingerprint": cache_context.fingerprint,
    }
    legacy_entries = legacy_translation_cache_entry_count(translation_cache)
    if legacy_entries:
        print(f"⚠️ 已迁移但未复用来源不明的旧缓存: {legacy_entries} 条")
    if args.force:
        print("🧹 强制模式：忽略并清除内存中的翻译缓存")
        translation_cache = new_translation_cache()

    # 2. Identify tweets to process
    print("🔍 检查待翻译推文...")

    translated_by_id = {
        str(item.get("tweet_id")): item
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
        if tweet_id is not None:
            existing_translation = translated_by_id.get(str(tweet_id))
            already_translated = bool(
                existing_translation
                and translation_record_is_current(existing_translation, clean, cache_context.fingerprint)
            )
        else:
            already_translated = clean in translated_texts_without_id

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
        return 0

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
            metrics=metrics,
            cache_context=cache_context,
            cache_results=True,
            call_recorder=call_recorder,
            provider_name="deepseek",
            operation="translation_sync_single",
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
        metrics=metrics,
        cache_context=cache_context,
        cache_results=True,
        call_recorder=call_recorder,
        provider_name="deepseek",
        operation="translation_sync_batch",
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
                config_fingerprint=cache_context.fingerprint,
            ))

    if args.force and len(new_translations) != len(to_process):
        failed_count = len(to_process) - len(new_translations)
        save_json(translation_cache_path(cache_dir), normalize_translation_cache(translation_cache))
        print(f"\n❌ 强制重翻失败 {failed_count} 条，未覆盖原翻译文件。")
        print(f"   旧数据仍保留在: {translated_file_path}")
        return 1

    if new_translations:
        current_data = merge_translated_tweets(translated_data, new_translations)

        print(f"\n💾 保存更新后的翻译数据 ({len(current_data)} 条)...")
        save_json(translated_file_path, current_data)

        # Save updated cache to disk
        save_json(translation_cache_path(cache_dir), normalize_translation_cache(translation_cache))

        print(
            f"   缓存命中/未命中/跳过: {metrics.get('cache_hits', 0)} / "
            f"{metrics.get('cache_misses', 0)} / {metrics.get('cache_bypassed', 0)}"
        )
        print(f"   当前缓存条目: {translation_cache_entry_count(translation_cache, cache_context)}")
        print(f"   缓存配置指纹: {metrics['cache_fingerprint']}")
        if args.force:
            print(f"✅ 重新翻译完成！共处理 {len(new_translations)} 条")
        else:
            print(f"✅ 同步完成！新增翻译 {len(new_translations)} 条")
    else:
        print("\n⚠️ 未能生成有效翻译")

    call_summary = call_recorder.summary()
    if call_summary["calls"]:
        print(
            f"   LLM 调用记录: {call_summary['successful_calls']} 成功 / "
            f"{call_summary['failed_calls']} 失败"
        )
        if call_summary["estimated_cost"]:
            print(f"   预估成本 (USD): {call_summary['estimated_cost']:.6f}")

    print("\n" + "=" * 60)
    failed_count = len(to_process) - len(new_translations)
    if failed_count:
        print(f"❌ 翻译同步未完整：{failed_count} 条失败")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
