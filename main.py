from __future__ import annotations

import argparse
import os
from collections import Counter
from datetime import datetime
from typing import Any

import requests

from xcrawler.clients import x_api
from xcrawler.clients.llm import create_openai_client
from xcrawler.config import load_config, require_secret
from xcrawler.paths import ensure_dir, translation_cache_path
from xcrawler.services.embeddings import encode_texts_with_cache
from xcrawler.services.llm_calls import LLMCallRecorder
from xcrawler.services.records import make_translated_tweet
from xcrawler.services.sampling import sample_evenly
from xcrawler.services.translation import (
    translate_batch,
    translate_text,
)
from xcrawler.services.translation_cache import (
    TranslationCacheContext,
    legacy_translation_cache_entry_count,
    new_translation_cache,
    normalize_translation_cache,
    translation_cache_entry_count,
)
from xcrawler.services.tweets import merge_translated_tweets, merge_tweets, validate_raw_tweets
from xcrawler.storage.factory import STORAGE_BACKENDS, create_store
from xcrawler.storage.json_store import load_json, replace_json_files_atomically, save_json
from xcrawler.utils import cli_validation
from xcrawler.utils.optional_dependencies import modules_available
from xcrawler.utils.text import clean_text, detect_language

_config = load_config()

# ======================
# 配置（默认值，CLI 参数可覆盖）
# ======================
X_BEARER_TOKEN = _config.x_bearer_token
DEEPSEEK_API_KEY = _config.deepseek_api_key
DEEPSEEK_BASE_URL = _config.deepseek_base_url
LLM_MODEL = _config.llm_model

TARGET_USERNAME = _config.target_username
MAX_PAGES = 50
MAX_RETRIES = 3
MAX_WORKERS = 5
CACHE_DIR = _config.cache_dir
BATCH_SIZE = 10
ANALYSIS_LIMIT = 1000


def ml_analysis_available() -> bool:
    return modules_available("sentence_transformers", "sklearn")


def parse_args():
    """解析 CLI 参数，覆盖 .env 默认值"""
    parser = argparse.ArgumentParser(description="Twitter 用户数据抓取 + 翻译 + 聚类分析")
    parser.add_argument(
        "-u", "--user", type=cli_validation.x_username, help="目标用户名（覆盖 .env 中的 TARGET_USERNAME）"
    )
    parser.add_argument("--pages", type=cli_validation.positive_int, help=f"抓取页数，每页100条（默认 {MAX_PAGES}）")
    parser.add_argument("--batch-size", type=cli_validation.positive_int, help=f"每批翻译条数（默认 {BATCH_SIZE}）")
    parser.add_argument("--model", help=f"LLM 模型名（默认 {LLM_MODEL}）")
    parser.add_argument("--cache-dir", help=f"缓存目录（默认 {CACHE_DIR}）")
    parser.add_argument("--analysis-limit", type=cli_validation.positive_int, default=ANALYSIS_LIMIT,
                        help=f"聚类和画像最多分析的翻译推文数（默认 {ANALYSIS_LIMIT}）")
    parser.add_argument("--no-translate", action="store_true", help="跳过翻译，仅抓取")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="snapshot 模式：使用本次完整结果替换历史（默认 archive 合并模式）",
    )
    parser.add_argument("--storage", "--storage-backend", dest="storage_backend", choices=STORAGE_BACKENDS,
                        default=_config.storage_backend, help="运行元数据存储后端（默认 json）")
    parser.add_argument("--sqlite-path", default=_config.sqlite_path, help="SQLite 数据库路径")
    return parser.parse_args()

# ======================
# 初始化客户端和缓存（lazy，首次调用时创建）
# ======================
ds_client = None

def _get_ds_client():
    global ds_client
    if ds_client is None:
        api_key = require_secret("DEEPSEEK_API_KEY", DEEPSEEK_API_KEY, purpose="翻译和画像分析")
        ds_client = create_openai_client(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
    return ds_client

# embed_model moved to main()


# Deferred: HEADERS built in validate_runtime_config() after token validation
HEADERS: dict[str, str] = {}

# 创建缓存目录
ensure_dir(CACHE_DIR)

# 翻译缓存
translation_cache: dict[str, Any] = new_translation_cache()


def _translation_cache_context() -> TranslationCacheContext:
    return TranslationCacheContext(provider="deepseek", model=LLM_MODEL)


def _new_translation_metrics() -> dict[str, int | str]:
    return {
        "llm_calls": 0,
        "total_tokens": 0,
        "failed_batches": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "cache_bypassed": 0,
        "cache_fingerprint": _translation_cache_context().fingerprint,
    }


translation_metrics: dict[str, int | str] = _new_translation_metrics()
llm_call_recorder: LLMCallRecorder | None = None


def load_translation_cache():
    """加载翻译缓存"""
    return normalize_translation_cache(load_json(translation_cache_path(CACHE_DIR), default={}))


def save_translation_cache(cache):
    """保存翻译缓存"""
    save_json(translation_cache_path(CACHE_DIR), normalize_translation_cache(cache))


def deepseek_translate(text: str, detected_lang: str = None, use_cache: bool = True) -> str | None:
    """智能翻译单条推文到中文，支持缓存和重试（保留向后兼容）"""
    return translate_text(
        text,
        detected_lang=detected_lang,
        use_cache=use_cache,
        cache=translation_cache,
        client_factory=_get_ds_client,
        model=LLM_MODEL,
        max_retries=MAX_RETRIES,
        metrics=translation_metrics,
        cache_context=_translation_cache_context(),
        call_recorder=llm_call_recorder,
        provider_name="deepseek",
    )


def deepseek_translate_batch(texts: list[str], detected_langs: list[str | None] | None = None,
                              use_cache: bool = True) -> list[str | None]:
    """
    批量翻译推文到中文，一次 API 调用翻译多条，大幅降低费用。

    :param texts: 推文文本列表
    :param detected_langs: 每条推文的语言列表（可选）
    :param use_cache: 是否使用缓存
    :return: 翻译结果列表（与输入等长，失败的为 None）
    """
    return translate_batch(
        texts,
        detected_langs=detected_langs,
        use_cache=use_cache,
        cache=translation_cache,
        client_factory=_get_ds_client,
        model=LLM_MODEL,
        batch_size=BATCH_SIZE,
        max_retries=MAX_RETRIES,
        fallback_translate=deepseek_translate,
        metrics=translation_metrics,
        cache_context=_translation_cache_context(),
        call_recorder=llm_call_recorder,
        provider_name="deepseek",
    )


def deepseek_profile_summary(cluster_text):
    """生成用户画像，支持重试（委托给 xcrawler.services.profile）"""
    from xcrawler.services.profile import deepseek_profile_summary as _impl
    return _impl(
        cluster_text,
        client_factory=_get_ds_client,
        model=LLM_MODEL,
        max_retries=MAX_RETRIES,
        call_recorder=llm_call_recorder,
        provider_name="deepseek",
    )

# ======================
# X API
# ======================
def get_user_id(username: str) -> str:
    """获取用户ID，带错误处理"""
    try:
        return x_api.get_user_id(username, HEADERS, request_get=requests.get)
    except requests.exceptions.RequestException as e:
        raise Exception(f"获取用户ID失败: {str(e)}")


def get_user_profile(username: str) -> dict | None:
    """获取用户基础信息（bio、粉丝数、关注数等）"""
    try:
        return x_api.get_user_profile(username, HEADERS, request_get=requests.get)
    except Exception as e:
        print(f"⚠️ 获取用户信息失败: {str(e)}")
        return None

def fetch_tweets(user_id: str) -> list[dict]:
    """抓取推文，带错误处理和进度显示"""
    return x_api.fetch_user_tweets(user_id, HEADERS, MAX_PAGES, request_get=requests.get)


def print_execution_plan(*, max_pages: int, batch_size: int, no_translate: bool, cache_size: int, analysis_limit: int) -> None:
    max_tweets = max_pages * 100
    estimated_batches = 0 if no_translate else (max_tweets + batch_size - 1) // batch_size
    print("📋 执行计划:")
    print(f"   预计最多抓取: {max_pages} 页 / {max_tweets} 条")
    print(f"   翻译缓存: {cache_size} 条")
    if no_translate:
        print("   LLM 调用: 跳过翻译和画像分析")
    else:
        print(f"   预计最多翻译批次: {estimated_batches} 批（实际会扣除中文和缓存命中）")
        print(f"   后续步骤: 向量化聚类 + 画像摘要（最多 {analysis_limit} 条）")
    print()


def validate_runtime_config(*, no_translate: bool) -> None:
    global HEADERS
    token = require_secret("X_BEARER_TOKEN", X_BEARER_TOKEN, purpose="抓取公开推文")
    HEADERS = x_api.auth_headers(token)
    if not no_translate:
        require_secret("DEEPSEEK_API_KEY", DEEPSEEK_API_KEY, purpose="翻译和画像分析")

# ======================
# 主流程
# ======================
def main():
    global translation_cache, translation_metrics, llm_call_recorder, TARGET_USERNAME, MAX_PAGES, BATCH_SIZE, LLM_MODEL, CACHE_DIR, ANALYSIS_LIMIT

    # 应用 CLI 参数（覆盖 .env 默认值）
    args = parse_args()
    if args.user:
        TARGET_USERNAME = args.user
    if args.pages is not None:
        MAX_PAGES = args.pages
    if args.batch_size is not None:
        BATCH_SIZE = args.batch_size
    if args.model:
        LLM_MODEL = args.model
    if args.cache_dir:
        CACHE_DIR = args.cache_dir
    if args.analysis_limit is not None:
        ANALYSIS_LIMIT = args.analysis_limit
    os.makedirs(CACHE_DIR, exist_ok=True)
    llm_call_recorder = LLMCallRecorder(
        create_store(CACHE_DIR, backend=args.storage_backend, sqlite_path=args.sqlite_path),
        pricing=_config.llm_pricing,
        username=TARGET_USERNAME,
    )

    print("=" * 60)
    print(f"🎯 目标用户: {TARGET_USERNAME}")
    print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")
    
    # 加载翻译缓存
    translation_cache = load_translation_cache()
    translation_metrics = _new_translation_metrics()
    cache_entries = translation_cache_entry_count(translation_cache, _translation_cache_context())
    legacy_entries = legacy_translation_cache_entry_count(translation_cache)
    print(f"💾 已加载当前配置翻译缓存: {cache_entries} 条")
    if legacy_entries:
        print(f"⚠️ 已迁移但未复用来源不明的旧缓存: {legacy_entries} 条")
    print(f"   缓存配置指纹: {translation_metrics['cache_fingerprint']}\n")
    print_execution_plan(
        max_pages=MAX_PAGES,
        batch_size=BATCH_SIZE,
        no_translate=args.no_translate,
        cache_size=cache_entries,
        analysis_limit=ANALYSIS_LIMIT,
    )
    
    try:
        validate_runtime_config(no_translate=args.no_translate)

        # 1. 获取用户ID
        print("🚀 获取用户 ID...")
        user_id = get_user_id(TARGET_USERNAME)
        print(f"✅ 用户 ID: {user_id}\n")

        # 1.5 获取用户基础信息
        print("👤 获取用户基础信息...")
        profile_info = get_user_profile(TARGET_USERNAME)
        if profile_info:
            profile_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_profile.json")
            save_json(profile_file, profile_info)
            print(f"   粉丝: {profile_info['followers_count']}  关注: {profile_info['following_count']}  推文: {profile_info['tweet_count']}")
            if profile_info.get("description"):
                desc = profile_info["description"][:80]
                print(f"   简介: {desc}{'...' if len(profile_info['description']) > 80 else ''}")
            print(f"💾 用户信息已保存至: {profile_file}\n")
        else:
            print("⚠️ 无法获取用户信息，继续执行\n")

        # 2. 抓取推文
        print("📥 抓取推文（已排除转发和回复）...")
        raw_tweets = fetch_tweets(user_id)
        raw_tweets = validate_raw_tweets(raw_tweets, source="X API full fetch")
        print(f"📊 共抓取 {len(raw_tweets)} 条原创推文\n")
        
        if len(raw_tweets) == 0:
            print("❌ 没有抓取到任何推文，请检查用户是否存在或是否有权限")
            return 1
        
        # 保存原始推文：默认保留历史，只有 --replace 显式覆盖。
        raw_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_raw_tweets.json")
        existing_raw = load_json(raw_file, default=[])
        existing_raw = validate_raw_tweets(existing_raw, source=raw_file)
        if not args.replace:
            raw_tweets = merge_tweets(existing_raw, raw_tweets)
            save_json(raw_file, raw_tweets)
            print(f"💾 原始推文已保存至: {raw_file}\n")

        # 3. 清洗 + 批量翻译
        if args.no_translate:
            if args.replace:
                save_json(raw_file, raw_tweets)
            print("⏭️  --no-translate 模式：跳过翻译和分析，仅保存原始推文")
            print(f"\n✅ 完成！原始推文已保存至: {raw_file}")
            return 0

        print("🧹 清洗 + 智能批量翻译...")
        translated = []
        translated_data = []  # 保存完整数据
        lang_stats = Counter()  # 统计语言分布
        
        # 预处理：清洗和语言检测
        to_process = []
        for t in raw_tweets:
            original_text = clean_text(t.get("text", ""))
            if len(original_text) < 6:
                continue
            detected_lang = detect_language(original_text)
            lang_stats[detected_lang] += 1
            to_process.append((t.get("id"), original_text, detected_lang, t.get("created_at", "")))

        # 批量翻译（每 BATCH_SIZE 条一组，大幅减少 API 调用）
        all_ids = [t[0] for t in to_process]
        all_texts = [t[1] for t in to_process]
        all_langs = [t[2] for t in to_process]
        all_created = [t[3] for t in to_process]

        print(f"🚀 批量翻译 {len(all_texts)} 条推文（每批 {BATCH_SIZE} 条）...")
        batch_results = deepseek_translate_batch(all_texts, all_langs)

        # 收集结果
        failed_list = []
        save_counter = 0
        for i, (tweet_id, original, lang, created) in enumerate(zip(all_ids, all_texts, all_langs, all_created)):
            translated_text = batch_results[i]
            if translated_text:
                translated.append(translated_text)
                translated_data.append(make_translated_tweet(
                    tweet_id=tweet_id,
                    original=original,
                    translated=translated_text,
                    detected_language=lang,
                    created_at=created,
                    config_fingerprint=_translation_cache_context().fingerprint,
                ))
                save_counter += 1
                if save_counter % 50 == 0:
                    save_translation_cache(translation_cache)
            else:
                failed_list.append({"tweet_id": tweet_id, "original": original, "detected_language": lang, "created_at": created})

        # 最终保存缓存
        save_translation_cache(translation_cache)
        if all_texts:
            batches = (len(all_texts) + BATCH_SIZE - 1) // BATCH_SIZE
            print(f"✅ 批量翻译完成，共 {batches} 批（每批 {BATCH_SIZE} 条）\n")
        else:
            print("✅ 无需要翻译的推文\n")
        print(f"📈 翻译 LLM 调用: {translation_metrics['llm_calls']} 次")
        if translation_metrics.get("total_tokens"):
            print(f"   Token 用量: {translation_metrics['total_tokens']}")
        if translation_metrics.get("failed_batches"):
            print(f"   失败批次: {translation_metrics['failed_batches']}")
        print(
            f"   缓存命中/未命中: {translation_metrics['cache_hits']} / "
            f"{translation_metrics['cache_misses']}"
        )
        print()
        call_summary = llm_call_recorder.summary()
        if call_summary["calls"]:
            print(
                f"   调用级记录: {call_summary['successful_calls']} 成功 / "
                f"{call_summary['failed_calls']} 失败"
            )
            if call_summary["estimated_cost"]:
                print(f"   预估成本 (USD): {call_summary['estimated_cost']:.6f}")
        print()

        # 保存失败列表供下次重试
        failed_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_failed.json")
        if failed_list:
            save_json(failed_file, failed_list)
            print(f"⚠️ {len(failed_list)} 条翻译失败，已保存至: {failed_file}")
            print("   下次运行将自动重试\n")
        elif os.path.exists(failed_file):
            save_json(failed_file, [])
            print(f"✅ 已清理过期翻译失败清单: {failed_file}\n")
        
        # 显示语言统计
        print("\n📊 语言分布统计:")
        for lang, count in lang_stats.most_common():
            lang_name = {
                "ja": "日语", "en": "英语", "zh-cn": "中文", "zh": "中文", 
                "unknown": "未知", "ko": "韩语", "es": "西班牙语", "fr": "法语"
            }.get(lang, lang)
            print(f"   {lang_name}: {count} 条")
        print()

        # 保存翻译结果
        translated_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_translated.json")
        existing_translated = load_json(translated_file, default=[])
        if not isinstance(existing_translated, list):
            raise ValueError(f"翻译文件必须是 JSON 数组: {translated_file}")
        if args.replace and failed_list:
            print("❌ --replace 本次翻译未全部成功，原 raw/translated 快照均未覆盖。")
            return 1
        if args.replace:
            replace_json_files_atomically({raw_file: raw_tweets, translated_file: translated_data})
            print(f"💾 原始推文已保存至: {raw_file}")
        else:
            translated_data = merge_translated_tweets(existing_translated, translated_data)
            save_json(translated_file, translated_data)
        print(f"💾 翻译结果已保存至: {translated_file}")
        print(f"✅ 成功翻译 {len(translated)} 条推文\n")

        if failed_list:
            print(f"❌ 翻译未完整：{len(failed_list)} 条失败，已保存成功结果并返回失败状态。")
            return 1

        if len(translated) < 10:
            print("⚠️ 可用推文过少（< 10条），无法进行有效分析")
            return 0

        if not ml_analysis_available():
            print("⚠️ 未安装 ML 可选依赖，已完成抓取和翻译，跳过向量聚类与画像生成。")
            print("   如需完整分析，请运行: python3 -m pip install -e '.[ml]'")
            return 0

        analysis_texts = sample_evenly(translated, ANALYSIS_LIMIT)
        if len(translated) > len(analysis_texts):
            print(f"⚠️ 长输入保护：已保存全部 {len(translated)} 条翻译，聚类/画像按时间跨度均匀抽样分析 {len(analysis_texts)} 条")

        # 4. 动态聚类
        # 动态确定聚类数量：每10条推文1个主题，最少2个，最多8个
        cluster_num = max(2, min(8, len(analysis_texts) // 10))
        print(f"🔢 向量化 + 聚类（聚类数: {cluster_num}）...")
        
        # Lazy import
        from sentence_transformers import SentenceTransformer
        from sklearn.cluster import KMeans
        embedding_model_name = "paraphrase-multilingual-MiniLM-L12-v2"
        embed_model = SentenceTransformer(embedding_model_name)
        vectors = encode_texts_with_cache(
            analysis_texts,
            model_name=embedding_model_name,
            cache_path=os.path.join(CACHE_DIR, "embeddings_cache.json"),
            encoder=embed_model.encode,
        )
        labels = KMeans(n_clusters=cluster_num, random_state=42).fit_predict(vectors)

        clusters = {}
        for label, text in zip(labels, analysis_texts):
            clusters.setdefault(label, []).append(text)

        # 显示聚类结果
        print(f"✅ 聚类完成，共 {len(clusters)} 个主题：")
        for k, v in sorted(clusters.items()):
            print(f"   主题 {k}: {len(v)} 条推文")
        print()

        # 5. 生成画像
        cluster_text = ""
        for k, v in sorted(clusters.items()):
            cluster_text += f"\n【主题 {k}】（共 {len(v)} 条）\n"
            cluster_text += "\n".join(v[:5]) + "\n"

        print("🧠 生成兴趣画像...")
        profile = deepseek_profile_summary(cluster_text)

        # 保存完整分析结果
        result = {
            "username": TARGET_USERNAME,
            "user_id": user_id,
            "analysis_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "stats": {
                "raw_tweets": len(raw_tweets),
                "translated_tweets": len(translated),
                "analyzed_tweets": len(analysis_texts),
                "translation_llm_calls": translation_metrics["llm_calls"],
                "translation_total_tokens": translation_metrics.get("total_tokens") or None,
                "translation_failed_batches": translation_metrics["failed_batches"],
                "translation_cache_hits": translation_metrics["cache_hits"],
                "translation_cache_misses": translation_metrics["cache_misses"],
                "translation_cache_fingerprint": translation_metrics["cache_fingerprint"],
                "clusters": cluster_num,
                "language_distribution": dict(lang_stats)
            },
            "clusters": {int(k): v for k, v in clusters.items()},  # 转换 numpy.int32 为 int
            "profile": profile
        }
        
        result_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_analysis.json")
        save_json(result_file, result)
        print(f"💾 完整分析已保存至: {result_file}\n")

        # 6. 输出结果
        print("\n" + "=" * 60)
        print("🎨 用户兴趣画像")
        print("=" * 60 + "\n")
        print(profile)
        print("\n" + "=" * 60)
        print(f"✅ 分析完成！共分析 {len(translated)} 条推文，识别 {cluster_num} 个主题")
        print("=" * 60 + "\n")
        return 0
        
    except Exception as e:
        print(f"\n❌ 程序执行出错: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1

# ======================
# 入口
# ======================
if __name__ == "__main__":
    raise SystemExit(main())
