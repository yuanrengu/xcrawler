import os
import re
import json
import time
import argparse
import requests
from openai import OpenAI

from dotenv import load_dotenv
from datetime import datetime
from collections import Counter


_ = load_dotenv()

# ======================
# 配置（默认值，CLI 参数可覆盖）
# ======================
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")

TARGET_USERNAME = os.getenv("TARGET_USERNAME", "MiracleHe")
MAX_PAGES = 50
MAX_RETRIES = 3
MAX_WORKERS = 5
CACHE_DIR = "cache"
BATCH_SIZE = 10


def parse_args():
    """解析 CLI 参数，覆盖 .env 默认值"""
    parser = argparse.ArgumentParser(description="Twitter 用户数据抓取 + 翻译 + 聚类分析")
    parser.add_argument("-u", "--user", help="目标用户名（覆盖 .env 中的 TARGET_USERNAME）")
    parser.add_argument("--pages", type=int, help=f"抓取页数，每页100条（默认 {MAX_PAGES}）")
    parser.add_argument("--batch-size", type=int, help=f"每批翻译条数（默认 {BATCH_SIZE}）")
    parser.add_argument("--model", help=f"LLM 模型名（默认 {LLM_MODEL}）")
    parser.add_argument("--cache-dir", help=f"缓存目录（默认 {CACHE_DIR}）")
    parser.add_argument("--no-translate", action="store_true", help="跳过翻译，仅抓取")
    return parser.parse_args()

# ======================
# 初始化客户端和缓存（lazy，首次调用时创建）
# ======================
ds_client = None

def _get_ds_client():
    global ds_client
    if ds_client is None:
        ds_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    return ds_client

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
        except Exception:
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
    except Exception:
        return "unknown"

def deepseek_translate(text: str, detected_lang: str = None, use_cache: bool = True) -> str | None:
    """智能翻译单条推文到中文，支持缓存和重试（保留向后兼容）"""
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

    p = f"""
你是一名精通多国语言的翻译专家，特别擅长将社交媒体内容（推特/X）翻译成地道、自然的中文。

【任务】
请将以下[{detected_lang}]推文翻译成简体中文。

【要求】
1. **地道表达**：不要直译，使用符合中文母语者习惯的表达方式。
2. **语境理解**：准确理解推特特有的非正式语境、语气和情感（如吐槽、兴奋、反讽）。
3. **术语处理**：保留专有名词（人名、地名、作品名）、技术术语或特定的原文标签（如 #Hashtag）。
4. **网络用语**：如果原文包含网络梗、流行语或缩写（如 lol, omg, wwww），请翻译成对应的中文网络用语或流行梗。
5. **格式保持**：不要随意解释或扩写，只输出翻译后的文本。

【原文】
{text}
""".strip()

    # 重试机制
    for attempt in range(MAX_RETRIES):
        try:
            r = _get_ds_client().chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": p}],
                temperature=0.1
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


def deepseek_translate_batch(texts: list[str], detected_langs: list[str | None] | None = None,
                              use_cache: bool = True) -> list[str | None]:
    """
    批量翻译推文到中文，一次 API 调用翻译多条，大幅降低费用。

    :param texts: 推文文本列表
    :param detected_langs: 每条推文的语言列表（可选）
    :param use_cache: 是否使用缓存
    :return: 翻译结果列表（与输入等长，失败的为 None）
    """
    global translation_cache

    n = len(texts)
    if detected_langs is None:
        langs: list[str | None] = [None] * n
    else:
        langs = list(detected_langs)

    results: list[str | None] = [None] * n

    # 1. 先从缓存和中文直通中提取已有的
    to_translate_indices = []
    to_translate_texts = []
    to_translate_langs = []

    for i in range(n):
        text = texts[i]
        lang = langs[i]

        # 检查缓存
        if use_cache and text in translation_cache:
            results[i] = translation_cache[text]
            continue

        # 检测语言
        if not lang:
            lang = detect_language(text)
            langs[i] = lang

        # 中文直通
        if lang in ("zh-cn", "zh"):
            if use_cache:
                translation_cache[text] = text
            results[i] = text
            continue

        to_translate_indices.append(i)
        to_translate_texts.append(text)
        to_translate_langs.append(lang)

    if not to_translate_texts:
        return results

    # 2. 分批调用 API
    total_batches = (len(to_translate_texts) + BATCH_SIZE - 1) // BATCH_SIZE
    translated_count = 0
    for batch_idx, batch_start in enumerate(range(0, len(to_translate_texts), BATCH_SIZE)):
        batch_end = batch_start + BATCH_SIZE
        batch_indices = to_translate_indices[batch_start:batch_end]
        batch_texts = to_translate_texts[batch_start:batch_end]
        batch_langs = to_translate_langs[batch_start:batch_end]
        batch_size = len(batch_texts)

        print(f"   📦 批次 [{batch_idx + 1}/{total_batches}] 翻译 {batch_size} 条...", end="", flush=True)

        # 构建编号列表
        numbered_lines = "\n".join(f"[{j+1}] {t}" for j, t in enumerate(batch_texts))
        lang_hint = ", ".join(set(batch_langs))

        p = f"""你是一名精通多国语言的翻译专家，擅长将社交媒体内容翻译成地道中文。

【任务】
将以下 {batch_size} 条推文依次翻译成简体中文。原文语言可能包含 {lang_hint} 等。

【要求】
1. 地道表达，不要直译
2. 保留专有名词和 #Hashtag
3. 网络用语翻译成对应中文网络用语
4. 只输出翻译，不要解释

【输出格式】
每行一条翻译，格式为 [编号] 翻译内容，必须与原文编号一一对应。

【原文】
{numbered_lines}""".strip()

        # 重试
        for attempt in range(MAX_RETRIES):
            try:
                r = _get_ds_client().chat.completions.create(
                    model=LLM_MODEL,
                    messages=[{"role": "user", "content": p}],
                    temperature=0.1
                )
                response_text = r.choices[0].message.content.strip()

                # 解析响应：按 [N] 前缀分割
                parsed = _parse_batch_response(response_text, batch_size)

                for j, idx in enumerate(batch_indices):
                    if j < len(parsed) and parsed[j]:
                        results[idx] = parsed[j]
                        if use_cache:
                            translation_cache[texts[idx]] = parsed[j]
                        translated_count += 1
                print(f" ✅ 已翻译 {translated_count}/{len(to_translate_texts)} 条")
                break
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    print(f"⚠️ 批量翻译失败，重试 {attempt + 1}/{MAX_RETRIES}... {str(e)}")
                    time.sleep(2 ** attempt)
                else:
                    print(f"❌ 批量翻译失败，回退到单条翻译...")
                    # 回退：逐条翻译
                    for j, idx in enumerate(batch_indices):
                        single = deepseek_translate(texts[idx], langs[idx], use_cache)
                        results[idx] = single

    return results


def _parse_batch_response(response: str, expected_count: int) -> list[str]:
    """
    解析批量翻译响应，提取 [N] 开头的翻译结果。
    兼容多种格式：[1] xxx、1. xxx、1) xxx 等。
    """
    lines = response.strip().split("\n")
    results = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # 匹配 [N]、N.、N) 等格式
        match = re.match(r'^\[?\d+\]?\s*[\.\):：]?\s*(.+)', line)
        if match:
            results.append(match.group(1).strip())

    # 如果解析失败（行数不对），尝试按行直接返回
    if len(results) != expected_count:
        # fallback: 过滤空行后直接返回
        results = [l.strip() for l in lines if l.strip()]

    return results

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
            r = _get_ds_client().chat.completions.create(
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


def get_user_profile(username: str) -> dict | None:
    """获取用户基础信息（bio、粉丝数、关注数等）"""
    url = f"https://api.twitter.com/2/users/by/username/{username}"
    params = {
        "user.fields": "description,public_metrics,created_at,profile_image_url,verified,location"
    }
    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if "data" not in data:
            return None
        user = data["data"]
        metrics = user.get("public_metrics", {})
        profile = {
            "username": username,
            "name": user.get("name", ""),
            "description": user.get("description", ""),
            "location": user.get("location", ""),
            "verified": user.get("verified", False),
            "created_at": user.get("created_at", ""),
            "profile_image_url": user.get("profile_image_url", ""),
            "followers_count": metrics.get("followers_count", 0),
            "following_count": metrics.get("following_count", 0),
            "tweet_count": metrics.get("tweet_count", 0),
            "listed_count": metrics.get("listed_count", 0),
        }
        return profile
    except Exception as e:
        print(f"⚠️ 获取用户信息失败: {str(e)}")
        return None

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
    global translation_cache, TARGET_USERNAME, MAX_PAGES, BATCH_SIZE, LLM_MODEL, CACHE_DIR

    # 应用 CLI 参数（覆盖 .env 默认值）
    args = parse_args()
    if args.user:
        TARGET_USERNAME = args.user
    if args.pages:
        MAX_PAGES = args.pages
    if args.batch_size:
        BATCH_SIZE = args.batch_size
    if args.model:
        LLM_MODEL = args.model
    if args.cache_dir:
        CACHE_DIR = args.cache_dir

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

        # 1.5 获取用户基础信息
        print("👤 获取用户基础信息...")
        profile_info = get_user_profile(TARGET_USERNAME)
        if profile_info:
            profile_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_profile.json")
            with open(profile_file, 'w', encoding='utf-8') as f:
                json.dump(profile_info, f, ensure_ascii=False, indent=2)
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
        print(f"📊 共抓取 {len(raw_tweets)} 条原创推文\n")
        
        if len(raw_tweets) == 0:
            print("❌ 没有抓取到任何推文，请检查用户是否存在或是否有权限")
            return
        
        # 保存原始推文
        raw_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_raw_tweets.json")
        with open(raw_file, 'w', encoding='utf-8') as f:
            json.dump(raw_tweets, f, ensure_ascii=False, indent=2)
        print(f"💾 原始推文已保存至: {raw_file}\n")

        # 3. 清洗 + 批量翻译
        if args.no_translate:
            print("⏭️  --no-translate 模式：跳过翻译和分析，仅保存原始推文")
            print(f"\n✅ 完成！原始推文已保存至: {raw_file}")
            return

        print("🧹 清洗 + 智能批量翻译...")
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

        # 批量翻译（每 BATCH_SIZE 条一组，大幅减少 API 调用）
        all_texts = [t[0] for t in to_process]
        all_langs = [t[1] for t in to_process]
        all_created = [t[2] for t in to_process]

        print(f"🚀 批量翻译 {len(all_texts)} 条推文（每批 {BATCH_SIZE} 条）...")
        batch_results = deepseek_translate_batch(all_texts, all_langs)

        # 收集结果
        failed_list = []
        save_counter = 0
        for i, (original, lang, created) in enumerate(zip(all_texts, all_langs, all_created)):
            translated_text = batch_results[i]
            if translated_text:
                translated.append(translated_text)
                translated_data.append({
                    "original": original,
                    "translated": translated_text,
                    "detected_language": lang,
                    "created_at": created
                })
                save_counter += 1
                if save_counter % 50 == 0:
                    save_translation_cache(translation_cache)
            else:
                failed_list.append({"original": original, "detected_language": lang, "created_at": created})

        # 最终保存缓存
        save_translation_cache(translation_cache)
        batches = max(1, len(all_texts) // BATCH_SIZE)
        print(f"✅ 批量翻译完成，共 {batches} 批（每批 {BATCH_SIZE} 条）\n")

        # 保存失败列表供下次重试
        if failed_list:
            failed_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_failed.json")
            with open(failed_file, 'w', encoding='utf-8') as f:
                json.dump(failed_list, f, ensure_ascii=False, indent=2)
            print(f"⚠️ {len(failed_list)} 条翻译失败，已保存至: {failed_file}")
            print(f"   下次运行将自动重试\n")
        
        # 显示语言统计
        print(f"\n📊 语言分布统计:")
        for lang, count in lang_stats.most_common():
            lang_name = {
                "ja": "日语", "en": "英语", "zh-cn": "中文", "zh": "中文", 
                "unknown": "未知", "ko": "韩语", "es": "西班牙语", "fr": "法语"
            }.get(lang, lang)
            print(f"   {lang_name}: {count} 条")
        print()

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
