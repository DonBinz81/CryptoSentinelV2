import asyncio

import httpx
import pytest

from backend.app.data.market_data.http import CachedHttpProvider


@pytest.mark.asyncio
async def test_concurrent_identical_requests_share_one_provider_call() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return httpx.Response(200, json={"data": [{"id": 1}]})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://provider.test",
    ) as client:
        provider = CachedHttpProvider(
            base_url="https://provider.test",
            timeout_seconds=1,
            requests_per_minute=30,
            cache_ttl_seconds=60,
            client=client,
        )
        requests = [
            provider._request_json("/items", params={"start": 1, "limit": 200})
            for _ in range(10)
        ]
        results = await asyncio.gather(*requests)

    assert calls == 1
    assert provider.requests_made == 1
    assert all(result == {"data": [{"id": 1}]} for result in results)
