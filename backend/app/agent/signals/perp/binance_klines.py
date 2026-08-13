"""Specialized Binance kline feed for the Perp Volume Profile signal."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

import httpx

from backend.app.agent.signals.common.indicators import Candle

BinanceMarket = Literal["futures", "spot"]


class BinanceKlineFeedError(RuntimeError):
    """Raised when Binance klines cannot be fetched or parsed."""


@dataclass(frozen=True)
class BinanceKlineCacheEntry:
    market: BinanceMarket
    symbol: str
    interval: str
    candles: list[Candle]
    updated_at: datetime


_KLINE_CACHE: dict[tuple[BinanceMarket, str, str], BinanceKlineCacheEntry] = {}


class BinanceKlineFeed:
    """Fetch 5m OHLCV candles directly for the signal engine.

    This is intentionally not wired through ``MarketDataProvider`` because the
    Step 6 plan requires a specialized feed for Volume Profile.
    """

    def __init__(
        self,
        *,
        futures_base_url: str | None = None,
        spot_base_url: str = "https://api.binance.com",
        timeout_seconds: float = 10.0,
    ) -> None:
        self.futures_base_url = (futures_base_url or "https://fapi.binance.com").rstrip("/")
        self.spot_base_url = spot_base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def _binance_klines(
        self,
        symbol: str,
        interval: str,
        limit: int,
        market: BinanceMarket,
        *,
        start_time: datetime | None = None,
    ) -> list[Candle]:
        base_url = self.futures_base_url if market == "futures" else self.spot_base_url
        path = "/fapi/v1/klines" if market == "futures" else "/api/v3/klines"
        params: dict[str, str | int] = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
        if start_time is not None:
            params["startTime"] = int(start_time.timestamp() * 1000)
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(f"{base_url}{path}", params=params)
            if response.status_code >= 400:
                return []
            return [_parse_kline(row) for row in response.json()]
        except Exception:
            return []

    async def fetch(
        self,
        *,
        symbol: str,
        interval: str = "5m",
        limit: int = 288,
        market: BinanceMarket = "futures",
        start_time: datetime | None = None,
    ) -> list[Candle]:
        candles = await self._binance_klines(symbol, interval, limit, market, start_time=start_time)
        if not candles:
            if start_time is not None:
                raise BinanceKlineFeedError(f"no_klines_binance_{symbol.upper()}")
            # Fallback CEX: Bitget -> KuCoin (per token senza mercato Binance).
            from backend.app.agent.signals.perp.cex_fallback import fetch_klines_fallback

            candles = await fetch_klines_fallback(
                symbol=symbol, interval=interval, limit=limit,
                futures=(market == "futures"), timeout=self.timeout_seconds,
            )
        if not candles:
            raise BinanceKlineFeedError(f"no_klines_any_cex_{symbol.upper()}")
        if start_time is None:
            _KLINE_CACHE[(market, symbol.upper(), interval)] = BinanceKlineCacheEntry(
                market=market,
                symbol=symbol.upper(),
                interval=interval,
                candles=candles,
                updated_at=datetime.now(UTC),
            )
        return candles


    async def fetch_prices(
        self,
        *,
        symbols: list[str],
        market: BinanceMarket = "futures",
    ) -> dict[str, Decimal]:
        """Prezzo corrente per piu' symbol in una sola chiamata (ticker/price batch).

        Ritorna una mappa SYMBOL->prezzo (es. {"BTCUSDT": Decimal("...")}).
        """
        if not symbols:
            return {}
        base_url = self.futures_base_url if market == "futures" else self.spot_base_url
        path = "/fapi/v1/ticker/price" if market == "futures" else "/api/v3/ticker/price"
        symbols_param = json.dumps([s.upper() for s in symbols], separators=(",", ":"))
        result: dict[str, Decimal] = {}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(f"{base_url}{path}", params={"symbols": symbols_param})
            if response.status_code < 400:
                result = {str(row["symbol"]).upper(): Decimal(str(row["price"])) for row in response.json()}
        except Exception:
            result = {}
        # Su Binance futures alcuni low-cap/meme sono quotati col prefisso "1000"
        # (es. LUNC -> 1000LUNCUSDT, SHIB -> 1000SHIBUSDT): prezzo ×1000. Senza
        # questo passaggio il refresh non trova "LUNCUSDT", il prezzo resta
        # congelato e gli stop non scattano. Si tenta SOLO per i symbol mancanti.
        missing = [s for s in symbols if s.upper() not in result]
        if missing and market == "futures":
            thousand_map = {f"1000{s.upper()}": s.upper() for s in missing}
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.get(
                        f"{base_url}{path}",
                        params={"symbols": json.dumps(list(thousand_map), separators=(",", ":"))},
                    )
                if response.status_code < 400:
                    for row in response.json():
                        sym = str(row["symbol"]).upper()
                        if sym in thousand_map:
                            # Riporta al prezzo "unitario" coerente con l'entry (÷1000).
                            result[thousand_map[sym]] = Decimal(str(row["price"])) / Decimal("1000")
            except Exception:
                pass
            missing = [s for s in symbols if s.upper() not in result]

        # Fallback CEX per i symbol non coperti da Binance (Bitget -> KuCoin).
        if missing:
            from backend.app.agent.signals.perp.cex_fallback import fetch_price_fallback

            for sym in missing:
                price = await fetch_price_fallback(
                    symbol=sym, futures=(market == "futures"), timeout=self.timeout_seconds
                )
                if price is not None:
                    result[sym.upper()] = price
        return result


    async def fetch_funding_rates(self, *, assets: list[str]) -> dict[str, Decimal]:
        """lastFundingRate per asset dai futures Binance (premiumIndex). Best-effort."""
        if not assets:
            return {}
        # Mappa sia il symbol diretto sia la variante "1000XXX" (vedi fetch_prices):
        # il funding rate è una percentuale, quindi non va riscalato.
        wanted: dict[str, str] = {}
        for a in assets:
            wanted[f"{a.upper()}USDT"] = a.upper()
            wanted[f"1000{a.upper()}USDT"] = a.upper()
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(f"{self.futures_base_url}/fapi/v1/premiumIndex")
            if response.status_code >= 400:
                return {}
            out: dict[str, Decimal] = {}
            for row in response.json():
                sym = str(row.get("symbol", "")).upper()
                rate = row.get("lastFundingRate")
                if sym in wanted and rate is not None:
                    out[wanted[sym]] = Decimal(str(rate))
            return out
        except Exception:
            return {}


def get_kline_cache_entry(*, market: BinanceMarket, symbol: str, interval: str = "5m") -> BinanceKlineCacheEntry | None:
    """Return the latest in-memory kline cache entry for coverage diagnostics."""

    return _KLINE_CACHE.get((market, symbol.upper(), interval))


def clear_kline_cache() -> None:
    """Clear kline cache for tests."""

    _KLINE_CACHE.clear()


def _parse_kline(row: list) -> Candle:
    return Candle(
        timestamp=datetime.fromtimestamp(int(row[0]) / 1000, UTC),
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=float(row[5]),
    )
