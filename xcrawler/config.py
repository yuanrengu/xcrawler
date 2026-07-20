from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from dotenv import load_dotenv

from xcrawler.utils.cli_validation import validate_x_username

load_dotenv()

DEFAULT_TIMEZONE_OFFSET = 8.0
STORAGE_BACKENDS = ("json", "sqlite")


class ConfigError(ValueError):
    """配置值无效且无法安全推断用户意图。"""


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
    llm_pricing: dict[str, dict[str, float]] | None = None
    storage_backend: str = "json"
    sqlite_path: str | None = None


def parse_llm_pricing(value: str | None) -> dict[str, dict[str, float]]:
    """Parse an optional per-model LLM price table without shipping stale prices."""
    if not value:
        return {}
    try:
        raw: Any = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if not isinstance(raw, dict):
        return {}

    pricing: dict[str, dict[str, float]] = {}
    for model, rates in raw.items():
        if not isinstance(model, str) or not isinstance(rates, dict):
            continue
        try:
            input_rate = float(rates["input_per_million"])
            output_rate = float(rates["output_per_million"])
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(input_rate) or not math.isfinite(output_rate) or input_rate < 0 or output_rate < 0:
            continue
        pricing[model] = {
            "input_per_million": input_rate,
            "output_per_million": output_rate,
        }
    return pricing


def load_config() -> AppConfig:
    target_date_raw = os.getenv("TARGET_DATE", "2024-01-01")
    try:
        target_date = datetime.strptime(target_date_raw, "%Y-%m-%d")
    except ValueError as error:
        raise ConfigError(f"TARGET_DATE 必须为 YYYY-MM-DD，当前值: {target_date_raw!r}") from error

    timezone_raw = os.getenv("TIMEZONE_OFFSET", str(int(DEFAULT_TIMEZONE_OFFSET)))
    try:
        timezone_offset = float(timezone_raw)
    except ValueError as error:
        raise ConfigError(f"TIMEZONE_OFFSET 必须是数字，当前值: {timezone_raw!r}") from error
    if not math.isfinite(timezone_offset) or not -24 <= timezone_offset <= 24:
        raise ConfigError("TIMEZONE_OFFSET 必须是 -24 到 24 之间的有限数字")

    username_raw = os.getenv("TARGET_USERNAME", "MiracleHe")
    try:
        target_username = validate_x_username(username_raw)
    except ValueError as error:
        raise ConfigError(f"TARGET_USERNAME 无效: {error}") from error

    storage_backend = os.getenv("STORAGE_BACKEND", "json").strip().lower()
    if storage_backend not in STORAGE_BACKENDS:
        raise ConfigError(f"STORAGE_BACKEND 必须是: {', '.join(STORAGE_BACKENDS)}")

    return AppConfig(
        target_username=target_username,
        cache_dir=os.getenv("CACHE_DIR", "cache"),
        x_bearer_token=os.getenv("X_BEARER_TOKEN"),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com"),
        llm_model=os.getenv("LLM_MODEL", "deepseek-chat"),
        target_date=target_date,
        timezone_offset=timezone_offset,
        llm_pricing=parse_llm_pricing(os.getenv("LLM_PRICING_JSON")),
        storage_backend=storage_backend,
        sqlite_path=os.getenv("SQLITE_PATH") or None,
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
    assert value is not None
    return value.strip()
