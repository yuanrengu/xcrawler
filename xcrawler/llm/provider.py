from __future__ import annotations

from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any, Protocol, cast

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

from xcrawler.utils.text import require_model_text


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LLMProvider(Protocol):
    name: str

    def chat(self, messages: list[dict[str, str]], *, model: str, temperature: float = 0.0) -> LLMResponse:
        ...


class OpenAICompatibleProvider:
    def __init__(self, *, api_key: str | None, base_url: str, name: str = "openai-compatible"):
        self.name = name
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def chat(self, messages: list[dict[str, str]], *, model: str, temperature: float = 0.0) -> LLMResponse:
        started = perf_counter()
        response = self.client.chat.completions.create(
            model=model,
            messages=cast(list[ChatCompletionMessageParam], messages),
            temperature=temperature,
        )
        latency_ms = int((perf_counter() - started) * 1000)
        usage = getattr(response, "usage", None)
        raw = require_model_text(response.choices[0].message.content)
        return LLMResponse(
            content=raw,
            model=model,
            provider=self.name,
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
            total_tokens=getattr(usage, "total_tokens", None),
            latency_ms=latency_ms,
        )


class DeepSeekProvider(OpenAICompatibleProvider):
    def __init__(self, *, api_key: str | None, base_url: str = "https://api.deepseek.com"):
        super().__init__(api_key=api_key, base_url=base_url, name="deepseek")
