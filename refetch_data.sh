#!/bin/bash
# 数据抓取脚本 - 支持全量和增量两种模式
# 自动从 .env 文件读取 TARGET_USERNAME 配置
#
# 使用方法:
#   ./refetch_data.sh              # 全量重新抓取（默认）
#   ./refetch_data.sh --incremental # 增量抓取（推荐Free API用户）
#   ./refetch_data.sh -i           # 增量抓取（简写）

# 解析命令行参数
MODE="full"  # 默认全量抓取
if [ "$1" = "--incremental" ] || [ "$1" = "-i" ]; then
    MODE="incremental"
elif [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "数据抓取脚本 - 支持全量和增量两种模式"
    echo ""
    echo "使用方法:"
    echo "  ./refetch_data.sh              # 全量重新抓取（默认）"
    echo "  ./refetch_data.sh --incremental # 增量抓取（推荐Free API用户）"
    echo "  ./refetch_data.sh -i           # 增量抓取（简写）"
    echo "  ./refetch_data.sh --help       # 显示此帮助信息"
    echo ""
    echo "模式说明:"
    echo "  全量抓取: 重新抓取所有数据，会备份现有数据"
    echo "  增量抓取: 在现有数据基础上补充新数据，避免API限流"
    echo ""
    exit 0
fi

echo "=================================================="
if [ "$MODE" = "incremental" ]; then
    echo "🔄 增量抓取数据（续传模式）"
else
    echo "🔄 全量重新抓取数据"
fi
echo "=================================================="
echo ""

# 1. 读取 .env 文件中的 TARGET_USERNAME
if [ -f ".env" ]; then
    # 从 .env 文件读取 TARGET_USERNAME，支持带引号和不带引号的格式
    TARGET_USERNAME=$(grep "^TARGET_USERNAME=" .env | cut -d '=' -f2 | tr -d '"' | tr -d "'")
    if [ -z "$TARGET_USERNAME" ]; then
        TARGET_USERNAME="MiracleHe"  # 默认值（与 Python 脚本一致）
        echo "⚠️  .env 文件中未找到 TARGET_USERNAME，使用默认值: $TARGET_USERNAME"
    else
        echo "✅ 从 .env 读取目标用户: $TARGET_USERNAME"
    fi
else
    TARGET_USERNAME="MiracleHe"  # 默认值（与 Python 脚本一致）
    echo "⚠️  未找到 .env 文件，使用默认用户: $TARGET_USERNAME"
    echo "💡 建议创建 .env 文件并设置 TARGET_USERNAME=your_target_user"
fi
echo ""

# 2. 根据模式决定是否备份
if [ "$MODE" = "full" ]; then
    echo "📦 备份现有数据..."
    mkdir -p cache_backup
    cp cache/*.json cache_backup/ 2>/dev/null || true
    echo "✅ 备份完成: cache_backup/"
    echo ""
else
    echo "📈 增量模式：保留现有数据，仅补充新数据"
    echo ""
fi

# 3. 显示当前配置
echo "⚙️  当前配置:"
if [ "$MODE" = "incremental" ]; then
    echo "   模式: 增量抓取（续传）"
    echo "   MAX_PAGES = 10 (避免API限流)"
else
    echo "   模式: 全量重新抓取"
    echo "   MAX_PAGES = 100 (可抓取1000条)"
fi
echo "   TARGET_USERNAME = $TARGET_USERNAME"
echo ""

# 3. 检查依赖
echo "🔍 检查依赖..."
python3 -c "import requests, openai, dotenv, langdetect" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️  缺少依赖，正在安装..."
    pip3 install requests openai python-dotenv "langdetect>=1.0.9" --break-system-packages -q
    if [ $? -eq 0 ]; then
        echo "✅ 依赖安装完成"
    else
        echo "❌ 依赖安装失败，请手动运行:"
        echo "   pip3 install requests openai python-dotenv \"langdetect>=1.0.9\" --break-system-packages"
        exit 1
    fi
else
    echo "✅ 依赖已安装"
fi
echo ""

# 4. 运行抓取
echo "🚀 开始抓取数据..."
echo "=================================================="
if [ "$MODE" = "incremental" ]; then
    python3 fetch_more_history.py
else
    python3 main.py
fi
exit_code=$?
echo "=================================================="
echo ""

# 5. 验证结果
if [ $exit_code -eq 0 ]; then
    echo "✅ 抓取完成！正在分析数据..."
    echo ""
    
    python3 -c "
import json
from datetime import datetime
from collections import Counter

try:
    with open('cache/${TARGET_USERNAME}_raw_tweets.json') as f:
        tweets = json.load(f)
    
    dates = [datetime.strptime(t['created_at'], '%Y-%m-%dT%H:%M:%S.%fZ') for t in tweets if 'created_at' in t]
    dates.sort()
    
    print('📊 新数据统计:')
    print(f'   总推文: {len(tweets)}条')
    print(f'   时间范围: {dates[0].date()} 至 {dates[-1].date()}')
    print(f'   跨度: {(dates[-1] - dates[0]).days}天')
    print()
    
    years = Counter([d.year for d in dates])
    print('📅 按年份:')
    for y in sorted(years.keys()):
        print(f'   {y}年: {years[y]}条')
    print()
    
    if 2024 in years:
        print('✅ 成功获取2024年数据！')
    else:
        print('⚠️  仍未获取到2024年数据，可能用户2024年未发推文')
        print('💡 或者需要增加 MAX_PAGES 到更大值（如50）')
    
except Exception as e:
    print(f'❌ 数据分析失败: {e}')
"
    
    echo ""
    echo "=================================================="
    echo "🎯 后续步骤:"
    echo "   1. 运行: python3 analyze_behavior.py  # 重新分析行为"
    echo "   2. 运行: python3 analyze_only.py      # 重新分析兴趣"
    echo "   3. 查看: ANALYSIS_SUMMARY.md          # 查看报告"
    echo ""
    echo "💡 使用说明:"
    echo "   全量抓取: ./refetch_data.sh"
    echo "   增量抓取: ./refetch_data.sh --incremental"
    echo "=================================================="
else
    echo "❌ 抓取失败（退出码: $exit_code）"
    echo ""
    echo "💡 可能的原因:"
    echo "   1. API Key 配置错误（检查 .env 文件）"
    echo "   2. 网络连接问题"
    echo "   3. Twitter API 限流"
    echo ""
    echo "📝 如需恢复备份:"
    echo "   cp cache_backup/*.json cache/"
fi
