from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime

from dotenv import load_dotenv


load_dotenv()

DEFAULT_TIMEZONE_OFFSET = 8.0


@dataclass
class AppConfig:
    target_username: str = "MiracleHe"
    cache_dir: str = "cache"
    x_bearer_token: str | None = None
    deepseek_api_key: str | None = None
    openai_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    openai_base_url: str = "https://api.openai.com"
    llm_model: str = "deepseek-chat"
    target_date: datetime = datetime(2024, 1, 1)
    timezone_offset: float = DEFAULT_TIMEZONE_OFFSET


def load_config() -> AppConfig:
    target_date_raw = os.getenv("TARGET_DATE", "2024-01-01")
    try:
        target_date = datetime.strptime(target_date_raw, "%Y-%m-%d")
    except ValueError:
        target_date = datetime(2024, 1, 1)

    return AppConfig(
        target_username=os.getenv("TARGET_USERNAME", "MiracleHe"),
        x_bearer_token=os.getenv("X_BEARER_TOKEN"),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com"),
        llm_model=os.getenv("LLM_MODEL", "deepseek-chat"),
        target_date=target_date,
        timezone_offset=float(os.getenv("TIMEZONE_OFFSET", str(int(DEFAULT_TIMEZONE_OFFSET)))),
    )


def is_missing_secret(value: str | None) -> bool:
    if value is None:
        return True
    stripped = value.strip()
    if not stripped:
        return True
    return stripped.startswith("your_") or stripped.endswith("_here")


def require_secret(name: str, value: str | None, *, purpose: str | None = None) -> str:
    if is_missing_secret(value):
        suffix = f"，用于{purpose}" if purpose else ""
        raise RuntimeError(f"未检测到有效的 {name}{suffix}。请复制 .env.example 为 .env 并填写真实值。")
    return value.strip()
