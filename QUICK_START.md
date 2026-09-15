# 快速开始

此页提供最短操作路径，完整命令、退出状态和限制见 [README](https://github.com/yuanrengu/xcrawler/blob/main/README.md)。步骤不承诺固定安装耗时，真实请求可能收费。

## 无密钥 Demo

macOS/Linux，Python 3.10+：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install xcrawler-ai
xcrawler demo
```

Windows PowerShell：用 `py -m venv .venv` 创建环境，再用 `.venv\Scripts\Activate.ps1` 激活。

浏览器打开 `demo_output/xcrawler_demo_report.html`。这是内置虚构数据的证据 HTML，不调用模型，不生成完整 PNG 图表；不需要绘图或 ML 扩展。

## 真实账号

安装绘图扩展，在同一个终端设置环境变量并替换占位符：

```bash
python -m pip install "xcrawler-ai[viz]"
export X_BEARER_TOKEN="your_x_bearer_token"
export DEEPSEEK_API_KEY="your_deepseek_api_key"
export TARGET_USERNAME="your_x_username"
```

PowerShell 的配置语法为 `$env:TARGET_USERNAME="your_x_username"`，密钥变量同理。终端历史可能记录输入，请在可信环境配置，不提交密钥。

当前无参数 `load_dotenv()` 不保证发现任意工作目录的 `.env`；独立安装先使用环境变量。源码 `.env` 方法见 [配置指南](https://github.com/yuanrengu/xcrawler/blob/main/CONFIG_GUIDE.md)。

逐条运行并检查退出状态：

```bash
xcrawler fetch --pages 3
xcrawler analyze interest --limit 300
xcrawler analyze behavior
xcrawler report
```

- `fetch` 分页未结束时返回 `2` 并保存部分数据；可补抓，或接受当前样本范围再分析。
- 兴趣分析至少需 5 条可用译文；Demo 样本数量不足。
- 未安装 ML 时跳过聚类，不影响单独的专业兴趣分析。
- `report` 只读取已有分析结果，不会自动调用模型更新结论。
- 报告位于 `cache/charts/{username}_report.html`；分享时连同引用的 PNG 一起复制。

## 日常更新

```bash
xcrawler fetch-more --pages 10 --target-date 2024-01-01
xcrawler translate
xcrawler analyze interest
xcrawler analyze behavior
xcrawler report
```

`fetch-more` 只更新 raw；检查各步状态后再继续。需要情感或网络结果时另运行 `xcrawler analyze sentiment` 或 `xcrawler analyze network`。

## 查看结果

用编辑器打开用户对应的 JSON，或用浏览器打开生成的 HTML。`analyze` 命令会重新分析，可能发起付费调用，不是只读查看命令。仓库里的 `ANALYSIS_SUMMARY.md` 是历史静态文档，不是本次自动生成的报告。

`--user` 与 `--cache-dir` 必须在相关命令间保持一致。更多内容见 [输出说明](https://github.com/yuanrengu/xcrawler/blob/main/README.md#输出与证据) 和 [增量抓取指南](https://github.com/yuanrengu/xcrawler/blob/main/FETCH_MORE_DATA.md)。
