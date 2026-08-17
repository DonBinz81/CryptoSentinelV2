"""Global market-cap ranking: resolution, caching and failure behaviour."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.data.market_data.cache import TTLCache
from backend.app.data.market_data.ranking import MarketRankingService


def _asset(symbol: str, rank: int | None, cap: float | None = 1.0):
    return SimpleNamespace(symbol=symbol, market_cap_rank=rank, market_cap=cap)


class _FakeProvider:
    """Returns a canned global ranking and records how it was queried."""

    def __init__(self, assets=None, error: Exception | None = None) -> None:
        self._assets = assets or []
        self._error = error
        self.calls: list[dict] = []

    async def get_market_list(self, currency, limit, asset_ids=None, page=1):
        self.calls.append({"limit": limit, "asset_ids": asset_ids})
        if self._error is not None:
            raise self._error
        return list(self._assets)


def _service(provider) -> MarketRankingService:
    return MarketRankingService(
        SimpleNamespace(),
        cache=TTLCache(3600.0),
        registry=SimpleNamespace(active=provider),
    )


@pytest.mark.asyncio
async def test_returns_global_rank_per_symbol():
    provider = _FakeProvider([_asset("BTC", 1, 1e12), _asset("ETH", 2, 4e11)])
    result = await _service(provider).ranking(["BTC", "ETH"])
    assert result["BTC"]["rank"] == 1
    assert result["ETH"]["rank"] == 2
    assert result["BTC"]["market_cap"] == 1e12


@pytest.mark.asyncio
async def test_the_ranking_is_read_top_down_never_per_symbol():
    """`asset_ids` takes provider ids, not tickers: asking by symbol matched
    unrelated tokens (UNI resolved to a coin ranked #6552)."""

    provider = _FakeProvider([_asset("BTC", 1)])
    await _service(provider).ranking(["BTC", "UNI"])
    assert provider.calls[0]["asset_ids"] is None


@pytest.mark.asyncio
async def test_a_repeated_ticker_resolves_to_the_largest_coin():
    provider = _FakeProvider([_asset("BTC", 1, 1e12), _asset("BTC", 980, 3e6)])
    result = await _service(provider).ranking(["BTC"])
    assert result["BTC"]["rank"] == 1


@pytest.mark.asyncio
async def test_ranking_is_fetched_once_then_served_from_cache():
    provider = _FakeProvider([_asset("BTC", 1)])
    service = _service(provider)
    await service.ranking(["BTC"])
    await service.ranking(["ETH"])
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_provider_failure_yields_null_rank_without_raising():
    provider = _FakeProvider(error=RuntimeError("quota exhausted"))
    result = await _service(provider).ranking(["BTC"])
    assert result["BTC"]["rank"] is None


@pytest.mark.asyncio
async def test_last_known_ranking_survives_a_failed_refresh():
    """A transient outage must not reshuffle the setup list."""

    provider = _FakeProvider([_asset("BTC", 1)])
    service = _service(provider)
    await service.ranking(["BTC"])
    service._cache.clear()  # simulate the daily expiry
    provider._error = RuntimeError("provider down")
    result = await service.ranking(["BTC"])
    assert result["BTC"]["rank"] == 1


@pytest.mark.asyncio
async def test_symbol_outside_the_covered_depth_has_no_rank():
    """Better no number than one borrowed from another coin."""

    provider = _FakeProvider([_asset("BTC", 1)])
    result = await _service(provider).ranking(["NOSUCHCOIN"])
    assert result["NOSUCHCOIN"] == {"rank": None, "market_cap": None}
