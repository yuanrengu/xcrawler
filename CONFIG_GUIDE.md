# 配置、存储与翻译恢复

本文对应当前源码。安装与主要流程见 [README](https://github.com/yuanrengu/xcrawler/blob/main/README.md)。

## 配置来源与优先级

当前代码在导入 `xcrawler.config` 时调用无参数 `load_dotenv()`。普通脚本的查找起点与调用模块位置有关；独立安装时不能保证读取当前工作目录的 `.env`。建议先使用显式环境变量：

```bash
# macOS/Linux，替换占位符，在运行命令的同一终端设置
export X_BEARER_TOKEN="your_x_bearer_token"
export DEEPSEEK_API_KEY="your_deepseek_api_key"
export TARGET_USERNAME="your_x_username"
```

```powershell
# Windows PowerShell
$env:X_BEARER_TOKEN="your_x_bearer_token"
$env:DEEPSEEK_API_KEY="your_deepseek_api_key"
$env:TARGET_USERNAME="your_x_username"
```

密钥可能留在终端历史中，请使用自己的可信环境。不要提交密钥、`.env` 或分析数据。

源码检出并通过 `pip install -e .` 安装时，可在源码根目录复制模板：

```bash
cp .env.example .env
# 使用编辑器填写 .env；不要直接执行未经检查的配置文件
```

非空占位符不是有效密钥；不使用的可选配置应留空或删除。当前没有 `--env-file` 参数。修改配置后重新启动命令；不要假定已导入的模块会自动重新加载。

通常优先级为：命令支持的 CLI 参数 > 进程环境变量 > 被发现的 `.env` > 代码默认值。现有环境变量不会被 `.env` 自动覆盖；配置加载和校验发生在部分 CLI 覆盖之前，因此非法环境值仍应先修正。

## 变量表

| 变量 | 默认值 | 用途 |
|---|---|---|
| `X_BEARER_TOKEN` | 无 | 抓取公开推文 |
| `DEEPSEEK_API_KEY` | 无 | 翻译及默认 AI 分析 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek 兼容服务地址 |
| `OPENAI_API_KEY` | 无 | 仅专业兴趣分析的备选 Provider |
| `OPENAI_BASE_URL` | `https://api.openai.com` | 未设置变量时的 OpenAI 地址；显式空字符串不会使用该默认值 |
| `LLM_MODEL` | `deepseek-chat` | 翻译及 AI 分析模型 |
| `TARGET_USERNAME` | `MiracleHe` | 默认目标账号，建议不带 `@` |
| `TARGET_DATE` | `2024-01-01` | 增量历史目标日期，格式 `YYYY-MM-DD` |
| `TIMEZONE_OFFSET` | `8` | 固定 UTC 偏移小时数；不自动处理夏令时 |
| `CACHE_DIR` | `cache` | 相对于运行目录的缓存位置 |
| `STORAGE_BACKEND` | `json` | `json` 或 `sqlite`，仅运行元数据 |
| `SQLITE_PATH` | 未指定时 `<cache-dir>/xcrawler.db` | 数据库位置 |
| `LLM_PRICING_JSON` | 未配置 | 每百万 input/output token 的 USD 单价，用于估算 |

```bash
xcrawler fetch --user alice --cache-dir ./research-cache --pages 3
xcrawler analyze interest --user alice --cache-dir ./research-cache --limit 100
```

`--user`、`--cache-dir` 只影响本次命令；后续操作需继续使用相同参数。分页数、批大小和分析条数使用 CLI 参数，不要假定存在同名环境变量。实际支持项以子命令 `--help` 为准。

## Provider 与模型

专业兴趣分析使用非空 `DEEPSEEK_API_KEY` 优先；仅其为空时选择 OpenAI 配置。这里的“备选”是启动时选择，不是请求失败后的自动切换。翻译、行为、情感和抓取后的聚类摘要仍使用 DeepSeek 兼容配置。

仅切换专业兴趣分析的示例（macOS/Linux；服务地址和模型均为占位示例，请按所用服务填写完整 API 路径）：

```bash
export DEEPSEEK_API_KEY=""
export OPENAI_API_KEY="your_openai_key"
export OPENAI_BASE_URL="https://your-provider.example/v1"
# 替换成该服务实际支持的模型；本项目不提供模型可用性保证
xcrawler analyze interest --model your_supported_model
```

之后执行翻译或行为分析前，恢复 DeepSeek 兼容配置。使用第三方兼容服务时需显式设置其地址、密钥和模型，文本将发送到该地址。

可选成本配置示例（仅结构示意，0.0 不是供应商报价）：

```dotenv
LLM_PRICING_JSON={"deepseek-chat":{"input_per_million":0.0,"output_per_million":0.0}}
```

请自行填写当前服务报价；不配置时调用记录的成本为 `null`。批处理减少重复提示开销，费用还取决于文本长度、输出、重试和缓存命中，不保证固定倍数。

## 翻译缓存与恢复

翻译目标是中文。检测为中文的文本通常跳过模型翻译；清洗后的文本短于 6 字符会被跳过。清洗移除 URL、@提及并整理空白，译文记录的 `original` 因而不等于完整 API 原文。

```bash
# 普通同步：新增、失效或来源待验证的译文
xcrawler translate

# 显式强制：绕过旧缓存，重新翻译符合条件的文本
xcrawler translate --force
```

- 缓存按 Provider、模型、目标语言、Prompt 版本及规范化服务地址身份隔离。服务地址身份包括协议、主机、端口和路径，不包括认证信息、查询参数或片段。
- 默认端口和末尾斜杠归一化；切换服务或模型可能触发重翻。
- 旧 `{原文: 译文}` 缓存留在 `legacy_entries` 供人工恢复，缺少来源信息的旧缓存不继续命中。
- 译文缺少配置指纹、原文变化、配置变化或内容无效时会重新验证/翻译；成功前保留旧译文。首次升级迁移可能增加模型调用。
- 抓取和普通同步按批保存成功译文到共享缓存。中断后使用相同配置重跑，可复用仍需翻译条目的成功结果；未完成批次可能再次调用模型。
- 缓存保存失败会停止流程，不会因此重试模型调用。
- **强制重翻不支持断点续跑。** 再带 `--force` 运行会从头重翻，可能重复收费。省略 `--force` 是普通同步：有效旧译文会被跳过，不会自动用新缓存替换它们。
- 强制重翻的主译文文件仅在全部成功后提交；期间保存的共享缓存不是强制任务恢复记录。`fetch --replace` 同样不会因缓存检查点而提交部分快照。

## 存储与并发

默认 `JsonStore` 使用 `analysis_runs.json` 和 `llm_calls.json`。支持存储选项的命令可切换：

```bash
xcrawler analyze interest --storage sqlite
xcrawler analyze behavior --storage sqlite --sqlite-path state/xcrawler.db
```

SQLite 使用结构化运行/调用表、索引、WAL、事务和 busy timeout；普通 Storage key 有 `json_documents` 兼容表。原始推文、译文、翻译缓存、向量缓存、图表和报告仍为文件。切换不自动迁移旧元数据，可通过 `query_analysis_runs()` 和 `query_llm_calls()` 查询数据库记录。

调用记录包含状态、模型、token、耗时和错误等元数据，不专门保存 Prompt/响应正文字段；错误信息仍可能含服务返回内容，不应视为可公开的无敏感数据。

JSON 受管操作使用同名 `.lock` advisory lock，默认等待最多 5 秒。读写、备份恢复和追加操作在锁内进行；多文件操作按规范化路径顺序取锁。网络和模型请求在锁外，整个业务流程不是一个事务。

归档和共享缓存保存时会在锁内重新读取最新文件并合并。翻译缓存只允许当前进程自上次成功保存后生成的键覆盖已有值；未修改的旧快照不能回滚其他进程的修正。同一键均生成新值时，以最后提交为准。显式快照仍遵循替换语义。

锁文件可保留复用，进程退出后操作系统释放实际锁；不要在运行时删除锁文件。SQLite 仅改变元数据存储，不会使普通文件工作流变为数据库事务。

## 文件保护与清理

JSON 在同目录写临时文件后原子替换，覆盖时保留有效 `.bak`。读取可从有效备份恢复；主文件和备份均损坏时明确报错。新 POSIX 目录默认 `0700`、受管文件 `0600`，已有父目录仅提示，不自动改权。

清理前停止进程，核对自定义目录、CSV/PNG/HTML、`.bak`、共享缓存、元数据、数据库及历史 `cache_backup/`。默认共享文件并非全部按用户名命名；删掉某个用户的主 JSON 不代表清除全部相关数据。不要把通配符删除示例当成可靠的按用户删除功能。
