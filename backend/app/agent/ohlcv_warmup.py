"""Warm up OHLCV caches for the selected agent watchlist."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from backend.app.agent.signals.perp.binance_klines import (
    BinanceKlineFeed,
    BinanceMarket,
    get_kline_cache_entry,
)
from backend.app.agent.signals.spot.momentum import MIN_SPOT_CANDLES, SPOT_WARMUP_CANDLES
from backend.app.agent.watchlist import selected_watchlist
from backend.app.core.config import Settings
from backend.app.core.logging import get_logger

logger = get_logger("agent.ohlcv_warmup")

BINANCE_SAFE_REQUEST_INTERVAL_SECONDS = 0.12
BINANCE_5M_HISTORY_LIMIT = 288
_WARMUP_LOCK = asyncio.Lock()


@dataclass(frozen=True)
class WarmupItem:
    asset: str
    market: str
    symbol: str
    status: str
    candles: int
    required_candles: int


async def warmup_selected_watchlist(
    settings: Settings,
    *,
    assets: list[str] | None = None,
    feed: BinanceKlineFeed | None = None,
) -> dict:
    """Fetch historical 5m klines for selected assets without exceeding sane request cadence."""

    selected_assets = _dedupe_assets(assets if assets is not None else selected_watchlist(settings))
    markets = _active_markets(settings.markets_enabled)
    if not selected_assets or not markets:
        return {"status": "skipped", "reason": "watchlist_empty", "items": []}

    feed = feed or BinanceKlineFeed(
        futures_base_url=settings.binance_futures_base_url,
        timeout_seconds=settings.market_data_request_timeout_seconds,
    )
    items: list[WarmupItem] = []
    async with _WARMUP_LOCK:
        last_request_at = 0.0
        for asset in selected_assets:
            if "spot" in markets:
                item, last_request_at = await _warmup_one(
                    feed=feed,
                    asset=asset,
                    market="spot",
                    cache_market="spot",
                    required_candles=MIN_SPOT_CANDLES,
                    limit=max(BINANCE_5M_HISTORY_LIMIT, SPOT_WARMUP_CANDLES),
                    last_request_at=last_request_at,
                )
                items.append(item)
            if "perp" in markets:
                interval = f"{settings.perp_volume_profile_candle_minutes}m"
                window = int(
                    settings.perp_volume_profile_window_hours
                    * 60
                    / settings.perp_volume_profile_candle_minutes
                )
                required = max(24, window // 4)
                item, last_request_at = await _warmup_one(
                    feed=feed,
                    asset=asset,
                    market="perp",
                    cache_market="futures",
                    required_candles=required,
                    limit=min(max(BINANCE_5M_HISTORY_LIMIT, window), 1500),
                    interval=interval,
                    last_request_at=last_request_at,
                )
                items.append(item)

    loaded = sum(1 for item in items if item.status == "loaded")
    ready = sum(1 for item in items if item.candles >= item.required_candles)
    logger.info(
        "agent_ohlcv_warmup_completed",
        requested_assets=len(selected_assets),
        markets=sorted(markets),
        items=len(items),
        loaded=loaded,
        ready=ready,
    )
    return {
        "status": "ok",
        "requested_assets": len(selected_assets),
        "markets": sorted(markets),
        "loaded": loaded,
        "ready": ready,
        "items": [item.__dict__ for item in items],
    }


async def _warmup_one(
    *,
    feed: BinanceKlineFeed,
    asset: str,
    market: str,
    cache_market: BinanceMarket,
    required_candles: int,
    limit: int,
    last_request_at: float,
    interval: str = "5m",
) -> tuple[WarmupItem, float]:
    symbol = f"{asset.upper()}USDT"
    cached = get_kline_cache_entry(market=cache_market, symbol=symbol, interval=interval)
    if cached and len(cached.candles) >= required_candles:
        return (
            WarmupItem(
                asset=asset.upper(),
                market=market,
                symbol=symbol,
                status="cached",
                candles=len(cached.candles),
                required_candles=required_candles,
            ),
            last_request_at,
        )

    now = asyncio.get_running_loop().time()
    wait_for = BINANCE_SAFE_REQUEST_INTERVAL_SECONDS - (now - last_request_at)
    if wait_for > 0:
        await asyncio.sleep(wait_for)
    request_started_at = asyncio.get_running_loop().time()
    try:
        candles = await feed.fetch(symbol=symbol, interval=interval, limit=limit, market=cache_market)
    except Exception as exc:
        logger.warning(
            "agent_ohlcv_warmup_failed",
            asset=asset.upper(),
            market=market,
            symbol=symbol,
            error=str(exc),
        )
        return (
            WarmupItem(
                asset=asset.upper(),
                market=market,
                symbol=symbol,
                status="failed",
                candles=0,
                required_candles=required_candles,
            ),
            request_started_at,
        )

    return (
        WarmupItem(
            asset=asset.upper(),
            market=market,
            symbol=symbol,
            status="loaded",
            candles=len(candles),
            required_candles=required_candles,
        ),
        request_started_at,
    )


def _dedupe_assets(assets: list[str]) -> list[str]:
    selected: list[str] = []
    seen: set[str] = set()
    for asset in assets:
        symbol = asset.strip().upper()
        if symbol and symbol not in seen:
            selected.append(symbol)
            seen.add(symbol)
    return selected


def _active_markets(value: str) -> set[str]:
    normalized = value.lower()
    if normalized == "spot":
        return {"spot"}
    if normalized in {"perp", "perpetual"}:
        return {"perp"}
    return {"spot", "perp"}
