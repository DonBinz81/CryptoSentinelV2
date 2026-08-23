"""I/O side of the shadow-stop simulation (NOTE/91): candle fetching and
state persistence for every active run. The pure state machine lives in
shadow_stop.py; everything that touches the network or the DB lives here,
wrapped so a failure can never delay or break real trading — same contract
as telemetry.py.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from backend.app.agent.shadow_stop import ShadowStopConfig, advance, new_run_state
from backend.app.core.logging import get_logger
from backend.app.persistence.models.shadow_stop import ShadowStopRun

logger = get_logger("agent.shadow_stop_runner")

_INTERVAL_SECONDS = 300  # 5m candles, matches the backtest this rule was validated on


def _ensure_utc(dt: datetime) -> datetime:
    """SQLite hands back naive datetimes; they are stored as UTC, mark them so."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _floor_5m(ts: datetime) -> datetime:
    epoch = ts.timestamp()
    return datetime.fromtimestamp(epoch - epoch % _INTERVAL_SECONDS, tz=UTC)


async def create_shadow_stop_run(
    *,
    position_id: str,
    user_id: str,
    asset: str,
    side: str,
    entry_price: Decimal,
    tp1: Decimal,
    entry_ts: datetime,
    cfg: ShadowStopConfig,
    variant: str = "baseline",
) -> None:
    """Fired-and-forgotten at position opening, alongside entry telemetry.

    Opens its own session (it outlives the request's one when scheduled via
    ``asyncio.create_task``) and never raises — a broken run must never delay
    or fail a real trade. Called once per variant (NOTE/92): each position
    gets one row per rule tested, keyed by (position_id, variant).
    """
    try:
        state = new_run_state(
            side=side, entry_price=float(entry_price), tp1=float(tp1),
            cfg=cfg, candle_count_budget=cfg.horizon_candles,
        )
        now = datetime.now(UTC)
        from backend.app.persistence.database import get_session_factory

        async with get_session_factory()() as session:
            session.add(ShadowStopRun(
                position_id=position_id, variant=variant, user_id=user_id, asset=asset, side=side,
                entry_price=entry_price, tp1=tp1, entry_ts=entry_ts,
                buffer_pct=Decimal(str(cfg.buffer_pct)), max_reentries=cfg.max_reentries,
                state_json=json.dumps(state), events_json="[]",
                created_at=now, updated_at=now,
            ))
            await session.commit()
        logger.info("shadow_stop_run_created", position_id=position_id, variant=variant, asset=asset, side=side)
    except Exception as exc:
        logger.warning("shadow_stop_run_create_failed", position_id=position_id, variant=variant, error=str(exc))


async def advance_active_runs(session, price_feed, *, now: datetime | None = None) -> None:
    """One tick: fetch newly-closed candles for every active run and advance
    it. Runs stay in the table (and keep being advanced) after the REAL
    position closes — the whole point is comparing the rule's outcome to
    what actually happened. Never raises: one broken run must not stop the
    others, and a fetch failure never blocks the trading loop.
    """
    _now = now or datetime.now(UTC)
    result = await session.execute(select(ShadowStopRun).where(ShadowStopRun.outcome.is_(None)))
    runs = result.scalars().all()
    changed = False
    for run in runs:
        try:
            if await _advance_one(session, price_feed, run, _now):
                changed = True
        except Exception as exc:
            logger.warning("shadow_stop_advance_failed", position_id=run.position_id, error=str(exc))
    if changed:
        await session.commit()


async def _advance_one(session, price_feed, run: ShadowStopRun, now: datetime) -> bool:
    closed_cutoff = now - timedelta(seconds=_INTERVAL_SECONDS)
    since = _ensure_utc(run.last_candle_ts) if run.last_candle_ts is not None else None
    if since is None:
        # First pass: floor to the interval boundary so the fetch's first
        # result is the candle COVERING entry_ts, not the one after it.
        fetch_from = _floor_5m(_ensure_utc(run.entry_ts))
    else:
        fetch_from = since
    if fetch_from > closed_cutoff:
        return False  # nothing closed yet since last check

    span_minutes = max(5, int((closed_cutoff - fetch_from).total_seconds() // 60) + 10)
    limit = min(1000, span_minutes // 5 + 2)
    candles = await price_feed.fetch(
        symbol=run.asset.upper() + "USDT", interval="5m", limit=limit,
        market="futures", start_time=fetch_from,
    )
    new_candles = [
        c for c in candles
        if c.timestamp <= closed_cutoff and (since is None or c.timestamp > since)
    ]
    if not new_candles:
        return False

    state = json.loads(run.state_json)
    events_log = json.loads(run.events_json)
    for candle in sorted(new_candles, key=lambda c: c.timestamp):
        state, events = advance(state, candle)
        for ev in events:
            events_log.append({
                "kind": ev.kind, "price": ev.price, "pnl_leg_pct": ev.pnl_leg_pct,
                "at": candle.timestamp.isoformat(),
            })
        run.last_candle_ts = candle.timestamp
        if state["phase"] == "done":
            break

    run.state_json = json.dumps(state)
    run.events_json = json.dumps(events_log)
    run.outcome = state.get("outcome")
    run.pnl_virtual_pct = Decimal(str(round(state["pnl_virtual_pct"], 4)))
    run.updated_at = datetime.now(UTC)
    session.add(run)
    if state.get("outcome") is not None:
        logger.info(
            "shadow_stop_run_finished",
            position_id=run.position_id, outcome=state["outcome"],
            pnl_virtual_pct=float(run.pnl_virtual_pct),
        )
    return True
