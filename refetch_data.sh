#!/usr/bin/env bash
set -euo pipefail

# Legacy compatibility wrapper. New integrations should call `xcrawler` directly.
usage() {
    echo "用法:"
    echo "  ./refetch_data.sh                 # 重建快照（等价于 xcrawler fetch --replace）"
    echo "  ./refetch_data.sh --incremental   # 安全增量抓取"
    echo "  ./refetch_data.sh -i              # 安全增量抓取"
    echo "  可在模式参数后追加 xcrawler 子命令参数。"
}

mode="full"
if [[ ${1:-} == "--incremental" || ${1:-} == "-i" ]]; then
    mode="incremental"
    shift
elif [[ ${1:-} == "--help" || ${1:-} == "-h" ]]; then
    usage
    exit 0
fi

echo "⚠️  refetch_data.sh 是兼容入口，新流程请直接使用 xcrawler CLI。"

if [[ "$mode" == "incremental" ]]; then
    exec python3 -m xcrawler.cli fetch-more "$@"
fi

echo "⚠️  全量模式会使用本次结果替换快照；需保留历史时请改用 -i。"
exec python3 -m xcrawler.cli fetch --replace "$@"
