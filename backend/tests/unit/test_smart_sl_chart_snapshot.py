"""Tests for the Smart SL chart snapshot fix (NOTE/93 parte 2).

David flagged that the chart shown for an open position never reached the
price level where a Smart SL actually sold. Root cause: the Smart SL sell
path creates its close trade directly and never called
``_snapshot_closed_trade`` -- unlike every other close path (stop, TP,
breakeven), so no frozen chart existed for these events and the app fell
back to a live-fetch chart with an unrealistic 1.5s network timeout.

This drives ``_process_smart_sl`` end-to-end (real DB, real dry-run venue,
no network) to prove the snapshot now gets created for an L1 sell, exactly
like it already does for the other close reasons.
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
from backend.app.persistence.models.trade_charts import TradeChartSnapshot
from backend.app.persistence.models.trades import PerpTrade
from backend.app.persistence.repositories.positions import PerpPositionRepository
from backend.app.persistence.sync_database import create_all_sync, init_sync_db, reset_sync_db
from backend.app.persistence.database import close_db, get_session_factory, init_db
from backend.tests.unit.test_agent_step6 import USER_ID, settings


@pytest.fixture
async def db(tmp_path: Path):
    reset_sync_db()
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'smart_sl_chart.db'}")
    init_sync_db(f"sqlite:///{tmp_path / 'smart_sl_chart.db'}")
    create_all_sync()
    yield
    await close_db()
    reset_sync_db()


class _FakeFeed:
    """Ultime candele 5m chiuse, tutte oltre il livello -- soddisfa
    _smart_sl_confirmed senza toccare la rete."""

    def __init__(self, close: float):
        now = datetime.now(UTC)
        self.candles = [
            Candle(timestamp=now - timedelta(minutes=m), open=close, high=close, low=close, close=close, volume=1.0)
            for m in (15, 10, 5)
        ]

    async def fetch(self, *, symbol, interval, limit, market):
        return self.candles


@pytest.mark.asyncio
async def test_smart_sl_sell_creates_a_chart_snapshot(db):
    svc = AgentService(settings(), spot_registry=SimpleNamespace(), perp_registry=SimpleNamespace())
    ms = svc._ms
    now = datetime.now(UTC)

    entry = Decimal("100.0")
    isl = Decimal("110.0")  # short: lo stop sta SOPRA l'entry; dist = 10
    dist = abs(entry - isl)
    level_1 = entry + Decimal(str(ms.perp_smart_sl_l1_frac)) * dist  # short: livello sopra l'entry
    price_beyond_l1 = level_1 + Decimal("0.5")

    svc.price_feed = _FakeFeed(float(price_beyond_l1))

    pos = PerpPosition(
        venue="dry_run",
        position_id="pos_ssl_chart_test",
        user_id=str(USER_ID),
        asset="BNB",
        side="short",
        size=Decimal("1.0"),
        entry_price=entry,
        current_price=price_beyond_l1,
        leverage=10,
        pnl_unrealized=Decimal("0"),
        initial_stop_loss=isl,
        stop_loss=isl,
        take_profit_1=Decimal("94"),
        status="open",
        opened_at=now - timedelta(hours=1),
        updated_at=now,
    )

    async with get_session_factory()() as session:
        session.add(pos)
        await session.commit()

        await svc._process_smart_sl(session, pos, price_beyond_l1, ms, now)
        await session.commit()

        trades = (await session.execute(
            select(PerpTrade).where(PerpTrade.position_id == "pos_ssl_chart_test")
        )).scalars().all()
        ssl_trades = [t for t in trades if "smart_sl_sell_l1" in (t.notes or "")]
        assert len(ssl_trades) == 1, f"attesa 1 vendita L1, trovate: {[t.notes for t in trades]}"
        close_trade = ssl_trades[0]

        snapshots = (await session.execute(
            select(TradeChartSnapshot).where(TradeChartSnapshot.close_trade_id == close_trade.trade_id)
        )).scalars().all()
        assert len(snapshots) == 1, "la vendita Smart SL deve congelare uno snapshot del grafico, come ogni altra chiusura"
        assert snapshots[0].position_id == "pos_ssl_chart_test"
        assert snapshots[0].market == "perp"


@pytest.mark.asyncio
async def test_smart_sl_sell_without_confirmation_creates_no_snapshot(db):
    """Se la conferma non arriva (prezzo non ancora confermato su N candele
    chiuse), non deve scattare ne' la vendita ne' lo snapshot."""
    svc = AgentService(settings(), spot_registry=SimpleNamespace(), perp_registry=SimpleNamespace())
    ms = svc._ms
    now = datetime.now(UTC)

    entry = Decimal("100.0")
    isl = Decimal("90.0")
    dist = abs(entry - isl)
    level_1 = entry + Decimal(str(ms.perp_smart_sl_l1_frac)) * dist
    price_beyond_l1 = level_1 + Decimal("0.5")

    # feed con troppo poche candele chiuse: _smart_sl_confirmed fallisce (fail-closed)
    class _EmptyFeed:
        async def fetch(self, **kwargs):
            return []

    svc.price_feed = _EmptyFeed()

    pos = PerpPosition(
        venue="dry_run",
        position_id="pos_ssl_chart_unconfirmed",
        user_id=str(USER_ID),
        asset="BNB",
        side="short",
        size=Decimal("1.0"),
        entry_price=entry,
        current_price=price_beyond_l1,
        leverage=10,
        pnl_unrealized=Decimal("0"),
        initial_stop_loss=isl,
        stop_loss=isl,
        take_profit_1=Decimal("94"),
        status="open",
        opened_at=now - timedelta(hours=1),
        updated_at=now,
    )

    async with get_session_factory()() as session:
        session.add(pos)
        await session.commit()

        await svc._process_smart_sl(session, pos, price_beyond_l1, ms, now)
        await session.commit()

        trades = (await session.execute(
            select(PerpTrade).where(PerpTrade.position_id == "pos_ssl_chart_unconfirmed")
        )).scalars().all()
        assert trades == []
        snapshots = (await session.execute(select(TradeChartSnapshot))).scalars().all()
        assert snapshots == []
