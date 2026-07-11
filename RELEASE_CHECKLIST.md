# Release Checklist

发布前用这份清单确认 xcrawler 已具备可复用开源产品的基本条件。

## 发布前

- [ ] `main` 分支已合并目标版本的全部 PR。
- [ ] `ruff check .` 和 `pytest -ra` 本地通过。
- [ ] GitHub Actions 通过。
- [ ] `python -m pip install -e ".[test]"` 可正常安装。
- [ ] `xcrawler --help` 可正常显示。
- [ ] `python3 -m build` 成功生成 wheel 和 sdist。
- [ ] `python3 -m twine check dist/*` 通过。
- [ ] 在干净虚拟环境从 wheel 安装后，`xcrawler --version`、`xcrawler --help` 和 `xcrawler demo` 通过。
- [ ] `README.md`、`QUICK_START.md`、`.env.example` 与当前 CLI 保持一致。
- [ ] `CONTRIBUTING.md`、`SECURITY.md`、`LICENSE` 存在且链接有效。
- [ ] 默认隐私行为已核对：敏感生活事件和证据原文默认隐藏。
- [ ] 示例输出和截图不包含真实密钥、联系方式或非公开个人信息。

## 版本与标签

- [ ] 更新 `pyproject.toml` 中的版本号。
- [ ] `xcrawler/__init__.py` 与 `pyproject.toml` 版本号一致。
- [ ] `CHANGELOG.md` 将待发布内容从 `Unreleased` 移入当前版本和日期。
- [ ] 创建并验证签名或 annotated Git tag，例如 `v0.4.0`。
- [ ] 在 README 更新对应版本的变更摘要。
- [ ] 创建 GitHub Release，标题使用版本号，例如 `v0.4.0`。
- [ ] Release notes 包含：新增能力、兼容性说明、迁移提示、已知限制。

## 发布后

- [ ] 确认 Release 页面、源码包和文档链接可访问。
- [ ] 创建下一阶段 roadmap 或 follow-up issues。
- [ ] 如涉及安全或隐私变更，在 release notes 中单独说明。
