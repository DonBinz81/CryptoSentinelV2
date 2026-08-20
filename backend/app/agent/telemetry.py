"""Positioning telemetry capture (NOTE/76-78): archive what Binance forgets.

The futures positioning endpoints keep ~30 days of history, so the evidence
behind the surviving conditional leads (per-pair OI build-up, Brain
confidence) must be frozen at trade time. Two capture paths:

- ``capture_entry_telemetry``: fired-and-forgotten at each perp opening; opens
  its own DB session (it outlives the request's one) and never raises.
- ``snapshot_open_position``: one row per open position per slow tick, using
  the caller's session.

Fetchers are injectable so tests exercise the capture logic without network.
Telemetry must NEVER delay or break trading: every path is wrapped, a failed
fetch writes NULL plus an ``error`` marker instead of losing the row.
"""

from __future__ import annotations

import statistics
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from backend.app.core.logging import get_logger
from backend.app.persistence.models.telemetry import EntryTelemetry, PositionTelemetry

logger = get_logger("agent.telemetry")

_BASE = "https://fapi.binance.com"
_TIMEOUT = 6.0


async def _get_json(client: httpx.AsyncClient, path: str, **params):
    resp = await client.get(_BASE + path, params=params)
    resp.raise_for_status()
    return resp.json()


async def fetch_entry_metrics(asset: str, now_ms: int) -> tuple[dict, list[str]]:
    """Fetch the three positioning metrics; partial failures are per-metric."""
    out: dict = {"oi_d24_pct": None, "ls_ratio": None, "ls_d24_pct": None, "taker_4h": None}
    errors: list[str] = []
    sym = asset.upper() + "USDT"
    t24 = now_ms - 24 * 3600_000
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            oi = await _get_json(client, "/futures/data/openInterestHist",
                                 symbol=sym, period="1h", startTime=t24, endTime=now_ms, limit=30)
            vals = [float(r["sumOpenInterest"]) for r in oi]
            if len(vals) > 3 and vals[0] > 0:
                out["oi_d24_pct"] = (vals[-1] / vals[0] - 1) * 100
        except Exception as exc:
            errors.append(f"oi:{type(exc).__name__}")
        try:
            ls = await _get_json(client, "/futures/data/globalLongShortAccountRatio",
                                 symbol=sym, period="1h", startTime=t24, endTime=now_ms, limit=30)
            vals = [float(r["longShortRatio"]) for r in ls]
            if vals:
                out["ls_ratio"] = vals[-1]
                if len(vals) > 3 and vals[0] > 0:
                    out["ls_d24_pct"] = (vals[-1] / vals[0] - 1) * 100
        except Exception as exc:
            errors.append(f"ls:{type(exc).__name__}")
        try:
            tk = await _get_json(client, "/futures/data/takerlongshortRatio",
                                 symbol=sym, period="15m",
                                 startTime=now_ms - 4 * 3600_000, endTime=now_ms, limit=20)
            vals = [float(r["buySellRatio"]) for r in tk]
            if vals:
                out["taker_4h"] = statistics.mean(vals)
        except Exception as exc:
            errors.append(f"taker:{type(exc).__name__}")
    return out, errors


async def fetch_open_interest(asset: str) -> float | None:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        data = await _get_json(client, "/fapi/v1/openInterest", symbol=asset.upper() + "USDT")
        return float(data["openInterest"])


async def capture_entry_telemetry(
    *,
    position_id: str,
    user_id: str,
    asset: str,
    side: str,
    brain_confidence: float | None,
    fetcher=fetch_entry_metrics,
) -> None:
    """Background task at position opening. Own session; never raises."""
    try:
        now = datetime.now(UTC)
        metrics, errors = await fetcher(asset, int(now.timestamp() * 1000))
        from backend.app.persistence.database import get_session_factory

        async with get_session_factory()() as session:
            session.add(EntryTelemetry(
                position_id=position_id, user_id=user_id, asset=asset, side=side,
                timestamp_utc=now,
                oi_d24_pct=_dec(metrics.get("oi_d24_pct")),
                ls_ratio=_dec(metrics.get("ls_ratio")),
                ls_d24_pct=_dec(metrics.get("ls_d24_pct")),
                taker_4h=_dec(metrics.get("taker_4h")),
                brain_confidence=_dec(brain_confidence),
                error=";".join(errors)[:200] or None,
            ))
            await session.commit()
        logger.info("entry_telemetry_captured", asset=asset, position_id=position_id,
                    errors=errors or None)
    except Exception as exc:  # telemetry must never surface into trading
        logger.warning("entry_telemetry_failed", asset=asset, error=str(exc))


async def snapshot_open_position(session, pos, now: datetime, fetcher=fetch_open_interest) -> None:
    """One OI + adverse-depth snapshot for an open perp position. Never raises."""
    try:
        oi = None
        try:
            oi = await fetcher(pos.asset)
        except Exception as exc:
            logger.warning("position_telemetry_oi_failed", asset=pos.asset,
                           error=type(exc).__name__)
        entry = pos.entry_price
        price = pos.current_price
        adverse = None
        if entry and price:
            adverse = (entry - price) / entry * 100 if pos.side == "long" else (price - entry) / entry * 100
        session.add(PositionTelemetry(
            position_id=pos.position_id, timestamp_utc=now,
            open_interest=_dec(oi), price=price,
            adverse_pct=_dec(float(adverse) if adverse is not None else None),
        ))
    except Exception as exc:
        logger.warning("position_telemetry_failed", asset=getattr(pos, "asset", "?"),
                       error=str(exc))


def _dec(v) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(round(float(v), 6)))
    except Exception:
        return None
