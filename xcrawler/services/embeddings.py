from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from typing import Any

from xcrawler.storage.json_store import load_json, update_json

Encoder = Callable[[list[str]], Any]


def _cache_key(model_name: str, text: str) -> str:
    payload = f"{model_name}\0{text}".encode()
    return hashlib.sha256(payload).hexdigest()


def _to_list_vectors(vectors: Any) -> list[list[float]]:
    if hasattr(vectors, "tolist"):
        vectors = vectors.tolist()
    return [list(vector) for vector in vectors]


def encode_texts_with_cache(
    texts: Sequence[str],
    *,
    model_name: str,
    cache_path: str,
    encoder: Encoder,
) -> list[list[float]]:
    """Encode texts and persist embeddings keyed by model and text hash."""
    cache = load_json(cache_path, default={})
    if not isinstance(cache, dict):
        cache = {}

    items = cache.get("items")
    if not isinstance(items, dict):
        items = {}

    keys = [_cache_key(model_name, text) for text in texts]
    missing_by_key: dict[str, str] = {}
    for key, text in zip(keys, texts):
        if key not in items and key not in missing_by_key:
            missing_by_key[key] = text

    if missing_by_key:
        missing_keys = list(missing_by_key.keys())
        missing_texts = list(missing_by_key.values())
        encoded = _to_list_vectors(encoder(missing_texts))
        if len(encoded) != len(missing_texts):
            raise ValueError("embedding encoder returned an unexpected number of vectors")
        for key, vector in zip(missing_keys, encoded):
            items[key] = vector
        additions = dict(zip(missing_keys, encoded))

        def merge(current: Any) -> dict[str, Any]:
            latest = current.get("items") if isinstance(current, dict) else None
            return {"version": 1, "items": {**(latest if isinstance(latest, dict) else {}), **additions}}

        update_json(cache_path, merge, default={})

    return [items[key] for key in keys]
