# Twitter 用户画像分析工具

一个强大的 Twitter (X) 用户行为分析工具，支持数据抓取、翻译、兴趣画像、时间行为分析和生活事件检测。支持多用户分析，配置灵活。

## 🎯 功能特性

### 0. 多用户支持 🆕
- ✅ 通过 `.env` 配置 `TARGET_USERNAME`
- ✅ 一次配置，所有脚本自动生效
- ✅ 支持同时分析多个用户（数据互不覆盖）
- ✅ 文件命名：`{username}_{类型}.json`

### 1. 数据采集与处理
- ✅ 自动抓取指定用户的推文（排除转发和回复）
- ✅ **增量抓取**：`fetch_more_history.py` 支持续传，避免重复抓取
- ✅ **智能限流处理**：自动检测并等待 API 限流
- ✅ **多语言智能翻译**：自动检测并翻译日语/英语→中文（支持缓存，避免重复翻译）
- ✅ **语言分布统计**：显示推文的语言构成分析
- ✅ 文本清洗和预处理

### 2. 兴趣画像分析
- ✅ **专业版分析** (`analyze_pro.py`)：AI 驱动的深度兴趣画像分析
  - 严格的证据导向分析原则
  - 区分核心兴趣与边缘兴趣
  - 置信度评估和关键词提取
- ✅ **聚类版分析** (`main.py`)：基于向量的主题聚类（K-Means）
- ✅ **快速分析** (`analyze_only.py`)：仅分析现有数据，不重新抓取

### 3. 时间行为分析 🆕
- ✅ 24小时发推时间分布
- ✅ 工作日 vs 周末活跃度对比
- ✅ 最活跃时段和星期识别
- ✅ 作息特征分析

### 4. 生活事件检测 🆕
- ✅ 自动识别推文中的重要生活事件：
  - 🎂 生日相关
  - 💕 感情状态
  - 🎓 学业/职业变动
  - 🏥 健康事件
  - ✈️ 旅行/搬家
  - 🛒 重大购物
  - 📌 其他重要事件

## 📂 项目结构

```
xcrawler/
├── main.py                      # 主程序：数据抓取 + 翻译 + 聚类分析
├── fetch_more_history.py        # 增量抓取：续传历史推文，避免 API 限流
├── analyze_pro.py               # 专业分析：AI 驱动的兴趣画像分析 🆕
├── analyze_behavior.py          # 行为分析：时间模式 + 生活事件
├── analyze_only.py              # 快速分析：仅兴趣画像（不抓取数据）
├── refetch_data.sh              # 便捷脚本：增量抓取数据（已优化为增量模式）
├── requirements.txt             # 依赖包列表
├── .env                         # 环境变量配置（需自行创建）
├── cache/                       # 缓存目录
│   ├── {username}_raw_tweets.json         # 原始推文
│   ├── {username}_translated.json         # 翻译结果
│   ├── {username}_analysis.json           # 聚类分析结果
│   ├── {username}_interest_profile.json   # 专业兴趣画像 🆕
│   ├── {username}_behavior.json           # 行为模式分析
│   └── translation_cache.json             # 翻译缓存（通用）
├── cache_backup/                # 备份目录
├── CONFIG_GUIDE.md              # 配置指南：多用户配置说明 🆕
├── FETCH_MORE_DATA.md           # 增量抓取说明
├── BEHAVIOR_ANALYSIS.md         # 行为分析功能说明
├── QUICK_START.md               # 快速开始指南
└── ANALYSIS_SUMMARY.md          # 示例分析报告
```

## 🚀 快速开始

### 1. 环境准备

```bash
# 安装依赖
pip3 install -r requirements.txt

# 如果遇到系统保护，使用（macOS）
pip3 install -r requirements.txt --break-system-packages

# 或者使用引号避免 shell 解析问题
pip3 install "langdetect>=1.0.9"
```

### 2. 配置 API 密钥

创建 `.env` 文件：

```bash
# Twitter API (用于数据抓取)
X_BEARER_TOKEN=your_twitter_bearer_token

# DeepSeek API (用于翻译和AI分析)
DEEPSEEK_API_KEY=your_deepseek_api_key

# 目标用户名（可修改为任意 X 用户名）
TARGET_USERNAME=MiracleHe
```

**获取方式：**
- Twitter API Token: https://developer.twitter.com/
- DeepSeek API Key: https://platform.deepseek.com/

**多用户分析：**
- 修改 `.env` 中的 `TARGET_USERNAME` 即可切换用户
- 详见 [CONFIG_GUIDE.md](CONFIG_GUIDE.md)

### 3. 运行分析

#### 方案 A：首次完整分析

```bash
# Step 1: 抓取数据 + 翻译 + 聚类分析
python3 main.py

# Step 2: 专业兴趣画像分析（推荐）
python3 analyze_pro.py

# Step 3: 行为分析（时间模式 + 生活事件）
python3 analyze_behavior.py
```

#### 方案 B：增量抓取（推荐 Free API）

```bash
# 首次抓取
python3 main.py

# 增量补充历史数据（每天运行一次，避免限流）
python3 fetch_more_history.py

# 重新分析
python3 analyze_pro.py
python3 analyze_behavior.py
```

#### 方案 C：仅分析现有数据

```bash
# 快速分析（不重新抓取）
python3 analyze_only.py      # 聚类分析
python3 analyze_pro.py       # 专业分析
python3 analyze_behavior.py  # 行为分析
```

## 🌐 多语言翻译功能

### 支持的语言
- 🇯🇵 **日语** → 中文（保持原有功能）
- 🇺🇸 **英语** → 中文（新增功能）
- 🇨🇳 **中文** → 直接保留（跳过翻译）
- 🌍 **其他语言** → 跳过处理

### 智能特性
- ✅ **自动语言检测**：使用 `langdetect` 库自动识别推文语言
- ✅ **智能翻译策略**：根据检测语言使用不同的翻译提示词
- ✅ **语言分布统计**：显示推文的语言构成分析
- ✅ **翻译缓存机制**：避免重复翻译，节省 API 调用
- ✅ **网络用语适配**：针对不同语言的网络用语和梗进行本地化翻译

### 输出示例

#### 语言分布统计
```
📊 语言分布统计:
   英语: 45 条 (45%)
   日语: 23 条 (23%)
   中文: 12 条 (12%)
   韩语: 8 条 (8%)
   未知: 3 条 (3%)
```

#### 翻译数据格式
```json
{
  "original": "Hello world! This is my first tweet!",
  "translated": "你好世界！这是我的第一条推文！",
  "detected_language": "en",
  "created_at": "2024-01-01T12:00:00.000Z"
}
```

### 翻译质量优化
- **技术术语保留**：保持专业术语的准确性
- **语气风格保持**：保留原文的情感色彩和语气
- **网络用语本地化**：将英语/日语网络梗翻译为对应的中文网络用语
- **上下文理解**：基于推文特点进行语境化翻译

## 📊 输出示例

### 专业兴趣画像（analyze_pro.py）

```json
{
  "interests": [
    {
      "tag": "游戏娱乐",
      "level": "core",
      "confidence": 0.85,
      "keywords": ["手游", "抽卡", "排位", "游戏"],
      "evidence_count": 28
    },
    {
      "tag": "美妆护肤",
      "level": "core",
      "confidence": 0.78,
      "keywords": ["韩系妆容", "护肤品", "美妆"],
      "evidence_count": 22
    },
    {
      "tag": "餐饮工作",
      "level": "core",
      "confidence": 0.82,
      "keywords": ["日本料理", "服装店", "工作"],
      "evidence_count": 15
    },
    {
      "tag": "音乐订阅",
      "level": "peripheral",
      "confidence": 0.45,
      "keywords": ["Spotify", "Apple Music"],
      "evidence_count": 8
    }
  ]
}
```

**特点：**
- ✅ 严格的证据导向（多次出现才识别）
- ✅ 置信度量化（0~1）
- ✅ 核心/边缘兴趣区分
- ✅ 关键词提取

### 行为分析报告（analyze_behavior.py）

```
⏰ 时间行为分析
============================================================

📊 总推文数: 100
📅 工作日 vs 周末: 84 vs 16 (5.25:1)

🕐 最活跃时段（日本时间）:
   12:00 - 9条推文  ← 午休高峰
   11:00 - 8条推文
   20:00 - 8条推文  ← 晚间高峰

📆 最活跃星期:
   周五 - 24条 (24%)  ← 周五综合症
   周四 - 20条 (20%)
   周一 - 18条 (18%)

⏱️ 时段分布:
   深夜 (0-6点): 16条 (16.0%)  ← 夜猫子倾向
   早晨 (6-9点): 8条 (8.0%)    ← 起床较晚
   上午 (9-12点): 21条 (21.0%)
   下午 (12-18点): 26条 (26.0%)
   晚上 (18-24点): 29条 (29.0%)  ← 最活跃

🎉 生活事件检测
============================================================

🎓 学业/职业:
   • 被拜托帮忙服装店开业（2025-12-15）
   • 在日本料理店工作（2025-11-30）

🏥 健康相关:
   • 肚子疼和头痛严重（2025-11-25）
   • 宠物Jiro疑似FIP后奇迹康复（2025-10-06）

🛒 重大购物:
   • Delonghi咖啡机（2025-12-26）
   • 美妆产品（2025-11-15）
   • 森海塞尔Momentum 4耳机（想要）

🎨 行为特征总结
============================================================

1. 作息特征
   夜间型用户，晚上最活跃，早晨活动少。

2. 活跃模式
   工作日高频使用，周末减少，午休和晚间是高峰。

3. 生活状态
   餐饮从业者，关注美妆、游戏、宠物，有经济压力。
```

## 🎛️ 配置选项

### 统一配置（推荐）

**所有脚本都从 `.env` 读取配置：**

```bash
# .env
TARGET_USERNAME=MiracleHe     # 目标用户名（一次配置，全局生效）
```

### 脚本内部配置

#### main.py
```python
TARGET_USERNAME = os.getenv("TARGET_USERNAME", "MiracleHe")  # 从环境变量读取
MAX_PAGES = 50                 # 抓取页数（每页100条）
MAX_RETRIES = 3                # API重试次数
CACHE_DIR = "cache"            # 缓存目录
```

#### fetch_more_history.py
```python
TARGET_USERNAME = os.getenv("TARGET_USERNAME", "MiracleHe")  # 从环境变量读取
MAX_PAGES = 10                 # Free API：每天10页，避免限流
TARGET_YEAR = 2024             # 目标年份
REQUEST_INTERVAL = 3           # 请求间隔（秒）
```

#### analyze_pro.py
```python
TARGET_USERNAME = os.getenv("TARGET_USERNAME", "MiracleHe")  # 从环境变量读取
MODEL = os.getenv("LLM_MODEL", "deepseek-chat")          # LLM 模型
```

#### analyze_behavior.py
```python
TARGET_USERNAME = os.getenv("TARGET_USERNAME", "MiracleHe")  # 从环境变量读取
CACHE_DIR = "cache"            # 缓存目录
JST_OFFSET = timedelta(hours=9)  # 时区偏移（日本时区 UTC+9）
```

**多用户配置详见：** [CONFIG_GUIDE.md](CONFIG_GUIDE.md)

## 📋 依赖说明

### 必需依赖
```
requests>=2.31.0           # HTTP 请求
openai>=1.0.0             # DeepSeek API 调用
python-dotenv>=1.0.0      # 环境变量管理
langdetect>=1.0.9         # 语言检测（多语言翻译支持）
```

### 分析依赖
```
sentence-transformers>=2.2.0  # 文本向量化
scikit-learn>=1.3.0          # 聚类算法
tqdm>=4.66.0                 # 进度条
```

### 深度学习依赖
```
transformers>=4.35.0
torch>=2.0.0
huggingface-hub>=0.19.0
```

## 🔍 使用场景

### 1. 市场营销
- **目标用户画像**：了解潜在客户的兴趣和行为
- **最佳触达时间**：根据活跃时段优化投放
- **内容策略**：基于兴趣主题定制内容

### 2. 竞品分析
- **竞争对手分析**：了解竞品的目标用户群体
- **行业趋势**：通过多用户分析发现行业趋势

### 3. 社交媒体研究
- **用户行为研究**：分析社交媒体使用模式
- **内容传播**：研究不同类型内容的传播效果

### 4. 个人应用
- **自我认知**：分析自己的推文了解行为模式
- **时间管理**：优化社交媒体使用时间

## ⚠️ 注意事项

### API 限制
- **Twitter Free API**: 极严格限制（月限1500条）
  - 建议使用 `fetch_more_history.py` 分批抓取
  - 每天运行一次，每次10页（1000条）
  - 脚本自动处理限流等待
- **Twitter Basic API** ($100/月): 约100次/月
- **DeepSeek API**: 翻译和分析会消耗 API 额度
- **建议**: 
  - 使用翻译缓存机制减少重复调用
  - Free 用户设置 `MAX_PAGES=10`
  - 增量抓取避免超限

### 隐私保护
- ⚠️ 仅用于公开推文分析
- ⚠️ 遵守 Twitter 使用条款
- ⚠️ 尊重用户隐私，谨慎使用分析结果

### 数据准确性
- 分析基于用户**公开的原创推文**（排除转发和回复）
- AI 事件检测可能存在误判，建议人工复核
- 时间分析基于推文时间戳，假设用户在特定时区

## 🐛 故障排除

### 问题1: "ModuleNotFoundError: No module named 'langdetect'"
```bash
# 安装语言检测库（注意使用引号）
pip3 install "langdetect>=1.0.9"

# 或安装所有依赖
pip3 install -r requirements.txt --break-system-packages
```

### 问题2: "zsh: 1.0.9 not found"
这是 shell 解析问题，使用引号包围版本号：
```bash
pip3 install "langdetect>=1.0.9"
```

### 问题3: "ModuleNotFoundError: No module named 'XXX'"
```bash
# 安装所有依赖
pip3 install -r requirements.txt --break-system-packages

# 或仅安装必需依赖
pip3 install requests openai python-dotenv "langdetect>=1.0.9" --break-system-packages
```

### 问题4: "找不到数据文件"
先运行 `main.py` 抓取数据，再运行其他分析脚本。

### 问题5: "API 限流（429）"
**Twitter Free API 限制极严格：**
- 建议使用 `fetch_more_history.py` 增量抓取（每天10页）
- 脚本会自动等待限流时间（15分钟）
- 或手动设置 `MAX_PAGES` ≤ 10

### 问题6: "翻译失败"
检查 `.env` 文件中的 `DEEPSEEK_API_KEY` 是否正确。

### 问题7: "语言检测不准确"
- 短文本（<3个字符）会被标记为"未知"
- 包含大量链接和@符号的推文可能影响检测准确性
- 混合语言推文以主要语言为准

### 问题8: "聚类错误"
确保有足够的推文（至少10条）进行有效分析。

### 问题9: "文件名包含用户名"
这是正常设计，支持多用户分析：
- 修改 `.env` 中的 `TARGET_USERNAME` 即可切换用户
- 详见 [CONFIG_GUIDE.md](CONFIG_GUIDE.md)

## 🔄 更新日志

### v2.1.0 - 多语言翻译支持 🆕
- ✅ 新增自动语言检测功能
- ✅ 支持英语→中文翻译
- ✅ 智能跳过中文推文
- ✅ 语言分布统计显示
- ✅ 针对不同语言优化翻译提示词
- ✅ 网络用语本地化翻译

### v2.0.0 - 专业分析版本
- ✅ 新增专业兴趣画像分析（analyze_pro.py）
- ✅ 新增行为分析功能（analyze_behavior.py）
- ✅ 新增生活事件检测
- ✅ 多用户支持和配置统一
- ✅ 增量抓取功能

## 📚 相关文档

- [CONFIG_GUIDE.md](CONFIG_GUIDE.md) - 配置指南：多用户分析配置 🆕
- [QUICK_START.md](QUICK_START.md) - 快速开始指南
- [FETCH_MORE_DATA.md](FETCH_MORE_DATA.md) - 增量抓取说明
- [BEHAVIOR_ANALYSIS.md](BEHAVIOR_ANALYSIS.md) - 行为分析功能说明
- [ANALYSIS_SUMMARY.md](ANALYSIS_SUMMARY.md) - 完整的用户分析报告示例

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

---

**免责声明**: 本工具仅供学习和研究使用，请遵守相关法律法规和平台使用条款，尊重用户隐私。
