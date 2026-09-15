# xcrawler

[中文](https://github.com/yuanrengu/xcrawler/blob/main/README.md) | [English](https://github.com/yuanrengu/xcrawler/blob/main/README.en.md)

<p align="center">
  <img src="https://raw.githubusercontent.com/yuanrengu/xcrawler/main/assets/note.png" alt="xcrawler 功能示意图，非实际报告截图" width="800">
</p>

<p align="center">功能示意；实际输出为本地 JSON、CSV、PNG 和 HTML 文件。</p>

[![Tests](https://img.shields.io/github/actions/workflow/status/yuanrengu/xcrawler/test.yml?branch=main&label=tests)](https://github.com/yuanrengu/xcrawler/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/yuanrengu/xcrawler/blob/main/LICENSE)

**xcrawler** 是面向公开 X/Twitter 时间线的命令行分析工具：抓取推文、翻译为中文、生成兴趣与行为分析，再导出可复核的本地报告。

- **兴趣画像**：标签、模型置信度和推文 ID 证据；另有可选的向量聚类。
- **行为与情感**：发帖时间分布、生活事件检测、批量情感分类。
- **内容网络**：Hashtag、Mention 频率及共现统计。
- **本地输出**：保存数据、图表和报告；增量合并、翻译缓存及运行记录便于持续使用。

适合个人内容复盘、获得授权的公开账号研究和内容分析。证据 ID 可供追溯，不能自动证明模型结论正确。

> 结果在本地保存；翻译和 AI 分析会向配置的模型服务发送文本。Demo 不调用网络或模型。请仅处理有权访问的公开内容，勿用于骚扰、跟踪、人肉搜索或歧视性画像。

本文描述当前源码行为。已核对的 PyPI `0.4.2` 发布包不包含本页所述的最新报告隐私过滤、样本证据校验和分析退出码修复；需要这些行为时请使用[源码安装](#源码开发)。源码当前版本号也为 `0.4.2`，不能只凭 `xcrawler --version` 判断修复是否存在。发布记录见 [CHANGELOG](https://github.com/yuanrengu/xcrawler/blob/main/CHANGELOG.md)，源码新增内容列在 `Unreleased`。

## 目录

- [无密钥体验](#无密钥体验)
- [分析真实账号](#分析真实账号)
- [命令与前置条件](#命令与前置条件)
- [日常更新与快照](#日常更新与快照)
- [输出与证据](#输出与证据)
- [配置与存储](#配置与存储)
- [隐私与数据边界](#隐私与数据边界)
- [故障排除](#故障排除)
- [源码开发](#源码开发)
- [详细文档与贡献](#详细文档与贡献)

## 无密钥体验

需要 Python 3.10+。以下为 macOS/Linux 的虚拟环境步骤：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install xcrawler-ai
xcrawler demo
```

Windows PowerShell 使用 `py -m venv .venv`，再运行 `.venv\Scripts\Activate.ps1` 激活环境；后续 `python` 和 `xcrawler` 命令相同。

用浏览器打开 `demo_output/xcrawler_demo_report.html`。Demo 使用内置虚构数据，生成 JSON 和证据 HTML，不执行真实分析，也不生成完整 PNG 图表；无需 API Key、ML 或绘图扩展。

```bash
xcrawler demo --output ./sample-report
xcrawler --help
```

Demo 只有少量记录，不适合直接拿来运行要求至少 5 条文本的兴趣或情感分析。

## 分析真实账号

### 安装所需扩展

在已激活的环境中安装绘图扩展，即可完成抓取、专业兴趣分析和报告流程：

```bash
python -m pip install "xcrawler-ai[viz]"
```

| 安装项 | 用途 |
|---|---|
| `xcrawler-ai` | CLI、抓取、翻译、AI 分析、CSV、Demo |
| `xcrawler-ai[viz]` | 增加报告、网络与情感分析所需的绘图依赖 |
| `xcrawler-ai[ml]` | 增加向量聚类依赖 |
| `xcrawler-ai[all]` | 同时安装 ML 与绘图依赖 |

ML 依赖体积较大，首次聚类可能下载模型。未安装 ML 时，完整抓取与翻译后会跳过聚类；专业兴趣分析 `analyze interest` 不需要 ML。

### 配置密钥

抓取需要 X API Bearer Token；翻译及默认 AI 分析需要 DeepSeek 或兼容服务的密钥。真实请求可能产生费用，读取范围和额度以所用服务账户为准。

macOS/Linux，在当前终端设置以下变量，将占位符换成自己的值：

```bash
export X_BEARER_TOKEN="your_x_bearer_token"
export DEEPSEEK_API_KEY="your_deepseek_api_key"
export TARGET_USERNAME="your_x_username"
```

Windows PowerShell：

```powershell
$env:X_BEARER_TOKEN="your_x_bearer_token"
$env:DEEPSEEK_API_KEY="your_deepseek_api_key"
$env:TARGET_USERNAME="your_x_username"
```

密钥输入可能留在终端历史中，请在自己的可信环境配置；不要把密钥、`.env` 或输出数据提交到仓库。

**当前 `.env` 限制：** 代码调用无参数 `load_dotenv()`，查找起点与包位置有关，不能保证读取任意工作目录的 `.env`。独立安装时优先使用上述环境变量；源码根目录的 `.env` 用法及优先级见 [配置指南](https://github.com/yuanrengu/xcrawler/blob/main/CONFIG_GUIDE.md)。

### 运行流程

在同一个已配置的终端逐条运行：

```bash
# 先用较小页数验证配置；每条命令结束后检查输出和退出状态
xcrawler fetch --pages 3

# 使用已有译文生成专业画像和行为结果
xcrawler analyze interest --limit 300
xcrawler analyze behavior

# 读取现有数据生成图表与 HTML，不会自动重新分析
xcrawler report
```

`fetch` 达到页数上限但还有下一页时会保存部分数据并返回 `2`；可继续补抓，或明确接受当前样本范围后再分析。兴趣分析至少需要 5 条可用译文；不足时先增加有效数据。完整抓取后少于 10 条译文也会跳过聚类。

报告默认位于 `cache/charts/{username}_report.html`。使用 `--user` 临时切换账号时，后续每条命令也应指定同一账号；参数不会修改下一次运行的默认值。

## 命令与前置条件

下表中的输入为对应用户的本地文件，均可通过 `--cache-dir` 指定目录（Demo 使用 `--output`）。

| 命令 | 输入/用途 | API 配置 | 可选依赖 |
|---|---|---|---|
| `demo` | 内置虚构数据 → 证据 HTML | 无 | 无 |
| `fetch` | X 时间线 → raw、译文；条件满足时聚类 | X + DeepSeek 兼容配置 | 聚类需 `ml` |
| `fetch --no-translate` | 仅抓取 raw，跳过翻译和分析 | X | 无 |
| `fetch-more` | 更新 raw，首次也可开始抓取 | X | 无 |
| `translate` | raw → 新增或失效记录的译文 | 需要翻译调用时使用 DeepSeek 兼容配置 | 无 |
| `analyze interest` | 译文 → 专业兴趣画像，至少 5 条文本 | DeepSeek，或其密钥为空时使用 OpenAI 配置 | 无 |
| `analyze behavior` | raw + 译文 → 时间统计、事件与总结 | DeepSeek 兼容配置 | 无 |
| `analyze sentiment` | 译文 → 情感结果，至少 5 条文本 | DeepSeek 兼容配置 | `viz` |
| `analyze network` | raw → 标签/提及频率、共现和柱状图 | 无 | `viz` |
| `report` | raw 必需；按已有译文、画像、行为结果补充报告 | 无 | `viz` |
| `export csv` | 导出已有 raw、译文或兴趣画像 | 无 | 无 |

```bash
xcrawler fetch --user alice --pages 10 --batch-size 10 --analysis-limit 500
xcrawler analyze interest --user alice --limit 100 --temperature 0
xcrawler analyze network --user alice --top 20
xcrawler analyze sentiment --user alice --top 10
xcrawler report --user alice --format png --output ./charts
xcrawler export csv --user alice --type translations --output ./csv
xcrawler fetch --help
```

每个子命令支持 `--verbose` 诊断；不是每个命令都支持 `--model` 或存储选项，以对应 `--help` 为准。条数限制不是 token 上限；较长文本仍可能超过模型上下文。

## 日常更新与快照

### 增量更新

```bash
xcrawler fetch-more --pages 10 --target-date 2024-01-01
xcrawler translate
xcrawler analyze interest
xcrawler analyze behavior
xcrawler report
```

逐条检查状态，按需要重跑分析。`fetch-more` 只更新 raw；跳过翻译或分析可能让报告继续展示旧结果。它的 `--pages` 是向前、向后和重试共享的 HTTP 请求预算，不保证每个请求获得 100 条。

目标日期和分页结束都不保证取得账号的全部历史；可获取范围受 API、权限、删除内容和请求预算影响。

### 合并与替换

- `fetch` 默认按 tweet ID 合并历史，远端删除不会自动删除本地历史。
- `fetch --replace` 显式替换快照：分页完整且本次翻译全部成功后，提交 raw/translated；分页不完整时不覆盖。
- `fetch --replace --no-translate` 不进行翻译：完整抓取后替换 raw，并从已有译文中移除不在新快照中的 ID；缺失的译文文件不会因此创建。
- 源码中的 `./refetch_data.sh` 等价于 `fetch --replace`；`./refetch_data.sh -i` 等价于 `fetch-more`。它是兼容包装器，不会额外备份到 `cache_backup/`、安装依赖或验证数据。新流程使用 CLI。

### 退出状态

| 命令/情况 | 退出码与结果 |
|---|---|
| `fetch` 完整抓取、翻译成功 | `0`；缺少 ML 或不足 10 条译文时也可跳过聚类并返回 `0` |
| `fetch` 页数上限且还有下一页 | `2`；合并模式保存部分结果，替换模式拒绝覆盖 |
| `fetch` 翻译部分失败 | `1`；合并模式可保留成功结果，替换模式保留原快照 |
| `fetch-more` | 完成 `0`、失败 `1`、安全保存但范围不完整 `2` |
| `analyze interest` | 成功 `0`，分析或保存失败 `1` |
| `analyze behavior` | 完成 `0`；时间统计有效但事件/总结失败 `2`；执行或保存失败 `1` |
| `analyze sentiment` | 完成 `0`、部分批次失败 `2`；全部失败 `1` 且保留旧结果和图表 |
| `translate` | 完成/无需更新 `0`，失败记录未全部恢复时 `1` |

不能仅凭文件存在判断任务成功。CSV 导出没有可导出的文件时也可能正常退出；应核对提示及实际产物。更多恢复说明见 [增量抓取指南](https://github.com/yuanrengu/xcrawler/blob/main/FETCH_MORE_DATA.md)。

## 输出与证据

以下路径相对于运行目录；默认缓存目录可用 `CACHE_DIR` 或 `--cache-dir` 更改。

| 默认路径 | 内容 |
|---|---|
| `cache/{username}_raw_tweets.json` | 保留的原始推文记录 |
| `cache/{username}_translated.json` | 清洗后的原文、中文译文、ID、时间和指纹 |
| `cache/{username}_interest_profile.json` | 专业兴趣画像；供报告和兴趣 CSV 使用 |
| `cache/{username}_profile.json` | 抓取到的账号基本资料 |
| `cache/{username}_analysis.json` | 可选聚类及摘要，不等于专业兴趣画像 |
| `cache/{username}_behavior.json` | 时间统计、生活事件和总结 |
| `cache/{username}_sentiment.json` | 分类明细、分布、失败批次数 |
| `cache/{username}_network.json` | 标签、提及与共现统计 |
| `cache/{username}_fetch_status.json` | 增量抓取范围与阶段状态 |
| `cache/charts/` | PNG 与 HTML；支持命令的 `--output` 可更改位置 |
| `cache/csv/` | CSV；`export csv --output` 可更改位置 |
| `cache/analysis_runs.json`、`cache/llm_calls.json` | 运行与模型调用元数据；SQLite 模式改存数据库 |

报告包括小时、星期、语言、专业兴趣图表（取决于输入文件），以及已有兴趣/事件的证据区；不会自动加入网络和情感图表。HTML 通过相对路径引用 PNG，分享时需一起携带相关图片。

以下为**虚构的兴趣条目节选**，不是完整文件：

```json
{
  "tag": "开源工具",
  "level": "core",
  "confidence": 0.8,
  "keywords": ["Python", "开源"],
  "evidence_count": 2,
  "evidence_tweet_ids": ["1740000000000000001", "1740000000000000002"]
}
```

`evidence_count` 是有效证据 ID 数量；`confidence` 是模型判断，不是经过校准的统计概率。当前兴趣/事件分析仅接受实际输入样本的证据 ID，并记录 `sampling.sample_tweet_ids`；ID 合法不表示语义已经核实。

翻译字段 `original` 可能已经移除 URL、@提及并整理空白，不能代替 raw 文本。清洗后少于 6 字符的文本会跳过翻译，原始条数与译文条数可能不同。

CSV 对危险公式前缀加单引号，长 tweet ID 按文本保护；其他 CSV 工具可能显示这个单引号。情感失败批次为 `unknown`，不计作 `neutral`。

## 配置与存储

- 默认 `TARGET_USERNAME=MiracleHe`、`CACHE_DIR=cache`、`TIMEZONE_OFFSET=8`、`LLM_MODEL=deepseek-chat`；真实操作前请设置自己的目标账号。
- 兴趣分析优先使用非空 `DEEPSEEK_API_KEY`，只有其为空才选择 OpenAI 配置；不是请求失败后的自动切换。OpenAI 服务还需要匹配的模型名。
- 默认翻译批大小为 10；批处理和缓存减少重复开销，但不保证固定费用降幅。
- 默认兴趣分析上限 300 条，行为事件抽样上限 200 条，抓取后的聚类上限 1000 条；按记录顺序均匀抽样，不保证每个时间区间等量。
- `STORAGE_BACKEND=sqlite` 只切换运行/调用元数据；推文、译文、缓存和报告仍是文件。两种后端不会自动迁移。

```bash
xcrawler analyze interest --storage sqlite
xcrawler analyze sentiment --storage sqlite --sqlite-path state/xcrawler.db
```

完整变量表、Provider 设置、缓存迁移、重翻与文件锁说明见 [配置指南](https://github.com/yuanrengu/xcrawler/blob/main/CONFIG_GUIDE.md)。

## 隐私与数据边界

抓取默认排除转发和回复，不代表用户的全部互动。

默认行为分析隐藏被识别为敏感的事件描述和证据 ID；报告生成时再次过滤，包括旧数据。过滤依赖类别、标记和关键词，不是全面匿名化：兴趣及普通事件证据可能展示原文或个人信息，请在分享前复核。

如果确需显示敏感事件，必须在生成行为数据和报告时都显式启用；仅在报告阶段开启不能恢复先前已删除的内容：

```bash
xcrawler analyze behavior --include-sensitive-events
xcrawler report --include-sensitive-events
```

原始数据、译文和模型输入不因报告过滤而自动脱敏。报告链接的证据只说明引用来源；模型可能误判，发帖时间也不能证明实际作息或所在地。

POSIX 新建目录默认 `0700`，受管文件 `0600`；已有父目录不会自动改权。Windows 应结合文件系统访问控制管理数据。JSON 更新使用锁、原子写入和 `.bak` 恢复，但整个抓取/分析流程不是一个事务。

清理数据前先停止相关进程，确认自定义输出目录、`.bak`、共享翻译/向量缓存、运行元数据、SQLite 数据库以及历史备份。只删除 `{username}_*.json` 不等于清除全部关联内容，也不能靠文件名安全清理共享记录。不要在运行中删除 `.lock` 文件。

## 故障排除

| 现象 | 排查方式 |
|---|---|
| 找不到 `xcrawler` | 激活安装时使用的虚拟环境；用 `python -m pip show xcrawler-ai` 核对 |
| `.env` 未生效/提示缺少密钥 | 先用显式环境变量；检查 `.env` 查找位置和已有环境变量优先级 |
| 找不到输入文件 | 对齐 `--user`、`--cache-dir`；先抓取，再翻译/分析，不要把分析命令当作只读查看 |
| 缺少 matplotlib | `python -m pip install "xcrawler-ai[viz]"` |
| 跳过聚类 | 检查是否安装 `ml`、译文是否至少 10 条、抓取是否完整 |
| 兴趣/情感文本不足 | 至少 5 条有效文本；兴趣 `--limit` 也不能低于实际分析要求 |
| HTTP 401/403 | 检查 Token 和账户访问权限；重试不能补足权限 |
| HTTP 429 | 降低请求预算，检查服务额度；超过程序等待上限会停止，不会无限等待 |
| 退出码 `2` | 查看命令输出；增量任务还可查看 fetch status 文件，确认未完成范围 |
| 翻译失败或模型报错 | 检查密钥、服务地址、模型名和输入长度；缓存迁移也可能增加请求 |
| 报告没有更新 | `report` 不重新分析；更新译文后重跑所需分析 |
| 分享后图片不显示 | 将 HTML 与其引用的 PNG 一起复制 |

## 源码开发

以下步骤需要 Git，与上面的 PyPI 安装是两条可选路径：

```bash
git clone https://github.com/yuanrengu/xcrawler.git
cd xcrawler
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
# 需要图表时再安装；聚类可选 .[ml] 或 .[all]
python -m pip install -e ".[viz]"
ruff check .
mypy xcrawler
python -m pytest
```

Windows 激活方式见前文。开发安装用于运行当前源码，详细流程见 [CONTRIBUTING](https://github.com/yuanrengu/xcrawler/blob/main/CONTRIBUTING.md)。

```text
xcrawler/       配置、CLI、客户端、服务、存储和工具
main.py         抓取/翻译/聚类的兼容入口
analyze_*.py    分析命令实现和旧脚本入口
tests/          按职责拆分的回归测试
.github/        CI、依赖更新和 PR 模板
```

## 详细文档与贡献

- [快速开始](https://github.com/yuanrengu/xcrawler/blob/main/QUICK_START.md)：最小操作路径。
- [配置指南](https://github.com/yuanrengu/xcrawler/blob/main/CONFIG_GUIDE.md)：环境、Provider、存储与翻译恢复。
- [增量抓取](https://github.com/yuanrengu/xcrawler/blob/main/FETCH_MORE_DATA.md)：请求预算、替换与状态。
- [行为分析](https://github.com/yuanrengu/xcrawler/blob/main/BEHAVIOR_ANALYSIS.md)：抽样、隐私与结果解释。
- [更新日志](https://github.com/yuanrengu/xcrawler/blob/main/CHANGELOG.md)、[发布检查](https://github.com/yuanrengu/xcrawler/blob/main/RELEASE_CHECKLIST.md)。
- [贡献指南](https://github.com/yuanrengu/xcrawler/blob/main/CONTRIBUTING.md)：先关联 Issue，再提交分支和 PR。
- [安全报告](https://github.com/yuanrengu/xcrawler/blob/main/SECURITY.md)：密钥或隐私问题请按私下报告流程处理。

本项目使用 [MIT License](https://github.com/yuanrengu/xcrawler/blob/main/LICENSE)。请遵守所用服务的规则和适用法律，勿用于未经授权的个人画像或平台外广告定向。
