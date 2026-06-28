from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar


T = TypeVar("T")


def sample_evenly(items: Sequence[T], limit: int) -> list[T]:
    """Return up to limit items spread across the original ordering."""
    if limit < 1:
        raise ValueError("limit must be >= 1")

    n = len(items)
    if n <= limit:
        return list(items)
    if limit == 1:
        return [items[0]]

    indices = [round(i * (n - 1) / (limit - 1)) for i in range(limit)]
    return [items[i] for i in indices]
