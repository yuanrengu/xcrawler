from __future__ import annotations

import re


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
        return detect(clean)
    except ImportError:
        return "unknown"
    except Exception:
        return "unknown"
