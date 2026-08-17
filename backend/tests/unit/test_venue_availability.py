"""Per-venue pair availability: the three states and how they are reached."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.app.data.market_data.cache import TTLCache
from backend.app.execution.venue_availability import (
    AVAILABLE,
    UNAVAILABLE,
    UNKNOWN,
    VenueAvailabilityService,
)

ZERO = "0x0000000000000000000000000000000000000000"
POOL = "0x16b9A82891338f9bA80E2D6970FddA79D1eb0daE"

USDT = "0x55d398326f99059fF775485246999027B3197955"
BTCB = "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c"


def _settings(**overrides):
    base = dict(
        aster_base_url="https://fapi.asterdex.com",
        bsc_network="mainnet",
        spot_quote_token_address=USDT,
        spot_token_map={"BTC": BTCB},
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class _FakeAster:
    """Stands in for the public exchangeInfo call. No credentials involved."""

    def __init__(self, payload=None, error: Exception | None = None) -> None:
        self._payload = payload
        self._error = error
        self.calls = 0

    async def public_exchange_info(self):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._payload


def _exchange_info(*bases: str) -> dict:
    return {
        "symbols": [
            {"baseAsset": base, "contractType": "PERPETUAL", "status": "TRADING"}
            for base in bases
        ]
    }


class _FakeSpot:
    """Stands in for the PancakeSwap factory lookup."""

    def __init__(self, pair: str = POOL, error: Exception | None = None) -> None:
        self._pair = pair
        self._error = error

    def build_path(self, from_asset: str, to_asset: str) -> list[str]:
        return [from_asset, to_asset]

    async def pair_address(self, token_a: str, token_b: str) -> str:
        if self._error is not None:
            raise self._error
        return self._pair


def _service(*, aster=None, spot=None, settings=None) -> VenueAvailabilityService:
    return VenueAvailabilityService(
        settings or _settings(),
        cache=TTLCache(60.0),
        aster_client=aster or _FakeAster(_exchange_info("BTC")),
        spot_provider=spot or _FakeSpot(),
    )


@pytest.mark.asyncio
async def test_perp_pair_available():
    result = await _service(aster=_FakeAster(_exchange_info("BTC", "ETH"))).availability(["BTC"])
    assert result["BTC"]["perp"] == {"venue": "aster", "status": AVAILABLE}


@pytest.mark.asyncio
async def test_perp_pair_unavailable_is_reported_with_a_reason():
    service = _service(aster=_FakeAster(_exchange_info("BTC")))
    result = await service.availability(["COMP"])
    assert result["COMP"]["perp"]["status"] == UNAVAILABLE
    assert result["COMP"]["perp"]["reason"]


@pytest.mark.asyncio
async def test_perp_ignores_markets_that_are_not_trading_perpetuals():
    payload = {
        "symbols": [
            {"baseAsset": "BTC", "contractType": "PERPETUAL", "status": "TRADING"},
            {"baseAsset": "TON", "contractType": "PERPETUAL", "status": "BREAK"},
            {"baseAsset": "COMP", "contractType": "CURRENT_QUARTER", "status": "TRADING"},
        ]
    }
    result = await _service(aster=_FakeAster(payload)).availability(["BTC", "TON", "COMP"])
    assert result["BTC"]["perp"]["status"] == AVAILABLE
    assert result["TON"]["perp"]["status"] == UNAVAILABLE
    assert result["COMP"]["perp"]["status"] == UNAVAILABLE


@pytest.mark.asyncio
async def test_venue_unreachable_is_unknown_not_unavailable():
    """An outage on our side must never look like a missing market."""

    service = _service(aster=_FakeAster(error=RuntimeError("network down")))
    result = await service.availability(["BTC"])
    assert result["BTC"]["perp"]["status"] == UNKNOWN


@pytest.mark.asyncio
async def test_spot_pair_available_when_every_hop_has_a_pool():
    result = await _service(spot=_FakeSpot(POOL)).availability(["BTC"])
    assert result["BTC"]["spot"] == {"venue": "pancakeswap", "status": AVAILABLE}


@pytest.mark.asyncio
async def test_spot_pair_unavailable_when_the_factory_returns_no_pool():
    result = await _service(spot=_FakeSpot(ZERO)).availability(["BTC"])
    assert result["BTC"]["spot"]["status"] == UNAVAILABLE


@pytest.mark.asyncio
async def test_spot_rpc_failure_is_unknown():
    result = await _service(spot=_FakeSpot(error=RuntimeError("rpc down"))).availability(["BTC"])
    assert result["BTC"]["spot"]["status"] == UNKNOWN


@pytest.mark.asyncio
async def test_spot_symbol_without_a_curated_address_is_unknown():
    """Never claim a pool exists from a ticker: one ticker matches many tokens."""

    result = await _service().availability(["DOGE"])
    assert result["DOGE"]["spot"]["status"] == UNKNOWN


@pytest.mark.asyncio
async def test_spot_on_testnet_is_unknown_not_unavailable():
    """Mainnet addresses probed against the testnet factory find no pool.

    Reporting that as `unavailable` would block, in the setup screen, coins that
    trade perfectly well on mainnet.
    """

    service = _service(settings=_settings(bsc_network="testnet"), spot=_FakeSpot(ZERO))
    result = await service.availability(["BTC"])
    assert result["BTC"]["spot"]["status"] == UNKNOWN


@pytest.mark.asyncio
async def test_spot_unknown_when_no_quote_token_is_configured():
    service = _service(settings=_settings(spot_quote_token_address=None))
    result = await service.availability(["BTC"])
    assert result["BTC"]["spot"]["status"] == UNKNOWN


@pytest.mark.asyncio
async def test_runtime_network_override_wins_over_configuration(monkeypatch):
    """The engine can switch chain at runtime; the setup screen must follow.

    Settings say mainnet, an admin moved execution to testnet: reading the raw
    configuration here would make the UI describe a chain the engine is not on.
    """

    import backend.app.execution.venue_availability as module

    monkeypatch.setattr(
        module,
        "effective_execution_settings",
        lambda s: SimpleNamespace(**{**vars(s), "bsc_network": "testnet"}),
    )
    service = _service(settings=_settings(bsc_network="mainnet"), spot=_FakeSpot(POOL))
    result = await service.availability(["BTC"])
    assert result["BTC"]["spot"]["status"] == UNKNOWN
    assert "test" in result["BTC"]["spot"]["reason"]


@pytest.mark.asyncio
async def test_perp_markets_are_fetched_once_and_cached():
    aster = _FakeAster(_exchange_info("BTC", "ETH"))
    service = _service(aster=aster)
    await service.availability(["BTC"])
    await service.availability(["ETH"])
    assert aster.calls == 1


@pytest.mark.asyncio
async def test_no_pair_list_is_hard_coded():
    """Adding a market on the venue must not require a code change."""

    service = _service(aster=_FakeAster(_exchange_info("COMP")))
    result = await service.availability(["COMP"])
    assert result["COMP"]["perp"]["status"] == AVAILABLE


class _DepthProvider(_FakeSpot):
    """Fake router+pool: routes through WBNB, like the real one, and has reserves."""

    def __init__(self, pair: str, token0: str, reserve0: int, reserve1: int, wbnb: str) -> None:
        super().__init__(pair)
        self._token0 = token0
        self._r0 = reserve0
        self._r1 = reserve1
        self.wbnb_address = wbnb

    def build_path(self, from_asset: str, to_asset: str) -> list[str]:
        return [from_asset, self.wbnb_address, to_asset]

    async def pair_reserves(self, pair: str):
        return self._token0, self._r0, self._r1


WBNB = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"


@pytest.mark.asyncio
async def test_pool_depth_is_measured_on_the_hop_the_router_would_use():
    """A deep direct pair the router never touches is not usable liquidity."""

    # Pool WBNB/token: 2 WBNB a side, and the quote/WBNB pool prices BNB at 600.
    provider = _DepthProvider(POOL, WBNB, 2 * 10**18, 10**18, WBNB)
    service = VenueAvailabilityService(
        _settings(), cache=TTLCache(60.0), aster_client=_FakeAster(_exchange_info("BTC")),
        spot_provider=provider,
    )
    service._cache.set("pancakeswap:bnb_price_usd", Decimal("600"))
    depth = await service.spot_pool_liquidity_usd("BTC")
    assert depth == Decimal("1200")


@pytest.mark.asyncio
async def test_pool_depth_is_none_on_testnet():
    """Mainnet addresses against a testnet factory measure nothing real."""

    service = VenueAvailabilityService(
        _settings(bsc_network="testnet"), cache=TTLCache(60.0),
        aster_client=_FakeAster(_exchange_info("BTC")), spot_provider=_FakeSpot(POOL),
    )
    assert await service.spot_pool_liquidity_usd("BTC") is None


@pytest.mark.asyncio
async def test_pool_depth_is_none_for_unmapped_symbols():
    service = _service()
    assert await service.spot_pool_liquidity_usd("DOGE") is None


@pytest.mark.asyncio
async def test_pool_depth_is_none_when_the_reading_fails():
    """A failed reading must stay unknown: zero would block every trade."""

    service = _service(spot=_FakeSpot(error=RuntimeError("rpc down")))
    assert await service.spot_pool_liquidity_usd("BTC") is None
