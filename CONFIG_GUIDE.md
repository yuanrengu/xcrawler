# 配置指南

## 📌 统一配置方案

所有脚本现在都从 `.env` 文件读取 `TARGET_USERNAME`，提高了复用性。推荐使用统一 CLI 入口 `xcrawler`，旧脚本入口仍保留兼容。

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

### 方法 2：命令行参数（推荐）

使用统一 CLI 的 `--user` 参数临时指定用户，无需修改 `.env`：

```bash
xcrawler fetch -u another_user
xcrawler analyze interest -u another_user
xcrawler analyze behavior -u another_user
```

**优点：**
- ✅ 不修改文件
- ✅ 适合临时切换用户
- ✅ 所有命令统一入口

---

## 📂 文件命名规则

所有数据文件都使用 `{username}_{类型}.json` 格式：

```
cache/
├── MiracleHe_raw_tweets.json          # 原始推文
├── MiracleHe_translated.json          # 翻译后的推文
├── MiracleHe_analysis.json            # 行为分析
├── MiracleHe_interest_profile.json   # 兴趣画像
└── translation_cache.json           # 翻译缓存（通用）
```

**好处：**
- ✅ 可以同时分析多个用户
- ✅ 数据不会互相覆盖
- ✅ 一目了然知道是谁的数据

---

## 🚀 使用示例

### 示例 1：分析单个用户

```bash
# 1. 修改 .env 或使用 --user 参数
TARGET_USERNAME=MiracleHe

# 2. 依次运行（统一 CLI）
xcrawler fetch -u MiracleHe              # 抓取并翻译
xcrawler analyze interest -u MiracleHe   # 兴趣画像分析
xcrawler analyze behavior -u MiracleHe   # 行为分析
```

---

### 示例 2：分析多个用户

```bash
# 用户 A
xcrawler fetch -u user_a
xcrawler analyze interest -u user_a

# 用户 B
xcrawler fetch -u user_b
xcrawler analyze interest -u user_b

# 数据文件：
# cache/user_a_*.json
# cache/user_b_*.json
```

---

### 示例 3：临时切换用户

```bash
# 无需修改 .env，直接使用 --user 参数
xcrawler fetch -u new_user
xcrawler analyze interest -u new_user
```

---

## ⚙️ 所有支持配置的命令

| 命令 | 功能 | 读取配置 |
|------|------|---------|
| `xcrawler fetch` | 抓取并翻译推文 | ✅ `TARGET_USERNAME` |
| `xcrawler fetch-more` | 增量抓取历史数据 | ✅ `TARGET_USERNAME` |
| `xcrawler analyze interest` | 兴趣画像分析 | ✅ `TARGET_USERNAME` |
| `xcrawler analyze behavior` | 行为分析 | ✅ `TARGET_USERNAME` |
| `xcrawler analyze sentiment` | 情感分析 | ✅ `TARGET_USERNAME` |
| `xcrawler analyze network` | Hashtag/Mention 网络分析 | ✅ `TARGET_USERNAME` |

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

### 2. 临时测试：使用 `--user` 参数
```bash
xcrawler fetch -u test_user
```

### 3. 多用户分析
```bash
xcrawler fetch -u user1
xcrawler fetch -u user2
xcrawler fetch -u user3
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

现在所有脚本都支持通过 `.env` 或 `--user` 参数配置用户名，复用性大大提高！

**核心优势：**
- ✅ 一次配置，全局生效
- ✅ 支持多用户分析
- ✅ 向后兼容
- ✅ 灵活切换

修改 `.env` 中的 `TARGET_USERNAME` 或使用 `xcrawler -u <用户名>` 即可开始使用！
