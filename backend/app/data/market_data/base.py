"""Normalized market data contracts shared by every provider."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ProviderName(StrEnum):
    """Supported market data providers."""

    CMC = "cmc"
    COINGECKO = "coingecko"


class ProviderError(RuntimeError):
    """Raised when a provider request cannot be completed."""


class ProviderConfigurationError(ProviderError):
    """Raised when a selected provider is missing required configuration."""


class ProviderCapabilityError(ProviderError):
    """Raised when the provider cannot supply the requested granularity."""


class MarketAsset(BaseModel):
    """Provider-neutral latest market data for one asset."""

    id: str = Field(description="Stable provider-neutral slug used by the application.")
    symbol: str
    name: str
    image_url: str | None = None
    price: float
    percent_change_1h: float | None = None
    percent_change_24h: float | None = None
    percent_change_7d: float | None = None
    market_cap: float | None = None
    market_cap_rank: int | None = None
    volume_24h: float | None = None
    high_24h: float | None = None
    low_24h: float | None = None
    currency: str = "usd"
    provider: ProviderName
    provider_id: str
    last_updated: datetime | None = None


class PriceQuote(BaseModel):
    """Normalized current price for one asset and currency."""

    asset_id: str
    currency: str
    price: float
    provider: ProviderName
    provider_id: str
    last_updated: datetime | None = None


class AssetIdentity(BaseModel):
    """Provider-neutral identity used to reconcile historical application IDs."""

    app_id: str
    provider_id: str
    symbol: str
    name: str


class OHLCVBar(BaseModel):
    """Normalized OHLCV point. Volume may be absent when upstream omits it."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    market_cap: float | None = None
    currency: str = "usd"
    provider: ProviderName | str


class ProviderRuntimeStatus(BaseModel):
    """Non-secret provider runtime diagnostics."""

    name: ProviderName
    configured: bool
    cache_entries: int
    credits_used: int
    credits_remaining: int | None = None
    credit_level: str | None = None
    requests_made: int
    requests_per_minute: int


class MarketDataProvider(ABC):
    """Common interface consumed by the agent, notifications, API, and UI."""

    name: ProviderName

    @abstractmethod
    async def resolve_asset_identities(
        self,
        asset_ids: list[str],
        identity_hints: list[AssetIdentity] | None = None,
    ) -> list[AssetIdentity]:
        """Resolve application IDs to native provider IDs without fetching prices."""

    @abstractmethod
    async def get_prices(self, asset_ids: list[str], currencies: list[str]) -> list[PriceQuote]:
        """Return current normalized prices."""

    @abstractmethod
    async def get_ohlcv(
        self,
        asset_id: str,
        currency: str,
        days: int,
        interval: str | None = None,
    ) -> list[OHLCVBar]:
        """Return normalized historical OHLCV points."""

    @abstractmethod
    async def search(self, query: str, currency: str, limit: int = 25) -> list[MarketAsset]:
        """Search assets and return normalized latest market data."""

    @abstractmethod
    async def get_market_list(
        self,
        currency: str,
        limit: int,
        page: int = 1,
        asset_ids: list[str] | None = None,
    ) -> list[MarketAsset]:
        """Return a normalized market-cap ordered list."""

    @abstractmethod
    def status(self) -> ProviderRuntimeStatus:
        """Return non-secret runtime diagnostics."""
