from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Sequence


def _run_script(module_name: str, args: Sequence[str]) -> int:
    module = importlib.import_module(module_name)
    old_argv = sys.argv[:]
    try:
        sys.argv = [f"{module_name}.py", *args]
        module.main()
    finally:
        sys.argv = old_argv
    return 0


def _add_common_options(parser: argparse.ArgumentParser, *, model: bool = False) -> None:
    parser.add_argument("-u", "--user", help="目标用户名")
    parser.add_argument("--cache-dir", help="缓存目录")
    if model:
        parser.add_argument("--model", help="LLM 模型名")
    parser.add_argument("--verbose", action="store_true", help="保留参数，供后续详细日志使用")


def _forward_common(args: argparse.Namespace, *, include_model: bool = False) -> list[str]:
    forwarded: list[str] = []
    if args.user:
        forwarded.extend(["--user", args.user])
    if args.cache_dir:
        forwarded.extend(["--cache-dir", args.cache_dir])
    if include_model and getattr(args, "model", None):
        forwarded.extend(["--model", args.model])
    return forwarded


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xcrawler",
        description="X/Twitter 用户画像分析统一 CLI",
    )
    parser.add_argument("--version", action="version", version="xcrawler 0.3.0")

    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch = subparsers.add_parser("fetch", help="抓取数据、翻译并执行聚类分析")
    _add_common_options(fetch, model=True)
    fetch.add_argument("--pages", type=int, help="抓取页数")
    fetch.add_argument("--batch-size", type=int, help="每批翻译条数")
    fetch.add_argument("--no-translate", action="store_true", help="仅抓取不翻译")
    fetch.set_defaults(handler=_handle_fetch)

    fetch_more = subparsers.add_parser("fetch-more", help="智能增量抓取新推文和历史推文")
    _add_common_options(fetch_more)
    fetch_more.add_argument("--pages", type=int, help="最大抓取页数")
    fetch_more.add_argument("--target-date", help="历史抓取目标日期，格式 YYYY-MM-DD")
    fetch_more.add_argument("--interval", type=int, help="请求间隔秒数")
    fetch_more.set_defaults(handler=_handle_fetch_more)

    translate = subparsers.add_parser("translate", help="同步或重翻已有原始推文")
    _add_common_options(translate)
    translate.add_argument("--force", action="store_true", help="强制重新翻译所有推文")
    translate.set_defaults(handler=_handle_translate)

    analyze = subparsers.add_parser("analyze", help="运行分析任务")
    analyze_subparsers = analyze.add_subparsers(dest="analysis", required=True)

    interest = analyze_subparsers.add_parser("interest", help="专业兴趣画像分析")
    _add_common_options(interest, model=True)
    interest.add_argument("--temperature", type=float, help="模型温度")
    interest.set_defaults(handler=_handle_analyze_interest)

    behavior = analyze_subparsers.add_parser("behavior", help="时间行为和生活事件分析")
    _add_common_options(behavior)
    behavior.add_argument("--include-sensitive-events", action="store_true", help="包含敏感生活事件详情和证据")
    behavior.set_defaults(handler=_handle_analyze_behavior)

    sentiment = analyze_subparsers.add_parser("sentiment", help="情感分析")
    _add_common_options(sentiment)
    sentiment.add_argument("--output", help="输出目录")
    sentiment.add_argument("--top", type=int, help="显示 Top N 正/负面推文")
    sentiment.set_defaults(handler=_handle_analyze_sentiment)

    network = analyze_subparsers.add_parser("network", help="Hashtag / Mention 网络分析")
    _add_common_options(network)
    network.add_argument("--top", type=int, help="显示 Top N 结果")
    network.add_argument("--output", help="输出目录")
    network.set_defaults(handler=_handle_analyze_network)

    report = subparsers.add_parser("report", help="生成图表和 HTML 报告")
    _add_common_options(report)
    report.add_argument("--output", help="输出目录")
    report.add_argument("--format", choices=["png", "html"], help="输出格式")
    report.add_argument("--include-sensitive-events", action="store_true", help="在 HTML 报告中展示敏感事件证据")
    report.set_defaults(handler=_handle_report)

    export = subparsers.add_parser("export", help="导出数据")
    export_subparsers = export.add_subparsers(dest="export_type", required=True)
    csv_export = export_subparsers.add_parser("csv", help="导出 CSV")
    _add_common_options(csv_export)
    csv_export.add_argument("--output", help="输出目录")
    csv_export.add_argument("--type", choices=["all", "tweets", "translations", "interests"], help="导出类型")
    csv_export.set_defaults(handler=_handle_export_csv)

    return parser


def _handle_fetch(args: argparse.Namespace) -> int:
    forwarded = _forward_common(args, include_model=True)
    if args.pages is not None:
        forwarded.extend(["--pages", str(args.pages)])
    if args.batch_size is not None:
        forwarded.extend(["--batch-size", str(args.batch_size)])
    if args.no_translate:
        forwarded.append("--no-translate")
    return _run_script("main", forwarded)


def _handle_fetch_more(args: argparse.Namespace) -> int:
    forwarded = _forward_common(args)
    if args.pages is not None:
        forwarded.extend(["--pages", str(args.pages)])
    if args.target_date:
        forwarded.extend(["--target-date", args.target_date])
    if args.interval is not None:
        forwarded.extend(["--interval", str(args.interval)])
    return _run_script("fetch_more_history", forwarded)


def _handle_translate(args: argparse.Namespace) -> int:
    forwarded = []
    if args.user:
        forwarded.extend(["--user", args.user])
    if args.force:
        forwarded.append("--force")
    return _run_script("translate_sync", forwarded)


def _handle_analyze_interest(args: argparse.Namespace) -> int:
    forwarded = _forward_common(args, include_model=True)
    if args.temperature is not None:
        forwarded.extend(["--temperature", str(args.temperature)])
    return _run_script("analyze_pro", forwarded)


def _handle_analyze_behavior(args: argparse.Namespace) -> int:
    forwarded = _forward_common(args)
    if args.include_sensitive_events:
        forwarded.append("--include-sensitive-events")
    return _run_script("analyze_behavior", forwarded)


def _handle_analyze_sentiment(args: argparse.Namespace) -> int:
    forwarded = _forward_common(args)
    if args.output:
        forwarded.extend(["--output", args.output])
    if args.top is not None:
        forwarded.extend(["--top", str(args.top)])
    return _run_script("analyze_sentiment", forwarded)


def _handle_analyze_network(args: argparse.Namespace) -> int:
    forwarded = _forward_common(args)
    if args.top is not None:
        forwarded.extend(["--top", str(args.top)])
    if args.output:
        forwarded.extend(["--output", args.output])
    return _run_script("analyze_network", forwarded)


def _handle_report(args: argparse.Namespace) -> int:
    forwarded = _forward_common(args)
    if args.output:
        forwarded.extend(["--output", args.output])
    if args.format:
        forwarded.extend(["--format", args.format])
    if args.include_sensitive_events:
        forwarded.append("--include-sensitive-events")
    return _run_script("visualize", forwarded)


def _handle_export_csv(args: argparse.Namespace) -> int:
    forwarded = _forward_common(args)
    if args.output:
        forwarded.extend(["--output", args.output])
    if args.type:
        forwarded.extend(["--type", args.type])
    return _run_script("export_csv", forwarded)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
