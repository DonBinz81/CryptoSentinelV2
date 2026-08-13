"""Fallback CEX (Bitget, KuCoin) per candele e prezzi quando Binance non ha il token.

Cascata: Binance (chiamante) -> Bitget -> KuCoin. Ogni adapter normalizza nel
formato Candle interno e degrada in silenzio (ritorna vuoto/None) in caso di
errore, cosi' aggiungere fonti non puo' mai rompere il percorso Binance.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import httpx

from backend.app.agent.signals.common.indicators import Candle
from backend.app.core.logging import get_logger

logger = get_logger("agent.cex_fallback")

_BITGET = "https://api.bitget.com"
_KUCOIN = "https://api.kucoin.com"
_KUCOIN_FUTURES = "https://api-futures.kucoin.com"

# Mappe intervallo per i formati specifici di ogni exchange (coprono gli intervalli usati).
_BITGET_SPOT_GRAN = {"1m": "1min", "5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h", "1d": "1day"}
_BITGET_MIX_GRAN = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1H", "4h": "4H", "1d": "1D"}
_KUCOIN_TYPE = {"1m": "1min", "5m": "5min", "15m": "15min", "1h": "1hour", "4h": "4hour", "1d": "1day"}
_KUCOIN_FUT_MIN = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}


def _split_base_quote(symbol: str) -> tuple[str, str]:
    s = symbol.upper()
    for quote in ("USDT", "USDC", "USD"):
        if s.endswith(quote):
            return s[: -len(quote)], quote
    return s, "USDT"


async def _bitget_klines(client: httpx.AsyncClient, symbol: str, interval: str, limit: int, futures: bool) -> list[Candle]:
    gran = (_BITGET_MIX_GRAN if futures else _BITGET_SPOT_GRAN).get(interval)
    if not gran:
        return []
    if futures:
        url = f"{_BITGET}/api/v2/mix/market/candles"
        params = {"symbol": symbol.upper(), "granularity": gran, "limit": str(limit), "productType": "usdt-futures"}
    else:
        url = f"{_BITGET}/api/v2/spot/market/candles"
        params = {"symbol": symbol.upper(), "granularity": gran, "limit": str(limit)}
    response = await client.get(url, params=params)
    if response.status_code >= 400:
        return []
    data = response.json().get("data") or []
    # row: [ts(ms), open, high, low, close, baseVol, quoteVol]
    out = [
        Candle(
            timestamp=datetime.fromtimestamp(int(row[0]) / 1000, UTC),
            open=float(row[1]), high=float(row[2]), low=float(row[3]),
            close=float(row[4]), volume=float(row[5]),
        )
        for row in data
    ]
    out.sort(key=lambda c: c.timestamp)
    return out[-limit:]


async def _kucoin_klines(client: httpx.AsyncClient, symbol: str, interval: str, limit: int, futures: bool) -> list[Candle]:
    base, quote = _split_base_quote(symbol)
    if futures:
        gran = _KUCOIN_FUT_MIN.get(interval)
        if not gran:
            return []
        url = f"{_KUCOIN_FUTURES}/api/v1/kline/query"
        params = {"symbol": f"{base}{quote}M", "granularity": gran}
        response = await client.get(url, params=params)
        if response.status_code >= 400:
            return []
        data = response.json().get("data") or []
        # row: [time(ms), open, high, low, close, volume]
        out = [
            Candle(
                timestamp=datetime.fromtimestamp(int(row[0]) / 1000, UTC),
                open=float(row[1]), high=float(row[2]), low=float(row[3]),
                close=float(row[4]), volume=float(row[5]) if len(row) > 5 else 0.0,
            )
            for row in data
        ]
        out.sort(key=lambda c: c.timestamp)
        return out[-limit:]
    ktype = _KUCOIN_TYPE.get(interval)
    if not ktype:
        return []
    url = f"{_KUCOIN}/api/v1/market/candles"
    params = {"type": ktype, "symbol": f"{base}-{quote}"}
    response = await client.get(url, params=params)
    if response.status_code >= 400:
        return []
    data = response.json().get("data") or []
    # row KuCoin spot: [time(sec), open, close, high, low, volume, turnover] (ordine: close prima di high)
    out = [
        Candle(
            timestamp=datetime.fromtimestamp(int(row[0]), UTC),
            open=float(row[1]), close=float(row[2]), high=float(row[3]),
            low=float(row[4]), volume=float(row[5]),
        )
        for row in data
    ]
    out.sort(key=lambda c: c.timestamp)
    return out[-limit:]


async def fetch_klines_fallback(*, symbol: str, interval: str, limit: int, futures: bool, timeout: float) -> list[Candle]:
    """Prova Bitget poi KuCoin; ritorna le prime candele non vuote o []."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        for name, fn in (("bitget", _bitget_klines), ("kucoin", _kucoin_klines)):
            try:
                candles = await fn(client, symbol, interval, limit, futures)
            except Exception as exc:
                logger.warning("cex_fallback_klines_failed", source=name, symbol=symbol, error=str(exc))
                continue
            if candles:
                logger.info("cex_fallback_klines_ok", source=name, symbol=symbol, candles=len(candles), futures=futures)
                return candles
    return []


async def fetch_price_fallback(*, symbol: str, futures: bool, timeout: float) -> Decimal | None:
    """Ultimo prezzo da Bitget poi KuCoin; None se nessuno lo espone."""
    base, quote = _split_base_quote(symbol)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            if futures:
                response = await client.get(
                    f"{_BITGET}/api/v2/mix/market/ticker",
                    params={"symbol": symbol.upper(), "productType": "usdt-futures"},
                )
            else:
                response = await client.get(
                    f"{_BITGET}/api/v2/spot/market/tickers", params={"symbol": symbol.upper()}
                )
            if response.status_code < 400:
                data = response.json().get("data") or []
                rows = data if isinstance(data, list) else [data]
                if rows:
                    px = rows[0].get("lastPr") or rows[0].get("last") or rows[0].get("close")
                    if px:
                        return Decimal(str(px))
        except Exception as exc:
            logger.warning("cex_fallback_price_failed", source="bitget", symbol=symbol, error=str(exc))
        try:
            if futures:
                response = await client.get(
                    f"{_KUCOIN_FUTURES}/api/v1/ticker", params={"symbol": f"{base}{quote}M"}
                )
                if response.status_code < 400:
                    data = response.json().get("data") or {}
                    px = data.get("price") or data.get("lastTradePrice")
                    if px:
                        return Decimal(str(px))
            else:
                response = await client.get(
                    f"{_KUCOIN}/api/v1/market/orderbook/level1", params={"symbol": f"{base}-{quote}"}
                )
                if response.status_code < 400:
                    data = response.json().get("data") or {}
                    px = data.get("price")
                    if px:
                        return Decimal(str(px))
        except Exception as exc:
            logger.warning("cex_fallback_price_failed", source="kucoin", symbol=symbol, error=str(exc))
    return None
