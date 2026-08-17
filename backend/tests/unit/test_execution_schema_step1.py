"""Step 1 schema: position.venue, perp_trades.position_id and the perp_orders table.

Only the minimal schema evolution is covered here — no venue abstraction, no router,
no ExecutionResult. Those come later and must not change the economics frozen by
test_position_lifecycle_golden.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select, text

from backend.app.persistence.database import close_db, get_session_factory, init_db
from backend.app.persistence.models.orders import PerpOrder
from backend.app.persistence.models.trades import PerpTrade
from backend.app.persistence.sync_database import (
    create_all_sync,
    init_sync_db,
    reset_sync_db,
)

USER_ID = UUID("00000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 8, 17, tzinfo=UTC)


@pytest.fixture()
async def db(tmp_path: Path):
    reset_sync_db()
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'schema.db'}")
    init_sync_db(f"sqlite:///{tmp_path / 'schema.db'}")
    create_all_sync()
    yield
    await close_db()
    reset_sync_db()


def _trade(trade_id: str, position_id: str | None = None) -> PerpTrade:
    return PerpTrade(
        trade_id=trade_id,
        position_id=position_id,
        user_id=str(USER_ID),
        asset="BTC",
        side="long",
        direction="close",
        size=Decimal("1"),
        price=Decimal("100"),
        leverage=10,
        status="confirmed",
        timestamp_utc=NOW,
        venue="dry_run",
    )


@pytest.mark.asyncio
async def test_perp_orders_table_exists_and_accepts_a_minimal_order(db) -> None:
    """The POSITION -> ORDER -> EXECUTION chain must be representable from day one."""
    async with get_session_factory()() as session:
        session.add(
            PerpOrder(
                order_id="ord_1",
                position_id="pos_abc",
                user_id=str(USER_ID),
                venue="dry_run",
                purpose="tp1",
                status="created",
                requested_qty=Decimal("5"),
                filled_qty=Decimal("0"),
                created_at=NOW,
                updated_at=NOW,
            )
        )
        await session.commit()

        stored = (await session.execute(select(PerpOrder))).scalars().all()

    assert len(stored) == 1
    order = stored[0]
    assert order.status == "created"
    assert order.venue == "dry_run"
    assert order.purpose == "tp1"
    # Venue-specific identifiers stay empty until a real venue produces them.
    assert order.venue_order_id is None
    assert order.tx_hash is None


@pytest.mark.asyncio
async def test_perp_order_supports_the_dry_run_lifecycle(db) -> None:
    """created -> confirmed with the full quantity: the dry-run path, same as live."""
    async with get_session_factory()() as session:
        order = PerpOrder(
            order_id="ord_2",
            position_id="pos_abc",
            user_id=str(USER_ID),
            venue="dry_run",
            purpose="ratchet",
            status="created",
            requested_qty=Decimal("1.25"),
            filled_qty=Decimal("0"),
            created_at=NOW,
            updated_at=NOW,
        )
        session.add(order)
        await session.commit()

        order.status = "confirmed"
        order.filled_qty = order.requested_qty
        await session.commit()

        reloaded = (
            await session.execute(select(PerpOrder).where(PerpOrder.order_id == "ord_2"))
        ).scalar_one()

    assert reloaded.status == "confirmed"
    assert reloaded.filled_qty == Decimal("1.25")


@pytest.mark.asyncio
async def test_perp_trade_position_id_is_persisted(db) -> None:
    """New executions carry the explicit link, no id parsing needed."""
    async with get_session_factory()() as session:
        session.add(_trade("cls_pos_xyz_deadbeef", position_id="pos_xyz"))
        await session.commit()
        stored = (await session.execute(select(PerpTrade))).scalar_one()

    assert stored.position_id == "pos_xyz"


@pytest.mark.asyncio
async def test_backfill_fills_position_id_on_historical_rows(db) -> None:
    """Historical rows have the link only inside trade_id: the backfill extracts it."""
    from backend.app.persistence.database import _backfill_perp_trade_position_id

    async with get_session_factory()() as session:
        # Simulate pre-migration rows: position_id still NULL.
        session.add_all(
            [
                _trade("cls_pos_11111111_aabbccdd"),
                _trade("ssl_pos_22222222_11223344"),
                _trade("add_pos_33333333_99887766"),
                _trade("dry_44444444"),  # opening trade: no position in the id
            ]
        )
        await session.commit()

    engine_session = get_session_factory()()
    async with engine_session as session:
        await _backfill_perp_trade_position_id(session)
        await session.commit()
        rows = {
            t.trade_id: t.position_id
            for t in (await session.execute(select(PerpTrade))).scalars().all()
        }

    assert rows["cls_pos_11111111_aabbccdd"] == "pos_11111111"
    assert rows["ssl_pos_22222222_11223344"] == "pos_22222222"
    assert rows["add_pos_33333333_99887766"] == "pos_33333333"
    # Opening trades carry no position id in the string: they must stay untouched.
    assert rows["dry_44444444"] is None


@pytest.mark.asyncio
async def test_backfill_is_idempotent_and_does_not_overwrite(db) -> None:
    """Running it twice changes nothing, and an existing link is never rewritten."""
    from backend.app.persistence.database import _backfill_perp_trade_position_id

    async with get_session_factory()() as session:
        session.add(_trade("cls_pos_55555555_aaaaaaaa"))
        session.add(_trade("cls_pos_66666666_bbbbbbbb", position_id="pos_manual"))
        await session.commit()

    async with get_session_factory()() as session:
        await _backfill_perp_trade_position_id(session)
        await _backfill_perp_trade_position_id(session)
        await session.commit()
        rows = {
            t.trade_id: t.position_id
            for t in (await session.execute(select(PerpTrade))).scalars().all()
        }

    assert rows["cls_pos_55555555_aaaaaaaa"] == "pos_55555555"
    # Already linked: the backfill must leave it alone.
    assert rows["cls_pos_66666666_bbbbbbbb"] == "pos_manual"


@pytest.mark.asyncio
async def test_position_id_column_is_indexed(db) -> None:
    """The link is queried per position: it must be indexed, not scanned."""
    async with get_session_factory()() as session:
        indexes = (
            await session.execute(
                text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='perp_trades'")
            )
        ).scalars().all()

    assert any("position_id" in (name or "") for name in indexes), indexes
