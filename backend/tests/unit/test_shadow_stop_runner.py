"""Tests for the shadow-stop I/O layer (NOTE/91): run creation, candle
fetching and persistence across ticks. Mirrors test_telemetry.py's contract:
a broken fetch must never raise into the caller, and a run keeps advancing
across multiple ticks exactly like production's slow_tick calls.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from backend.app.agent.shadow_stop import ShadowStopConfig
from backend.app.agent.shadow_stop_runner import advance_active_runs, create_shadow_stop_run
from backend.app.agent.signals.common.indicators import Candle
from backend.app.persistence import database
from backend.app.persistence.database import close_db, get_session_factory, init_db
from backend.app.persistence.models.shadow_stop import ShadowStopRun

T0 = datetime(2026, 8, 23, 0, 0, tzinfo=UTC)
CFG = ShadowStopConfig(buffer_pct=0.1, max_reentries=1)


@pytest.fixture
async def db(tmp_path: Path):
    database._engine = None
    database._session_factory = None
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    yield
    await close_db()


def _candle(minute, o, h, l, c):
    return Candle(timestamp=T0 + timedelta(minutes=minute), open=o, high=h, low=l, close=c, volume=1.0)


class _FakePriceFeed:
    """Serves a fixed candle list regardless of the requested window — the
    runner is responsible for filtering by start_time/closed_cutoff."""

    def __init__(self, candles):
        self.candles = candles
        self.calls = 0

    async def fetch(self, *, symbol, interval, limit, market, start_time=None):
        self.calls += 1
        if start_time is None:
            return list(self.candles)
        return [c for c in self.candles if c.timestamp >= start_time]


class _BrokenPriceFeed:
    async def fetch(self, **kwargs):
        raise RuntimeError("network down")


@pytest.mark.asyncio
async def test_run_created_with_expected_initial_state(db):
    await create_shadow_stop_run(
        position_id="pos_1", user_id="u", asset="LINK", side="long",
        entry_price=Decimal("10.0"), tp1=Decimal("10.5"), entry_ts=T0, cfg=CFG,
    )
    async with get_session_factory()() as session:
        row = (await session.execute(select(ShadowStopRun))).scalar_one()
        assert row.position_id == "pos_1"
        assert row.outcome is None
        assert row.pnl_virtual_pct is None
        assert row.buffer_pct == Decimal("0.1")
        assert row.max_reentries == 1


@pytest.mark.asyncio
async def test_advance_runs_to_tp1_across_two_ticks(db):
    await create_shadow_stop_run(
        position_id="pos_2", user_id="u", asset="XRP", side="long",
        entry_price=Decimal("100"), tp1=Decimal("105"), entry_ts=T0, cfg=CFG,
    )
    candles = [
        _candle(0, 99, 101, 98, 100.5),     # signal candle -> fixes stop ~97.9
        _candle(5, 99, 100.2, 99.5, 100.0),  # calm candle, no event
        _candle(10, 100, 106, 99.9, 105.5),  # TP1
    ]
    feed = _FakePriceFeed(candles)

    async with get_session_factory()() as session:
        # First tick only sees "now" at minute 6: candle at minute 10 not closed yet.
        await advance_active_runs(session, feed, now=T0 + timedelta(minutes=6))
        row = (await session.execute(select(ShadowStopRun))).scalar_one()
        assert row.outcome is None  # still running: TP1 candle hasn't closed

    async with get_session_factory()() as session:
        await advance_active_runs(session, feed, now=T0 + timedelta(minutes=16))
        row = (await session.execute(select(ShadowStopRun))).scalar_one()
        assert row.outcome == "tp1"
        assert row.pnl_virtual_pct > 0


@pytest.mark.asyncio
async def test_run_keeps_advancing_after_it_finishes_is_not_reprocessed(db):
    await create_shadow_stop_run(
        position_id="pos_3", user_id="u", asset="DOT", side="long",
        entry_price=Decimal("10"), tp1=Decimal("10.5"), entry_ts=T0, cfg=CFG,
    )
    candles = [
        _candle(0, 9.9, 10.1, 9.8, 10.0),
        _candle(5, 9.9, 10.6, 9.85, 10.55),  # TP1
    ]
    feed = _FakePriceFeed(candles)
    async with get_session_factory()() as session:
        await advance_active_runs(session, feed, now=T0 + timedelta(minutes=11))
        row = (await session.execute(select(ShadowStopRun))).scalar_one()
        assert row.outcome == "tp1"
        calls_after_first = feed.calls

    # A finished run must be excluded from the next tick's query entirely.
    async with get_session_factory()() as session:
        await advance_active_runs(session, feed, now=T0 + timedelta(minutes=30))
    assert feed.calls == calls_after_first


@pytest.mark.asyncio
async def test_fetch_failure_never_raises_and_leaves_run_untouched(db):
    await create_shadow_stop_run(
        position_id="pos_4", user_id="u", asset="ETH", side="long",
        entry_price=Decimal("2000"), tp1=Decimal("2100"), entry_ts=T0, cfg=CFG,
    )
    async with get_session_factory()() as session:
        await advance_active_runs(session, _BrokenPriceFeed(), now=T0 + timedelta(minutes=30))
        row = (await session.execute(select(ShadowStopRun))).scalar_one()
        assert row.outcome is None  # untouched, not crashed
