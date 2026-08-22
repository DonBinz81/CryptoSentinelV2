"""Strategy column on perp_positions / perp_trades (NOTE/85 constraint 1, NOTE/87).

Phase 0 of the second-strategy perimeter: every perp row records which engine
opened it, close legs inherit it from the position, and rows that predate the
column read the explicit default instead of NULL. Without this the coexistence
period of two strategies would be unrecoverable after the fact.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import select, text

from backend.app.agent.service import AgentService
from backend.app.persistence.database import (
    _apply_column_migrations,
    close_db,
    get_session_factory,
    init_db,
)
from backend.app.persistence.models.positions import DEFAULT_PERP_STRATEGY, PerpPosition
from backend.app.persistence.models.trades import PerpTrade
from backend.app.persistence.repositories.trades import PerpTradeRepository
from backend.app.persistence.runtime_state import set_runtime_value
from backend.app.persistence.sync_database import (
    create_all_sync,
    init_sync_db,
    reset_sync_db,
)
from backend.app.schemas.mobile_agent import AgentMobileSettings
# Reuse the existing Settings builder, same as the golden lifecycle test.
from backend.tests.unit.test_agent_step6 import settings as agent_settings

USER_ID = UUID("00000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 8, 22, tzinfo=UTC)
SECOND_STRATEGY = "pullback_continuation_v1"


@pytest.fixture()
async def db(tmp_path: Path):
    reset_sync_db()
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'strategy.db'}")
    init_sync_db(f"sqlite:///{tmp_path / 'strategy.db'}")
    create_all_sync()
    yield
    await close_db()
    reset_sync_db()


def _position(strategy: str | None = None) -> PerpPosition:
    kwargs: dict = {}
    if strategy is not None:
        kwargs["strategy"] = strategy
    return PerpPosition(
        position_id="pos_strategy_test",
        user_id=str(USER_ID),
        asset="BTC",
        side="long",
        size=Decimal("10"),
        entry_price=Decimal("100"),
        current_price=Decimal("100"),
        leverage=10,
        pnl_unrealized=Decimal("0"),
        stop_loss=Decimal("90"),
        initial_stop_loss=Decimal("90"),
        take_profit_1=Decimal("110"),
        take_profit_2=Decimal("120"),
        entry_atr=Decimal("5"),
        venue="dry_run",
        opening_fee_usd=Decimal("0"),
        slippage_usd=Decimal("0"),
        funding_accrued_usd=Decimal("0"),
        status="open",
        opened_at=NOW,
        updated_at=NOW,
        **kwargs,
    )


def _trade(trade_id: str, strategy: str | None = None) -> PerpTrade:
    kwargs: dict = {}
    if strategy is not None:
        kwargs["strategy"] = strategy
    return PerpTrade(
        trade_id=trade_id,
        user_id=str(USER_ID),
        asset="BTC",
        side="long",
        direction="open",
        size=Decimal("1"),
        price=Decimal("100"),
        leverage=10,
        status="confirmed",
        timestamp_utc=NOW,
        venue="dry_run",
        **kwargs,
    )


@pytest.mark.asyncio
async def test_orm_default_is_volume_profile_v1(db) -> None:
    """Rows written without an explicit strategy get the default, never NULL."""
    async with get_session_factory()() as session:
        session.add(_position())
        session.add(_trade("dry_default"))
        await session.commit()
        pos = (await session.execute(select(PerpPosition))).scalar_one()
        trade = (await session.execute(select(PerpTrade))).scalar_one()

    assert pos.strategy == DEFAULT_PERP_STRATEGY == "volume_profile_v1"
    assert trade.strategy == DEFAULT_PERP_STRATEGY


@pytest.mark.asyncio
async def test_explicit_strategy_is_preserved(db) -> None:
    """A second engine writes its own tag and the default must not clobber it."""
    async with get_session_factory()() as session:
        session.add(_position(strategy=SECOND_STRATEGY))
        session.add(_trade("dry_explicit", strategy=SECOND_STRATEGY))
        await session.commit()
        pos = (await session.execute(select(PerpPosition))).scalar_one()
        trade = (await session.execute(select(PerpTrade))).scalar_one()

    assert pos.strategy == SECOND_STRATEGY
    assert trade.strategy == SECOND_STRATEGY


@pytest.mark.asyncio
async def test_migration_backfills_legacy_rows_and_is_idempotent(db) -> None:
    """Pre-migration rows must read the default: this is what keeps the guardian
    routing safe once two guardians exist (NOTE/85, cross-check point 3)."""
    if sqlite3.sqlite_version_info < (3, 35, 0):  # pragma: no cover
        pytest.skip("DROP COLUMN needs SQLite >= 3.35")

    async with get_session_factory()() as session:
        # Simulate the pre-migration schema: column absent, one historical row.
        await session.execute(text("ALTER TABLE perp_trades DROP COLUMN strategy"))
        await session.execute(
            text(
                "INSERT INTO perp_trades (trade_id, user_id, asset, side, direction,"
                " size, price, leverage, status, timestamp_utc)"
                " VALUES ('legacy_row', :uid, 'BTC', 'long', 'open',"
                " 1, 100, 10, 'confirmed', :ts)"
            ),
            {"uid": str(USER_ID), "ts": NOW.isoformat()},
        )
        await session.commit()

    async with get_session_factory()() as session:
        # Twice on purpose: the ALTER list must stay idempotent.
        await _apply_column_migrations(session)
        await _apply_column_migrations(session)
        await session.commit()
        value = (
            await session.execute(
                text("SELECT strategy FROM perp_trades WHERE trade_id = 'legacy_row'")
            )
        ).scalar_one()

    assert value == DEFAULT_PERP_STRATEGY


@pytest.mark.asyncio
async def test_close_inherits_strategy_from_position(db) -> None:
    """The close leg written by the engine carries the position's strategy."""
    settings = AgentMobileSettings(
        perp_protection_mode="off",
        perp_smart_sl_enabled=False,
        perp_trailing_enabled=False,
        perp_time_stop_enabled=False,
        perp_breakeven_enabled=False,
        perp_fee_mode="none",
        execution_mode="dry_run",
    )
    set_runtime_value(str(USER_ID), "mobile_agent_settings", settings.model_dump_json())
    service = AgentService(
        agent_settings(), spot_registry=SimpleNamespace(), perp_registry=SimpleNamespace()
    )
    pos = _position(strategy=SECOND_STRATEGY)
    pos.current_price = Decimal("85")  # below the 90 stop: full stop-loss close

    async with get_session_factory()() as session:
        await service._check_sl_tp(session, [], [pos], NOW)
        trades = await PerpTradeRepository(session).list_for_user(str(USER_ID))

    closes = [t for t in trades if t.direction == "close"]
    assert pos.status == "closed"
    assert len(closes) == 1
    assert closes[0].strategy == SECOND_STRATEGY
