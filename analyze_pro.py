from __future__ import annotations

import argparse
import json

# analyze_pro.py
import os
import re
from typing import Any

from xcrawler.config import load_config
from xcrawler.llm.provider import DeepSeekProvider, OpenAICompatibleProvider
from xcrawler.services.analysis_runs import (
    complete_analysis_run,
    create_analysis_run,
    fail_analysis_run,
    record_analysis_run,
)
from xcrawler.services.evidence import validate_interest_evidence
from xcrawler.services.llm_calls import LLMCallRecorder, ObservedLLMProvider
from xcrawler.services.records import normalize_translated_tweets
from xcrawler.services.sampling import sample_evenly
from xcrawler.storage.json_store import JsonStore, load_json, save_json
from xcrawler.utils import cli_validation

# =========================
# 初始化
# =========================

_config = load_config()

API_KEY = _config.deepseek_api_key or _config.openai_api_key
BASE_URL = _config.deepseek_base_url if _config.deepseek_api_key else _config.openai_base_url
PROVIDER_NAME = "deepseek" if _config.deepseek_api_key else "openai"
MODEL = _config.llm_model
TARGET_USERNAME = _config.target_username

provider: OpenAICompatibleProvider | None = None


def _get_provider() -> OpenAICompatibleProvider:
    global provider
    if not API_KEY:
        raise RuntimeError("未检测到 API Key，请设置 DEEPSEEK_API_KEY 或 OPENAI_API_KEY")
    if provider is None:
        if PROVIDER_NAME == "deepseek":
            provider = DeepSeekProvider(api_key=API_KEY, base_url=BASE_URL)
        else:
            provider = OpenAICompatibleProvider(
                api_key=API_KEY,
                base_url=BASE_URL,
                name=PROVIDER_NAME,
            )
    return provider


def _ensure_interest_evidence_fields(result: dict[str, Any]) -> dict[str, Any]:
    if isinstance(result, dict):
        for interest in result.get("interests", []):
            if isinstance(interest, dict):
                interest.setdefault("evidence_tweet_ids", [])
    return result

# =========================
# 核心 Prompt（专业版）
# =========================

PROMPT_TEMPLATE = """
你是一名专业的“用户兴趣画像分析专家”，
擅长在样本数量有限、语言存在翻译噪声、内容结构不完整的情况下，
从用户的日常社交媒体文本中提炼稳定、可复现的长期兴趣画像。

========================
【分析目标】
========================
请基于用户发布的社交媒体文本，分析该用户的“长期兴趣爱好与内容偏好”，
而不是短期情绪、偶发事件、单次吐槽或转发行为。

========================
【重要背景说明】
========================
1. 文本原始语言可能多种多样，已翻译为中文
   - 可能存在用词不统一、表达生硬的问题
   - 请基于“语义一致性”而非字面词频进行判断
2. 样本数量有限（通常 20–300 条）
3. 文本中可能混杂日常记录、情绪表达、转发内容

========================
【严格分析原则（必须遵守）】
========================
1. 只提取“多次出现、有明确主题指向”的兴趣信号
2. 禁止根据单条文本或偶发内容推断兴趣
3. 忽略纯情绪宣泄、寒暄、无个人立场的新闻转发
4. 若证据不足，请降低置信度
5. 不进行人格、心理、价值观推断
6. evidence_tweet_ids 只能使用输入文本中出现过的 tweet_id，不能编造，不能输出 unknown

========================
【分析步骤（请严格执行）】
========================
Step 1：提取可归类的兴趣信号（主题 / 活动 / 内容领域）
Step 2：合并语义相近信号，形成候选兴趣
Step 3：区分核心兴趣（core）与边缘兴趣（peripheral）
Step 4：评估每个兴趣的置信度（0~1）
Step 5：提炼支持关键词或典型表达

========================
【输出要求】
========================
- 只输出 JSON
- 不输出解释性文字
- JSON 结构要求：
  {{
    "interests": [
      {{
        "tag": "兴趣标签",
        "level": "core/peripheral",
        "confidence": 0.8,
        "keywords": ["kw1", "kw2"],
        "evidence_count": 5,
        "evidence_tweet_ids": ["tweet_id_1", "tweet_id_2"]
      }}
    ]
  }}

- 兴趣数量建议 3–7 个
- 不要输出重复或高度相似标签

========================
【用户文本】
========================
{user_text}
""".strip()


# =========================
# 对外主函数
# =========================

def analyze_user_interest(
    texts: list[str],
    temperature: float = 0.2,
    llm=None,
) -> dict[str, Any]:
    """
    分析用户兴趣画像（少数据优化版）

    :param texts: 已翻译成中文的推文列表
    :param temperature: 模型温度，建议 0.1 ~ 0.3
    :return: (结构化兴趣画像 dict, total_tokens: int | None)
    """

    if not texts or len(texts) < 5:
        raise ValueError("文本数量过少，至少需要 5 条以上才能进行兴趣分析")

    joined_text = "\n".join(f"- {t}" for t in texts)
    prompt = PROMPT_TEMPLATE.format(user_text=joined_text)

    response = (llm or _get_provider()).chat(
        [
            {"role": "system", "content": "你是一个严谨、克制、以证据为导向的分析助手。请务必输出合法的 JSON 格式。"},
            {"role": "user", "content": prompt}
        ],
        model=MODEL,
        temperature=temperature
    )

    content = response.content

    result = None

    # 尝试直接解析
    try:
        result = _ensure_interest_evidence_fields(json.loads(content))
    except json.JSONDecodeError:
        pass

    # 从 markdown 代码块提取
    if result is None:
        match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if match:
            try:
                result = _ensure_interest_evidence_fields(json.loads(match.group(1)))
            except json.JSONDecodeError:
                pass

    if result is None:
        raise RuntimeError(f"模型返回的不是合法 JSON：\n{content}")

    return result, response.total_tokens


# =========================
# 数据加载与分析
# =========================

def load_translated_tweets(cache_dir: str = "cache", username: str = None) -> list[str]:
    """
    加载已翻译的推文数据
    
    :param cache_dir: 缓存目录
    :param username: 用户名
    :return: 翻译后的文本列表
    """
    if username is None:
        username = TARGET_USERNAME
        
    translated_file = os.path.join(cache_dir, f"{username}_translated.json")
    
    if not os.path.exists(translated_file):
        raise FileNotFoundError(
            f"未找到翻译文件: {translated_file}\n"
            f"请先运行 main.py 抓取并翻译数据"
        )
    
    data = load_json(translated_file, default=[])
    
    # 提取翻译后的文本，兼容旧格式 translated.json（缺少 tweet_id 时补 None）。
    # 保留 tweet_id 前缀，便于模型输出 evidence_tweet_ids。
    texts = [
        f"[tweet_id={item.get('tweet_id') or 'unknown'}] {item['translated']}"
        for item in normalize_translated_tweets(data)
        if item.get("translated")
    ]
    
    return texts


def load_translated_records(cache_dir: str = "cache", username: str = None) -> list[dict[str, Any]]:
    """加载标准化后的翻译记录，用于 evidence 校验。"""
    if username is None:
        username = TARGET_USERNAME

    translated_file = os.path.join(cache_dir, f"{username}_translated.json")

    if not os.path.exists(translated_file):
        raise FileNotFoundError(
            f"未找到翻译文件: {translated_file}\n"
            f"请先运行 main.py 抓取并翻译数据"
        )

    return normalize_translated_tweets(load_json(translated_file, default=[]))


def save_analysis_result(result: dict[str, Any], cache_dir: str = "cache", username: str = None):
    """
    保存分析结果
    
    :param result: 分析结果
    :param cache_dir: 缓存目录
    :param username: 用户名，如果为 None 则使用环境变量 TARGET_USERNAME
    """
    if username is None:
        username = TARGET_USERNAME
    
    output_file = os.path.join(cache_dir, f"{username}_interest_profile.json")
    
    save_json(output_file, result)
    
    print(f"\n✅ 分析结果已保存: {output_file}")


# =========================
# 主函数
# =========================

def parse_args():
    parser = argparse.ArgumentParser(description="AI 驱动的专业兴趣画像分析")
    parser.add_argument("-u", "--user", help="目标用户名")
    parser.add_argument("--model", help=f"LLM 模型名（默认 {MODEL}）")
    parser.add_argument("--temperature", type=cli_validation.temperature, default=0.2, help="模型温度（默认 0.2，范围 0-2）")
    parser.add_argument("--limit", type=cli_validation.positive_int, default=300, help="最多分析的翻译文本数（默认 300）")
    parser.add_argument("--cache-dir", help="缓存目录")
    return parser.parse_args()

def main():
    global TARGET_USERNAME, MODEL

    args = parse_args()
    if args.user:
        TARGET_USERNAME = args.user
    if args.model:
        MODEL = args.model
    cache_dir = args.cache_dir or "cache"

    print("=" * 60)
    print("🎯 用户兴趣画像分析（专业版）")
    print("=" * 60)
    print(f"📌 目标用户: {TARGET_USERNAME}")
    print()
    run = None
    store = JsonStore(cache_dir)
    
    try:
        # 1. 加载数据
        print("📂 加载翻译数据...")
        translated_records = load_translated_records(cache_dir, TARGET_USERNAME)
        all_texts = [
            f"[tweet_id={item.get('tweet_id') or 'unknown'}] {item['translated']}"
            for item in translated_records
            if item.get("translated")
        ]
        texts = sample_evenly(all_texts, args.limit)
        print(f"✅ 已加载 {len(all_texts)} 条翻译文本")
        if len(all_texts) > len(texts):
            print(f"⚠️ 长输入保护：按时间跨度均匀抽样分析 {len(texts)} 条文本，可通过 --limit 调整")
        print()
        
        # 2. 执行分析
        print("🔍 开始分析用户兴趣画像...")
        print("⚙️  使用模型:", MODEL)
        print("📋 执行计划:")
        print(f"   输入文本: {len(texts)} / {len(all_texts)} 条")
        print("   LLM 调用: 1 次兴趣画像分析")
        print(f"   长输入保护: 最多 {args.limit} 条文本")
        print()
        run = create_analysis_run(
            username=TARGET_USERNAME,
            analysis_type="interest",
            model=MODEL,
            params={"temperature": args.temperature, "limit": args.limit},
            input_range={
                "translated_records": len(translated_records),
                "available_texts": len(all_texts),
                "analyzed_texts": len(texts),
                "strategy": "single_prompt_even_sampling",
            },
            config={"provider": PROVIDER_NAME},
        )
        call_recorder = LLMCallRecorder(
            store,
            pricing=_config.llm_pricing,
            analysis_run_id=run.id,
            username=TARGET_USERNAME,
        )
        observed_provider = ObservedLLMProvider(
            _get_provider(),
            call_recorder,
            operation="interest_analysis",
        )
        
        result, total_tokens = analyze_user_interest(
            texts,
            temperature=args.temperature,
            llm=observed_provider,
        )
        result = validate_interest_evidence(result, translated_records, require_evidence=True)
        result["analysis_run_id"] = run.id
        run.llm_calls = 1
        run.total_tokens = total_tokens
        record_analysis_run(store, complete_analysis_run(run))
        call_summary = call_recorder.summary()
        print(
            f"📈 LLM 调用: {call_summary['successful_calls']} 成功 / "
            f"{call_summary['failed_calls']} 失败，Token {call_summary['total_tokens']}"
        )
        if call_summary["estimated_cost"]:
            print(f"   预估成本 (USD): {call_summary['estimated_cost']:.6f}")
        
        # 3. 显示结果
        print("=" * 60)
        print("📊 分析结果")
        print("=" * 60)
        print()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print()
        
        # 4. 保存结果
        save_analysis_result(result, cache_dir, TARGET_USERNAME)
        
        # 5. 统计信息
        if isinstance(result, dict) and "interests" in result:
            interests = result["interests"]
            core_count = sum(1 for i in interests if i.get("level") == "core")
            peripheral_count = len(interests) - core_count
            
            print()
            print("📈 统计信息:")
            print(f"   总兴趣数: {len(interests)}")
            print(f"   核心兴趣: {core_count}")
            print(f"   边缘兴趣: {peripheral_count}")
        
        print()
        print("=" * 60)
        print("✅ 分析完成！")
        print("=" * 60)
        return 0
        
    except FileNotFoundError as e:
        if run:
            record_analysis_run(store, fail_analysis_run(run, e))
        print(f"❌ 错误: {e}")
        print()
        print("💡 请先运行以下命令抓取数据:")
        print("   python3 main.py")
        return 1
        
    except ValueError as e:
        if run:
            record_analysis_run(store, fail_analysis_run(run, e))
        print(f"❌ 错误: {e}")
        return 1
        
    except RuntimeError as e:
        if run:
            record_analysis_run(store, fail_analysis_run(run, e))
        print(f"❌ 运行时错误: {e}")
        return 1
        
    except Exception as e:
        if run:
            record_analysis_run(store, fail_analysis_run(run, e))
        import traceback
        traceback.print_exc()
        print(f"❌ 未知错误: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
