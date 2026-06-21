from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Storage(ABC):
    """Minimal storage contract for cache-backed workflows."""

    @abstractmethod
    def load_json(self, key: str, default: Any = None) -> Any:
        """Load JSON-compatible data by storage key."""

    @abstractmethod
    def save_json(self, key: str, data: Any) -> None:
        """Save JSON-compatible data by storage key."""

    @abstractmethod
    def append_json_record(self, key: str, record: dict[str, Any]) -> None:
        """Append a dict record to a JSON list."""
