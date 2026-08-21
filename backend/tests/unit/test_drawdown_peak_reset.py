"""Tests for the manual drawdown-peak reset (NOTE/83).

Twin of test_daily_counter_reset.py. The drawdown reference peak only ever
grows (``peak = max(peak, total)``), so a fired drawdown cap has no natural
exit path. The reset re-bases the peak at the current equity; these tests pin
down the semantics:

- the drawdown drops to ~0 right after the reset (peak == equity);
- the cap stays armed: a NEW loss from the re-based peak counts in full;
- max_drawdown_pct (historical record) is NOT rewound by the reset;
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
async def test_reset_rebases_peak_and_zeroes_drawdown(db):
    settings = get_settings()
    user_id = str(settings.default_user_id)
    service = AgentService(settings)
    now = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)

    async with get_session_factory()() as session:
        await _make_portfolio(session, user_id)
        # A realized loss puts the portfolio well below its 1000 peak.
        session.add(_perp_close(user_id, Decimal("-120"), now - timedelta(hours=2)))
        await session.commit()

        await service._update_portfolio_state(session, [], [], now)
        portfolio = await PnlRepository(session).get_portfolio(user_id)
        assert portfolio.drawdown_pct == Decimal("12.00")  # 120 on peak 1000
        max_dd_before = portfolio.max_drawdown_pct

        result = await service.reset_drawdown_peak(session, note="test")
        assert result["status"] == "ok"
        assert result["resets_today"] == 1
        assert result["peak_before_usd"] == 1000.0
        assert result["drawdown_before_pct"] == 12.0
        # Peak == equity now: drawdown restarts at ~0.
        assert abs(result["drawdown_pct_now"]) < 0.01
        portfolio = await PnlRepository(session).get_portfolio(user_id)
        assert portfolio.peak_equity_usd == Decimal("880")
        # The historical record is untouched by the reset.
        assert portfolio.max_drawdown_pct == max_dd_before


@pytest.mark.asyncio
async def test_cap_stays_armed_on_the_new_stretch(db):
    settings = get_settings()
    user_id = str(settings.default_user_id)
    service = AgentService(settings)
    now = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)

    async with get_session_factory()() as session:
        await _make_portfolio(session, user_id)
        session.add(_perp_close(user_id, Decimal("-120"), now - timedelta(hours=2)))
        await session.commit()
        await service._update_portfolio_state(session, [], [], now)

        await service.reset_drawdown_peak(session)

        # A NEW loss after the reset counts in full from the 880 base.
        session.add(_perp_close(user_id, Decimal("-88"), now + timedelta(hours=1)))
        await session.commit()
        await service._update_portfolio_state(session, [], [], now + timedelta(hours=2))
        portfolio = await PnlRepository(session).get_portfolio(user_id)
        assert portfolio.drawdown_pct == Decimal("10.00")  # 88 on peak 880


@pytest.mark.asyncio
async def test_resets_today_increments_and_is_reported(db):
    settings = get_settings()
    user_id = str(settings.default_user_id)
    service = AgentService(settings)

    async with get_session_factory()() as session:
        await _make_portfolio(session, user_id)
        r1 = await service.reset_drawdown_peak(session)
        r2 = await service.reset_drawdown_peak(session)
        assert (r1["resets_today"], r2["resets_today"]) == (1, 2)
        portfolio = await PnlRepository(session).get_portfolio(user_id)
        assert portfolio.drawdown_peak_resets_today == 2
        assert portfolio.drawdown_peak_reset_at is not None


@pytest.mark.asyncio
async def test_stale_trail_clears_on_day_rollover(db):
    settings = get_settings()
    user_id = str(settings.default_user_id)
    service = AgentService(settings)

    async with get_session_factory()() as session:
        await _make_portfolio(session, user_id)
        portfolio = await PnlRepository(session).get_portfolio(user_id)
        # Reset happened yesterday evening; today is a new day.
        yesterday = datetime(2026, 8, 19, 23, 0, tzinfo=UTC)
        portfolio.drawdown_peak_reset_at = yesterday
        portfolio.drawdown_peak_resets_today = 3
        await session.commit()

        today = datetime(2026, 8, 20, 0, 5, tzinfo=UTC)
        await service._update_portfolio_state(session, [], [], today)
        portfolio = await PnlRepository(session).get_portfolio(user_id)
        assert portfolio.drawdown_peak_reset_at is None
        assert portfolio.drawdown_peak_resets_today == 0


@pytest.mark.asyncio
async def test_first_reset_of_a_new_day_starts_from_one(db):
    settings = get_settings()
    user_id = str(settings.default_user_id)
    service = AgentService(settings)

    async with get_session_factory()() as session:
        await _make_portfolio(session, user_id)
        portfolio = await PnlRepository(session).get_portfolio(user_id)
        portfolio.drawdown_peak_reset_at = datetime.now(UTC) - timedelta(days=1)
        portfolio.drawdown_peak_resets_today = 5
        await session.commit()

        result = await service.reset_drawdown_peak(session)
        assert result["resets_today"] == 1
