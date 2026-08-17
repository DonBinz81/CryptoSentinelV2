"""ExecutionResult, DryRunPerpVenue and the minimal venue router.

The point of this layer is that the strategy stops knowing whether an exit was
simulated or sent to a DEX: it asks, and reads an authoritative result.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import select

from backend.app.execution.venue_router import VENUE_UNAVAILABLE, PerpVenueRouter
from backend.app.execution.venues import DRY_RUN_VENUE, DryRunPerpVenue, ExecutionResult
from backend.app.persistence.database import close_db, get_session_factory, init_db
from backend.app.persistence.models.orders import PerpOrder
from backend.app.persistence.sync_database import (
    create_all_sync,
    init_sync_db,
    reset_sync_db,
)

USER_ID = UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture()
async def db(tmp_path: Path):
    reset_sync_db()
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'venue.db'}")
    init_sync_db(f"sqlite:///{tmp_path / 'venue.db'}")
    create_all_sync()
    yield
    await close_db()
    reset_sync_db()


@pytest.mark.asyncio
async def test_dry_run_venue_writes_a_confirmed_order(db) -> None:
    """The dry-run must exercise the real ORDER row, not bypass it."""
    venue = DryRunPerpVenue()
    async with get_session_factory()() as session:
        result = await venue.execute(
            session,
            position_id="pos_1",
            user_id=str(USER_ID),
            purpose="tp1",
            qty=Decimal("5"),
            price=Decimal("110"),
        )
        await session.commit()
        orders = (await session.execute(select(PerpOrder))).scalars().all()

    assert isinstance(result, ExecutionResult)
    assert result.confirmed is True
    assert result.venue == DRY_RUN_VENUE
    # A simulated venue fills in full at the requested price: no economics invented.
    assert result.executed_qty == Decimal("5")
    assert result.executed_price == Decimal("110")

    assert len(orders) == 1
    order = orders[0]
    assert order.status == "confirmed"
    assert order.filled_qty == Decimal("5")
    assert order.purpose == "tp1"
    assert order.position_id == "pos_1"
    assert order.order_id == result.venue_order_id


@pytest.mark.asyncio
async def test_dry_run_venue_records_every_purpose(db) -> None:
    """Entry, TP, ratchet and Smart SL must all be traceable to their order."""
    venue = DryRunPerpVenue()
    async with get_session_factory()() as session:
        for purpose in ("entry", "tp1", "tp2", "ratchet", "smart_sl", "stop_loss"):
            await venue.execute(
                session,
                position_id="pos_2",
                user_id=str(USER_ID),
                purpose=purpose,
                qty=Decimal("1"),
                price=Decimal("100"),
            )
        await session.commit()
        stored = (await session.execute(select(PerpOrder))).scalars().all()

    assert {o.purpose for o in stored} == {
        "entry", "tp1", "tp2", "ratchet", "smart_sl", "stop_loss",
    }
    assert all(o.status == "confirmed" for o in stored)


@pytest.mark.asyncio
async def test_router_resolves_dry_run_for_new_positions() -> None:
    router = PerpVenueRouter()
    venue = await router.resolve_entry_venue("perp", "BTC", execution_mode="dry_run")
    assert venue is not None
    assert venue.name == DRY_RUN_VENUE


@pytest.mark.asyncio
async def test_router_refuses_to_open_live_without_a_venue() -> None:
    """No live perp venue exists yet: it must fail, not silently simulate."""
    router = PerpVenueRouter()
    assert await router.resolve_entry_venue("perp", "BTC", execution_mode="live") is None
    assert VENUE_UNAVAILABLE == "venue_unavailable"


def test_router_reads_the_venue_from_the_position_and_never_reselects() -> None:
    """An open position keeps its venue: entry, TP, ratchet and close go there."""
    router = PerpVenueRouter()
    position = SimpleNamespace(position_id="pos_3", venue=DRY_RUN_VENUE)
    venue = router.resolve_position_venue(position)
    assert venue is not None and venue.name == DRY_RUN_VENUE


def test_router_rejects_a_position_without_venue() -> None:
    """No hidden fallback: an unknown venue means the operation is refused."""
    router = PerpVenueRouter()
    assert router.resolve_position_venue(SimpleNamespace(position_id="pos_4", venue=None)) is None
    assert router.resolve_position_venue(SimpleNamespace(position_id="pos_5", venue="aster")) is None


def test_execution_result_defaults_are_conservative() -> None:
    """Venue-specific identifiers stay empty until a venue actually produces them."""
    result = ExecutionResult(
        confirmed=True,
        venue=DRY_RUN_VENUE,
        executed_qty=Decimal("1"),
        executed_price=Decimal("100"),
    )
    assert result.fee is None
    assert result.venue_order_id is None
    assert result.venue_execution_id is None
    assert result.tx_hash is None
    assert result.status == "confirmed"


@pytest.mark.asyncio
async def test_router_refuses_a_pair_the_venue_does_not_list(monkeypatch) -> None:
    """A pair the venue does not list must not open, dry-run included.

    A simulation that opens positions the live venue would refuse is not a
    rehearsal of anything.
    """

    import backend.app.execution.venue_router as module

    async def _availability(symbols):
        return {"COMP": {"perp": {"venue": "aster", "status": "unavailable"}}}

    monkeypatch.setattr(
        module, "get_venue_availability_service", lambda: SimpleNamespace(availability=_availability)
    )
    router = PerpVenueRouter()
    assert await router.resolve_entry_venue("perp", "COMP", execution_mode="dry_run") is None


@pytest.mark.asyncio
async def test_router_still_opens_when_availability_is_unknown(monkeypatch) -> None:
    """`unknown` is our own blind spot, not a missing market: it must not block."""

    import backend.app.execution.venue_router as module

    async def _availability(symbols):
        return {"BTC": {"perp": {"venue": "aster", "status": "unknown"}}}

    monkeypatch.setattr(
        module, "get_venue_availability_service", lambda: SimpleNamespace(availability=_availability)
    )
    router = PerpVenueRouter()
    venue = await router.resolve_entry_venue("perp", "BTC", execution_mode="dry_run")
    assert venue is not None


@pytest.mark.asyncio
async def test_router_opens_when_the_availability_check_itself_fails(monkeypatch) -> None:
    """A broken check must not become a trading halt."""

    import backend.app.execution.venue_router as module

    async def _availability(symbols):
        raise RuntimeError("aster unreachable")

    monkeypatch.setattr(
        module, "get_venue_availability_service", lambda: SimpleNamespace(availability=_availability)
    )
    router = PerpVenueRouter()
    venue = await router.resolve_entry_venue("perp", "BTC", execution_mode="dry_run")
    assert venue is not None
