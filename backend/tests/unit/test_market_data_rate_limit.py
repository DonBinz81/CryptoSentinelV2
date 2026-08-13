import pytest

from backend.app.data.market_data.rate_limit import AsyncRateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_queues_requests_over_threshold() -> None:
    now = 0.0
    sleeps: list[float] = []

    def clock() -> float:
        return now

    async def sleep(seconds: float) -> None:
        nonlocal now
        sleeps.append(seconds)
        now += seconds

    limiter = AsyncRateLimiter(1, clock=clock, sleep=sleep)
    await limiter.acquire()
    await limiter.acquire()

    assert sleeps == [60.0]
