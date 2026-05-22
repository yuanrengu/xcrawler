# 快速开始指南

## 🚀 5分钟上手

### Step 1: 安装依赖（2分钟）

```bash
# 进入项目目录
cd /Users/heyonggang/code/open/23AI/11tool/xcrawler

# 安装所有依赖
pip3 install -r requirements.txt --break-system-packages
```

### Step 2: 配置 API（1分钟）

编辑 `.env` 文件：

```bash
# Twitter API Token (必须 - 用于抓取数据)
X_BEARER_TOKEN=你的Twitter_Bearer_Token

# DeepSeek API Key (必须 - 用于翻译和分析)
DEEPSEEK_API_KEY=你的DeepSeek_API_Key
```

**快速获取:**
- Twitter: https://developer.twitter.com/en/portal/dashboard
- DeepSeek: https://platform.deepseek.com/api_keys

### Step 3: 运行分析（2分钟）

```bash
# 1️⃣ 完整流程：抓取数据 + 兴趣分析
python3 main.py

# 2️⃣ 行为分析：时间模式 + 生活事件检测
python3 analyze_behavior.py

# ✅ 完成！查看结果
cat cache/MiracleHe_behavior.json
```

## 📊 查看结果

### 方式1: 终端查看

```bash
# 查看行为分析
python3 analyze_behavior.py

# 查看兴趣画像
python3 analyze_only.py
```

### 方式2: 文件查看

```bash
# 打开分析报告
open ANALYSIS_SUMMARY.md

# 查看JSON数据
cat cache/MiracleHe_behavior.json | jq .
```

### 方式3: Python 读取

```python
import json

# 读取行为分析结果
with open('cache/MiracleHe_behavior.json', 'r') as f:
    behavior = json.load(f)

print("最活跃时段:", behavior['time_analysis']['top_active_hours'])
print("生活事件:", behavior['life_events'])
```

## 🎯 更换目标用户

### 修改配置

编辑 `.env` 文件，修改 `TARGET_USERNAME`：

```bash
# .env
TARGET_USERNAME=your_target_user  # ← 改成你要分析的用户名
```

所有脚本会自动读取 `.env` 中的配置，无需修改代码。

### 重新运行

```bash
python3 main.py                # 抓取新用户数据
python3 analyze_behavior.py   # 分析新用户行为
```

详见 [CONFIG_GUIDE.md](CONFIG_GUIDE.md)。

## 💡 常用命令

```bash
# 只分析已有数据（不抓取）
python3 analyze_only.py       # 兴趣画像
python3 analyze_behavior.py   # 行为分析

# 清空缓存重新开始
rm cache/*.json

# 查看帮助
python3 main.py --help

# 查看依赖
pip3 list | grep -E "(openai|requests|transformers)"
```

## 🔧 自定义配置

### 修改抓取数量

```python
# main.py
MAX_PAGES = 5  # 5页 = 500条推文（推荐：5-10页）
```

### 修改聚类数量

```python
# main.py 或 analyze_only.py
cluster_num = max(2, min(8, len(translated) // 10))
# 改为固定值：
cluster_num = 5  # 固定5个主题
```

### 修改时区

编辑 `.env` 文件：
```bash
# 时区偏移（UTC+N），默认9（日本），中国设为8
TIMEZONE_OFFSET=8
```

## 📈 输出文件说明

| 文件名 | 说明 | 大小 |
|--------|------|------|
| `MiracleHe_raw_tweets.json` | 原始推文数据 | ~40KB |
| `MiracleHe_translated.json` | 翻译后的推文 | ~30KB |
| `MiracleHe_analysis.json` | 兴趣画像分析 | ~17KB |
| `MiracleHe_behavior.json` | **行为模式分析** | ~4KB |
| `translation_cache.json` | 翻译缓存 | ~22KB |

## ⚡ 性能优化

### 使用翻译缓存

```bash
# 第一次运行（慢）
python3 main.py  # 需要翻译所有推文

# 后续运行（快）
python3 main.py  # 自动使用缓存，跳过已翻译内容
```

### 减少 API 调用

```python
# main.py
MAX_PAGES = 3  # 减少抓取页数

# analyze_behavior.py
translated_data[:50]  # 只分析前50条推文（默认200条）
```

## 🆘 常见问题

### Q1: 安装依赖时报错
```bash
# macOS 系统保护
pip3 install -r requirements.txt --break-system-packages

# 或使用虚拟环境
python3 -m venv venv
source venv/bin/activate
pip3 install -r requirements.txt
```

### Q2: API 调用失败
```bash
# 检查 API Key
cat .env | grep API_KEY

# 测试连接
curl -H "Authorization: Bearer $(grep DEEPSEEK_API_KEY .env | cut -d= -f2)" \
     https://api.deepseek.com/v1/models
```

### Q3: 找不到数据文件
```bash
# 确保先运行 main.py
python3 main.py

# 检查文件
ls -lh cache/
```

### Q4: 内存不足
```python
# 减少向量模型精度
embed_model = SentenceTransformer("all-MiniLM-L6-v2")  # 更轻量

# 或减少数据量
MAX_PAGES = 3
```

## 📚 下一步

- 📖 阅读 [完整文档](README.md)
- 📊 查看 [示例报告](ANALYSIS_SUMMARY.md)
- 🔍 了解 [行为分析](BEHAVIOR_ANALYSIS.md)

## 🎉 完成！

现在你已经掌握了基本用法，可以开始分析任何公开的 Twitter 用户了！

**提示**: 
- 首次运行需要下载模型文件（约300MB），请耐心等待
- 翻译和分析会消耗 API 额度，请合理使用
- 遵守 Twitter 使用条款，尊重用户隐私

---

*有问题？查看 [完整 README](README.md) 或提交 Issue*
