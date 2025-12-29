import os
import json
from openai import OpenAI
from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans
from dotenv import load_dotenv
from datetime import datetime

# 禁用 tokenizers 并行警告
os.environ["TOKENIZERS_PARALLELISM"] = "false"

_ = load_dotenv()

# ======================
# 配置
# ======================
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
TARGET_USERNAME = os.getenv("TARGET_USERNAME", "MiracleHe")  # 从环境变量读取
CACHE_DIR = "cache"

# ======================
# 初始化客户端
# ======================
ds_client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL
)

print("🔄 加载向量模型...")
embed_model = SentenceTransformer(
    "paraphrase-multilingual-MiniLM-L12-v2"
)

def deepseek_profile_summary(cluster_text):
    """生成用户画像，支持重试"""
    prompt = f"""
你是一名数据分析师。

请根据以下推文主题，总结该用户的：
1. 核心兴趣（1-3 个）
2. 次要兴趣
3. 内容风格
4. 情绪倾向

要求：
- 使用简体中文
- 偏客观分析
- 输出结构化结果

推文主题内容：
{cluster_text}
"""
    
    r = ds_client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    return r.choices[0].message.content.strip()

def main():
    print("=" * 60)
    print(f"🎯 目标用户: {TARGET_USERNAME}")
    print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")
    
    # 1. 加载已有的翻译数据
    translated_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_translated.json")
    raw_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_raw_tweets.json")
    
    if not os.path.exists(translated_file):
        print(f"❌ 找不到翻译文件: {translated_file}")
        return
    
    print("📂 加载已有的翻译数据...")
    with open(translated_file, 'r', encoding='utf-8') as f:
        translated_data = json.load(f)
    
    with open(raw_file, 'r', encoding='utf-8') as f:
        raw_tweets = json.load(f)
    
    # 提取翻译后的文本
    translated = [item["translated"] for item in translated_data]
    print(f"✅ 已加载 {len(translated)} 条翻译数据\n")
    
    if len(translated) < 10:
        print("⚠️ 可用推文过少（< 10条），无法进行有效分析")
        return
    
    # 2. 动态聚类
    cluster_num = max(2, min(8, len(translated) // 10))
    print(f"🔢 向量化 + 聚类（聚类数: {cluster_num}）...")
    
    vectors = embed_model.encode(translated)
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
    profile = deepseek_profile_summary(cluster_text)
    
    # 4. 保存完整分析结果
    result = {
        "username": TARGET_USERNAME,
        "user_id": "1307832526484901889",  # 从之前的运行结果获取
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
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"💾 完整分析已保存至: {result_file}\n")
    
    # 5. 输出结果
    print("\n" + "=" * 60)
    print("🎨 用户兴趣画像")
    print("=" * 60 + "\n")
    print(profile)
    print("\n" + "=" * 60)
    print(f"✅ 分析完成！共分析 {len(translated)} 条推文，识别 {cluster_num} 个主题")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    main()
