from __future__ import annotations

from openai import OpenAI


def create_openai_client(api_key: str | None, base_url: str) -> OpenAI:
    return OpenAI(api_key=api_key, base_url=base_url)
