import os
import json
import argparse
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from xcrawler.services.records import normalize_translated_tweets

# 尝试导入可选依赖
try:
    from openai import OpenAI
    from dotenv import load_dotenv
    _ = load_dotenv()
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False
    print("⚠️ openai 或 dotenv 未安装，将跳过AI分析部分")

# 禁用 tokenizers 并行警告
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# ======================
# 配置
# ======================
TARGET_USERNAME = os.getenv("TARGET_USERNAME", "MiracleHe")  # 从环境变量读取
CACHE_DIR = "cache"

if AI_AVAILABLE:
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
    ds_client = OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL
    )

def analyze_time_patterns(raw_tweets):
    """分析发推时间模式"""
    # UTC+N 时区偏移，默认+9 (日本/韩国)
    tz_offset = float(os.getenv("TIMEZONE_OFFSET", "9"))
    JST_OFFSET = timedelta(hours=tz_offset)
    tz_label = f"UTC+{int(tz_offset)}" if tz_offset == int(tz_offset) else f"UTC+{tz_offset}"
    
    hour_counts = Counter()
    weekday_counts = Counter()
    weekend_vs_weekday = {"weekday": 0, "weekend": 0}
    time_period_counts = {
        "深夜 (0-6点)": 0,
        "早晨 (6-9点)": 0,
        "上午 (9-12点)": 0,
        "下午 (12-18点)": 0,
        "晚上 (18-24点)": 0
    }
    
    for tweet in raw_tweets:
        if "created_at" not in tweet:
            continue
        
        # 解析UTC时间并转换为本地时间（兼容有/无微秒格式）
        try:
            dt_utc = datetime.strptime(tweet["created_at"], "%Y-%m-%dT%H:%M:%S.%fZ")
        except ValueError:
            dt_utc = datetime.strptime(tweet["created_at"], "%Y-%m-%dT%H:%M:%SZ")
        dt_jst = dt_utc + JST_OFFSET
        
        hour = dt_jst.hour
        weekday = dt_jst.weekday()  # 0=周一, 6=周日
        
        hour_counts[hour] += 1
        weekday_counts[weekday] += 1
        
        # 工作日 vs 周末
        if weekday < 5:
            weekend_vs_weekday["weekday"] += 1
        else:
            weekend_vs_weekday["weekend"] += 1
        
        # 时间段分类
        if 0 <= hour < 6:
            time_period_counts["深夜 (0-6点)"] += 1
        elif 6 <= hour < 9:
            time_period_counts["早晨 (6-9点)"] += 1
        elif 9 <= hour < 12:
            time_period_counts["上午 (9-12点)"] += 1
        elif 12 <= hour < 18:
            time_period_counts["下午 (12-18点)"] += 1
        else:
            time_period_counts["晚上 (18-24点)"] += 1
    
    # 找出最活跃的时段
    top_hours = hour_counts.most_common(3)
    top_weekdays = weekday_counts.most_common(3)
    
    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    
    return {
        "hour_distribution": dict(hour_counts),
        "weekday_distribution": {weekday_names[k]: v for k, v in weekday_counts.items()},
        "weekend_vs_weekday": weekend_vs_weekday,
        "time_period_counts": time_period_counts,
        "top_active_hours": [(f"{h}:00", count) for h, count in top_hours],
        "top_active_weekdays": [(weekday_names[d], count) for d, count in top_weekdays],
        "total_tweets": len(raw_tweets),
        "tz_label": tz_label
    }

def detect_life_events(translated_data):
    """使用AI检测生活事件"""
    if not AI_AVAILABLE:
        print("⚠️ AI功能不可用，跳过事件检测")
        return None
    
    # 准备推文文本
    tweets_text = "\n\n".join([
        f"[tweet_id={item.get('tweet_id') or 'unknown'}][{item.get('created_at', 'unknown')}] {item['translated']}"
        for item in translated_data[:200]  # 分析前200条
    ])
    
    prompt = f"""
你是一名专业的社交媒体分析师。请从以下推文中识别用户提到的**重要生活事件**。

**需要识别的事件类型**：
1. 生日相关：提到自己或他人的生日、年龄
2. 感情相关：恋爱、分手、表白、约会、结婚等
3. 学业/职业：入学、毕业、找工作、换工作、升职等
4. 健康：生病、受伤、康复等
5. 旅行/搬家：去哪里旅行、搬到哪里等
6. 重大购物：买房、买车、买贵重物品等
7. 其他重要事件：考试、比赛、演出等

**输出格式**（JSON）：
```json
{{
  "birthday_mentions": [
    {{"description": "具体内容1", "evidence_tweet_ids": ["tweet_id_1"]}}
  ],
  "relationship_events": [],
  "career_education": [],
  "health_events": [],
  "travel_relocation": [],
  "major_purchases": [],
  "other_events": []
}}
```

**要求**：
- 只提取明确提到的事件，不要推测
- 如果某类事件没有，返回空数组 []
- 每个事件用简短的一句话描述，并保留支撑它的 evidence_tweet_ids
- 如果有时间信息，请保留

推文内容：
{tweets_text}
"""
    
    try:
        r = ds_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        result = r.choices[0].message.content.strip()
        
        # 尝试解析 JSON
        import re
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', result, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
        else:
            # 尝试直接解析
            return json.loads(result)
    except Exception as e:
        print(f"❌ 生活事件检测失败: {str(e)}")
        return None


def _normalize_life_events(life_events):
    """兼容旧式字符串事件，统一补 evidence_tweet_ids 字段。"""
    if not isinstance(life_events, dict):
        return life_events

    normalized = {}
    for category, events in life_events.items():
        normalized_events = []
        for event in events or []:
            if isinstance(event, dict):
                event.setdefault("description", "")
                event.setdefault("evidence_tweet_ids", [])
                event.setdefault("confidence", None)
                event.setdefault("sensitive", category in {
                    "birthday_mentions",
                    "relationship_events",
                    "health_events",
                    "travel_relocation",
                    "major_purchases",
                })
                normalized_events.append(event)
            else:
                normalized_events.append({
                    "description": str(event),
                    "evidence_tweet_ids": [],
                    "confidence": None,
                    "sensitive": category in {
                        "birthday_mentions",
                        "relationship_events",
                        "health_events",
                        "travel_relocation",
                        "major_purchases",
                    },
                })
        normalized[category] = normalized_events
    return normalized

def generate_behavior_summary(time_analysis, life_events):
    """生成行为特征总结"""
    if not AI_AVAILABLE:
        return "AI功能不可用，无法生成总结"
    
    prompt = f"""
你是一名数据分析师。请根据以下用户的时间行为和生活事件，生成一份简洁的行为特征总结。

**时间行为数据**：
- 总推文数: {time_analysis['total_tweets']}
- 工作日推文: {time_analysis['weekend_vs_weekday']['weekday']}条
- 周末推文: {time_analysis['weekend_vs_weekday']['weekend']}条
- 最活跃时段: {', '.join([f"{h} ({c}条)" for h, c in time_analysis['top_active_hours']])}
- 最活跃星期: {', '.join([f"{d} ({c}条)" for d, c in time_analysis['top_active_weekdays']])}
- 时段分布: {json.dumps(time_analysis['time_period_counts'], ensure_ascii=False)}

**生活事件**：
{json.dumps(life_events, ensure_ascii=False, indent=2)}

**请输出**：
1. 作息特征（2-3句话）
2. 活跃模式（2-3句话）
3. 生活状态概括（2-3句话）

要求：简洁、客观、有洞察力。
"""
    
    try:
        r = ds_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ 总结生成失败: {str(e)}")
        return "无法生成总结"

def parse_args():
    parser = argparse.ArgumentParser(description="用户行为分析：时间模式 + 生活事件检测")
    parser.add_argument("-u", "--user", help="目标用户名")
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
    print(f"📊 行为分析: 时间模式 + 生活事件")
    print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")
    
    # 1. 加载数据
    raw_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_raw_tweets.json")
    translated_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_translated.json")
    
    if not os.path.exists(raw_file) or not os.path.exists(translated_file):
        print(f"❌ 找不到数据文件，请先运行 main.py 抓取数据")
        return
    
    print("📂 加载数据...")
    with open(raw_file, 'r', encoding='utf-8') as f:
        raw_tweets = json.load(f)
    
    with open(translated_file, 'r', encoding='utf-8') as f:
        translated_data = normalize_translated_tweets(json.load(f))
    
    print(f"✅ 已加载 {len(raw_tweets)} 条原始推文\n")
    
    # 2. 时间行为分析
    print("⏰ 分析发推时间模式...")
    time_analysis = analyze_time_patterns(raw_tweets)
    print("✅ 时间分析完成\n")
    
    # 3. 生活事件检测
    if AI_AVAILABLE:
        print("🔍 检测生活事件（使用AI）...")
        life_events = detect_life_events(translated_data)
        if life_events:
            life_events = _normalize_life_events(life_events)
            print("✅ 事件检测完成\n")
        else:
            print("⚠️ 事件检测失败\n")
            life_events = {}
    else:
        print("⚠️ 跳过AI事件检测\n")
        life_events = {}
    
    # 4. 生成行为总结
    if AI_AVAILABLE:
        print("🧠 生成行为特征总结...")
        behavior_summary = generate_behavior_summary(time_analysis, life_events)
        print("✅ 总结生成完成\n")
    else:
        behavior_summary = "需要安装 openai 和 python-dotenv 才能使用AI分析功能"
    
    # 5. 保存结果
    result = {
        "username": TARGET_USERNAME,
        "analysis_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "time_analysis": time_analysis,
        "life_events": life_events,
        "behavior_summary": behavior_summary
    }
    
    result_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_behavior.json")
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"💾 行为分析已保存至: {result_file}\n")
    
    # 6. 输出结果
    print("\n" + "=" * 60)
    print("⏰ 时间行为分析")
    print("=" * 60 + "\n")
    
    print(f"📊 总推文数: {time_analysis['total_tweets']}")
    print(f"📅 工作日 vs 周末: {time_analysis['weekend_vs_weekday']['weekday']} vs {time_analysis['weekend_vs_weekday']['weekend']}")
    
    print(f"\n🕐 最活跃时段（{time_analysis['tz_label']}）:")
    for hour, count in time_analysis['top_active_hours']:
        print(f"   {hour} - {count}条推文")
    
    print(f"\n📆 最活跃星期:")
    for day, count in time_analysis['top_active_weekdays']:
        print(f"   {day} - {count}条推文")
    
    print(f"\n⏱️ 时段分布:")
    for period, count in time_analysis['time_period_counts'].items():
        percentage = (count / time_analysis['total_tweets'] * 100) if time_analysis['total_tweets'] > 0 else 0
        print(f"   {period}: {count}条 ({percentage:.1f}%)")
    
    print("\n" + "=" * 60)
    print("🎉 生活事件检测")
    print("=" * 60 + "\n")
    
    if life_events:
        event_labels = {
            "birthday_mentions": "🎂 生日相关",
            "relationship_events": "💕 感情相关",
            "career_education": "🎓 学业/职业",
            "health_events": "🏥 健康相关",
            "travel_relocation": "✈️ 旅行/搬家",
            "major_purchases": "🛒 重大购物",
            "other_events": "📌 其他事件"
        }
        
        has_events = False
        for key, label in event_labels.items():
            events = life_events.get(key, [])
            if events:
                has_events = True
                print(f"{label}:")
                for event in events:
                    if isinstance(event, dict):
                        evidence = ", ".join(event.get("evidence_tweet_ids", []))
                        suffix = f" (evidence: {evidence})" if evidence else ""
                        print(f"   • {event.get('description', '')}{suffix}")
                    else:
                        print(f"   • {event}")
                print()
        
        if not has_events:
            print("未检测到明确的生活事件")
    else:
        print("事件检测失败")
    
    print("\n" + "=" * 60)
    print("🎨 行为特征总结")
    print("=" * 60 + "\n")
    print(behavior_summary)
    
    print("\n" + "=" * 60)
    print("✅ 分析完成！")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    main()
