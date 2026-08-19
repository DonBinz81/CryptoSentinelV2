"""Tests for the manual daily-loss counter reset (NOTE/63).

The daily loss figure is not a stored counter: it is recomputed on every
portfolio update as a sum of realized PnL since a start point. The reset moves
that start point forward; these tests pin down the semantics:

- realized losses before the reset stop counting, later ones count;
- unrealized PnL of open positions keeps counting (open risk is never hidden);
- the reset trail (count + timestamp) increments within a day and clears on
  the first update after the next midnight — no separate rollover job.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from backend.app.agent.service import AgentService
from backend.app.core.config import get_settings
from backend.app.persistence import database
from backend.app.persistence.database import close_db, get_session_factory, init_db
from backend.app.persistence.models.trades import PerpTrade
from backend.app.persistence.repositories.pnl import PnlRepository


@pytest.fixture
async def db(tmp_path: Path):
    database._engine = None
    database._session_factory = None
    url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    await init_db(url)
    yield url
    await close_db()


def _perp_close(user_id: str, pnl: Decimal, ts: datetime) -> PerpTrade:
    return PerpTrade(
        trade_id=f"cls_test_{uuid4().hex[:8]}",
        user_id=user_id,
        asset="TEST",
        side="long",
        direction="close",
        size=Decimal("1"),
        price=Decimal("100"),
        leverage=1,
        status="confirmed",
        pnl_usd=pnl,
        timestamp_utc=ts,
    )


async def _make_portfolio(session, user_id: str) -> None:
    await PnlRepository(session).upsert_portfolio(
        user_id,
        total_equity_usd=Decimal("1000"),
        initial_equity_usd=Decimal("1000"),
        peak_equity_usd=Decimal("1000"),
    )


@pytest.mark.asyncio
async def test_reset_restarts_realized_sum(db):
    settings = get_settings()
    user_id = str(settings.default_user_id)
    service = AgentService(settings)
    now = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)

    async with get_session_factory()() as session:
        await _make_portfolio(session, user_id)
        # A loss earlier today, before the reset.
        session.add(_perp_close(user_id, Decimal("-90"), now - timedelta(hours=2)))
        await session.commit()

        await service._update_portfolio_state(session, [], [], now)
        portfolio = await PnlRepository(session).get_portfolio(user_id)
        assert portfolio.daily_loss_limit_used_pct < Decimal("-8")  # blocked territory

        result = await service.reset_daily_loss_counter(session, note="test")
        assert result["status"] == "ok"
        assert result["resets_today"] == 1
        assert result["pnl_before_pct"] < -8
        # No open positions: the counter restarts at ~0 immediately.
        assert abs(result["daily_loss_used_pct_now"]) < 0.01

        # A NEW loss after the reset counts from the new start point only.
        session.add(_perp_close(user_id, Decimal("-10"), datetime.now(UTC) + timedelta(seconds=1)))
        await session.commit()
        later = datetime.now(UTC) + timedelta(seconds=2)
        await service._update_portfolio_state(session, [], [], later)
        portfolio = await PnlRepository(session).get_portfolio(user_id)
        # -10 on ~910 equity is ~-1.1%: the old -90 is gone from the count.
        assert Decimal("-2") < portfolio.daily_loss_limit_used_pct < Decimal("-0.5")


@pytest.mark.asyncio
async def test_resets_today_increments_and_is_reported(db):
    settings = get_settings()
    user_id = str(settings.default_user_id)
    service = AgentService(settings)

    async with get_session_factory()() as session:
        await _make_portfolio(session, user_id)
        r1 = await service.reset_daily_loss_counter(session)
        r2 = await service.reset_daily_loss_counter(session)
        assert (r1["resets_today"], r2["resets_today"]) == (1, 2)
        portfolio = await PnlRepository(session).get_portfolio(user_id)
        assert portfolio.daily_counter_resets_today == 2
        assert portfolio.daily_counter_reset_at is not None


@pytest.mark.asyncio
async def test_stale_marker_clears_on_day_rollover(db):
    settings = get_settings()
    user_id = str(settings.default_user_id)
    service = AgentService(settings)

    async with get_session_factory()() as session:
        await _make_portfolio(session, user_id)
        portfolio = await PnlRepository(session).get_portfolio(user_id)
        # Reset happened yesterday evening; today is a new day.
        yesterday = datetime(2026, 8, 18, 23, 0, tzinfo=UTC)
        portfolio.daily_counter_since = yesterday
        portfolio.daily_counter_reset_at = yesterday
        portfolio.daily_counter_resets_today = 3
        await session.commit()

        today = datetime(2026, 8, 19, 0, 5, tzinfo=UTC)
        await service._update_portfolio_state(session, [], [], today)
        portfolio = await PnlRepository(session).get_portfolio(user_id)
        assert portfolio.daily_counter_since is None
        assert portfolio.daily_counter_reset_at is None
        assert portfolio.daily_counter_resets_today == 0


@pytest.mark.asyncio
async def test_first_reset_of_a_new_day_starts_from_one(db):
    settings = get_settings()
    user_id = str(settings.default_user_id)
    service = AgentService(settings)

    async with get_session_factory()() as session:
        await _make_portfolio(session, user_id)
        portfolio = await PnlRepository(session).get_portfolio(user_id)
        portfolio.daily_counter_reset_at = datetime.now(UTC) - timedelta(days=1)
        portfolio.daily_counter_resets_today = 5
        await session.commit()

        result = await service.reset_daily_loss_counter(session)
        assert result["resets_today"] == 1
