"""Async fixed-window request limiter."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from time import monotonic


class AsyncRateLimiter:
    """Limit calls over a rolling 60-second window."""

    def __init__(
        self,
        requests_per_minute: int,
        *,
        clock: Callable[[], float] = monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if requests_per_minute < 1:
            raise ValueError("requests_per_minute must be positive")
        self.requests_per_minute = requests_per_minute
        self._clock = clock
        self._sleep = sleep
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = self._clock()
                while self._timestamps and now - self._timestamps[0] >= 60.0:
                    self._timestamps.popleft()
                if len(self._timestamps) < self.requests_per_minute:
                    self._timestamps.append(now)
                    return
                wait_seconds = max(0.001, 60.0 - (now - self._timestamps[0]))
            await self._sleep(wait_seconds)
