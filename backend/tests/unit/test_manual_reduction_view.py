"""Badge fields: how much of a Perp position the user closed by hand.

Runnable locally: this touches the read side only (views + repositories), never
``agent.service``, so it does not pull in the web3/ckzg chain that has no
Windows ARM64 wheel.

The property that matters: a position shrinks through TP1, ratchet steps and
Smart SL sells too. Those must NEVER count as manual interventions — otherwise
the badge would appear on positions the user never touched.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from backend.app.persistence.database import close_db, get_session_factory, init_db
from backend.app.persistence.models.positions import PerpPosition
from backend.app.persistence.models.trades import PerpTrade
from backend.app.persistence.views import ViewService

USER_ID = str(UUID("00000000-0000-0000-0000-000000000001"))
NOW = datetime(2026, 9, 3, tzinfo=UTC)


@pytest.fixture()
async def db(tmp_path: Path):
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'badge.db'}")
    yield
    await close_db()


def _position(position_id: str, size: Decimal) -> PerpPosition:
    return PerpPosition(
        position_id=position_id,
        user_id=USER_ID,
        asset="LINK",
        side="long",
        size=size,
        entry_price=Decimal("100"),
        current_price=Decimal("100"),
        leverage=10,
        pnl_unrealized=Decimal("0"),
        status="open",
        opened_at=NOW,
        updated_at=NOW,
    )


def _trade(position_id: str, direction: str, size: Decimal, notes: str, seq: int) -> PerpTrade:
    return PerpTrade(
        trade_id=f"t{seq}_{position_id}",
        position_id=position_id,
        user_id=USER_ID,
        asset="LINK",
        side="long",
        direction=direction,
        size=size,
        price=Decimal("100"),
        leverage=10,
        status="confirmed",
        venue="dry_run",
        timestamp_utc=NOW,
        notes=notes,
        pnl_usd=Decimal("1"),
    )


async def _perp_view(rows: list):
    async with get_session_factory()() as session:
        for row in rows:
            session.add(row)
        await session.commit()
        return await ViewService(session).perp_view(USER_ID)


async def _first_position(rows: list):
    view = await _perp_view(rows)
    assert view.open_positions, "nessuna posizione aperta nella vista"
    return view.open_positions[0]


# ── nessun intervento umano ────────────────────────────────────────────────


async def test_untouched_position_has_no_badge(db) -> None:
    pos = await _first_position(
        [
            _position("pos_a", Decimal("10")),
            _trade("pos_a", "open", Decimal("10"), "dry_run_step6", 1),
        ]
    )
    assert pos.manual_close_count == 0
    assert pos.manual_reduced_pct is None


async def test_automatic_exits_alone_never_produce_a_badge(db) -> None:
    """Il punto che conta: TP1, ratchet e Smart SL riducono la size, ma non
    sono interventi dell'utente. Senza questa distinzione il badge comparirebbe
    su posizioni mai toccate a mano."""
    pos = await _first_position(
        [
            _position("pos_b", Decimal("2.5")),
            _trade("pos_b", "open", Decimal("10"), "dry_run_step6", 1),
            _trade("pos_b", "close", Decimal("5"), "auto_close:take_profit_1_partial", 2),
            _trade("pos_b", "close", Decimal("1.25"), "auto_close:ratchet_step_partial", 3),
            _trade("pos_b", "close", Decimal("1.25"), "auto_close:smart_sl_sell_l1", 4),
        ]
    )
    assert pos.manual_close_count == 0
    assert pos.manual_reduced_pct is None


# ── interventi umani ───────────────────────────────────────────────────────


async def test_one_manual_close_is_measured_on_the_original_size(db) -> None:
    pos = await _first_position(
        [
            _position("pos_c", Decimal("5")),
            _trade("pos_c", "open", Decimal("10"), "dry_run_step6", 1),
            _trade("pos_c", "close", Decimal("5"), "manual_close:manual_partial_close", 2),
        ]
    )
    assert pos.manual_close_count == 1
    assert pos.manual_reduced_pct == "50.00"


async def test_only_the_manual_share_is_counted(db) -> None:
    """Scenario reale (FET, 3/09): manuale 50%, poi TP1 automatico, poi un
    secondo intervento manuale. La percentuale deve riflettere SOLO i due
    interventi umani, non la riduzione complessiva della posizione."""
    pos = await _first_position(
        [
            _position("pos_d", Decimal("1")),
            _trade("pos_d", "open", Decimal("2540.2235"), "dry_run_step6", 1),
            _trade("pos_d", "close", Decimal("1270.1117"), "manual_close:manual_partial_close", 2),
            _trade("pos_d", "close", Decimal("952.5838"), "auto_close:take_profit_1_partial", 3),
            _trade("pos_d", "close", Decimal("317.5279"), "manual_close:manual_full_close", 4),
        ]
    )
    assert pos.manual_close_count == 2
    # (1270,1117 + 317,5279) / 2540,2235 = 62,50%
    assert pos.manual_reduced_pct == "62.50"


async def test_two_manual_closes_sum_up(db) -> None:
    pos = await _first_position(
        [
            _position("pos_e", Decimal("2.5")),
            _trade("pos_e", "open", Decimal("10"), "dry_run_step6", 1),
            _trade("pos_e", "close", Decimal("5"), "manual_close:manual_partial_close", 2),
            _trade("pos_e", "close", Decimal("2.5"), "manual_close:manual_partial_close", 3),
        ]
    )
    assert pos.manual_close_count == 2
    assert pos.manual_reduced_pct == "75.00"


# ── casi limite ────────────────────────────────────────────────────────────


async def test_unknown_opening_size_reports_count_without_percentage(db) -> None:
    """Righe storiche i cui trade non hanno position_id: il conteggio resta
    affidabile, la percentuale no. Meglio nessuna percentuale che una sbagliata."""
    pos = await _first_position(
        [
            _position("pos_f", Decimal("5")),
            _trade("pos_f", "close", Decimal("5"), "manual_close:manual_partial_close", 2),
        ]
    )
    assert pos.manual_close_count == 1
    assert pos.manual_reduced_pct is None


async def test_each_position_is_measured_separately(db) -> None:
    """Una posizione ridotta a mano non deve contaminare le altre della lista."""
    view = await _perp_view(
        [
            _position("pos_g", Decimal("5")),
            _trade("pos_g", "open", Decimal("10"), "dry_run_step6", 1),
            _trade("pos_g", "close", Decimal("5"), "manual_close:manual_partial_close", 2),
            _position("pos_h", Decimal("10")),
            _trade("pos_h", "open", Decimal("10"), "dry_run_step6", 3),
        ]
    )
    by_id = {p.position_id: p for p in view.open_positions}
    assert by_id["pos_g"].manual_close_count == 1
    assert by_id["pos_g"].manual_reduced_pct == "50.00"
    assert by_id["pos_h"].manual_close_count == 0
    assert by_id["pos_h"].manual_reduced_pct is None


async def test_another_user_positions_are_not_mixed_in(db) -> None:
    other = _position("pos_i", Decimal("5"))
    other.user_id = "00000000-0000-0000-0000-0000000000ff"
    other_trade = _trade("pos_i", "close", Decimal("5"), "manual_close:manual_partial_close", 9)
    other_trade.user_id = other.user_id

    view = await _perp_view(
        [
            _position("pos_j", Decimal("10")),
            _trade("pos_j", "open", Decimal("10"), "dry_run_step6", 1),
            other,
            other_trade,
        ]
    )
    ids = {p.position_id for p in view.open_positions}
    assert ids == {"pos_j"}
    assert view.open_positions[0].manual_close_count == 0
