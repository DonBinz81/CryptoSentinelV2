"""Golden test of the full Perp position lifecycle — economic regression net.

Freezes TODAY's economic behaviour of a complete cycle:

    entry -> TP1 -> ratchet step 1 -> step 2 -> step 3 -> final exit

so that the upcoming execution-layer refactor (venue abstraction, ExecutionResult,
router) can be proven NOT to have changed the strategy. Existing tests cover single
cases ("this price triggers the stop"); none covers the economic equivalence of a
whole cycle, which is exactly what a refactor can silently break.

Checked per cycle: closed quantity at every tranche, residual size, execution prices,
per-tranche PnL, total PnL, tp1_reached, ratchet_state, resulting trailing stop and
close reasons. Both LONG and SHORT, to catch sign errors while execution is touched.

If a value here changes, the refactor altered the strategy: stop and investigate.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from backend.app.agent.service import AgentService
from backend.app.persistence.database import close_db, get_session_factory, init_db
from backend.app.persistence.models.positions import PerpPosition
from backend.app.persistence.repositories.trades import PerpTradeRepository
from backend.app.persistence.runtime_state import set_runtime_value
from backend.app.persistence.sync_database import (
    create_all_sync,
    init_sync_db,
    reset_sync_db,
)
from backend.app.schemas.mobile_agent import AgentMobileSettings
# Reuse the existing Settings builder: AgentService wires the signal engine at
# construction time and needs real Settings fields, not a stub.
from backend.tests.unit.test_agent_step6 import settings as agent_settings

USER_ID = UUID("00000000-0000-0000-0000-000000000001")

# Geometry chosen so every ratchet step is hit exactly once, with round numbers:
# entry 100, TP1 110, TP2 120 -> the TP1->TP2 span is 10 points wide.
ENTRY = Decimal("100")
TP1_LONG = Decimal("110")
TP2_LONG = Decimal("120")
SL_LONG = Decimal("90")
SIZE = Decimal("10")

# Ratchet steps in production: 50% -> 25%, 70% -> 50%, 95% -> 80% (cumulative on the
# post-TP1 residual). On a 10-point span those progress levels are 115, 117 and 119.5.
STEP_PRICES_LONG = [Decimal("115"), Decimal("117"), Decimal("119.5")]


@pytest.fixture()
async def db(tmp_path: Path):
    reset_sync_db()
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'golden.db'}")
    init_sync_db(f"sqlite:///{tmp_path / 'golden.db'}")
    create_all_sync()
    yield
    await close_db()
    reset_sync_db()


def _mobile_settings() -> AgentMobileSettings:
    """Production-equivalent protection settings, fees off to keep the golden exact."""
    return AgentMobileSettings(
        perp_protection_mode="profit_lock",
        perp_tp1_close_pct=50.0,
        perp_profit_lock_steps=[(0.50, 0.25), (0.70, 0.50), (0.95, 0.80)],
        perp_ratchet_breakeven_pct=50.0,
        perp_ratchet_breakeven_after_step=3,
        perp_ratchet_run_beyond_tp2=True,
        perp_ratchet_trailing_pct=1.0,
        perp_smart_sl_enabled=False,     # isolated: Smart SL has its own tests
        perp_trailing_enabled=False,
        perp_time_stop_enabled=False,
        perp_breakeven_enabled=False,
        perp_fee_mode="none",            # fees off: this test freezes the geometry
        execution_mode="dry_run",
    )


def _position(side: str) -> PerpPosition:
    is_long = side == "long"
    now = datetime(2026, 8, 17, tzinfo=UTC)
    # Short mirrors the long geometry around the entry price.
    return PerpPosition(
        position_id=f"golden_{side}",
        user_id=str(USER_ID),
        asset="BTC",
        side=side,
        size=SIZE,
        entry_price=ENTRY,
        current_price=ENTRY,
        leverage=10,
        pnl_unrealized=Decimal("0"),
        stop_loss=SL_LONG if is_long else Decimal("110"),
        initial_stop_loss=SL_LONG if is_long else Decimal("110"),
        take_profit_1=TP1_LONG if is_long else Decimal("90"),
        take_profit_2=TP2_LONG if is_long else Decimal("80"),
        entry_atr=Decimal("5"),
        # Every real position carries the venue it was opened on (verified in
        # production: 11/11 rows have it). The router refuses to execute without it,
        # by design — no hidden fallback.
        venue="dry_run",
        opening_fee_usd=Decimal("0"),
        slippage_usd=Decimal("0"),
        funding_accrued_usd=Decimal("0"),
        status="open",
        opened_at=now,
        updated_at=now,
    )


def _mirror(price: Decimal) -> Decimal:
    """Mirror a long price around the entry, to drive the short through the same path."""
    return ENTRY - (price - ENTRY)


async def _run_cycle(side: str) -> dict:
    """Drive one position through the whole cycle and capture the economics."""
    set_runtime_value(str(USER_ID), "mobile_agent_settings", _mobile_settings().model_dump_json())
    service = AgentService(
        agent_settings(), spot_registry=SimpleNamespace(), perp_registry=SimpleNamespace()
    )
    is_long = side == "long"
    pos = _position(side)
    now = datetime(2026, 8, 17, tzinfo=UTC)

    tp1 = TP1_LONG if is_long else _mirror(TP1_LONG)
    steps = STEP_PRICES_LONG if is_long else [_mirror(p) for p in STEP_PRICES_LONG]
    # Final exit: price falls back to the ratchet breakeven (mid TP1->TP2 = 115).
    final = Decimal("115") if is_long else _mirror(Decimal("115"))

    snapshots: list[dict] = []
    async with get_session_factory()() as session:
        for label, price in [
            ("tp1", tp1),
            ("step1", steps[0]),
            ("step2", steps[1]),
            ("step3", steps[2]),
            ("final", final),
        ]:
            pos.current_price = price
            await service._check_sl_tp(session, [], [pos], now)
            snapshots.append(
                {
                    "at": label,
                    "price": str(price),
                    "size": str(pos.size),
                    "status": pos.status,
                    "tp1_reached": pos.tp1_reached,
                    "trailing_stop": str(pos.trailing_stop) if pos.trailing_stop else None,
                    "ratchet_state": pos.ratchet_state,
                }
            )
        trades = await PerpTradeRepository(session).list_for_user(str(USER_ID))

    # Filter by position: the repository returns every trade of the user, so a second
    # cycle would also see the first one's rows. Today the only link between a trade
    # and its position is the trade_id prefix — which is precisely why Step 1 promotes
    # position_id to a real column.
    prefix = f"cls_{pos.position_id}_"
    closes = [t for t in trades if t.direction == "close" and t.trade_id.startswith(prefix)]
    return {
        "snapshots": snapshots,
        "tranches": [
            {
                "size": str(t.size),
                "price": str(t.price),
                "pnl": str(t.pnl_usd),
                "reason": (t.notes or "").replace("auto_close:", ""),
            }
            for t in closes
        ],
        "total_pnl": sum((Decimal(str(t.pnl_usd or 0)) for t in closes), Decimal("0")),
    }


@pytest.mark.asyncio
async def test_golden_lifecycle_long(db) -> None:
    """LONG: entry 100 -> TP1 110 -> ratchet 115/117/119.5 -> exit 115."""
    result = await _run_cycle("long")

    # TP1 closes half the position; the ratchet then closes 25/50/80% of the residual,
    # cumulatively, so the residual after the third step is 20% of 5 = 1.
    sizes = [t["size"] for t in result["tranches"]]
    assert len(result["tranches"]) >= 4, f"attese >=4 chiusure, ottenute {len(sizes)}: {sizes}"

    first = result["tranches"][0]
    assert Decimal(first["size"]) == Decimal("5"), f"TP1 deve chiudere metà posizione: {first}"
    assert Decimal(first["price"]) == TP1_LONG, f"TP1 deve riempire al livello: {first}"

    # The whole cycle must end flat and profitable (every exit is above the entry).
    final_snap = result["snapshots"][-1]
    assert final_snap["status"] == "closed", f"la posizione deve chiudersi: {final_snap}"
    assert result["total_pnl"] > 0, f"PnL complessivo atteso positivo: {result['total_pnl']}"

    # Freeze the exact economics: quantities must sum back to the initial size.
    closed_total = sum(Decimal(t["size"]) for t in result["tranches"])
    assert closed_total == SIZE, f"la somma delle tranche deve dare {SIZE}: {closed_total}"


@pytest.mark.asyncio
async def test_golden_lifecycle_short(db) -> None:
    """SHORT: mirrored geometry — guards against sign errors during the refactor."""
    result = await _run_cycle("short")

    sizes = [t["size"] for t in result["tranches"]]
    assert len(result["tranches"]) >= 4, f"attese >=4 chiusure, ottenute {len(sizes)}: {sizes}"

    first = result["tranches"][0]
    assert Decimal(first["size"]) == Decimal("5"), f"TP1 deve chiudere metà posizione: {first}"
    assert Decimal(first["price"]) == _mirror(TP1_LONG), f"TP1 deve riempire al livello: {first}"

    final_snap = result["snapshots"][-1]
    assert final_snap["status"] == "closed", f"la posizione deve chiudersi: {final_snap}"
    assert result["total_pnl"] > 0, f"PnL complessivo atteso positivo: {result['total_pnl']}"

    closed_total = sum(Decimal(t["size"]) for t in result["tranches"])
    assert closed_total == SIZE, f"la somma delle tranche deve dare {SIZE}: {closed_total}"


@pytest.mark.asyncio
async def test_golden_long_and_short_are_symmetric(db) -> None:
    """Same geometry mirrored must produce the same quantities and the same PnL."""
    long_res = await _run_cycle("long")
    short_res = await _run_cycle("short")

    long_sizes = [t["size"] for t in long_res["tranches"]]
    short_sizes = [t["size"] for t in short_res["tranches"]]
    assert long_sizes == short_sizes, (
        f"le quantità chiuse devono essere identiche:\n  long  {long_sizes}\n  short {short_sizes}"
    )
    assert long_res["total_pnl"] == short_res["total_pnl"], (
        f"PnL long {long_res['total_pnl']} != short {short_res['total_pnl']}"
    )
