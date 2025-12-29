# 配置指南

## 📌 统一配置方案

所有脚本现在都从 `.env` 文件读取 `TARGET_USERNAME`，提高了复用性。

---

## 🔧 配置方法

### 方法 1：修改 `.env` 文件（推荐）

编辑 `.env` 文件，修改目标用户名：

```bash
# .env
TARGET_USERNAME=MiracleHe  # ← 改成你要分析的用户名
```

**优点：**
- ✅ 一次配置，所有脚本生效
- ✅ 配置持久化
- ✅ 适合长期使用同一个用户

---

### 方法 2：临时环境变量

```bash
# 仅本次运行有效
TARGET_USERNAME=another_user python3 main.py

# 或者导出环境变量
export TARGET_USERNAME=another_user
python3 main.py
python3 analyze_pro.py
```

**优点：**
- ✅ 不修改文件
- ✅ 适合临时切换用户
- ✅ 不会影响其他终端会话

---

## 📂 文件命名规则

所有数据文件都使用 `{username}_{类型}.json` 格式：

```
cache/
├── MiracleHe_raw_tweets.json          # 原始推文
├── MiracleHe_translated.json          # 翻译后的推文
├── MiracleHe_analysis.json            # 行为分析
├── MiracleHe_interest_profile.json   # 兴趣画像
└── translation_cache.json          # 翻译缓存（通用）
```

**好处：**
- ✅ 可以同时分析多个用户
- ✅ 数据不会互相覆盖
- ✅ 一目了然知道是谁的数据

---

## 🚀 使用示例

### 示例 1：分析单个用户

```bash
# 1. 修改 .env
TARGET_USERNAME=MiracleHe

# 2. 依次运行
python3 main.py              # 抓取并翻译
python3 analyze_pro.py       # 兴趣画像分析
python3 analyze_behavior.py  # 行为分析
```

---

### 示例 2：分析多个用户

```bash
# 用户 A
TARGET_USERNAME=user_a python3 main.py
TARGET_USERNAME=user_a python3 analyze_pro.py

# 用户 B
TARGET_USERNAME=user_b python3 main.py
TARGET_USERNAME=user_b python3 analyze_pro.py

# 数据文件：
# cache/user_a_*.json
# cache/user_b_*.json
```

---

### 示例 3：切换用户

```bash
# 修改 .env
vim .env  # 改 TARGET_USERNAME=new_user

# 重新运行
python3 main.py
python3 analyze_pro.py
```

---

## ⚙️ 所有支持配置的脚本

| 脚本 | 功能 | 读取配置 |
|------|------|---------|
| `main.py` | 抓取并翻译推文 | ✅ `TARGET_USERNAME` |
| `fetch_more_history.py` | 增量抓取历史数据 | ✅ `TARGET_USERNAME` |
| `analyze_pro.py` | 兴趣画像分析 | ✅ `TARGET_USERNAME` |
| `analyze_behavior.py` | 行为分析 | ✅ `TARGET_USERNAME` |
| `analyze_only.py` | 仅分析（不翻译） | ✅ `TARGET_USERNAME` |

---

## 🔒 默认值

所有脚本都有默认值 `MiracleHe`，如果未设置 `TARGET_USERNAME`，会自动使用默认值：

```python
TARGET_USERNAME = os.getenv("TARGET_USERNAME", "MiracleHe")
```

**这意味着：**
- ✅ 向后兼容，旧配置依然有效
- ✅ 新用户可以直接修改 `.env`
- ✅ 不会因为缺少配置而报错

---

## 💡 最佳实践

### 1. 长期使用：修改 `.env`
```bash
# .env
TARGET_USERNAME=my_target_user
```

### 2. 临时测试：使用环境变量
```bash
TARGET_USERNAME=test_user python3 main.py
```

### 3. 多用户分析：脚本循环
```bash
for user in user1 user2 user3; do
    TARGET_USERNAME=$user python3 main.py
    TARGET_USERNAME=$user python3 analyze_pro.py
done
```

---

## ⚠️ 注意事项

1. **文件名冲突**
   - 不同用户的数据会保存到不同文件
   - `translation_cache.json` 是所有用户共享的翻译缓存

2. **API 配额**
   - 所有用户共享同一个 API 配额
   - 注意不要短时间内抓取太多用户

3. **数据备份**
   - 切换用户前建议备份 `cache/` 目录
   - 或者将旧数据移到 `cache_backup_{username}/`

---

## 🎯 总结

现在所有脚本都支持通过 `.env` 配置用户名，复用性大大提高！

**核心优势：**
- ✅ 一次配置，全局生效
- ✅ 支持多用户分析
- ✅ 向后兼容
- ✅ 灵活切换

修改 `.env` 中的 `TARGET_USERNAME` 即可开始使用！
