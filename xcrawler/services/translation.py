from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import Any

from xcrawler.services.translation_cache import (
    TranslationCacheContext,
    ensure_translation_cache,
    get_cached_translation,
    set_cached_translation,
)
from xcrawler.utils.text import detect_language

ClientFactory = Callable[[], object]
TranslationMetrics = dict[str, int | str]


def _increment_metric(metrics: TranslationMetrics | None, key: str, amount: int = 1) -> None:
    if metrics is None:
        return
    current = metrics.get(key, 0)
    metrics[key] = (current if isinstance(current, int) else 0) + amount


def _record_usage(metrics: TranslationMetrics | None, response: object) -> None:
    if metrics is None:
        return
    _increment_metric(metrics, "llm_calls")
    usage = getattr(response, "usage", None)
    total_tokens = getattr(usage, "total_tokens", None)
    if isinstance(total_tokens, int):
        _increment_metric(metrics, "total_tokens", total_tokens)


def _cache_context(cache_context: TranslationCacheContext | None, model: str) -> TranslationCacheContext:
    return cache_context or TranslationCacheContext(provider="unknown", model=model)


def _record_cache_lookup(
    metrics: TranslationMetrics | None,
    context: TranslationCacheContext,
    *,
    enabled: bool,
    hit: bool = False,
) -> None:
    if metrics is None:
        return
    metrics["cache_fingerprint"] = context.fingerprint
    if not enabled:
        _increment_metric(metrics, "cache_bypassed")
    elif hit:
        _increment_metric(metrics, "cache_hits")
    else:
        _increment_metric(metrics, "cache_misses")


def parse_batch_response(response: str, expected_count: int) -> list[str]:
    lines = [line.strip() for line in response.strip().split("\n") if line.strip()]
    if not lines:
        return []

    numbered: dict[int, str] = {}
    saw_numbered_line = False
    unnumbered_lines = 0
    for line in lines:
        match = re.match(r"^(?:\[(\d+)\]|(\d+)[\.\):：])\s*[\.\):：]?\s*(.+)", line)
        if match:
            saw_numbered_line = True
            idx = int(match.group(1) or match.group(2))
            text = match.group(3).strip()
            if idx < 1 or idx > expected_count or idx in numbered or not text:
                return []
            numbered[idx] = text
        else:
            unnumbered_lines += 1

    if saw_numbered_line:
        if unnumbered_lines:
            return []
        if set(numbered) != set(range(1, expected_count + 1)):
            return []
        return [numbered[i] for i in range(1, expected_count + 1)]

    if len(lines) == expected_count:
        return lines
    return []


def translate_text(
    text: str,
    *,
    detected_lang: str | None,
    use_cache: bool,
    cache: dict[str, Any],
    client_factory: ClientFactory,
    model: str,
    max_retries: int,
    metrics: TranslationMetrics | None = None,
    cache_context: TranslationCacheContext | None = None,
    cache_results: bool | None = None,
) -> str | None:
    context = _cache_context(cache_context, model)
    ensure_translation_cache(cache)
    should_cache_results = use_cache if cache_results is None else cache_results

    if use_cache:
        cached = get_cached_translation(cache, text, context)
        if cached is not None:
            _record_cache_lookup(metrics, context, enabled=True, hit=True)
            return cached
        _record_cache_lookup(metrics, context, enabled=True)
    else:
        _record_cache_lookup(metrics, context, enabled=False)

    if not detected_lang:
        detected_lang = detect_language(text)

    if detected_lang in ("zh-cn", "zh"):
        if should_cache_results:
            set_cached_translation(cache, text, text, context)
        return text

    prompt = f"""
你是一名精通多国语言的翻译专家，特别擅长将社交媒体内容（推特/X）翻译成地道、自然的中文。

【任务】
请将以下[{detected_lang}]推文翻译成简体中文。

【要求】
1. **地道表达**：不要直译，使用符合中文母语者习惯的表达方式。
2. **语境理解**：准确理解推特特有的非正式语境、语气和情感（如吐槽、兴奋、反讽）。
3. **术语处理**：保留专有名词（人名、地名、作品名）、技术术语或特定的原文标签（如 #Hashtag）。
4. **网络用语**：如果原文包含网络梗、流行语或缩写（如 lol, omg, wwww），请翻译成对应的中文网络用语或流行梗。
5. **格式保持**：不要随意解释或扩写，只输出翻译后的文本。

【原文】
{text}
""".strip()

    for attempt in range(max_retries):
        try:
            response = client_factory().chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            _record_usage(metrics, response)
            result = response.choices[0].message.content.strip()
            if should_cache_results:
                set_cached_translation(cache, text, result, context)
            return result
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"⚠️ 翻译失败，重试 {attempt + 1}/{max_retries}... 错误: {str(e)}")
                time.sleep(2 ** attempt)
            else:
                print(f"❌ 翻译失败，跳过该条推文: {str(e)}")
                return None

    return None


def translate_batch(
    texts: list[str],
    *,
    detected_langs: list[str | None] | None,
    use_cache: bool,
    cache: dict[str, Any],
    client_factory: ClientFactory,
    model: str,
    batch_size: int,
    max_retries: int,
    fallback_translate: Callable[[str, str | None, bool], str | None],
    metrics: TranslationMetrics | None = None,
    cache_context: TranslationCacheContext | None = None,
    cache_results: bool | None = None,
) -> list[str | None]:
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")

    context = _cache_context(cache_context, model)
    ensure_translation_cache(cache)
    should_cache_results = use_cache if cache_results is None else cache_results

    n = len(texts)
    langs = [None] * n if detected_langs is None else list(detected_langs)
    results: list[str | None] = [None] * n

    to_translate_indices = []
    to_translate_texts = []
    to_translate_langs = []

    for i, text in enumerate(texts):
        lang = langs[i]

        if use_cache:
            cached = get_cached_translation(cache, text, context)
            if cached is not None:
                _record_cache_lookup(metrics, context, enabled=True, hit=True)
                results[i] = cached
                continue
            _record_cache_lookup(metrics, context, enabled=True)
        else:
            _record_cache_lookup(metrics, context, enabled=False)

        if not lang:
            lang = detect_language(text)
            langs[i] = lang

        if lang in ("zh-cn", "zh"):
            if should_cache_results:
                set_cached_translation(cache, text, text, context)
            results[i] = text
            continue

        to_translate_indices.append(i)
        to_translate_texts.append(text)
        to_translate_langs.append(lang)

    if not to_translate_texts:
        return results

    total_batches = (len(to_translate_texts) + batch_size - 1) // batch_size
    translated_count = 0

    for batch_idx, batch_start in enumerate(range(0, len(to_translate_texts), batch_size)):
        batch_end = batch_start + batch_size
        batch_indices = to_translate_indices[batch_start:batch_end]
        batch_texts = to_translate_texts[batch_start:batch_end]
        batch_langs = to_translate_langs[batch_start:batch_end]
        current_batch_size = len(batch_texts)

        print(f"   📦 批次 [{batch_idx + 1}/{total_batches}] 翻译 {current_batch_size} 条...", end="", flush=True)

        numbered_lines = "\n".join(f"[{j + 1}] {t}" for j, t in enumerate(batch_texts))
        lang_hint = ", ".join(set(batch_langs))

        prompt = f"""你是一名精通多国语言的翻译专家，擅长将社交媒体内容翻译成地道中文。

【任务】
将以下 {current_batch_size} 条推文依次翻译成简体中文。原文语言可能包含 {lang_hint} 等。

【要求】
1. 地道表达，不要直译
2. 保留专有名词和 #Hashtag
3. 网络用语翻译成对应中文网络用语
4. 只输出翻译，不要解释

【输出格式】
每行一条翻译，格式为 [编号] 翻译内容，必须与原文编号一一对应。

【原文】
{numbered_lines}""".strip()

        for attempt in range(max_retries):
            try:
                response = client_factory().chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                )
                _record_usage(metrics, response)
                response_text = response.choices[0].message.content.strip()
                parsed = parse_batch_response(response_text, current_batch_size)
                if len(parsed) != current_batch_size:
                    raise ValueError(
                        f"批量翻译响应数量不匹配，期望 {current_batch_size} 条，实际解析 {len(parsed)} 条"
                    )

                for j, idx in enumerate(batch_indices):
                    results[idx] = parsed[j]
                    if should_cache_results:
                        set_cached_translation(cache, texts[idx], parsed[j], context)
                    translated_count += 1
                print(f" ✅ 已翻译 {translated_count}/{len(to_translate_texts)} 条")
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"⚠️ 批量翻译失败，重试 {attempt + 1}/{max_retries}... {str(e)}")
                    time.sleep(2 ** attempt)
                else:
                    print("❌ 批量翻译失败，回退到单条翻译...")
                    _increment_metric(metrics, "failed_batches")
                    for idx in batch_indices:
                        results[idx] = fallback_translate(texts[idx], langs[idx], use_cache)

    return results
