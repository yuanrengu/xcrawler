# 快速开始指南

## 🚀 5分钟上手

### Step 1: 安装依赖（2分钟）

```bash
# 克隆并进入项目目录
git clone https://github.com/yuanrengu/xcrawler.git
cd xcrawler

# 推荐：使用虚拟环境，安装全功能依赖并获得 xcrawler 命令
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[all]"
```

### Step 2: 配置 API（1分钟）

编辑 `.env` 文件：

```bash
# Twitter API Token (必须 - 用于抓取数据)
X_BEARER_TOKEN=你的Twitter_Bearer_Token

# DeepSeek API Key (必须 - 用于翻译和分析)
DEEPSEEK_API_KEY=你的DeepSeek_API_Key

# 目标用户名（不带 @）
TARGET_USERNAME=MiracleHe

# 可选：每百万 input/output token 的 USD 单价，用于本地成本估算
# LLM_PRICING_JSON={"deepseek-chat":{"input_per_million":0.0,"output_per_million":0.0}}

# 可选：长期、多用户运行时使用 SQLite 保存运行元数据
STORAGE_BACKEND=json
# SQLITE_PATH=cache/xcrawler.db
```

每次翻译和 AI 分析的调用元数据会追加到 `cache/llm_calls.json`。该文件包含模型、Token、耗时、成功/失败和错误类型，但不会保存 Prompt 或模型响应正文。

默认 JSON 工作流无需改动。若启用 `STORAGE_BACKEND=sqlite`，运行记录和 LLM 调用记录改存到 `cache/xcrawler.db`，原始推文、翻译、缓存、图表和报告仍保留原文件格式。也可单次运行 `xcrawler analyze interest --storage sqlite`；项目不会自动迁移旧 JSON 元数据。

**快速获取:**
- Twitter: https://developer.twitter.com/en/portal/dashboard
- DeepSeek: https://platform.deepseek.com/api_keys

### Step 3: 运行分析（2分钟）

```bash
# 1️⃣ 完整流程：抓取数据 + 兴趣分析
xcrawler fetch

# 2️⃣ 行为分析：时间模式 + 生活事件检测
xcrawler analyze behavior

# ✅ 完成！查看结果
cat cache/MiracleHe_behavior.json
```

## 📊 查看结果

### 方式1: 终端查看

```bash
# 查看行为分析
xcrawler analyze behavior

# 查看兴趣画像
xcrawler analyze interest
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
xcrawler fetch                 # 抓取新用户数据
xcrawler analyze behavior      # 分析新用户行为
```

详见 [CONFIG_GUIDE.md](CONFIG_GUIDE.md)。

## 💡 常用命令

```bash
# 只分析已有数据（不抓取）
xcrawler analyze interest     # 兴趣画像
xcrawler analyze behavior     # 行为分析

# 清空缓存重新开始
rm cache/*.json

# 查看帮助
xcrawler --help

# 查看依赖
pip3 list | grep -E "(openai|requests|transformers)"
```

## 🔧 自定义配置

### 修改抓取数量

```bash
# 5 页 = 最多 500 条推文，推荐先用 3-10 页测试
xcrawler fetch --pages 5
```

### 控制分析规模

```bash
# 限制聚类/画像最多处理的翻译推文数，避免大数据集过慢
xcrawler fetch --analysis-limit 500

# 限制专业兴趣画像最多输入的翻译文本数
xcrawler analyze interest --limit 300
```

### 修改时区

编辑 `.env` 文件：
```bash
# 时区偏移（UTC+N），默认8（中国）
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
xcrawler fetch  # 需要翻译所有推文

# 后续运行（快）
xcrawler fetch  # 自动使用缓存，跳过已翻译内容
```

缓存会按 Provider、模型、目标语言和 Prompt 版本隔离。切换模型或翻译策略后会自动产生未命中，避免复用来源不一致的旧译文；`xcrawler translate --force` 会绕过旧缓存并重建当前配置缓存。

### 减少 API 调用

```bash
# 减少抓取页数
xcrawler fetch --pages 3

# 使用增量抓取，避免每天全量重新抓
xcrawler fetch-more --pages 3

# 使用输入上限控制后续分析成本
xcrawler analyze interest --limit 100
```

## 🆘 常见问题

### Q1: 安装依赖时报错
```bash
# 使用虚拟环境
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[all]"
```

### Q2: API 调用失败
```bash
# 检查 API Key 是否已配置（不会打印密钥内容）
python3 - <<'PY'
from dotenv import load_dotenv
import os
load_dotenv()
for key in ("X_BEARER_TOKEN", "DEEPSEEK_API_KEY"):
    print(f"{key}: {'已配置' if os.getenv(key) else '未配置'}")
PY

# 测试 DeepSeek 连接
python3 - <<'PY'
from dotenv import load_dotenv
import os
import requests
load_dotenv()
key = os.getenv("DEEPSEEK_API_KEY")
resp = requests.get(
    "https://api.deepseek.com/v1/models",
    headers={"Authorization": f"Bearer {key}"},
    timeout=10,
)
print(resp.status_code)
PY
```

### Q3: 找不到数据文件
```bash
# 确保先运行抓取流程
xcrawler fetch

# 检查文件
ls -lh cache/
```

### Q4: 内存不足
```bash
# 减少抓取页数
xcrawler fetch --pages 3

# 限制聚类/画像输入规模
xcrawler fetch --analysis-limit 300

# 专业兴趣分析也可以限制输入文本数
xcrawler analyze interest --limit 100
```

## 📚 下一步

- 📖 阅读 [完整文档](README.md)
- 📊 查看 [示例报告](ANALYSIS_SUMMARY.md)
- 🔍 了解 [行为分析](BEHAVIOR_ANALYSIS.md)

## 🎉 完成！

现在你已经掌握了基本用法，可以开始分析任何公开的 Twitter 用户了！

**提示**: 
- 首次运行需要下载模型文件（约470MB），请耐心等待
- 翻译和分析会消耗 API 额度，请合理使用
- 遵守 Twitter 使用条款，尊重用户隐私

---

*有问题？查看 [完整 README](README.md) 或提交 Issue*
