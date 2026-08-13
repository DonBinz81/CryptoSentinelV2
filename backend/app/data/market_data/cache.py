"""Small in-memory TTL cache used to avoid duplicate provider credits."""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Any, Callable


@dataclass(slots=True)
class _Entry:
    value: Any
    expires_at: float


class TTLCache:
    """Process-local cache with deterministic clock injection for tests."""

    def __init__(self, ttl_seconds: float, clock: Callable[[], float] = monotonic) -> None:
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: dict[str, _Entry] = {}

    def get(self, key: str) -> Any | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= self._clock():
            self._entries.pop(key, None)
            return None
        return entry.value

    def set(self, key: str, value: Any, ttl_seconds: float | None = None) -> None:
        ttl = self.ttl_seconds if ttl_seconds is None else ttl_seconds
        self._entries[key] = _Entry(value=value, expires_at=self._clock() + ttl)

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        now = self._clock()
        expired = [key for key, entry in self._entries.items() if entry.expires_at <= now]
        for key in expired:
            self._entries.pop(key, None)
        return len(self._entries)
