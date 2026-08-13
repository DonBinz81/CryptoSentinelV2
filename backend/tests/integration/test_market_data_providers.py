from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from backend.app.core.config import Settings
from backend.app.data.market_data.base import (
    AssetIdentity,
    MarketAsset,
    MarketDataProvider,
    OHLCVBar,
    PriceQuote,
    ProviderName,
)
from backend.app.data.market_data.cmc import CMCProvider
from backend.app.data.market_data.coingecko import CoinGeckoProvider
from backend.app.data.market_data.credits import CreditBudget
from backend.app.data.market_data.registry import MarketDataRegistry


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "eligible_tokens": [f"TOKEN_{index}" for index in range(149)],
        "cmc_api_key": "test-key",
        "cmc_base_url": "https://cmc.test",
        "coingecko_base_url": "https://coingecko.test",
        "market_data_cache_ttl_seconds": 60,
    }
    values.update(overrides)
    return Settings.model_construct(**values)


class StubProvider(MarketDataProvider):
    def __init__(self, name: ProviderName) -> None:
        self.name = name
        self.calls = 0

    async def resolve_asset_identities(
        self,
        asset_ids: list[str],
        identity_hints: list[AssetIdentity] | None = None,
    ) -> list[AssetIdentity]:
        del identity_hints
        return [
            AssetIdentity(
                app_id=asset_id,
                provider_id=asset_id,
                symbol=asset_id.upper(),
                name=asset_id.title(),
            )
            for asset_id in asset_ids
        ]

    async def get_prices(self, asset_ids: list[str], currencies: list[str]) -> list[PriceQuote]:
        self.calls += 1
        return [
            PriceQuote(
                asset_id=asset_ids[0],
                currency=currencies[0],
                price=1.0,
                provider=self.name,
                provider_id="1",
            )
        ]

    async def get_ohlcv(
        self,
        asset_id: str,
        currency: str,
        days: int,
        interval: str | None = None,
    ) -> list[OHLCVBar]:
        del days, interval
        return [
            OHLCVBar(
                timestamp=datetime.now(UTC),
                open=1,
                high=2,
                low=0.5,
                close=1.5,
                volume=10,
                currency=currency,
                provider=self.name,
            )
        ]

    async def search(self, query: str, currency: str, limit: int = 25) -> list[MarketAsset]:
        del query, limit
        return await self.get_market_list(currency, 1)

    async def get_market_list(
        self,
        currency: str,
        limit: int,
        page: int = 1,
        asset_ids: list[str] | None = None,
    ) -> list[MarketAsset]:
        del limit, page, asset_ids
        self.calls += 1
        return [
            MarketAsset(
                id="bitcoin",
                symbol="BTC",
                name="Bitcoin",
                price=100,
                volume_24h=50,
                currency=currency,
                provider=self.name,
                provider_id="1",
            )
        ]

    def status(self):
        from backend.app.data.market_data.base import ProviderRuntimeStatus

        return ProviderRuntimeStatus(
            name=self.name,
            configured=True,
            cache_entries=0,
            credits_used=0,
            requests_made=self.calls,
            requests_per_minute=60,
        )


@pytest.mark.asyncio
async def test_global_selector_routes_calls_to_selected_provider() -> None:
    cmc = StubProvider(ProviderName.CMC)
    coingecko = StubProvider(ProviderName.COINGECKO)
    registry = MarketDataRegistry(
        settings(),
        providers={ProviderName.CMC: cmc, ProviderName.COINGECKO: coingecko},
    )

    await registry.active.get_market_list("usd", 1)
    assert cmc.calls == 0
    assert coingecko.calls == 1

    registry.select(ProviderName.CMC)
    await registry.active.get_market_list("usd", 1)
    assert cmc.calls == 1
    assert coingecko.calls == 1


@pytest.mark.asyncio
async def test_registry_active_override_ignores_configured_global_provider() -> None:
    cmc = StubProvider(ProviderName.CMC)
    coingecko = StubProvider(ProviderName.COINGECKO)
    registry = MarketDataRegistry(
        settings(market_data_provider="cmc", market_data_alert_provider="coingecko"),
        providers={ProviderName.CMC: cmc, ProviderName.COINGECKO: coingecko},
        active_override=ProviderName.COINGECKO,
    )

    await registry.active.get_market_list("usd", 1)

    assert registry.active_name is ProviderName.COINGECKO
    assert cmc.calls == 0
    assert coingecko.calls == 1


@pytest.mark.asyncio
async def test_registry_reconciles_legacy_coingecko_id_without_price_fallback() -> None:
    class IdentityProvider(StubProvider):
        async def resolve_asset_identities(
            self,
            asset_ids: list[str],
            identity_hints: list[AssetIdentity] | None = None,
        ) -> list[AssetIdentity]:
            if self.name is ProviderName.COINGECKO:
                return [
                    AssetIdentity(
                        app_id=asset_id,
                        provider_id=asset_id,
                        symbol="OLD",
                        name="Legacy Coin",
                    )
                    for asset_id in asset_ids
                ]
            if identity_hints:
                return [
                    AssetIdentity(
                        app_id=hint.app_id,
                        provider_id="999",
                        symbol=hint.symbol,
                        name=hint.name,
                    )
                    for hint in identity_hints
                ]
            return []

        async def get_prices(
            self,
            asset_ids: list[str],
            currencies: list[str],
        ) -> list[PriceQuote]:
            self.calls += 1
            return [
                PriceQuote(
                    asset_id=asset_ids[0],
                    currency=currencies[0],
                    price=42.0,
                    provider=self.name,
                    provider_id=asset_ids[0],
                )
            ]

    cmc = IdentityProvider(ProviderName.CMC)
    coingecko = IdentityProvider(ProviderName.COINGECKO)
    registry = MarketDataRegistry(
        settings(market_data_provider="cmc"),
        providers={ProviderName.CMC: cmc, ProviderName.COINGECKO: coingecko},
    )

    quotes = await registry.get_prices(["legacy-coingecko-id"], ["usd"])

    assert quotes[0].asset_id == "legacy-coingecko-id"
    assert quotes[0].provider is ProviderName.CMC
    assert quotes[0].price == 42.0
    assert cmc.calls == 1
    assert coingecko.calls == 0


@pytest.mark.asyncio
async def test_registry_keeps_cmc_results_when_identity_lookup_fails() -> None:
    class PartialCMCProvider(StubProvider):
        async def resolve_asset_identities(
            self,
            asset_ids: list[str],
            identity_hints: list[AssetIdentity] | None = None,
        ) -> list[AssetIdentity]:
            del identity_hints
            return [
                AssetIdentity(
                    app_id=asset_ids[0],
                    provider_id="101",
                    symbol="ONE",
                    name="Resolved Coin",
                )
            ]

        async def get_market_list(
            self,
            currency: str,
            limit: int,
            page: int = 1,
            asset_ids: list[str] | None = None,
        ) -> list[MarketAsset]:
            del limit, page
            return [
                MarketAsset(
                    id=asset_ids[0],
                    symbol="ONE",
                    name="Resolved Coin",
                    price=1.0,
                    currency=currency,
                    provider=self.name,
                    provider_id=asset_ids[0],
                )
            ]

    class FailingIdentityProvider(StubProvider):
        async def resolve_asset_identities(
            self,
            asset_ids: list[str],
            identity_hints: list[AssetIdentity] | None = None,
        ) -> list[AssetIdentity]:
            del asset_ids, identity_hints
            from backend.app.data.market_data.base import ProviderError

            raise ProviderError("identity source unavailable")

    registry = MarketDataRegistry(
        settings(market_data_provider="cmc"),
        providers={
            ProviderName.CMC: PartialCMCProvider(ProviderName.CMC),
            ProviderName.COINGECKO: FailingIdentityProvider(ProviderName.COINGECKO),
        },
    )

    items = await registry.get_market_list(
        "usd",
        2,
        asset_ids=["resolved-coin", "unresolved-coin"],
    )

    assert [item.id for item in items] == ["resolved-coin"]
    assert items[0].price == 1.0


@pytest.mark.asyncio
async def test_registry_caches_identity_resolution_for_repeated_price_refreshes() -> None:
    class CountingIdentityProvider(StubProvider):
        def __init__(self, name: ProviderName) -> None:
            super().__init__(name)
            self.identity_calls = 0

        async def resolve_asset_identities(
            self,
            asset_ids: list[str],
            identity_hints: list[AssetIdentity] | None = None,
        ) -> list[AssetIdentity]:
            self.identity_calls += 1
            if self.name is ProviderName.COINGECKO:
                return [
                    AssetIdentity(
                        app_id=asset_id,
                        provider_id=asset_id,
                        symbol=asset_id.upper(),
                        name=asset_id.title(),
                    )
                    for asset_id in asset_ids
                ]
            return [
                AssetIdentity(
                    app_id=hint.app_id,
                    provider_id=f"cmc-{hint.app_id}",
                    symbol=hint.symbol,
                    name=hint.name,
                )
                for hint in identity_hints or []
            ]

        async def get_prices(
            self,
            asset_ids: list[str],
            currencies: list[str],
        ) -> list[PriceQuote]:
            self.calls += 1
            return [
                PriceQuote(
                    asset_id=asset_id,
                    currency=currencies[0],
                    price=1.0,
                    provider=self.name,
                    provider_id=asset_id,
                )
                for asset_id in asset_ids
            ]

    cmc = CountingIdentityProvider(ProviderName.CMC)
    coingecko = CountingIdentityProvider(ProviderName.COINGECKO)
    registry = MarketDataRegistry(
        settings(market_data_provider="cmc"),
        providers={ProviderName.CMC: cmc, ProviderName.COINGECKO: coingecko},
    )

    await registry.get_prices(["bitcoin", "ethereum"], ["usd"])
    await registry.get_prices(["bitcoin", "ethereum"], ["usd"])

    assert cmc.identity_calls == 1
    assert coingecko.identity_calls == 1
    assert cmc.calls == 2


@pytest.mark.asyncio
async def test_registry_reuses_ranked_market_identities_for_favorite_refreshes() -> None:
    class RankedIdentityProvider(StubProvider):
        def __init__(self, name: ProviderName) -> None:
            super().__init__(name)
            self.identity_calls = 0

        async def resolve_asset_identities(
            self,
            asset_ids: list[str],
            identity_hints: list[AssetIdentity] | None = None,
        ) -> list[AssetIdentity]:
            del asset_ids, identity_hints
            self.identity_calls += 1
            return []

        async def get_market_list(
            self,
            currency: str,
            limit: int,
            page: int = 1,
            asset_ids: list[str] | None = None,
        ) -> list[MarketAsset]:
            del page, asset_ids
            self.calls += 1
            return [
                MarketAsset(
                    id="bitcoin",
                    symbol="BTC",
                    name="Bitcoin",
                    price=100,
                    volume_24h=50,
                    currency=currency,
                    provider=self.name,
                    provider_id="1",
                )
                for _ in range(limit)
            ]

        async def get_prices(
            self,
            asset_ids: list[str],
            currencies: list[str],
        ) -> list[PriceQuote]:
            self.calls += 1
            return [
                PriceQuote(
                    asset_id=asset_ids[0],
                    currency=currencies[0],
                    price=101.0,
                    provider=self.name,
                    provider_id=asset_ids[0],
                )
            ]

    cmc = RankedIdentityProvider(ProviderName.CMC)
    coingecko = RankedIdentityProvider(ProviderName.COINGECKO)
    registry = MarketDataRegistry(
        settings(),
        providers={ProviderName.CMC: cmc, ProviderName.COINGECKO: coingecko},
    )

    items = await registry.get_market_list("usd", 200)
    quotes = await registry.get_prices([items[0].id], ["usd"])

    assert len(items) == 200
    assert quotes[0].asset_id == "bitcoin"
    assert cmc.identity_calls == 0
    assert coingecko.identity_calls == 0


@pytest.mark.asyncio
async def test_cmc_and_coingecko_normalize_to_same_market_asset_shape() -> None:
    def cmc_handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-CMC_PRO_API_KEY"] == "test-key"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": 1,
                        "name": "Bitcoin",
                        "symbol": "BTC",
                        "slug": "bitcoin",
                        "cmc_rank": 1,
                        "quote": {
                            "USD": {
                                "price": 100,
                                "volume_24h": 50,
                                "market_cap": 1000,
                                "percent_change_24h": 2,
                            }
                        },
                    }
                ],
                "status": {"credit_count": 1},
            },
        )

    def gecko_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "id": "bitcoin",
                    "name": "Bitcoin",
                    "symbol": "btc",
                    "current_price": 100,
                    "total_volume": 50,
                    "market_cap": 1000,
                    "market_cap_rank": 1,
                    "price_change_percentage_24h": 2,
                }
            ],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(cmc_handler)) as cmc_client:
        cmc_items = await CMCProvider(settings(), cmc_client).get_market_list("usd", 1)
    async with httpx.AsyncClient(transport=httpx.MockTransport(gecko_handler)) as gecko_client:
        gecko_items = await CoinGeckoProvider(settings(), gecko_client).get_market_list("usd", 1)

    assert cmc_items[0].model_fields_set >= {"id", "symbol", "name", "price", "volume_24h", "provider"}
    assert gecko_items[0].model_fields_set >= {"id", "symbol", "name", "price", "volume_24h", "provider"}
    assert cmc_items[0].id == gecko_items[0].id == "bitcoin"
    assert cmc_items[0].symbol == gecko_items[0].symbol == "BTC"


@pytest.mark.asyncio
async def test_cmc_cache_avoids_duplicate_credit_consumption() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "data": [{
                    "id": 1,
                    "name": "Bitcoin",
                    "symbol": "BTC",
                    "slug": "bitcoin",
                    "quote": {"USD": {"price": 100}},
                }],
                "status": {"credit_count": 1},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = CMCProvider(settings(), client)
        await provider.get_market_list("usd", 1)
        remaining_after_first = provider.credit_budget.remaining
        await provider.get_market_list("usd", 1)

    assert calls == 1
    assert provider.credits_used == 1
    assert provider.credit_budget.remaining == remaining_after_first


@pytest.mark.asyncio
async def test_cmc_market_list_aggregates_600_items_in_200_item_chunks() -> None:
    requested: list[tuple[int, int]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params["start"])
        limit = int(request.url.params["limit"])
        requested.append((start, limit))
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": index,
                        "name": f"Coin {index}",
                        "symbol": f"C{index}",
                        "slug": f"coin-{index}",
                        "quote": {"USD": {"price": float(index)}},
                    }
                    for index in range(start, start + limit)
                ],
                "status": {"credit_count": 1},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        items = await CMCProvider(settings(), client).get_market_list("usd", 600)

    assert requested == [(1, 200), (201, 200), (401, 200)]
    assert len(items) == 600
    assert items[0].id == "coin-1"
    assert items[-1].id == "coin-600"


def test_cmc_credit_thresholds() -> None:
    budget = CreditBudget(monthly_limit=100, warning_threshold_pct=20, critical_threshold_pct=10)
    budget.consume(80)
    assert budget.level == "warning"
    budget.consume(10)
    assert budget.level == "critical"
    budget.consume(10)
    assert budget.level == "exhausted"


@pytest.mark.asyncio
async def test_cmc_v3_quote_array_is_normalized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/map"):
            return httpx.Response(
                200,
                json={"data": [{"id": 1, "name": "Bitcoin", "symbol": "BTC", "slug": "bitcoin"}]},
            )
        return httpx.Response(
            200,
            json=[
                {
                    "id": 1,
                    "name": "Bitcoin",
                    "symbol": "BTC",
                    "slug": "bitcoin",
                    "quote": [{"symbol": "USD", "price": 100.0, "volume_24h": 50.0}],
                }
            ],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        quotes = await CMCProvider(settings(), client).get_prices(["bitcoin"], ["usd"])

    assert len(quotes) == 1
    assert quotes[0].asset_id == "bitcoin"
    assert quotes[0].currency == "usd"
    assert quotes[0].price == 100.0


@pytest.mark.asyncio
async def test_cmc_preserves_legacy_favorite_ids_for_slug_aliases() -> None:
    mapped_assets = [
        {"id": 1839, "name": "BNB", "symbol": "BNB", "slug": "bnb"},
        {"id": 52, "name": "XRP", "symbol": "XRP", "slug": "xrp"},
        {"id": 5805, "name": "Avalanche", "symbol": "AVAX", "slug": "avalanche"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/map"):
            return httpx.Response(200, json={"data": mapped_assets})
        requested_ids = set(request.url.params["id"].split(","))
        return httpx.Response(
            200,
            json=[
                {
                    **item,
                    "quote": [{"symbol": "USD", "price": 100.0, "volume_24h": 50.0}],
                }
                for item in mapped_assets
                if str(item["id"]) in requested_ids
            ],
        )

    favorite_ids = ["binancecoin", "ripple", "avalanche-2"]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        items = await CMCProvider(settings(), client).get_market_list(
            "usd",
            len(favorite_ids),
            asset_ids=favorite_ids,
        )

    assert {item.id for item in items} == set(favorite_ids)
    assert {item.symbol for item in items} == {"BNB", "XRP", "AVAX"}


@pytest.mark.asyncio
async def test_cmc_matches_historical_id_from_quote_name_and_symbol() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/map"):
            return httpx.Response(200, json={"data": []})
        assert request.url.path == "/v3/cryptocurrency/quotes/latest"
        assert request.url.params["symbol"] == "OLD"
        return httpx.Response(
            200,
            json=[
                {
                    "id": 999,
                    "name": "Legacy Coin",
                    "symbol": "OLD",
                    "slug": "renamed-legacy-coin",
                    "quote": [{"symbol": "USD", "price": 1.0}],
                }
            ],
        )

    hint = AssetIdentity(
        app_id="old-coingecko-slug",
        provider_id="old-coingecko-slug",
        symbol="OLD",
        name="Legacy Coin",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        identities = await CMCProvider(settings(), client).resolve_asset_identities(
            [hint.app_id],
            [hint],
        )

    assert identities == [
        AssetIdentity(
            app_id="old-coingecko-slug",
            provider_id="999",
            symbol="OLD",
            name="Legacy Coin",
        )
    ]


def test_cmc_market_list_uses_stable_application_ids() -> None:
    item = CMCProvider._asset(
        {
            "id": 1839,
            "name": "BNB",
            "symbol": "BNB",
            "slug": "bnb",
            "quote": {"USD": {"price": 600}},
        },
        "usd",
    )

    assert item.id == "binancecoin"


@pytest.mark.asyncio
async def test_cmc_id_map_paginates_beyond_first_5000_assets() -> None:
    requested_starts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params["start"])
        requested_starts.append(start)
        if start == 1:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": index, "name": f"Coin {index}", "symbol": f"C{index}", "slug": f"coin-{index}"}
                        for index in range(1, 5001)
                    ]
                },
            )
        return httpx.Response(
            200,
            json={"data": [{"id": 5001, "name": "Deep Coin", "symbol": "DEEP", "slug": "deep-coin"}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        items = await CMCProvider(settings(), client)._id_map()

    assert requested_starts == [1, 5001]
    assert len(items) == 5001
    assert items[-1]["slug"] == "deep-coin"


@pytest.mark.asyncio
async def test_cmc_id_map_keeps_first_page_when_later_page_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["start"] == "1":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": index, "name": f"Coin {index}", "symbol": f"C{index}", "slug": f"coin-{index}"}
                        for index in range(1, 5001)
                    ]
                },
            )
        return httpx.Response(500, json={"status": {"error_message": "page unavailable"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        items = await CMCProvider(settings(), client)._id_map()

    assert len(items) == 5000
    assert items[0]["slug"] == "coin-1"
    assert items[-1]["slug"] == "coin-5000"


@pytest.mark.asyncio
async def test_cmc_resolves_identity_hint_by_symbol_when_map_does_not_contain_asset() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/map"):
            return httpx.Response(200, json={"data": []})
        assert request.url.params["symbol"] == "NIGHT"
        return httpx.Response(
            200,
            json=[
                {
                    "id": 12345,
                    "name": "Midnight",
                    "symbol": "NIGHT",
                    "slug": "midnight",
                    "quote": [{"symbol": "USD", "price": 0.03}],
                }
            ],
        )

    hint = AssetIdentity(
        app_id="midnight-3",
        provider_id="midnight-3",
        symbol="NIGHT",
        name="Midnight",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        identities = await CMCProvider(settings(), client).resolve_asset_identities(
            [hint.app_id],
            [hint],
        )

    assert identities == [
        AssetIdentity(
            app_id="midnight-3",
            provider_id="12345",
            symbol="NIGHT",
            name="Midnight",
        )
    ]


@pytest.mark.asyncio
async def test_invalid_identity_hint_does_not_block_valid_assets() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/map"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": 1,
                            "name": "Bitcoin",
                            "symbol": "BTC",
                            "slug": "bitcoin",
                        }
                    ]
                },
            )
        assert request.url.params["symbol"] == "FIGR_HELOC"
        return httpx.Response(400, json={"status": {"error_message": "Invalid symbol"}})

    hints = [
        AssetIdentity(app_id="bitcoin", provider_id="bitcoin", symbol="BTC", name="Bitcoin"),
        AssetIdentity(
            app_id="figure-heloc",
            provider_id="figure-heloc",
            symbol="FIGR_HELOC",
            name="Figure Heloc",
        ),
    ]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        identities = await CMCProvider(settings(), client).resolve_asset_identities(
            [hint.app_id for hint in hints],
            hints,
        )

    assert identities == [
        AssetIdentity(
            app_id="bitcoin",
            provider_id="1",
            symbol="BTC",
            name="Bitcoin",
        )
    ]


@pytest.mark.asyncio
async def test_cmc_fetches_resolved_numeric_provider_id_without_map_lookup() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        assert request.url.path == "/v3/cryptocurrency/quotes/latest"
        assert request.url.params["id"] == "12345"
        return httpx.Response(
            200,
            json=[
                {
                    "id": 12345,
                    "name": "Midnight",
                    "symbol": "NIGHT",
                    "slug": "midnight",
                    "quote": [{"symbol": "USD", "price": 0.03, "percent_change_24h": 4.0}],
                }
            ],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        items = await CMCProvider(settings(), client).get_market_list(
            "usd",
            1,
            asset_ids=["12345"],
        )

    assert requested_paths == ["/v3/cryptocurrency/quotes/latest"]
    assert items[0].id == "12345"
    assert items[0].price == 0.03
    assert items[0].percent_change_24h == 4.0
    assert items[0].image_url.endswith("/12345.png")


@pytest.mark.asyncio
async def test_cmc_search_uses_ids_from_map_without_second_resolution() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path.endswith("/map"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": 1027,
                            "name": "Ethereum",
                            "symbol": "ETH",
                            "slug": "ethereum",
                        }
                    ]
                },
            )
        assert request.url.path == "/v3/cryptocurrency/quotes/latest"
        assert request.url.params["id"] == "1027"
        return httpx.Response(
            200,
            json=[
                {
                    "id": 1027,
                    "name": "Ethereum",
                    "symbol": "ETH",
                    "slug": "ethereum",
                    "quote": [
                        {
                            "symbol": "USD",
                            "price": 2500.0,
                            "percent_change_24h": 2.5,
                        }
                    ],
                }
            ],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        items = await CMCProvider(settings(), client).search("ether", "usd", 25)

    assert requested_paths == [
        "/v1/cryptocurrency/map",
        "/v3/cryptocurrency/quotes/latest",
    ]
    assert len(items) == 1
    assert items[0].id == "ethereum"
    assert items[0].symbol == "ETH"
    assert items[0].price == 2500.0


@pytest.mark.asyncio
async def test_cmc_historical_ohlcv_is_split_into_30_day_windows() -> None:
    requested_windows: list[tuple[datetime, datetime]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/map"):
            return httpx.Response(
                200,
                json={"data": [{"id": 1, "name": "Bitcoin", "symbol": "BTC", "slug": "bitcoin"}]},
            )
        assert request.url.path == "/v2/cryptocurrency/ohlcv/historical"
        start = datetime.fromisoformat(request.url.params["time_start"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(request.url.params["time_end"].replace("Z", "+00:00"))
        requested_windows.append((start, end))

        def point(timestamp: datetime) -> dict:
            iso = timestamp.isoformat().replace("+00:00", "Z")
            return {
                "time_open": iso,
                "quote": {
                    "USD": {
                        "open": 100,
                        "high": 110,
                        "low": 90,
                        "close": 105,
                        "volume": 50,
                        "timestamp": iso,
                    }
                },
            }

        return httpx.Response(
            200,
            json={
                "data": {
                    "id": 1,
                    "name": "Bitcoin",
                    "symbol": "BTC",
                    "quotes": [point(start), point(end)],
                },
                "status": {"credit_count": 1},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        bars = await CMCProvider(settings(), client).get_ohlcv("bitcoin", "usd", 75, "daily")

    assert len(requested_windows) == 3
    assert all((end - start).total_seconds() <= 30 * 24 * 3600 for start, end in requested_windows)
    assert requested_windows[0][1] == requested_windows[1][0]
    assert requested_windows[1][1] == requested_windows[2][0]
    assert len(bars) == 4
    assert bars == sorted(bars, key=lambda bar: bar.timestamp)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_coingecko_smoke() -> None:
    provider = CoinGeckoProvider(
        settings(
            coingecko_base_url="https://api.coingecko.com/api/v3",
            coingecko_requests_per_minute=10,
        )
    )
    items = await provider.get_market_list("usd", 1)
    assert items and items[0].price > 0
    assert items[0].provider is ProviderName.COINGECKO


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_cmc_smoke() -> None:
    api_key = os.getenv("CMC_API_KEY")
    if not api_key:
        pytest.skip("CMC_API_KEY is not present in the test process; real CMC call not executed")
    provider = CMCProvider(
        settings(
            cmc_api_key=api_key,
            cmc_base_url="https://pro-api.coinmarketcap.com",
        )
    )
    items = await provider.get_market_list("usd", 1)
    assert items and items[0].price > 0
    assert items[0].provider is ProviderName.CMC


def test_frontend_has_no_direct_coingecko_api_calls() -> None:
    root = Path(__file__).resolve().parents[3]
    offenders = []
    for path in (root / "src").rglob("*"):
        if path.suffix not in {".ts", ".tsx"}:
            continue
        if "api.coingecko.com" in path.read_text(encoding="utf-8"):
            offenders.append(path.relative_to(root).as_posix())
    assert offenders == []


def test_notification_checker_depends_on_registry() -> None:
    root = Path(__file__).resolve().parents[3]
    source = (root / "backend/app/notifications/price_checker.py").read_text(encoding="utf-8")
    assert "get_alert_market_data_registry" in source
    assert "api.coingecko.com" not in source
