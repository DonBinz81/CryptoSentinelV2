"""CoinGecko adapter preserving the existing application data source."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from backend.app.core.config import Settings
from backend.app.data.market_data.base import (
    AssetIdentity,
    MarketAsset,
    MarketDataProvider,
    OHLCVBar,
    PriceQuote,
    ProviderName,
    ProviderRuntimeStatus,
)
from backend.app.data.market_data.http import CachedHttpProvider


def _timestamp_ms(value: int | float) -> datetime:
    return datetime.fromtimestamp(float(value) / 1000.0, tz=UTC)


class CoinGeckoProvider(CachedHttpProvider, MarketDataProvider):
    """Normalize CoinGecko REST responses behind MarketDataProvider."""

    name = ProviderName.COINGECKO

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(
            base_url=settings.coingecko_base_url,
            timeout_seconds=settings.market_data_request_timeout_seconds,
            requests_per_minute=settings.coingecko_requests_per_minute,
            cache_ttl_seconds=settings.market_data_cache_ttl_seconds,
            client=client,
        )

    async def resolve_asset_identities(
        self,
        asset_ids: list[str],
        identity_hints: list[AssetIdentity] | None = None,
    ) -> list[AssetIdentity]:
        del identity_hints
        if not asset_ids:
            return []
        payload = await self._request_json(
            "/coins/markets",
            params={
                "vs_currency": "usd",
                "ids": ",".join(asset_ids),
                "order": "market_cap_desc",
                "per_page": min(len(asset_ids), 250),
                "page": 1,
                "sparkline": "false",
            },
            cache_ttl_seconds=86_400,
        )
        return [
            AssetIdentity(
                app_id=str(item["id"]),
                provider_id=str(item["id"]),
                symbol=str(item.get("symbol", "")).upper(),
                name=str(item.get("name", item["id"])),
            )
            for item in payload
        ]

    @staticmethod
    def _asset(item: dict[str, Any], currency: str) -> MarketAsset:
        return MarketAsset(
            id=str(item["id"]),
            symbol=str(item.get("symbol", "")).upper(),
            name=str(item.get("name", item["id"])),
            image_url=item.get("image"),
            price=float(item.get("current_price") or 0.0),
            percent_change_1h=item.get("price_change_percentage_1h_in_currency"),
            percent_change_24h=item.get("price_change_percentage_24h"),
            percent_change_7d=item.get("price_change_percentage_7d_in_currency"),
            market_cap=item.get("market_cap"),
            market_cap_rank=item.get("market_cap_rank"),
            volume_24h=item.get("total_volume"),
            high_24h=item.get("high_24h"),
            low_24h=item.get("low_24h"),
            currency=currency.lower(),
            provider=ProviderName.COINGECKO,
            provider_id=str(item["id"]),
            last_updated=item.get("last_updated"),
        )

    async def get_prices(self, asset_ids: list[str], currencies: list[str]) -> list[PriceQuote]:
        if not asset_ids or not currencies:
            return []
        payload = await self._request_json(
            "/simple/price",
            params={
                "ids": ",".join(asset_ids),
                "vs_currencies": ",".join(currency.lower() for currency in currencies),
                "include_last_updated_at": "true",
            },
        )
        quotes: list[PriceQuote] = []
        for asset_id, values in payload.items():
            last_updated = values.get("last_updated_at")
            for currency in currencies:
                normalized_currency = currency.lower()
                value = values.get(normalized_currency)
                if value is None:
                    continue
                quotes.append(
                    PriceQuote(
                        asset_id=asset_id,
                        currency=normalized_currency,
                        price=float(value),
                        provider=self.name,
                        provider_id=asset_id,
                        last_updated=datetime.fromtimestamp(last_updated, tz=UTC) if last_updated else None,
                    )
                )
        return quotes

    async def get_ohlcv(
        self,
        asset_id: str,
        currency: str,
        days: int,
        interval: str | None = None,
    ) -> list[OHLCVBar]:
        del interval
        allowed_days = 1 if days <= 1 else 7 if days <= 7 else 30 if days <= 30 else 365
        payload = await self._request_json(
            f"/coins/{asset_id}/ohlc",
            params={"vs_currency": currency.lower(), "days": allowed_days},
        )
        return [
            OHLCVBar(
                timestamp=_timestamp_ms(row[0]),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=None,
                currency=currency.lower(),
                provider=self.name,
            )
            for row in payload
        ]

    async def search(self, query: str, currency: str, limit: int = 25) -> list[MarketAsset]:
        search_payload = await self._request_json("/search", params={"query": query})
        ids = [str(item["id"]) for item in search_payload.get("coins", [])[:limit]]
        if not ids:
            return []
        return await self.get_market_list(currency, limit, asset_ids=ids)

    async def get_market_list(
        self,
        currency: str,
        limit: int,
        page: int = 1,
        asset_ids: list[str] | None = None,
    ) -> list[MarketAsset]:
        base_params = {
            "vs_currency": currency.lower(),
            "ids": ",".join(asset_ids) if asset_ids else None,
            "order": "market_cap_desc",
            "sparkline": "false",
            "price_change_percentage": "1h,24h,7d",
        }
        if asset_ids or limit <= 250:
            payload = await self._request_json(
                "/coins/markets",
                params={**base_params, "per_page": min(limit, 250), "page": page},
            )
            return [self._asset(item, currency) for item in payload]

        start_index = (page - 1) * limit
        end_index = start_index + limit
        first_api_page = start_index // 250 + 1
        last_api_page = (end_index - 1) // 250 + 1
        payload: list[dict[str, Any]] = []
        for api_page in range(first_api_page, last_api_page + 1):
            chunk = await self._request_json(
                "/coins/markets",
                params={**base_params, "per_page": 250, "page": api_page},
            )
            payload.extend(chunk)
        offset = start_index % 250
        return [self._asset(item, currency) for item in payload[offset : offset + limit]]

    def status(self) -> ProviderRuntimeStatus:
        return ProviderRuntimeStatus(
            name=self.name,
            configured=True,
            cache_entries=len(self.cache),
            credits_used=self.credits_used,
            requests_made=self.requests_made,
            requests_per_minute=self.rate_limiter.requests_per_minute,
        )
