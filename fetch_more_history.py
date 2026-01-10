"""
增量抓取历史推文
从最早的推文继续向历史抓取，直到获取2024年的数据
"""
import os
import json
import time
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# 配置
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN")
TARGET_USERNAME = os.getenv("TARGET_USERNAME", "MiracleHe")  # 从环境变量读取
CACHE_DIR = "cache"
MAX_PAGES = 10  # Free 账号：每天只抓10页（1000条），避免超限

# 从环境变量读取目标日期，默认为2024-01-01
target_date_str = os.getenv("TARGET_DATE", "2024-01-01")
try:
    TARGET_DATE = datetime.strptime(target_date_str, "%Y-%m-%d")
except ValueError:
    print(f"⚠️ TARGET_DATE 格式错误: {target_date_str}，使用默认值: 2024-01-01")
    TARGET_DATE = datetime(2024, 1, 1)

REQUEST_INTERVAL = 3  # 每次请求间隔3秒，更保守

HEADERS = {
    "Authorization": f"Bearer {X_BEARER_TOKEN}"
}

def get_user_id(username):
    """获取用户ID"""
    url = f"https://api.twitter.com/2/users/by/username/{username}"
    response = requests.get(url, headers=HEADERS, timeout=10)
    response.raise_for_status()
    return response.json()["data"]["id"]

def fetch_more_tweets(user_id, until_id=None):
    """继续抓取历史推文"""
    url = f"https://api.twitter.com/2/users/{user_id}/tweets"
    params = {
        "max_results": 100,
        "tweet.fields": "created_at,entities",
        "exclude": "retweets,replies"
    }
    
    if until_id:
        params["until_id"] = until_id  # 从指定推文ID之前开始
    
    all_tweets = []
    reached_target = False
    
    print(f"🚀 开始抓取历史推文...")
    if until_id:
        print(f"📍 从推文 ID {until_id} 之前开始")
    
    for page in range(MAX_PAGES):
        try:
            response = requests.get(url, headers=HEADERS, params=params, timeout=10)
            
            # 检查限流
            if response.status_code == 429:
                reset_time = response.headers.get('x-rate-limit-reset')
                if reset_time:
                    wait_seconds = int(reset_time) - int(time.time())
                    print(f"⏳ API 限流，等待 {wait_seconds // 60} 分 {wait_seconds % 60} 秒...")
                    time.sleep(wait_seconds + 5)
                    continue
                else:
                    print(f"⚠️ API 限流，请稍后再试")
                    break
            
            response.raise_for_status()
            data = response.json()
            
            page_tweets = data.get("data", [])
            if not page_tweets:
                print(f"📭 第 {page + 1} 页无数据，已抓取完所有推文")
                break
            
            all_tweets.extend(page_tweets)
            
            # 检查是否已到达目标日期（2024年1月1日）
            oldest_date = datetime.strptime(page_tweets[-1]["created_at"], "%Y-%m-%dT%H:%M:%S.%fZ")
            print(f"📄 第 {page + 1} 页: {len(page_tweets)}条 | 最早: {oldest_date.strftime('%Y-%m-%d')} | 累计: {len(all_tweets)}条")
            
            if oldest_date <= TARGET_DATE:
                reached_target = True
                print(f"✅ 已到达目标日期 {TARGET_DATE.strftime('%Y-%m-%d')}！")
                break
            
            # 检查剩余配额
            remaining = response.headers.get('x-rate-limit-remaining')
            if remaining:
                print(f"   剩余配额: {remaining} 次")
                if int(remaining) < 5:
                    print(f"⚠️ 配额不足，暂停抓取")
                    break
            
            # 获取下一页token
            token = data.get("meta", {}).get("next_token")
            if not token:
                print(f"✅ 已抓取所有可用推文")
                break
            params["pagination_token"] = token
            
            time.sleep(REQUEST_INTERVAL)  # 避免请求过快
            
        except Exception as e:
            print(f"⚠️ 第 {page + 1} 页抓取失败: {str(e)}")
            break
    
    return all_tweets, reached_target

def main():
    print("=" * 60)
    print(f"🎯 目标用户: {TARGET_USERNAME}")
    print(f"📅 目标: 抓取到 {TARGET_DATE.strftime('%Y-%m-%d')} 或最早推文")
    print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")
    
    # 加载现有数据
    raw_file = os.path.join(CACHE_DIR, f"{TARGET_USERNAME}_raw_tweets.json")
    
    if os.path.exists(raw_file):
        with open(raw_file, 'r', encoding='utf-8') as f:
            existing_tweets = json.load(f)
        print(f"💾 已加载现有数据: {len(existing_tweets)} 条")
        
        # 找到最早的推文ID
        oldest_tweet = min(existing_tweets, key=lambda t: t.get("created_at", ""))
        oldest_id = oldest_tweet["id"]
        oldest_date = datetime.strptime(oldest_tweet["created_at"], "%Y-%m-%dT%H:%M:%S.%fZ")
        print(f"📍 最早推文时间: {oldest_date.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📍 最早推文 ID: {oldest_id}\n")
        
        # 判断是否需要继续抓取
        if oldest_date <= TARGET_DATE:
            print(f"✅ 已有 {TARGET_DATE.strftime('%Y-%m-%d')} 或更早的数据，无需继续抓取")
            return
        else:
            print(f"📈 最早推文在 {TARGET_DATE.strftime('%Y-%m-%d')} 之后，继续抓取历史数据\n")
    else:
        print(f"⚠️ 未找到现有数据文件，将从头开始抓取\n")
        existing_tweets = []
        oldest_id = None
    
    # 获取用户ID
    print("🔍 获取用户 ID...")
    user_id = get_user_id(TARGET_USERNAME)
    print(f"✅ 用户 ID: {user_id}\n")
    
    # 抓取更多历史推文
    new_tweets, reached_target = fetch_more_tweets(user_id, until_id=oldest_id)
    
    if new_tweets:
        print(f"\n📊 本次抓取: {len(new_tweets)} 条新推文")
        
        # 合并数据（去重）
        existing_ids = {t["id"] for t in existing_tweets}
        new_unique = [t for t in new_tweets if t["id"] not in existing_ids]
        
        all_tweets = existing_tweets + new_unique
        all_tweets.sort(key=lambda t: t.get("created_at", ""), reverse=True)
        
        print(f"📊 新增推文: {len(new_unique)} 条")
        print(f"📊 总推文数: {len(all_tweets)} 条")
        
        # 统计时间范围
        dates = [datetime.strptime(t["created_at"], "%Y-%m-%dT%H:%M:%S.%fZ") for t in all_tweets]
        dates.sort()
        print(f"\n📅 时间范围:")
        print(f"   最早: {dates[0].strftime('%Y-%m-%d')}")
        print(f"   最新: {dates[-1].strftime('%Y-%m-%d')}")
        print(f"   跨度: {(dates[-1] - dates[0]).days} 天")
        
        # 按年份统计
        from collections import Counter
        years = Counter([d.year for d in dates])
        print(f"\n📊 按年份统计:")
        for year in sorted(years.keys()):
            print(f"   {year}年: {years[year]}条")
        
        # 保存
        with open(raw_file, 'w', encoding='utf-8') as f:
            json.dump(all_tweets, f, ensure_ascii=False, indent=2)
        print(f"\n💾 已保存至: {raw_file}")
        
        # 判断抓取结果
        earliest_date = dates[0]
        if reached_target:
            print(f"\n✅ 成功！已抓取到 {TARGET_DATE.strftime('%Y-%m-%d')} 的数据")
        elif earliest_date <= TARGET_DATE:
            print(f"\n✅ 成功！已抓取到 {earliest_date.strftime('%Y-%m-%d')}（早于目标日期）")
        else:
            print(f"\n⚠️ 未完全达到目标日期，最早推文: {earliest_date.strftime('%Y-%m-%d')}")
            print(f"💡 可能原因：用户在 {TARGET_DATE.strftime('%Y-%m-%d')} 之前没有推文，或需要增加 MAX_PAGES")
    else:
        print(f"\n⚠️ 未抓取到新推文")
    
    print("\n" + "=" * 60)
    print("✅ 抓取完成！")
    print("=" * 60)

if __name__ == "__main__":
    main()
