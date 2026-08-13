"""CoinMarketCap Startup REST adapter."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import ceil
import re
from typing import Any

import httpx

from backend.app.core.config import Settings
from backend.app.data.market_data.aliases import app_id_for_cmc_slug, cmc_slug_for_app_id
from backend.app.data.market_data.base import (
    AssetIdentity,
    MarketAsset,
    MarketDataProvider,
    OHLCVBar,
    PriceQuote,
    ProviderCapabilityError,
    ProviderConfigurationError,
    ProviderError,
    ProviderName,
    ProviderRuntimeStatus,
)
from backend.app.data.market_data.http import CachedHttpProvider
from backend.app.data.market_data.credits import CreditBudget


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _identity_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


# Cache leggera in memoria symbol(BSC) -> (indirizzo|None, scadenza). Nessun archivio su disco.
_CONTRACT_CACHE: dict[str, tuple[str | None, datetime]] = {}
_CONTRACT_CACHE_TTL = timedelta(hours=12)


class CMCProvider(CachedHttpProvider, MarketDataProvider):
    """Normalize CoinMarketCap REST responses behind MarketDataProvider."""

    name = ProviderName.CMC

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(
            base_url=settings.cmc_base_url,
            timeout_seconds=settings.market_data_request_timeout_seconds,
            requests_per_minute=settings.cmc_requests_per_minute,
            cache_ttl_seconds=settings.market_data_cache_ttl_seconds,
            client=client,
        )
        self.api_key = settings.cmc_api_key
        self.credit_budget = CreditBudget(
            monthly_limit=settings.cmc_monthly_credit_limit,
            warning_threshold_pct=settings.cmc_credit_warning_threshold,
            critical_threshold_pct=settings.cmc_credit_critical_threshold,
        )

    async def _request_json(self, *args: Any, **kwargs: Any) -> Any:
        credits_before = self.credits_used
        payload = await super()._request_json(*args, **kwargs)
        self.credit_budget.consume(self.credits_used - credits_before)
        return payload

    @property
    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ProviderConfigurationError("CMC_API_KEY is required when CMC is selected")
        return {
            "Accept": "application/json",
            "Accept-Encoding": "deflate, gzip",
            "X-CMC_PRO_API_KEY": self.api_key,
        }

    @staticmethod
    def _quote_for(item: dict[str, Any], currency: str) -> dict[str, Any]:
        quotes = item.get("quote", {})
        if isinstance(quotes, dict):
            return quotes.get(currency.upper(), {})
        if isinstance(quotes, list):
            return next(
                (quote for quote in quotes if str(quote.get("symbol", "")).upper() == currency.upper()),
                {},
            )
        return {}

    @classmethod
    def _asset(
        cls,
        item: dict[str, Any],
        currency: str,
        app_id: str | None = None,
    ) -> MarketAsset:
        normalized_currency = currency.upper()
        quote = cls._quote_for(item, normalized_currency)
        provider_id = str(item["id"])
        cmc_slug = str(item.get("slug") or provider_id)
        return MarketAsset(
            id=app_id or app_id_for_cmc_slug(cmc_slug),
            symbol=str(item.get("symbol", "")).upper(),
            name=str(item.get("name", item.get("slug", provider_id))),
            image_url=f"https://s2.coinmarketcap.com/static/img/coins/64x64/{provider_id}.png",
            price=float(quote.get("price") or 0.0),
            percent_change_1h=quote.get("percent_change_1h"),
            percent_change_24h=quote.get("percent_change_24h"),
            percent_change_7d=quote.get("percent_change_7d"),
            market_cap=quote.get("market_cap"),
            market_cap_rank=item.get("cmc_rank"),
            volume_24h=quote.get("volume_24h"),
            currency=currency.lower(),
            provider=ProviderName.CMC,
            provider_id=provider_id,
            last_updated=_parse_datetime(quote.get("last_updated") or item.get("last_updated")),
        )

    async def _id_map(self) -> list[dict[str, Any]]:
        page_size = 5000
        start = 1
        items: list[dict[str, Any]] = []
        while True:
            try:
                payload = await self._request_json(
                    "/v1/cryptocurrency/map",
                    params={
                        "listing_status": "active",
                        "start": start,
                        "limit": page_size,
                        "sort": "cmc_rank",
                    },
                    headers=self._headers,
                    estimated_credits=0,
                    cache_ttl_seconds=3600,
                )
            except ProviderError:
                if items:
                    return items
                raise
            page = list(payload.get("data", []))
            items.extend(page)
            if len(page) < page_size:
                return items
            start += page_size

    async def _resolve_ids(self, asset_ids: list[str]) -> dict[str, dict[str, Any]]:
        numeric = {
            asset_id: {
                "id": asset_id,
                "slug": asset_id,
                "symbol": "",
                "name": asset_id,
            }
            for asset_id in asset_ids
            if asset_id.isdigit()
        }
        remaining_ids = [asset_id for asset_id in asset_ids if asset_id not in numeric]
        if not remaining_ids:
            return numeric
        requested = {
            asset_id.lower(): cmc_slug_for_app_id(asset_id)
            for asset_id in remaining_ids
        }
        requested_candidates = set(requested.values()) | set(requested)
        resolved: dict[str, dict[str, Any]] = {}
        for item in await self._id_map():
            slug = str(item.get("slug", "")).lower()
            symbol = str(item.get("symbol", "")).lower()
            provider_id = str(item.get("id", ""))
            for candidate in (slug, symbol, provider_id):
                if candidate in requested_candidates and candidate not in resolved:
                    resolved[candidate] = item
        mapped = {
            asset_id: resolved.get(requested[asset_id.lower()]) or resolved.get(asset_id.lower())
            for asset_id in remaining_ids
            if resolved.get(requested[asset_id.lower()]) is not None
            or resolved.get(asset_id.lower()) is not None
        }
        return {**numeric, **mapped}

    async def resolve_asset_identities(
        self,
        asset_ids: list[str],
        identity_hints: list[AssetIdentity] | None = None,
    ) -> list[AssetIdentity]:
        if not asset_ids:
            return []
        hints = {hint.app_id: hint for hint in identity_hints or []}
        direct = await self._resolve_ids(asset_ids)
        resolved = {
            app_id: AssetIdentity(
                app_id=app_id,
                provider_id=str(item["id"]),
                symbol=str(item.get("symbol", "")).upper(),
                name=str(item.get("name", app_id)),
            )
            for app_id, item in direct.items()
        }

        unresolved = [asset_id for asset_id in asset_ids if asset_id not in resolved]
        if unresolved:
            catalog = await self._id_map()
            for app_id in unresolved:
                hint = hints.get(app_id)
                if hint is None:
                    continue
                matches = [
                    item
                    for item in catalog
                    if _identity_key(str(item.get("name", ""))) == _identity_key(hint.name)
                ]
                if len(matches) != 1 and hint.symbol:
                    matches = [
                        item
                        for item in catalog
                        if str(item.get("symbol", "")).upper() == hint.symbol.upper()
                    ]
                if len(matches) == 1:
                    item = matches[0]
                    resolved[app_id] = AssetIdentity(
                        app_id=app_id,
                        provider_id=str(item["id"]),
                        symbol=str(item.get("symbol", "")).upper(),
                        name=str(item.get("name", hint.name)),
                    )

        unresolved = [asset_id for asset_id in asset_ids if asset_id not in resolved]
        for app_id in unresolved:
            hint = hints.get(app_id)
            if hint is None or not hint.symbol:
                continue
            try:
                payload = await self._request_json(
                    "/v3/cryptocurrency/quotes/latest",
                    params={
                        "symbol": hint.symbol.upper(),
                        "convert": "USD",
                        "skip_invalid": "true",
                    },
                    headers=self._headers,
                    estimated_credits=1,
                )
            except ProviderError:
                continue
            candidates = [
                item
                for item in self._quote_items(payload)
                if str(item.get("symbol", "")).upper() == hint.symbol.upper()
            ]
            exact = next(
                (
                    item
                    for item in candidates
                    if _identity_key(str(item.get("name", ""))) == _identity_key(hint.name)
                ),
                None,
            )
            match = exact or (candidates[0] if len(candidates) == 1 else None)
            if match is not None:
                resolved[app_id] = AssetIdentity(
                    app_id=app_id,
                    provider_id=str(match["id"]),
                    symbol=str(match.get("symbol", "")).upper(),
                    name=str(match.get("name", hint.name)),
                )
        return [resolved[asset_id] for asset_id in asset_ids if asset_id in resolved]

    @staticmethod
    def _quote_items(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            return []
        data = payload.get("data", [])
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            items: list[dict[str, Any]] = []
            for value in data.values():
                if isinstance(value, list):
                    items.extend(value)
                elif isinstance(value, dict):
                    items.append(value)
            return items
        return []

    async def get_prices(self, asset_ids: list[str], currencies: list[str]) -> list[PriceQuote]:
        if not asset_ids or not currencies:
            return []
        resolved = await self._resolve_ids(asset_ids)
        if not resolved:
            return []
        canonical_by_id = {str(item["id"]): canonical for canonical, item in resolved.items()}
        payload = await self._request_json(
            "/v3/cryptocurrency/quotes/latest",
            params={
                "id": ",".join(canonical_by_id),
                "convert": ",".join(currency.upper() for currency in currencies),
                "skip_invalid": "true",
            },
            headers=self._headers,
            estimated_credits=max(1, ceil(len(canonical_by_id) / 100)),
        )
        quotes: list[PriceQuote] = []
        for item in self._quote_items(payload):
            provider_id = str(item["id"])
            canonical = canonical_by_id.get(provider_id, str(item.get("slug") or provider_id))
            for currency in currencies:
                normalized_currency = currency.upper()
                quote = self._quote_for(item, normalized_currency)
                if not quote:
                    continue
                quotes.append(
                    PriceQuote(
                        asset_id=canonical,
                        currency=currency.lower(),
                        price=float(quote["price"]),
                        provider=self.name,
                        provider_id=provider_id,
                        last_updated=_parse_datetime(quote.get("last_updated") or item.get("last_updated")),
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
        requested_interval = interval or ("hourly" if days <= 30 else "daily")
        if requested_interval not in {"hourly", "daily", "1h", "2h", "3h", "4h", "6h", "12h", "1d"}:
            raise ProviderCapabilityError(
                "CMC centralized OHLCV supports hourly or daily periods; 5m is quotes-only"
            )
        resolved = await self._resolve_ids([asset_id])
        if asset_id not in resolved:
            return []
        provider_id = str(resolved[asset_id]["id"])
        hourly = requested_interval in {"hourly", "1h", "2h", "3h", "4h", "6h", "12h"}
        end = datetime.now(UTC)
        start = end - timedelta(days=days)
        bars_by_timestamp: dict[datetime, OHLCVBar] = {}

        for window_start, window_end in self._historical_windows(start, end):
            expected_points = (
                ceil((window_end - window_start).total_seconds() / 3600) + 1
                if hourly
                else (window_end.date() - window_start.date()).days + 1
            )
            payload = await self._request_json(
                "/v2/cryptocurrency/ohlcv/historical",
                params={
                    "id": provider_id,
                    "convert": currency.upper(),
                    "time_period": "hourly" if hourly else "daily",
                    "interval": requested_interval,
                    "time_start": window_start.isoformat().replace("+00:00", "Z"),
                    "time_end": window_end.isoformat().replace("+00:00", "Z"),
                    "skip_invalid": "true",
                },
                headers=self._headers,
                estimated_credits=max(1, ceil(expected_points / 100)),
            )
            data = payload.get("data", {})
            if provider_id in data:
                data = data[provider_id]
            for point in data.get("quotes", []):
                quote = point.get("quote", {}).get(currency.upper(), {})
                timestamp = point.get("time_open") or quote.get("timestamp") or point.get("time_close")
                parsed_timestamp = _parse_datetime(timestamp)
                if parsed_timestamp is None or not quote:
                    continue
                bars_by_timestamp[parsed_timestamp] = OHLCVBar(
                    timestamp=parsed_timestamp,
                    open=float(quote["open"]),
                    high=float(quote["high"]),
                    low=float(quote["low"]),
                    close=float(quote["close"]),
                    volume=quote.get("volume"),
                    market_cap=quote.get("market_cap"),
                    currency=currency.lower(),
                    provider=self.name,
                )
        return [bars_by_timestamp[timestamp] for timestamp in sorted(bars_by_timestamp)]

    @staticmethod
    def _historical_windows(
        start: datetime,
        end: datetime,
        max_days: int = 30,
    ) -> list[tuple[datetime, datetime]]:
        """Split an inclusive historical range into windows no longer than max_days."""

        if start >= end:
            return []
        windows: list[tuple[datetime, datetime]] = []
        cursor = start
        max_span = timedelta(days=max_days)
        while cursor < end:
            window_end = min(cursor + max_span, end)
            windows.append((cursor, window_end))
            cursor = window_end
        return windows

    async def search(self, query: str, currency: str, limit: int = 25) -> list[MarketAsset]:
        needle = query.strip().lower()
        matches = [
            item
            for item in await self._id_map()
            if needle in str(item.get("name", "")).lower()
            or needle in str(item.get("symbol", "")).lower()
            or needle in str(item.get("slug", "")).lower()
        ][:limit]
        if not matches:
            return []
        app_id_by_provider_id = {
            str(item["id"]): app_id_for_cmc_slug(str(item.get("slug") or item["id"]))
            for item in matches
        }
        payload = await self._request_json(
            "/v3/cryptocurrency/quotes/latest",
            params={
                "id": ",".join(app_id_by_provider_id),
                "convert": currency.upper(),
                "skip_invalid": "true",
            },
            headers=self._headers,
            estimated_credits=max(1, ceil(len(app_id_by_provider_id) / 100)),
        )
        assets_by_provider_id = {
            str(item["id"]): self._asset(
                item,
                currency,
                app_id_by_provider_id.get(str(item["id"])),
            )
            for item in self._quote_items(payload)
        }
        return [
            assets_by_provider_id[provider_id]
            for provider_id in app_id_by_provider_id
            if provider_id in assets_by_provider_id
        ]

    async def get_market_list(
        self,
        currency: str,
        limit: int,
        page: int = 1,
        asset_ids: list[str] | None = None,
    ) -> list[MarketAsset]:
        if asset_ids:
            resolved = await self._resolve_ids(asset_ids)
            app_id_by_provider_id = {
                str(item["id"]): app_id
                for app_id, item in resolved.items()
            }
            provider_ids = list(app_id_by_provider_id)
            if not provider_ids:
                return []
            payload = await self._request_json(
                "/v3/cryptocurrency/quotes/latest",
                params={"id": ",".join(provider_ids), "convert": currency.upper(), "skip_invalid": "true"},
                headers=self._headers,
                estimated_credits=max(1, ceil(len(provider_ids) / 100)),
            )
            return [
                self._asset(item, currency, app_id_by_provider_id.get(str(item["id"])))
                for item in self._quote_items(payload)
            ]

        bounded_limit = min(limit, 5000)
        start = (page - 1) * bounded_limit + 1
        items: list[dict[str, Any]] = []
        while len(items) < bounded_limit:
            # Use chunks of 200 to match the market selector without
            # multiplying credit usage for 100/200/400/600 views.
            # Break only on an empty chunk (genuine end of data), not on a
            # partial chunk — the API may cap a single response at fewer items
            # than requested while still having more data available.
            chunk_limit = min(200, bounded_limit - len(items))
            payload = await self._request_json(
                "/v1/cryptocurrency/listings/latest",
                params={
                    "start": start + len(items),
                    "limit": chunk_limit,
                    "convert": currency.upper(),
                    "sort": "market_cap",
                    "sort_dir": "desc",
                },
                headers=self._headers,
                estimated_credits=1,
            )
            chunk = list(payload.get("data", []))
            items.extend(chunk)
            if len(chunk) == 0:
                break
        return [self._asset(item, currency) for item in items]

    async def resolve_contract_address(
        self,
        symbol: str,
        *,
        platform_match: str = "BNB Smart Chain",
    ) -> str | None:
        """Risolve l'indirizzo del contratto del token sulla chain BSC via /v2/cryptocurrency/info.

        Cache in memoria (TTL 12h) per symbol: nessun archivio persistente.
        Ritorna None se non configurato, non trovato o in errore (fail-closed).
        """
        if not self.api_key:
            return None
        key = symbol.upper()
        cached = _CONTRACT_CACHE.get(key)
        if cached is not None and cached[1] > datetime.now(UTC):
            return cached[0]
        address: str | None = None
        try:
            payload = await self._request_json(
                "/v2/cryptocurrency/info",
                params={"symbol": key, "skip_invalid": "true", "aux": "platform"},
                headers=self._headers,
                estimated_credits=1,
                cache_ttl_seconds=int(_CONTRACT_CACHE_TTL.total_seconds()),
            )
            data = payload.get("data", {})
            items = data.get(key) or data.get(key.lower()) or []
            if isinstance(items, dict):
                items = [items]
            for item in items:
                for entry in item.get("contract_address", []) or []:
                    name = str((entry.get("platform") or {}).get("name", ""))
                    if platform_match in name or "BEP20" in name:
                        address = entry.get("contract_address")
                        break
                if address is None:
                    platform = item.get("platform") or {}
                    if platform_match in str(platform.get("name", "")):
                        address = platform.get("token_address")
                if address:
                    break
        except ProviderError:
            return None
        _CONTRACT_CACHE[key] = (address, datetime.now(UTC) + _CONTRACT_CACHE_TTL)
        return address

    def status(self) -> ProviderRuntimeStatus:
        return ProviderRuntimeStatus(
            name=self.name,
            configured=bool(self.api_key),
            cache_entries=len(self.cache),
            credits_used=self.credits_used,
            credits_remaining=self.credit_budget.remaining,
            credit_level=self.credit_budget.level,
            requests_made=self.requests_made,
            requests_per_minute=self.rate_limiter.requests_per_minute,
        )
