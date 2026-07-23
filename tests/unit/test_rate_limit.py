"""Unit tests for the token-bucket rate limiter (fake clock, no real waiting)."""

from __future__ import annotations

import pytest

from archiver.clients.rate_limit import NullRateLimiter, TokenBucket


class FakeClock:
    """Manually advanced monotonic clock; records sleeps and advances on sleep."""

    def __init__(self) -> None:
        self.t = 0.0
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.t

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds  # sleeping advances time so the bucket refills


async def test_bucket_allows_up_to_capacity_immediately():
    clock = FakeClock()
    bucket = TokenBucket(rate=5.0, capacity=3.0, clock=clock.now, sleep=clock.sleep)
    for _ in range(3):
        await bucket.acquire()
    assert clock.sleeps == []  # first `capacity` tokens are free


async def test_bucket_waits_when_empty():
    clock = FakeClock()
    bucket = TokenBucket(rate=2.0, capacity=1.0, clock=clock.now, sleep=clock.sleep)
    await bucket.acquire()  # consumes the one token, no wait
    await bucket.acquire()  # must wait ~1/rate = 0.5s for a refill
    assert clock.sleeps
    assert clock.sleeps[0] == pytest.approx(0.5, rel=1e-6)


async def test_bucket_rejects_request_larger_than_capacity():
    bucket = TokenBucket(rate=1.0, capacity=1.0)
    with pytest.raises(ValueError):
        await bucket.acquire(2.0)


def test_bucket_rejects_nonpositive_rate():
    with pytest.raises(ValueError):
        TokenBucket(rate=0.0)


async def test_null_rate_limiter_never_waits():
    limiter = NullRateLimiter()
    await limiter.acquire()
    await limiter.acquire(1000.0)
