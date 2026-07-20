# Contributing to xcrawler

感谢你愿意改进 xcrawler。这个项目的目标是把 X/Twitter 用户画像分析流程做成可复用、可维护、可审计的开源工具。

## 开发环境

建议使用虚拟环境，避免污染系统 Python：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

复制配置模板并填入自己的密钥：

```bash
cp .env.example .env
```

`.env`、`cache/`、`cache_backup/`、SQLite `*.db`/`*.db-wal`/`*.db-shm` 中可能包含密钥或个人分析数据，请不要提交。

涉及本地持久化的变更必须保留私有权限策略：POSIX 新目录 `0700`、受管文件 `0600`，不得跟随受管文件或备份的符号链接，也不得静默修改用户已有父目录权限。

## 常用命令

```bash
# 查看统一 CLI
xcrawler --help

# 抓取、翻译并做基础分析
xcrawler fetch --user MiracleHe

# 专业兴趣画像
xcrawler analyze interest --user MiracleHe

# 行为分析
xcrawler analyze behavior --user MiracleHe

# 生成报告
xcrawler report --user MiracleHe

# 运行质量检查和测试
ruff check .
mypy xcrawler
pytest -q
```

## 提交 Pull Request

1. 先创建或关联一个 issue，说明动机、范围和验收标准。
2. 从 `main` 创建功能分支，分支名建议使用 `codex/<issue-number>-short-name` 或 `feature/<short-name>`。
3. 保持改动聚焦：修 bug、补文档、重构和新功能尽量拆成不同 PR。
4. 新增或修改行为时补充测试；文档-only PR 请说明未运行测试的原因。
5. PR 描述请包含：变更摘要、验证方式、关联 issue。

## 代码约定

- 优先复用 `xcrawler/` 下已有模块，不在顶层脚本中重复堆逻辑。
- 新功能默认走统一 CLI，同时保持旧脚本入口兼容。
- 分析输出应尽量可追溯：保留 `tweet_id`、`evidence_tweet_ids` 或 `analysis_run_id`。
- 涉及生活事件、健康、关系、地址、联系方式等敏感信息时，默认隐藏或脱敏。
- 默认存储仍是 JSON；需要更强查询能力时，应通过 `Storage` 接口扩展，不直接绕开存储层。

## 测试与验证

合并前至少运行：

```bash
pytest -q
```

如果修改了安装、依赖或 CLI 入口，也应额外验证：

```bash
python -m pip install -e ".[dev]"
xcrawler --help
python -m build
```

## 负责任使用

请勿提交用于骚扰、跟踪、人肉搜索、歧视性画像、平台外广告定向或获取非公开个人信息的功能。任何降低隐私保护默认值的变更，都需要在 issue 和 PR 中明确说明风险、动机和替代方案。
