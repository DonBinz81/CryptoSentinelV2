"""Dedicated OHLCV sources for charting and signal-adjacent market history.

This boundary intentionally keeps historical candle data outside the CMC/CoinGecko
latest-pricing provider selector. CMC can stay on a Basic plan while OHLCV is
served by exchange kline feeds that provide real candle volume.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from math import ceil

from backend.app.agent.signals.common.indicators import Candle
from backend.app.agent.signals.perp.binance_klines import BinanceKlineFeed, BinanceKlineFeedError
from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import get_logger
from backend.app.data.market_data.base import OHLCVBar
from backend.app.data.market_data.registry import MarketDataRegistry

logger = get_logger("market_data.ohlcv")


@dataclass(frozen=True)
class OhlcvRequest:
    asset_id: str
    currency: str
    days: int
    interval: str | None = None


class ExternalOHLCVService:
    """Resolve app assets to exchange symbols and fetch historical candles.

    Binance is the first source. ``BinanceKlineFeed`` already contains the
    Bitget/KuCoin fallback path, so future providers can be added inside this
    service without touching the public route or frontend contract.
    """

    source_name = "binance_klines"

    def __init__(self, settings: Settings | None = None, feed: BinanceKlineFeed | None = None) -> None:
        self.settings = settings or get_settings()
        self.feed = feed or BinanceKlineFeed(timeout_seconds=self.settings.market_data_request_timeout_seconds)

    async def get_ohlcv(self, registry: MarketDataRegistry, request: OhlcvRequest) -> list[OHLCVBar]:
        identities = await registry.resolve_asset_identities([request.asset_id])
        if not identities:
            return []

        base_symbol = identities[0].symbol.upper()
        interval = _normalize_interval(request.interval, request.days)
        limit = _limit_for(request.days, interval)
        symbol = _quote_symbol(base_symbol)

        try:
            candles = await self.feed.fetch(symbol=symbol, interval=interval, limit=limit, market="spot")
        except BinanceKlineFeedError as exc:
            logger.info(
                "ohlcv_exchange_source_empty",
                asset_id=request.asset_id,
                symbol=symbol,
                interval=interval,
                days=request.days,
                error=str(exc),
            )
            return []

        candles = _trim_days(candles, request.days)
        factor = await self._conversion_factor(request.currency)
        return [
            OHLCVBar(
                timestamp=candle.timestamp,
                open=_convert(candle.open, factor),
                high=_convert(candle.high, factor),
                low=_convert(candle.low, factor),
                close=_convert(candle.close, factor),
                volume=candle.volume,
                currency=request.currency.lower(),
                provider=self.source_name,
            )
            for candle in candles
        ]

    async def _conversion_factor(self, currency: str) -> Decimal:
        normalized = currency.lower()
        if normalized in {"usd", "usdt"}:
            return Decimal("1")
        conversion_symbol = {"eur": "EURUSDT", "btc": "BTCUSDT"}.get(normalized)
        if conversion_symbol is None:
            return Decimal("1")
        prices = await self.feed.fetch_prices(symbols=[conversion_symbol], market="spot")
        price = prices.get(conversion_symbol)
        if price is None or price <= 0:
            return Decimal("1")
        # Candle values are USDT-quoted. Divide by quote/USDT to display in quote.
        return Decimal("1") / price


def _normalize_interval(interval: str | None, days: int) -> str:
    value = (interval or "").lower()
    aliases = {
        "hourly": "1h",
        "daily": "1d",
        "1d": "1d",
        "1h": "1h",
        "4h": "4h",
        "15m": "15m",
        "5m": "5m",
    }
    if value in aliases:
        return aliases[value]
    return "1h" if days <= 30 else "1d"


def _limit_for(days: int, interval: str) -> int:
    per_day = {
        "5m": 288,
        "15m": 96,
        "1h": 24,
        "4h": 6,
        "1d": 1,
    }.get(interval, 24)
    return max(2, min(1000, ceil(days * per_day) + 1))


def _quote_symbol(base_symbol: str) -> str:
    return f"{base_symbol.upper()}USDT"


def _trim_days(candles: list[Candle], days: int) -> list[Candle]:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    trimmed = [candle for candle in candles if candle.timestamp >= cutoff]
    return trimmed or candles


def _convert(value: float, factor: Decimal) -> float:
    return float(Decimal(str(value)) * factor)


def get_ohlcv_service() -> ExternalOHLCVService:
    return ExternalOHLCVService()
