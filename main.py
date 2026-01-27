import os
import re
import json
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from openai import OpenAI

from dotenv import load_dotenv
from datetime import datetime
from collections import Counter


_ = load_dotenv()

# ======================
# 配置
# ======================
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")

TARGET_USERNAME = os.getenv("TARGET_USERNAME", "MiracleHe")  # 从环境变量读取，默认 MiracleHe
MAX_PAGES = 50                      # 控制抓取数量（50*100 = 5000 条，覆盖更长时间）
MAX_RETRIES = 3                       # API 重试次数
MAX_WORKERS = 5                       # 并发线程数
CACHE_DIR = "cache"                   # 缓存目录

# ======================
# 初始化客户端和缓存
# ======================
ds_client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL
)

# embed_model moved to main()


HEADERS = {
    "Authorization": f"Bearer {X_BEARER_TOKEN}"
}

# 创建缓存目录
os.makedirs(CACHE_DIR, exist_ok=True)

# 翻译缓存
translation_cache: dict[str, str] = {}

# ======================
# 工具函数
# ======================
def clean_text(text):
    text = re.sub(r"http\S+", "", text)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def load_translation_cache():
    """加载翻译缓存"""
    cache_file = os.path.join(CACHE_DIR, "translation_cache.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_translation_cache(cache):
    """保存翻译缓存"""
    cache_file = os.path.join(CACHE_DIR, "translation_cache.json")
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def detect_language(text: str) -> str:
    """检测文本语言"""
    try:
        from langdetect import detect
        # 清理文本，移除URL和@符号
        clean = re.sub(r"http\S+|@\w+|#\w+", "", text).strip()
        if len(clean) < 3:
            return "unknown"
        
        lang = detect(clean)
        return lang
    except ImportError:
        return "unknown"
    except:
        return "unknown"

def deepseek_translate(text: str, detected_lang: str = None, use_cache: bool = True) -> str | None:
    """智能翻译多语言到中文，支持缓存和重试"""
    global translation_cache
    
    # 检查缓存
    if use_cache and text in translation_cache:
        return translation_cache[text]
    
    # 检测语言 (如果没有传入)
    if not detected_lang:
        detected_lang = detect_language(text)
    
    # 如果已经是中文，直接返回
    if detected_lang == "zh-cn" or detected_lang == "zh":
        if use_cache:
            translation_cache[text] = text
        return text
    
    # 如果不是日语或英语，也尝试翻译（通用模式）
    
    prompt = f"""
你是一名专业的翻译专家。
请将以下推文（检测到的语言代码：{detected_lang}）翻译成自然、准确的简体中文：
- 保留技术术语和专有名词
- 保持原文的语气和风格
- 不要解释或扩写
- 如果是网络用语或梗，请翻译成对应的中文网络用语

原文：
{text}
"""
    
    # 重试机制
    for attempt in range(MAX_RETRIES):
        try:
            r = ds_client.chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )
            result = r.choices[0].message.content.strip()
            
            # 保存到缓存
            if use_cache:
                translation_cache[text] = result
            
            return result
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                print(f"⚠️ 翻译失败，重试 {attempt + 1}/{MAX_RETRIES}... 错误: {str(e)}")
                time.sleep(2 ** attempt)  # 指数退避
            else:
                print(f"❌ 翻译失败，跳过该条推文: {str(e)}")
                return None

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
    
    for attempt in range(MAX_RETRIES):
        try:
            r = ds_client.chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            return r.choices[0].message.content.strip()
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                print(f"⚠️ 画像生成失败，重试 {attempt + 1}/{MAX_RETRIES}...")
                time.sleep(2 ** attempt)
            else:
                print(f"❌ 画像生成失败: {str(e)}")
                raise

# ======================
# X API
# ======================
def get_user_id(username: str) -> str:
    """获取用户ID，带错误处理"""
    url = f"https://api.twitter.com/2/users/by/username/{username}"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if "data" not in data:
            raise ValueError(f"用户 '{username}' 不存在或无权访问")
        
        return data["data"]["id"]
    except requests.exceptions.RequestException as e:
        raise Exception(f"获取用户ID失败: {str(e)}")

def fetch_tweets(user_id: str) -> list[dict]:
    """抓取推文，带错误处理和进度显示"""
    url = f"https://api.twitter.com/2/users/{user_id}/tweets"
    params = {
        "max_results": 100,
        "tweet.fields": "created_at,entities",
        "exclude": "retweets,replies"  # 排除转发和回复
    }

    tweets = []
    for page in range(MAX_PAGES):
        try:
            response = requests.get(url, headers=HEADERS, params=params, timeout=10)
            
            # 检查是否被限流
            if response.status_code == 429:
                # 获取重置时间
                reset_time = response.headers.get('x-rate-limit-reset')
                if reset_time:
                    wait_seconds = int(reset_time) - int(time.time())
                    if wait_seconds > 0:
                        print(f"⏳ API 限流，需等待 {wait_seconds // 60} 分 {wait_seconds % 60} 秒...")
                        print(f"💡 提示：X API 有严格的频率限制，请稍后再试")
                        if page == 0:
                            raise Exception(f"API 限流，请等待 {wait_seconds // 60} 分钟后再运行")
                        break
                else:
                    print(f"⚠️ API 限流（429），建议等待 15 分钟后重试")
                    if page == 0:
                        raise Exception("API 限流，请等待 15 分钟后再运行")
                    break
            
            response.raise_for_status()
            data = response.json()
            
            # 检查是否有数据
            page_tweets = data.get("data", [])
            if not page_tweets:
                print(f"📭 第 {page + 1} 页无数据，停止抓取")
                break
            
            tweets.extend(page_tweets)
            print(f"📄 已抓取第 {page + 1} 页，本页 {len(page_tweets)} 条，累计 {len(tweets)} 条")
            
            # 显示剩余配额
            remaining = response.headers.get('x-rate-limit-remaining')
            if remaining:
                print(f"   剩余配额: {remaining} 次")
            
            # 检查是否有下一页
            token = data.get("meta", {}).get("next_token")
            if not token:
                print(f"✅ 已抓取所有可用推文")
                break
            params["pagination_token"] = token
            
            # 避免请求过快
            time.sleep(1)  # 增加到 1 秒
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                print(f"⚠️ API 限流，请稍后重试")
            else:
                print(f"⚠️ 第 {page + 1} 页抓取失败: {str(e)}")
            if page == 0:
                raise Exception(f"首页抓取失败: {str(e)}")
            break
        except requests.exceptions.RequestException as e:
            print(f"⚠️ 第 {page + 1} 页抓取失败: {str(e)}")
            if page == 0:
                raise Exception(f"首页抓取失败: {str(e)}")
            break

    return tweets

# ======================
# 主流程
# ======================
def main():
    global translation_cache
    
    print("=" * 60)
    print(f"🎯 目标用户: {TARGET_USERNAME}")
    print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")
    
    # 加载翻译缓存
    translation_cache = load_translation_cache()
    print(f"💾 已加载翻译缓存: {len(translation_cache)} 条\n")
    
    try:
        # 1. 获取用户ID
        print("🚀 获取用户 ID...")
        user_id = get_user_id(TARGET_USERNAME)
        print(f"✅ 用户 ID: {user_id}\n")

        # 2. 抓取推文
        print("📥 抓取推文（已排除转发和回复）...")
        raw_tweets = fetch_tweets(user_id)
        print(f"📊 共抓取 {len(raw_tweets)} 条原创推文\n")
        
        if len(raw_tweets) == 0:
            print("❌ 没有抓取到任何推文，请检查用户是否存在或是否有权限")
            return
        
        # 保存原始推文
        raw_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_raw_tweets.json")
        with open(raw_file, 'w', encoding='utf-8') as f:
            json.dump(raw_tweets, f, ensure_ascii=False, indent=2)
        print(f"💾 原始推文已保存至: {raw_file}\n")

        # 3. 清洗 + 翻译
        print("🧹 清洗 + 智能翻译（日/英 → 中）...")
        translated = []
        translated_data = []  # 保存完整数据
        lang_stats = Counter()  # 统计语言分布
        
        # 预处理：清洗和语言检测
        to_process = []
        for t in raw_tweets:
            original_text = clean_text(t["text"])
            if len(original_text) < 6:
                continue
                
            detected_lang = detect_language(original_text)
            lang_stats[detected_lang] += 1
            to_process.append((original_text, detected_lang, t.get("created_at", "")))

        # 并发翻译
        print(f"🚀 启动 {MAX_WORKERS} 个线程进行并行翻译...")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # 提交任务
            future_to_tweet = {
                executor.submit(deepseek_translate, text, lang): (text, lang, created_at)
                for text, lang, created_at in to_process
            }
            
            # 处理结果
            for future in tqdm(as_completed(future_to_tweet), total=len(to_process), desc="翻译进度"):
                original, lang, created = future_to_tweet[future]
                try:
                    translated_text = future.result()
                    if translated_text:
                        translated.append(translated_text)
                        translated_data.append({
                            "original": original,
                            "translated": translated_text,
                            "detected_language": lang,
                            "created_at": created
                        })
                except Exception as e:
                    print(f"❌ 处理推文出错: {str(e)}")
        
        # 显示语言统计
        print(f"\n📊 语言分布统计:")
        for lang, count in lang_stats.most_common():
            lang_name = {
                "ja": "日语", "en": "英语", "zh-cn": "中文", "zh": "中文", 
                "unknown": "未知", "ko": "韩语", "es": "西班牙语", "fr": "法语"
            }.get(lang, lang)
            print(f"   {lang_name}: {count} 条")
        print()
        
        # 保存翻译缓存
        save_translation_cache(translation_cache)
        print(f"💾 翻译缓存已更新: {len(translation_cache)} 条\n")
        
        # 保存翻译结果
        translated_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_translated.json")
        with open(translated_file, 'w', encoding='utf-8') as f:
            json.dump(translated_data, f, ensure_ascii=False, indent=2)
        print(f"💾 翻译结果已保存至: {translated_file}")
        print(f"✅ 成功翻译 {len(translated)} 条推文\n")

        if len(translated) < 10:
            print("⚠️ 可用推文过少（< 10条），无法进行有效分析")
            return

        # 4. 动态聚类
        # 动态确定聚类数量：每10条推文1个主题，最少2个，最多8个
        cluster_num = max(2, min(8, len(translated) // 10))
        print(f"🔢 向量化 + 聚类（聚类数: {cluster_num}）...")
        
        # Lazy import
        from sentence_transformers import SentenceTransformer
        from sklearn.cluster import KMeans
        embed_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
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
                "clusters": cluster_num,
                "language_distribution": dict(lang_stats)
            },
            "clusters": {int(k): v for k, v in clusters.items()},  # 转换 numpy.int32 为 int
            "profile": profile
        }
        
        result_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_analysis.json")
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"💾 完整分析已保存至: {result_file}\n")

        # 6. 输出结果
        print("\n" + "=" * 60)
        print("🎨 用户兴趣画像")
        print("=" * 60 + "\n")
        print(profile)
        print("\n" + "=" * 60)
        print(f"✅ 分析完成！共分析 {len(translated)} 条推文，识别 {cluster_num} 个主题")
        print("=" * 60 + "\n")
        
    except Exception as e:
        print(f"\n❌ 程序执行出错: {str(e)}")
        import traceback
        traceback.print_exc()

# ======================
# 入口
# ======================
if __name__ == "__main__":
    main()
