"""Client-side rate limiting (DESIGN.md §7.2).

A conservative token bucket paces outbound requests below any server limit; the
client additionally honors authoritative server signals (``Retry-After``) on 429.
Politeness is a design invariant, so the default rate is low.

Both the clock and the sleep coroutine are injectable, which keeps the token math
unit-testable without real waiting.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Protocol


class RateLimiter(Protocol):
    async def acquire(self, tokens: float = 1.0) -> None: ...


class TokenBucket:
    """Classic token bucket: refills at ``rate`` tokens/sec up to ``capacity``."""

    def __init__(
        self,
        rate: float,
        capacity: float | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if rate <= 0:
            raise ValueError("rate must be > 0")
        self.rate = rate
        self.capacity = capacity if capacity is not None else max(1.0, rate)
        self._tokens = self.capacity
        self._clock = clock
        self._sleep = sleep
        self._updated = clock()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = now - self._updated
        if elapsed > 0:
            self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
            self._updated = now

    async def acquire(self, tokens: float = 1.0) -> None:
        if tokens > self.capacity:
            raise ValueError("requested tokens exceed bucket capacity")
        async with self._lock:
            while True:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
                deficit = tokens - self._tokens
                await self._sleep(deficit / self.rate)


class NullRateLimiter:
    """No-op limiter for tests and unbounded contexts."""

    async def acquire(self, tokens: float = 1.0) -> None:
        return None
