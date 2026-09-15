# 行为分析

`xcrawler analyze behavior` 读取现有 raw 和 translated 文件，生成时间统计、生活事件及行为总结。安装与配置见 [README](https://github.com/yuanrengu/xcrawler/blob/main/README.md)。

## 前置条件与运行

正常安装已包含 OpenAI 兼容客户端依赖。行为命令需要 DeepSeek 兼容配置；它没有“仅时间分析”的 CLI 开关，缺少密钥不能当作正常的纯统计运行方式。

```bash
# 先抓取并翻译，或对已有 raw 执行 translate
xcrawler analyze behavior --user alice
```

需要同一缓存目录中的 `alice_raw_tweets.json` 和 `alice_translated.json`。该命令会发起模型调用，并非只读查看已有结果；查看结果应直接打开 `cache/alice_behavior.json`。

## 结果含义

- 时间统计基于 raw 中可解析的时间戳，按 `TIMEZONE_OFFSET` 固定偏移计算小时、星期和时段分布，不自动处理夏令时。
- 事件检测最多从译文中按记录顺序均匀抽取 200 条；不是逐一分析全部推文，也不保证各时间区间等量。
- 事件类别包括生日、关系、职业/学业、健康、旅行/搬迁、重大购物和其他事件。
- 事件证据只接受实际输入样本中的 ID，样本列表记录于 `sampling.sample_tweet_ids`；ID 存在不证明事件描述语义正确。
- 总结基于时间统计与经过隐私处理的事件。模型可能推断错误，不能由发帖时间断言实际作息、住址或生活状态。

记录数限制不等于 token 限制；长文本仍可能超过模型上下文。

## 隐私默认值

默认按事件类别、敏感标记和关键词过滤，敏感事件描述替换为占位符，证据 ID 清空。结果包含 `privacy`、`sampling`、`failed_steps` 等字段。

只有明确需要保留这些信息时，才使用：

```bash
xcrawler analyze behavior --user alice --include-sensitive-events
xcrawler report --user alice --include-sensitive-events
```

两步都需要显式开启：报告开关不能恢复默认分析时已从结果移除的内容。默认 `report` 会重新过滤先前显式保存的敏感事件。

这不是全局匿名化。raw、译文、模型输入、兴趣证据与普通事件证据可能仍含个人信息。报告隐私过滤不会撤回已经发送给模型服务的内容，也不能保证识别所有敏感信息。

## 退出状态与报告

| 状态 | 行为 |
|---|---|
| 完成 | 保存结果，返回 `0` |
| 事件检测或总结失败，时间统计仍有效 | 保存部分结果，返回 `2`，检查 `failed_steps` |
| 执行或结果保存失败 | 返回 `1`，尽力记录失败状态 |

```bash
# 读取已有结果生成报告，不会重新执行上述分析
xcrawler report --user alice
```

HTML 展示已有生活事件证据区，不是完整行为 JSON 的逐字段展示，也不自动生成封面示意图中的事件时间线。分享前应结合原文和分析范围人工复核。
