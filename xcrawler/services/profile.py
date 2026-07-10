from __future__ import annotations

import time

from xcrawler.services.llm_calls import LLMCallRecorder


def deepseek_profile_summary(
    cluster_text: str,
    *,
    client_factory,
    model: str,
    max_retries: int = 3,
    call_recorder: LLMCallRecorder | None = None,
    provider_name: str = "unknown",
    operation: str = "profile_summary",
) -> str:
    """生成用户画像，支持重试。

    :param cluster_text: 聚类后的推文文本
    :param client_factory: 返回 LLM 客户端的无参调用
    :param model: LLM 模型名
    :param max_retries: 最大重试次数
    :return: 画像文本
    """
    prompt = f"""
你是一名数据分析师。

请根据以下推文主题，总结该用户的：
1. 核心兴趣（1-3 个）
2. 次要兴趣
3. 内容风格
4. 情绪倾向

要求：
- 使用简体中文
- 偏客观分析
- 输出结构化结果

推文主题内容：
{cluster_text}
"""

    for attempt in range(max_retries):
        started = call_recorder.start() if call_recorder else None
        response = None
        try:
            response = client_factory().chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            raw = response.choices[0].message.content
            if call_recorder and started:
                call_recorder.record_success(
                    operation=operation,
                    provider=provider_name,
                    model=model,
                    started=started,
                    response=response,
                    attempt=attempt + 1,
                )
            return raw.strip() if raw else ""
        except Exception as e:
            if call_recorder and started:
                call_recorder.record_failure(
                    operation=operation,
                    provider=provider_name,
                    model=model,
                    started=started,
                    error=e,
                    attempt=attempt + 1,
                    response=response,
                )
            if attempt < max_retries - 1:
                print(f"⚠️ 画像生成失败，重试 {attempt + 1}/{max_retries}...")
                time.sleep(2**attempt)
            else:
                print(f"❌ 画像生成失败: {str(e)}")
                raise
