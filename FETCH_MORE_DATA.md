# 增量抓取、快照与恢复

安装和密钥设置见 [README](https://github.com/yuanrengu/xcrawler/blob/main/README.md)。本页描述当前源码，不承诺能获取账号的全部历史。

## 增量流程

```bash
xcrawler fetch-more --user alice --pages 10 --target-date 2024-01-01
xcrawler translate --user alice
```

`fetch-more` 更新原始数据，不翻译。随后按需重新运行兴趣、行为、情感或网络分析，再运行 `report`。报告渲染不会自动刷新分析结果。

Forward 阶段向前抓取新数据，Backward 阶段补历史。每个阶段成功后立即合并保存，后阶段失败不会撤销前阶段保存的数据。没有现有数据时也可开始抓取。

`--pages` 是 Forward、Backward 和重试共享的 HTTP 请求预算，默认 10，不是套餐额度，也不是必然成功的数据页数。每页最多 100 条；空页、少量记录、重试都会影响实际数据量。

`--target-date` 设置期望的历史边界；`--interval` 设置请求间隔。接口范围、权限和已删除内容等可能限制可取得的历史。不要将分页结束解释为拥有全部历史。

## 状态文件与退出码

状态保存在 `cache/{username}_fetch_status.json`，包括 `complete`、`has_more`、`forward_complete`、`backward_complete`、请求数、数据页数、重试数和停止原因。

| 退出码 | 含义 |
|---|---|
| `0` | 本次目标同步范围完成 |
| `1` | 抓取失败；检查前一阶段是否已保存结果 |
| `2` | 已安全保存进度，但预算或剩余分页等导致范围不完整 |

自动化应检查状态，不能仅检查文件是否存在。错误重试和限流等待有上限；需要较长时间恢复的限流会停止本次任务。

## 全量入口与替换语义

```bash
# 默认归档合并，保留已有历史
xcrawler fetch --user alice --pages 10

# 明确需要重建快照时使用；会删除本地不在新快照中的记录
xcrawler fetch --user alice --pages 10 --replace
```

`fetch --pages` 是数据分页上限，与 `fetch-more` 的共享 HTTP 请求预算不同。达到上限且还有下一页时，合并模式保存部分结果并返回 `2`；替换模式拒绝覆盖并返回 `2`。

正常替换在完整抓取和本次翻译全部成功后提交 raw/translated；翻译失败返回 `1` 并保留原快照。共享翻译缓存检查点不等于快照提交。

```bash
# 完整抓取后仅更新 raw，并按新快照 ID 过滤已有译文
xcrawler fetch --user alice --replace --no-translate
```

上述组合不进行翻译，不创建缺失的译文文件，也不更新兴趣/行为等派生结果。以后需要时运行 `translate` 并重新分析。

## 兼容包装器

仓库内的 `refetch_data.sh` 仅分派命令：

| 调用 | 实际行为 |
|---|---|
| `./refetch_data.sh` | `python3 -m xcrawler.cli fetch --replace` |
| `./refetch_data.sh -i` | `python3 -m xcrawler.cli fetch-more` |

可在模式参数后追加对应 CLI 参数。包装器本身不检查/安装依赖、不验证抓取结果，也不额外备份到 `cache_backup/`。底层 JSON 的 `.bak` 策略仍适用。需要脚本文件时使用源码检出；PyPI 用户直接使用 CLI。

## 失败后的处理

1. 阅读命令错误和 fetch status；确认用户名、目录与已完成阶段。
2. 检查网络、凭据、权限或服务额度；修复原因后再运行增量抓取。
3. 运行 `translate` 补齐缺失或失效译文，之后更新需要的分析和报告。
4. 数据损坏时，受管 JSON 读取会尝试有效 `.bak` 恢复；双方都不可用时明确报错。需要手动恢复时先停止进程、保留现场副本，再核对同一账号与对应版本的文件，不要盲目复制所有历史备份覆盖当前数据。

普通翻译可复用批次缓存，强制重翻不能断点续跑。详细规则见 [配置与翻译恢复](https://github.com/yuanrengu/xcrawler/blob/main/CONFIG_GUIDE.md#翻译缓存与恢复)。
