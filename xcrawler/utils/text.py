from __future__ import annotations

import re
from typing import TypeGuard, cast


def clean_text(text: str) -> str:
    text = re.sub(r"http\S+", "", text)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def detect_language(text: str) -> str:
    try:
        from langdetect import detect

        clean = re.sub(r"http\S+|@\w+|#\w+", "", text).strip()
        if len(clean) < 3:
            return "unknown"
        return cast(str, detect(clean))
    except ImportError:
        return "unknown"
    except Exception:
        return "unknown"


def usable_translation(value: object) -> TypeGuard[str]:
    """Reject blank text and bare batch labels, including legacy cached output."""
    return isinstance(value, str) and bool(value.strip()) and not all(
        re.fullmatch(r"(?:\[\d+\]|\d+[.\):：])\s*[.\):：]?", line.strip())
        for line in value.splitlines() if line.strip()
    )


def require_model_text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("模型响应必须包含非空文本")
    return value.strip()
