from __future__ import annotations

from openai import OpenAI

from xcrawler.llm.provider import DeepSeekProvider, OpenAICompatibleProvider


def create_openai_client(api_key: str | None, base_url: str) -> OpenAI:
    return OpenAI(api_key=api_key, base_url=base_url)


def create_llm_provider(api_key: str | None, base_url: str, provider: str = "deepseek") -> OpenAICompatibleProvider:
    if provider == "deepseek":
        return DeepSeekProvider(api_key=api_key, base_url=base_url)
    return OpenAICompatibleProvider(api_key=api_key, base_url=base_url, name=provider)
