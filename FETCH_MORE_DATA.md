# 获取更多历史数据指南

## 🔍 问题分析

当前只抓取了100条推文，时间范围：**2025年10月-12月**（84天）

原因：
- `MAX_PAGES = 8` 只抓取了8页（800条限制）
- 该用户最近3个月较活跃，100条只覆盖了84天
- **缺少2024年的数据**

## 📊 当前数据统计

```
总推文数: 100条
时间跨度: 2025-10-03 至 2025-12-26 (84天)

按月份:
  2025-10: 40条
  2025-11: 42条
  2025-12: 18条
```

## 🚀 解决方案

### 方法1: 修改 main.py 重新抓取（推荐）

#### Step 1: 修改配置

在 `main.py` 中修改（已完成）：

```python
MAX_PAGES = 32  # 从 8 改为 32，可抓取3200条
```

#### Step 2: 重新运行

```bash
# 确保依赖已安装
pip3 install requests openai python-dotenv --break-system-packages

# 重新抓取（会覆盖旧数据）
python3 main.py
```

**注意**: 这会重新翻译所有推文，但有翻译缓存所以很快。

---

### 方法2: 使用增量抓取脚本（不覆盖）

#### Step 1: 运行增量脚本

```bash
python3 fetch_more_history.py
```

该脚本会：
1. 加载现有的数据
2. **抓取最新**：自动获取上次抓取后新发布的所有推文
3. **补全历史**：从最早的推文继续向历史抓取（直到2024年）
4. 自动去重并合并数据
4. 抓取到2024年后自动停止

#### Step 2: 查看结果

```bash
# 查看新的数据统计
python3 -c "
import json
from datetime import datetime
from collections import Counter

with open('cache/pnyq_n_raw_tweets.json') as f:
    tweets = json.load(f)

dates = [datetime.strptime(t['created_at'], '%Y-%m-%dT%H:%M:%S.%fZ') for t in tweets]
dates.sort()

print(f'总推文数: {len(tweets)}')
print(f'时间范围: {dates[0].date()} 至 {dates[-1].date()}')

years = Counter([d.year for d in dates])
print(f'\\n按年份:')
for y in sorted(years.keys()):
    print(f'  {y}年: {years[y]}条')
"
```

---

### 方法3: 手动调用 Twitter API

如果Python环境有问题，可以直接用curl：

```bash
# 获取用户ID
USER_ID=$(curl -s -H "Authorization: Bearer $X_BEARER_TOKEN" \
  "https://api.twitter.com/2/users/by/username/pnyq_n" | \
  jq -r '.data.id')

echo "User ID: $USER_ID"

# 获取最早的推文ID
OLDEST_ID=$(jq -r '.[−1].id' cache/pnyq_n_raw_tweets.json)

echo "Oldest ID: $OLDEST_ID"

# 抓取更多历史推文（从最早的ID之前）
curl -s -H "Authorization: Bearer $X_BEARER_TOKEN" \
  "https://api.twitter.com/2/users/$USER_ID/tweets?max_results=100&until_id=$OLDEST_ID&tweet.fields=created_at&exclude=retweets,replies" \
  | jq '.data' > new_tweets.json
```

---

## 📈 预估数据量

假设用户从2024年1月开始活跃，按当前频率：

- **平均每天**: ~1.2条推文
- **2024全年**: ~440条
- **2025至今**: ~100条
- **预估总量**: ~540条

建议设置：
```python
MAX_PAGES = 10  # 保守估计：1000条足够
MAX_PAGES = 20  # 推荐：2000条确保完整
MAX_PAGES = 50  # 最大：5000条（适合超活跃用户）
```

---

## ⚠️ API 限制注意

Twitter API 有严格限制：

| 限制类型 | 数值 |
|---------|------|
| 每15分钟 | 1500 请求 |
| 每页推文数 | 100条 |
| 建议间隔 | 1秒/请求 |

**计算**:
- 抓取3200条（32页）需要 ~32秒
- 抓取5000条（50页）需要 ~50秒
- 如果触发限流，需等待15分钟

---

## 🔧 故障排除

### 问题1: ModuleNotFoundError

```bash
# 安装依赖
pip3 install requests openai python-dotenv tqdm --break-system-packages

# 或使用虚拟环境
python3 -m venv venv
source venv/bin/activate
pip3 install -r requirements.txt
```

### 问题2: API 限流 (429)

```bash
# 查看剩余配额
curl -I -H "Authorization: Bearer $X_BEARER_TOKEN" \
  "https://api.twitter.com/2/users/by/username/pnyq_n"

# 查看 x-rate-limit-remaining 和 x-rate-limit-reset
```

等待重置时间后再运行。

### 问题3: 已有2024数据但想要更早的

修改 `fetch_more_history.py`:

```python
TARGET_YEAR = 2023  # 或 2022
### 4. 无法获取最新数据

现在的脚本已经支持**双向抓取**：
- 只要运行 `python3 fetch_more_history.py`
- 它会自动检查并下载最新发布的推文
- 也会同时检查并补充历史推文

---

## ✅ 验证数据完整性

抓取完成后运行：

```bash
python3 -c "
import json
from datetime import datetime

with open('cache/pnyq_n_raw_tweets.json') as f:
    tweets = json.load(f)

dates = [datetime.strptime(t['created_at'], '%Y-%m-%dT%H:%M:%S.%fZ') for t in tweets]
dates.sort()

print('数据统计:')
print(f'  总推文: {len(tweets)}条')
print(f'  时间跨度: {(dates[-1] - dates[0]).days}天')
print(f'  最早: {dates[0]}')
print(f'  最新: {dates[-1]}')

# 检查时间连续性
gaps = []
for i in range(len(dates)-1):
    gap = (dates[i+1] - dates[i]).days
    if gap > 30:  # 超过30天视为空档
        gaps.append((dates[i], dates[i+1], gap))

if gaps:
    print(f'\\n⚠️ 发现 {len(gaps)} 个时间空档:')
    for start, end, days in gaps:
        print(f'  {start.date()} -> {end.date()} ({days}天)')
else:
    print('\\n✅ 数据连续，无明显空档')
"
```

---

## 📝 抓取后续步骤

数据更新后，需要重新翻译和分析：

```bash
# 1. 翻译新推文（使用缓存，只翻译新内容）
python3 main.py

# 2. 重新进行行为分析
python3 analyze_behavior.py

# 3. 重新生成兴趣画像
python3 analyze_only.py
```

---

## 💡 优化建议

### 1. 使用翻译缓存

```python
# 已翻译的内容会被缓存在
cache/translation_cache.json

# 下次运行时自动跳过，节省API调用
```

### 2. 分批抓取

如果担心API限流：

```python
# 第一次
MAX_PAGES = 10
python3 main.py

# 等待15分钟后
MAX_PAGES = 20  # 继续抓取
python3 fetch_more_history.py
```

### 3. 备份数据

```bash
# 抓取前备份
cp cache/pnyq_n_raw_tweets.json cache/pnyq_n_raw_tweets.backup.json

# 如果出错可以恢复
cp cache/pnyq_n_raw_tweets.backup.json cache/pnyq_n_raw_tweets.json
```

---

## 🎯 推荐流程

**最简单的方法**（推荐）：

```bash
# 1. 修改 MAX_PAGES（已完成）
# main.py 中 MAX_PAGES = 32

# 2. 备份现有数据
cp -r cache cache_backup

# 3. 重新完整抓取
python3 main.py

# 4. 验证数据
ls -lh cache/*.json

# 5. 重新分析
python3 analyze_behavior.py
```

完成后您将获得包含2024年数据的完整分析！

---

*注意: 抓取大量历史数据会消耗更多API配额和时间，请合理安排。*
