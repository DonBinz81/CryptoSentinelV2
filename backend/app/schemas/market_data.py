"""API schemas for normalized market data."""

from pydantic import BaseModel, Field

from backend.app.data.market_data.base import (
    MarketAsset,
    OHLCVBar,
    PriceQuote,
    ProviderName,
    ProviderRuntimeStatus,
)
from backend.app.data.mcp.cmc import CMCMPConnection


class MarketListResponse(BaseModel):
    provider: ProviderName
    currency: str
    items: list[MarketAsset]


class PriceListResponse(BaseModel):
    provider: ProviderName
    items: list[PriceQuote]


class OHLCVResponse(BaseModel):
    provider: str
    asset_id: str
    currency: str
    interval: str | None = None
    items: list[OHLCVBar]


class ProviderSelectionRequest(BaseModel):
    provider: ProviderName


class ProviderSelectionResponse(BaseModel):
    active: ProviderName
    providers: list[ProviderRuntimeStatus]
    cmc_mcp: CMCMPConnection
    selection_scope: str = Field(default="runtime_state", description="Selection is persisted in RuntimeState.")
