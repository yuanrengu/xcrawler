from __future__ import annotations

import re
import time
from collections.abc import Callable

from xcrawler.utils.text import detect_language


ClientFactory = Callable[[], object]


def _record_usage(metrics: dict[str, int] | None, response: object) -> None:
    if metrics is None:
        return
    metrics["llm_calls"] = metrics.get("llm_calls", 0) + 1
    usage = getattr(response, "usage", None)
    total_tokens = getattr(usage, "total_tokens", None)
    if isinstance(total_tokens, int):
        metrics["total_tokens"] = metrics.get("total_tokens", 0) + total_tokens


def parse_batch_response(response: str, expected_count: int) -> list[str]:
    lines = response.strip().split("\n")
    results = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^\[?\d+\]?\s*[\.\):：]?\s*(.+)", line)
        if match:
            results.append(match.group(1).strip())

    if len(results) != expected_count:
        results = [line.strip() for line in lines if line.strip()]

    return results


def translate_text(
    text: str,
    *,
    detected_lang: str | None,
    use_cache: bool,
    cache: dict[str, str],
    client_factory: ClientFactory,
    model: str,
    max_retries: int,
    metrics: dict[str, int] | None = None,
) -> str | None:
    if use_cache and text in cache:
        return cache[text]

    if not detected_lang:
        detected_lang = detect_language(text)

    if detected_lang in ("zh-cn", "zh"):
        if use_cache:
            cache[text] = text
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
            if use_cache:
                cache[text] = result
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
    cache: dict[str, str],
    client_factory: ClientFactory,
    model: str,
    batch_size: int,
    max_retries: int,
    fallback_translate: Callable[[str, str | None, bool], str | None],
    metrics: dict[str, int] | None = None,
) -> list[str | None]:
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")

    n = len(texts)
    langs = [None] * n if detected_langs is None else list(detected_langs)
    results: list[str | None] = [None] * n

    to_translate_indices = []
    to_translate_texts = []
    to_translate_langs = []

    for i, text in enumerate(texts):
        lang = langs[i]

        if use_cache and text in cache:
            results[i] = cache[text]
            continue

        if not lang:
            lang = detect_language(text)
            langs[i] = lang

        if lang in ("zh-cn", "zh"):
            if use_cache:
                cache[text] = text
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

                for j, idx in enumerate(batch_indices):
                    if j < len(parsed) and parsed[j]:
                        results[idx] = parsed[j]
                        if use_cache:
                            cache[texts[idx]] = parsed[j]
                        translated_count += 1
                print(f" ✅ 已翻译 {translated_count}/{len(to_translate_texts)} 条")
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"⚠️ 批量翻译失败，重试 {attempt + 1}/{max_retries}... {str(e)}")
                    time.sleep(2 ** attempt)
                else:
                    print("❌ 批量翻译失败，回退到单条翻译...")
                    if metrics is not None:
                        metrics["failed_batches"] = metrics.get("failed_batches", 0) + 1
                    for idx in batch_indices:
                        results[idx] = fallback_translate(texts[idx], langs[idx], use_cache)

    return results
