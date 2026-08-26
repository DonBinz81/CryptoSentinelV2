"""Tests for the Smart SL L1 geometric constraint (NOTE/97, David's rule).

L1 is a fraction (0.4) of the entry->initial-stop distance: when the entry
sits far from the reference candle, that fraction lands INSIDE the range the
candle already swept -- a sell level there gets collected by any ordinary
wick retest (21% of historical positions had this geometry; one real sell,
NEAR, was wasted on exactly this). The rule: L1 must sit at least
``perp_smart_sl_min_gap_from_ref_pct`` beyond the candle's extreme; if that
pushes it at/past L2, L1 is skipped entirely for the position.

End-to-end through _process_smart_sl (real DB, real dry-run venue, injected
candle feed -- no network), mirroring test_smart_sl_chart_snapshot.py.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from backend.app.agent.service import AgentService
from backend.app.agent.signals.common.indicators import Candle
from backend.app.persistence.models.positions import PerpPosition
from backend.app.persistence.models.trades import PerpTrade
from backend.app.persistence.sync_database import create_all_sync, init_sync_db, reset_sync_db
from backend.app.persistence.database import close_db, get_session_factory, init_db
from backend.tests.unit.test_agent_step6 import USER_ID, settings


@pytest.fixture
async def db(tmp_path: Path):
    reset_sync_db()
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'ref_gap.db'}")
    init_sync_db(f"sqlite:///{tmp_path / 'ref_gap.db'}")
    create_all_sync()
    yield
    await close_db()
    reset_sync_db()


class _FeedAt:
    """N closed 5m candles all at one price: satisfies the closed-candle
    confirmation at exactly that level."""

    def __init__(self, close: float):
        now = datetime.now(UTC)
        self.candles = [
            Candle(timestamp=now - timedelta(minutes=m), open=close, high=close, low=close, close=close, volume=1.0)
            for m in (20, 15, 10, 5)
        ]

    async def fetch(self, *, symbol, interval, limit, market):
        return self.candles


def _position(pid: str, *, entry: str, ref: str, isl: str, price: str) -> PerpPosition:
    now = datetime.now(UTC)
    return PerpPosition(
        venue="dry_run", position_id=pid, user_id=str(USER_ID),
        asset="PENGU", side="long", size=Decimal("1000"),
        entry_price=Decimal(entry), current_price=Decimal(price), leverage=10,
        pnl_unrealized=Decimal("0"),
        initial_stop_loss=Decimal(isl), stop_loss=Decimal(isl),
        stop_reference_price=Decimal(ref), stop_reference_field="low",
        take_profit_1=Decimal("0.0096"), status="open",
        opened_at=now - timedelta(hours=1), updated_at=now,
    )


async def _trades_for(session, pid: str) -> list[PerpTrade]:
    return list((await session.execute(
        select(PerpTrade).where(PerpTrade.position_id == pid)
    )).scalars().all())


# The PENGU geometry David flagged (numbers from the real position, NOTE/97):
# entry 0.00946, reference-candle low 0.00933, ISL = 0.00933*0.989 ≈ 0.0092274.
# Fraction L1 (0.4 of dist) ≈ 0.009367 -> ABOVE the 0.00933 low: inside the
# swept range. With gap 0.15%: L1_eff = 0.00933*0.9985 ≈ 0.0093160.
ENTRY, REF, ISL = "0.00946", "0.00933", "0.00922737"


@pytest.mark.asyncio
async def test_l1_no_longer_sells_inside_the_swept_range(db):
    svc = AgentService(settings(), spot_registry=SimpleNamespace(), perp_registry=SimpleNamespace())
    ms = svc._ms
    now = datetime.now(UTC)
    # price 0.009355: below the OLD fraction level (~0.009367) but still
    # inside the candle's range (above 0.00933). Old code sold here.
    price = Decimal("0.009355")
    svc.price_feed = _FeedAt(float(price))
    pos = _position("pos_gap_inside", entry=ENTRY, ref=REF, isl=ISL, price=str(price))
    async with get_session_factory()() as session:
        session.add(pos)
        await session.commit()
        await svc._process_smart_sl(session, pos, price, ms, now)
        await session.commit()
        assert await _trades_for(session, "pos_gap_inside") == []


@pytest.mark.asyncio
async def test_l1_sells_once_price_goes_beyond_the_candle_plus_gap(db):
    svc = AgentService(settings(), spot_registry=SimpleNamespace(), perp_registry=SimpleNamespace())
    ms = svc._ms
    now = datetime.now(UTC)
    # price 0.009310: below ref*(1-0.15%) ≈ 0.0093160 -> genuinely beyond the
    # swept range, the pushed-down L1 must fire here.
    price = Decimal("0.009310")
    svc.price_feed = _FeedAt(float(price))
    pos = _position("pos_gap_beyond", entry=ENTRY, ref=REF, isl=ISL, price=str(price))
    async with get_session_factory()() as session:
        session.add(pos)
        await session.commit()
        await svc._process_smart_sl(session, pos, price, ms, now)
        await session.commit()
        trades = await _trades_for(session, "pos_gap_beyond")
        assert [t.notes for t in trades] == ["auto_close:smart_sl_sell_l1"]


@pytest.mark.asyncio
async def test_degenerate_geometry_skips_l1_but_keeps_l2(db):
    now = datetime.now(UTC)
    # The clamp needs the pushed-down L1 to land at/past L2. With this
    # position's geometry (dist ≈ 0.00023263, L2 = entry - 0.7*dist ≈
    # 0.0092972) a gap of 1.05% puts L1_eff = ref*0.9895 ≈ 0.0092327 < L2:
    # exercised via a settings override rather than inventing an impossible
    # market geometry. L1 must be skipped entirely; L2 must fire normally.
    svc_big_gap = AgentService(
        settings(perp_smart_sl_min_gap_from_ref_pct=1.05),
        spot_registry=SimpleNamespace(), perp_registry=SimpleNamespace(),
    )
    ms = svc_big_gap._ms
    price = Decimal("0.009240")  # below L2 (~0.0092972), above ISL
    svc_big_gap.price_feed = _FeedAt(float(price))
    pos = _position("pos_gap_degenerate", entry=ENTRY, ref=REF, isl=ISL, price=str(price))
    async with get_session_factory()() as session:
        session.add(pos)
        await session.commit()
        await svc_big_gap._process_smart_sl(session, pos, price, ms, now)
        await session.commit()
        trades = await _trades_for(session, "pos_gap_degenerate")
        notes = [t.notes for t in trades]
        assert "auto_close:smart_sl_sell_l1" not in notes  # L1 skipped
        assert notes == ["auto_close:smart_sl_sell_l2"]    # L2 unaffected


@pytest.mark.asyncio
async def test_no_reference_price_keeps_fraction_level_as_is(db):
    """ATR-mode positions have no stop_reference_price: the rule must not
    apply and the old fraction level must keep working unchanged."""
    svc = AgentService(settings(), spot_registry=SimpleNamespace(), perp_registry=SimpleNamespace())
    ms = svc._ms
    now = datetime.now(UTC)
    price = Decimal("0.009355")  # inside range: with NO ref, old behavior sells
    svc.price_feed = _FeedAt(float(price))
    pos = _position("pos_gap_noref", entry=ENTRY, ref=REF, isl=ISL, price=str(price))
    pos.stop_reference_price = None
    pos.stop_reference_field = None
    async with get_session_factory()() as session:
        session.add(pos)
        await session.commit()
        await svc._process_smart_sl(session, pos, price, ms, now)
        await session.commit()
        trades = await _trades_for(session, "pos_gap_noref")
        assert [t.notes for t in trades] == ["auto_close:smart_sl_sell_l1"]
