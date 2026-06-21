from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime

from dotenv import load_dotenv


load_dotenv()


@dataclass
class AppConfig:
    target_username: str = "MiracleHe"
    cache_dir: str = "cache"
    x_bearer_token: str | None = None
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"
    target_date: datetime = datetime(2024, 1, 1)
    timezone_offset: float = 8.0


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
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        llm_model=os.getenv("LLM_MODEL", "deepseek-chat"),
        target_date=target_date,
        timezone_offset=float(os.getenv("TIMEZONE_OFFSET", "8")),
    )


def apply_common_overrides(config: AppConfig, args) -> AppConfig:
    if getattr(args, "user", None):
        config.target_username = args.user
    if getattr(args, "cache_dir", None):
        config.cache_dir = args.cache_dir
    if getattr(args, "model", None):
        config.llm_model = args.model
    return config
