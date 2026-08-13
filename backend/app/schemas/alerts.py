"""Schemas for user price-alert configuration sync."""

from pydantic import BaseModel, Field


class PriceAlertItem(BaseModel):
    coin_id: str
    coin_name: str
    coin_symbol: str = ""
    direction: str  # "above" | "below"
    threshold: float
    note: str | None = None
    crossing_only: bool = False
    keep_active_after_trigger: bool = False
    rearm_percent: float = Field(default=0.0, ge=0.0)
    last_observed_price: float | None = None


class RangeAlertItem(BaseModel):
    coin_id: str
    coin_name: str
    coin_symbol: str = ""
    min_price: float
    max_price: float
    note: str | None = None


class FavCoin(BaseModel):
    id: str
    name: str
    symbol: str = ""


class AlertSyncRequest(BaseModel):
    device_id: str | None = None
    price_alerts: list[PriceAlertItem] = Field(default_factory=list)
    range_alerts: list[RangeAlertItem] = Field(default_factory=list)
    fav_coins: list[FavCoin] = Field(default_factory=list)
    fav_up_pct: float = 0.0
    fav_down_pct: float = 0.0
    fav_currency: str = "usd"
    fav_ref_prices: dict[str, float] = Field(default_factory=dict)


class AlertSyncResponse(BaseModel):
    status: str
    price_alert_count: int
    range_alert_count: int
    fav_coin_count: int


class PendingFavAlert(BaseModel):
    coin_id: str
    coin_name: str
    coin_symbol: str = ""
    direction: str
    pct: float
    current_price: float
    ref_price: float


class PendingFavAlertsResponse(BaseModel):
    items: list[PendingFavAlert] = Field(default_factory=list)
