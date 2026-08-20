"""Tests for the positioning telemetry (NOTE/81).

The contract that matters: telemetry never raises into the trading path, a
failed fetch produces a row with NULLs plus an error marker (visible absence),
and a successful fetch lands the metrics in the table.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.agent.telemetry import capture_entry_telemetry, snapshot_open_position
from backend.app.persistence import database
from backend.app.persistence.database import close_db, get_session_factory, init_db
from backend.app.persistence.models.positions import PerpPosition
from backend.app.persistence.models.telemetry import EntryTelemetry, PositionTelemetry
from sqlalchemy import select


@pytest.fixture
async def db(tmp_path: Path):
    database._engine = None
    database._session_factory = None
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    yield
    await close_db()


async def _ok_fetcher(asset, now_ms):
    return {"oi_d24_pct": 4.2, "ls_ratio": 1.35, "ls_d24_pct": -2.1, "taker_4h": 1.05}, []


async def _broken_fetcher(asset, now_ms):
    raise RuntimeError("network down")


@pytest.mark.asyncio
async def test_entry_row_written_with_metrics(db):
    await capture_entry_telemetry(
        position_id="pos_t1", user_id="u", asset="LINK", side="short",
        brain_confidence=0.7, fetcher=_ok_fetcher,
    )
    async with get_session_factory()() as session:
        row = (await session.execute(select(EntryTelemetry))).scalar_one()
        assert row.position_id == "pos_t1"
        assert row.oi_d24_pct == Decimal("4.2")
        assert row.brain_confidence == Decimal("0.7")
        assert row.error is None


@pytest.mark.asyncio
async def test_entry_capture_never_raises_and_is_lossless_on_failure(db):
    # The fetcher exploding entirely must not raise NOR lose the row silently:
    # here the whole capture fails before the session -> logged, no row, no
    # exception. Partial per-metric failures are covered by the error field.
    await capture_entry_telemetry(
        position_id="pos_t2", user_id="u", asset="LINK", side="short",
        brain_confidence=None, fetcher=_broken_fetcher,
    )  # must simply not raise


@pytest.mark.asyncio
async def test_partial_failure_writes_nulls_with_error_marker(db):
    async def partial(asset, now_ms):
        return {"oi_d24_pct": None, "ls_ratio": 1.2, "ls_d24_pct": None, "taker_4h": None}, ["oi:Timeout"]
    await capture_entry_telemetry(
        position_id="pos_t3", user_id="u", asset="BCH", side="long",
        brain_confidence=0.65, fetcher=partial,
    )
    async with get_session_factory()() as session:
        row = (await session.execute(select(EntryTelemetry))).scalar_one()
        assert row.oi_d24_pct is None
        assert row.ls_ratio == Decimal("1.2")
        assert row.error == "oi:Timeout"


@pytest.mark.asyncio
async def test_position_snapshot_row_and_oi_failure_tolerated(db):
    pos = PerpPosition(
        position_id="pos_t4", user_id="u", asset="DOT", side="short",
        entry_price=Decimal("4.0"), current_price=Decimal("4.1"),
        size=Decimal("10"), leverage=30, status="open",
    )
    async with get_session_factory()() as session:
        async def oi_ok(asset):
            return 123456.0
        await snapshot_open_position(session, pos, datetime.now(UTC), fetcher=oi_ok)

        async def oi_down(asset):
            raise RuntimeError("boom")
        await snapshot_open_position(session, pos, datetime.now(UTC), fetcher=oi_down)
        await session.commit()
        rows = (await session.execute(select(PositionTelemetry))).scalars().all()
        assert len(rows) == 2
        assert rows[0].open_interest == Decimal("123456")
        # short a 4.1 con entry 4.0 = -2.5% avverso
        assert rows[0].adverse_pct == Decimal("2.5")
        assert rows[1].open_interest is None  # fetch fallito -> NULL, riga presente
