from __future__ import annotations

import argparse
import os
from datetime import datetime

from dotenv import load_dotenv
from sklearn.cluster import KMeans

from xcrawler.clients.llm import create_openai_client
from xcrawler.config import load_config, require_secret
from xcrawler.services.embeddings import encode_texts_with_cache
from xcrawler.services.profile import deepseek_profile_summary
from xcrawler.services.records import normalize_translated_tweets
from xcrawler.storage.json_store import load_json, save_json
from xcrawler.utils import cli_validation

_ = load_dotenv()
_config = load_config()

CACHE_DIR = _config.cache_dir
LLM_MODEL = _config.llm_model
TARGET_USERNAME = _config.target_username

def parse_args():
    parser = argparse.ArgumentParser(description="快速兴趣画像分析（仅分析现有数据）")
    parser.add_argument("-u", "--user", type=cli_validation.x_username, help="目标用户名")
    parser.add_argument("--cache-dir", help=f"缓存目录（默认 {CACHE_DIR}）")
    return parser.parse_args()

def main():
    global TARGET_USERNAME, CACHE_DIR

    args = parse_args()
    if args.user:
        TARGET_USERNAME = args.user
    if args.cache_dir:
        CACHE_DIR = args.cache_dir
    print("=" * 60)
    print(f"🎯 目标用户: {TARGET_USERNAME}")
    print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")
    
    # 1. 加载已有的翻译数据
    translated_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_translated.json")
    raw_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_raw_tweets.json")
    
    translated_data_raw = load_json(translated_file)
    if translated_data_raw is None:
        print(f"❌ 找不到翻译文件: {translated_file}")
        return 1
    translated_data = normalize_translated_tweets(translated_data_raw)
    
    print("📂 加载已有的翻译数据...")
    raw_tweets = load_json(raw_file, default=[])
    
    # 提取翻译后的文本
    translated = [item["translated"] for item in translated_data]
    print(f"✅ 已加载 {len(translated)} 条翻译数据\n")
    
    if len(translated) < 10:
        print("⚠️ 可用推文过少（< 10条），无法进行有效分析")
        return 0
    
    # 2. 动态聚类
    cluster_num = max(2, min(8, len(translated) // 10))
    print(f"🔢 向量化 + 聚类（聚类数: {cluster_num}）...")
    
    # Lazy import 向量模型
    from sentence_transformers import SentenceTransformer
    print("🔄 加载向量模型...")
    embedding_model_name = "paraphrase-multilingual-MiniLM-L12-v2"
    embed_model = SentenceTransformer(embedding_model_name)
    
    vectors = encode_texts_with_cache(
        translated,
        model_name=embedding_model_name,
        cache_path=os.path.join(CACHE_DIR, "embeddings_cache.json"),
        encoder=embed_model.encode,
    )
    labels = KMeans(n_clusters=cluster_num, random_state=42).fit_predict(vectors)
    
    clusters = {}
    for label, text in zip(labels, translated):
        clusters.setdefault(label, []).append(text)
    
    # 显示聚类结果
    print(f"✅ 聚类完成，共 {len(clusters)} 个主题：")
    for k, v in sorted(clusters.items()):
        print(f"   主题 {k}: {len(v)} 条推文")
    print()
    
    # 3. 生成画像
    cluster_text = ""
    for k, v in sorted(clusters.items()):
        cluster_text += f"\n【主题 {k}】（共 {len(v)} 条）\n"
        cluster_text += "\n".join(v[:5]) + "\n"

    print("🧠 生成兴趣画像...")
    def _create_client():
        return create_openai_client(
            api_key=require_secret("DEEPSEEK_API_KEY", _config.deepseek_api_key, purpose="兴趣画像"),
            base_url=_config.deepseek_base_url,
        )
    profile = deepseek_profile_summary(cluster_text, client_factory=_create_client, model=LLM_MODEL)
    
    # 4. 保存完整分析结果
    result = {
        "username": TARGET_USERNAME,
        "user_id": None,  # 仅分析模式下不重新获取ID
        "analysis_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "stats": {
            "raw_tweets": len(raw_tweets),
            "translated_tweets": len(translated),
            "clusters": cluster_num
        },
        "clusters": {int(k): v for k, v in clusters.items()},  # 转换 numpy.int32 为 int
        "profile": profile
    }
    
    result_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_analysis.json")
    save_json(result_file, result)
    print(f"💾 完整分析已保存至: {result_file}\n")
    
    # 5. 输出结果
    print("\n" + "=" * 60)
    print("🎨 用户兴趣画像")
    print("=" * 60 + "\n")
    print(profile)
    print("\n" + "=" * 60)
    print(f"✅ 分析完成！共分析 {len(translated)} 条推文，识别 {cluster_num} 个主题")
    print("=" * 60 + "\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main() or 0)
