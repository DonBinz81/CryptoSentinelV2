from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.dependencies import require_admin_access, require_read_access
from backend.app.api.routes.market_data import router
from backend.app.data.market_data.base import OHLCVBar, ProviderName
from backend.app.data.market_data.registry import get_market_data_registry
from backend.app.data.ohlcv_sources import get_ohlcv_service
from backend.tests.integration.test_market_data_providers import StubProvider, settings
from backend.app.data.market_data.registry import MarketDataRegistry
from datetime import UTC, datetime


class StubOHLCVService:
    source_name = "binance_klines"

    async def get_ohlcv(self, registry, request):
        del registry
        return [
            OHLCVBar(
                timestamp=datetime.now(UTC),
                open=1,
                high=2,
                low=0.5,
                close=1.5,
                volume=10,
                currency=request.currency,
                provider=self.source_name,
            )
        ]


def test_backend_market_data_response_shape() -> None:
    registry = MarketDataRegistry(
        settings(),
        providers={
            ProviderName.CMC: StubProvider(ProviderName.CMC),
            ProviderName.COINGECKO: StubProvider(ProviderName.COINGECKO),
        },
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_market_data_registry] = lambda: registry
    app.dependency_overrides[get_ohlcv_service] = lambda: StubOHLCVService()
    app.dependency_overrides[require_read_access] = lambda: None
    app.dependency_overrides[require_admin_access] = lambda: None
    client = TestClient(app)

    markets = client.get("/api/v1/market-data/markets").json()
    assert markets["provider"] == "coingecko"
    assert markets["items"][0]["symbol"] == "BTC"
    assert markets["items"][0]["price"] == 100
    assert markets["items"][0]["volume_24h"] == 50

    ohlcv = client.get("/api/v1/market-data/ohlcv", params={"asset_id": "bitcoin"}).json()
    assert ohlcv["provider"] == "binance_klines"
    assert ohlcv["items"][0].keys() >= {"open", "high", "low", "close", "volume", "timestamp"}

    selected = client.put("/api/v1/market-data/provider", json={"provider": "coingecko"}).json()
    assert selected["active"] == "coingecko"
