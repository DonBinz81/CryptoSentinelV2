"""Manual close of a single Perp position — engine-level tests.

VPS-only: importing ``agent.service`` pulls in web3 -> eth-account -> ckzg, which
has no Windows ARM64 wheel. The pure arithmetic these tests rely on is covered
locally by ``test_manual_close_math.py``; what is verified here is the part that
needs the real engine — that a human reduction resizes the position without
pretending to be TP1, without waking the regime guardian, and without letting a
retry close a second slice.
"""

from __future__ import annotations

import json
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
from backend.tests.unit.test_agent_step6 import settings as agent_settings

USER_ID = UUID("00000000-0000-0000-0000-000000000001")

ENTRY = Decimal("100")
SIZE = Decimal("10")


@pytest.fixture()
async def db(tmp_path: Path):
    reset_sync_db()
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'manual_close.db'}")
    init_sync_db(f"sqlite:///{tmp_path / 'manual_close.db'}")
    create_all_sync()
    yield
    await close_db()
    reset_sync_db()


def _mobile_settings(**overrides) -> AgentMobileSettings:
    base = dict(
        perp_protection_mode="profit_lock",
        perp_tp1_close_pct=50.0,
        perp_profit_lock_steps=[(0.50, 0.25), (0.70, 0.50), (0.95, 0.80)],
        perp_smart_sl_enabled=False,
        perp_trailing_enabled=False,
        perp_time_stop_enabled=False,
        perp_breakeven_enabled=False,
        perp_fee_mode="none",
        execution_mode="dry_run",
    )
    base.update(overrides)
    return AgentMobileSettings(**base)


def _service(**setting_overrides) -> AgentService:
    set_runtime_value(
        str(USER_ID), "mobile_agent_settings", _mobile_settings(**setting_overrides).model_dump_json()
    )
    service = AgentService(
        agent_settings(), spot_registry=SimpleNamespace(), perp_registry=SimpleNamespace()
    )

    # The manual path refreshes the live price best-effort; in tests that would
    # be a real Binance call. Neutralised: these tests are about bookkeeping.
    async def _no_refresh(*args, **kwargs):
        return None

    service._refresh_position_prices = _no_refresh  # type: ignore[method-assign]
    return service


def _position(
    side: str = "long",
    *,
    position_id: str = "pos_manual",
    size: Decimal = SIZE,
    price: Decimal = ENTRY,
    **overrides,
) -> PerpPosition:
    is_long = side == "long"
    now = datetime(2026, 8, 27, tzinfo=UTC)
    fields = dict(
        position_id=position_id,
        user_id=str(USER_ID),
        asset="LINK",
        side=side,
        size=size,
        entry_price=ENTRY,
        current_price=price,
        leverage=10,
        pnl_unrealized=Decimal("0"),
        stop_loss=Decimal("90") if is_long else Decimal("110"),
        initial_stop_loss=Decimal("90") if is_long else Decimal("110"),
        take_profit_1=Decimal("110") if is_long else Decimal("90"),
        take_profit_2=Decimal("120") if is_long else Decimal("80"),
        entry_atr=Decimal("5"),
        venue="dry_run",
        opening_fee_usd=Decimal("0"),
        slippage_usd=Decimal("0"),
        funding_accrued_usd=Decimal("0"),
        status="open",
        opened_at=now,
        updated_at=now,
    )
    fields.update(overrides)
    return PerpPosition(**fields)


async def _persist(session, pos: PerpPosition) -> None:
    session.add(pos)
    await session.commit()


async def _close(service, session, pos, *, pct, expected=None, key="key-0001-aaaa"):
    return await service.manual_close_perp_position(
        session,
        position_id=pos.position_id,
        percentage=pct,
        expected_size=expected if expected is not None else pos.size,
        idempotency_key=key,
    )


# ── the four presets, both sides ───────────────────────────────────────────


@pytest.mark.parametrize("side", ["long", "short"])
@pytest.mark.parametrize(
    ("pct", "closed", "left"), [(25, "2.5", "7.5"), (50, "5", "5"), (75, "7.5", "2.5")]
)
async def test_partial_presets_resize_the_position(db, side, pct, closed, left) -> None:
    service = _service()
    async with get_session_factory()() as session:
        pos = _position(side)
        await _persist(session, pos)
        result = await _close(service, session, pos, pct=pct)

    assert result["status"] == "confirmed"
    assert Decimal(result["executed_qty"]) == Decimal(closed)
    assert Decimal(result["remaining_qty"]) == Decimal(left)
    assert result["position_status"] == "open"
    assert result["close_reason"] == "manual_partial_close"
    assert pos.size == Decimal(left)


@pytest.mark.parametrize("side", ["long", "short"])
async def test_full_close_closes_the_position(db, side) -> None:
    service = _service()
    async with get_session_factory()() as session:
        pos = _position(side)
        await _persist(session, pos)
        result = await _close(service, session, pos, pct=100)

    assert result["status"] == "confirmed"
    assert result["position_status"] == "closed"
    assert result["close_reason"] == "manual_full_close"
    assert Decimal(result["remaining_qty"]) == Decimal("0")
    assert pos.status == "closed"


async def test_percentage_applies_to_the_residual(db) -> None:
    """50% then 50% leaves a quarter, not zero."""
    service = _service()
    async with get_session_factory()() as session:
        pos = _position()
        await _persist(session, pos)
        await _close(service, session, pos, pct=50, key="key-first-0001")
        second = await _close(
            service, session, pos, pct=50, expected=pos.size, key="key-second-002"
        )

    assert Decimal(second["executed_qty"]) == Decimal("2.5")
    assert Decimal(second["remaining_qty"]) == Decimal("2.5")


# ── the TP1 flag: the whole point of the feature ───────────────────────────


async def test_manual_partial_does_not_set_tp1_reached(db) -> None:
    service = _service()
    async with get_session_factory()() as session:
        pos = _position()
        await _persist(session, pos)
        await _close(service, session, pos, pct=25)

    assert pos.tp1_reached is False


async def test_real_tp1_still_sets_the_flag(db) -> None:
    """The regression guard: separating the two must not disarm the real TP1."""
    service = _service()
    now = datetime(2026, 8, 27, tzinfo=UTC)
    async with get_session_factory()() as session:
        pos = _position(price=Decimal("110"))
        await _persist(session, pos)
        await service._check_sl_tp(session, [], [pos], now)

    assert pos.tp1_reached is True


async def test_real_tp1_still_works_after_a_manual_reduction(db) -> None:
    """A manual 25% must not make the engine skip the TP1 that follows."""
    service = _service()
    now = datetime(2026, 8, 27, tzinfo=UTC)
    async with get_session_factory()() as session:
        pos = _position()
        await _persist(session, pos)
        await _close(service, session, pos, pct=25)
        assert pos.tp1_reached is False

        pos.current_price = Decimal("110")
        await service._check_sl_tp(session, [], [pos], now)
        size_after_tp1 = pos.size

    assert pos.tp1_reached is True
    # TP1 closes 50% of what is left (7.5) -> 3.75 remaining.
    assert size_after_tp1 == Decimal("3.75")


# ── ratchet renormalisation ────────────────────────────────────────────────


async def test_ratchet_state_is_rescaled_and_the_stage_kept(db) -> None:
    service = _service()
    armed = json.dumps({"base_size": "10", "closed_frac": "0.25", "last_step": 0})
    async with get_session_factory()() as session:
        pos = _position(tp1_reached=True, ratchet_state=armed)
        await _persist(session, pos)
        await _close(service, session, pos, pct=50)
        state = json.loads(pos.ratchet_state)

    assert Decimal(state["base_size"]) == Decimal("5")
    assert state["closed_frac"] == "0.25"
    assert state["last_step"] == 0


async def test_ratchet_not_armed_stays_absent(db) -> None:
    service = _service()
    async with get_session_factory()() as session:
        pos = _position()
        await _persist(session, pos)
        await _close(service, session, pos, pct=50)

    assert not pos.ratchet_state


async def test_next_ratchet_step_does_not_empty_the_residual(db) -> None:
    """Without renormalisation the first step after a manual reduction would
    ask for a quantity computed on the old base and, clamped, close everything."""
    service = _service()
    armed = json.dumps({"base_size": "10", "closed_frac": "0.0", "last_step": -1})
    now = datetime(2026, 8, 27, tzinfo=UTC)
    async with get_session_factory()() as session:
        pos = _position(
            tp1_reached=True, ratchet_state=armed, max_price=Decimal("110")
        )
        await _persist(session, pos)
        await _close(service, session, pos, pct=50)  # 10 -> 5, base 10 -> 5
        # Drive progress to the first ratchet step (50% of TP1->TP2 = 115).
        pos.current_price = Decimal("115")
        pos.max_price = Decimal("115")
        await service._check_sl_tp(session, [], [pos], now)

    # Step 1 closes 25% of the (rescaled) base: 1.25, leaving 3.75. Not zero.
    assert pos.status == "open"
    assert pos.size == Decimal("3.75")


# ── Smart SL renormalisation ───────────────────────────────────────────────


def _smart_sl_state(original_size: str = "10") -> str:
    return json.dumps(
        {
            "original_size": original_size,
            "original_entry": "100",
            "levels": [
                {
                    "status": "sold",
                    "sell_price": "96",
                    "reentries": 1,
                    "pre_sell_opening_fee": "2.0",
                    "pre_sell_slippage": "0.5",
                    "pre_sell_funding": "0.25",
                },
                {"status": "idle", "sell_price": None, "reentries": 0},
            ],
        }
    )


async def test_smart_sl_original_size_and_snapshots_are_rescaled(db) -> None:
    service = _service()
    async with get_session_factory()() as session:
        pos = _position(smart_sl_state=_smart_sl_state())
        await _persist(session, pos)
        await _close(service, session, pos, pct=25)
        state = json.loads(pos.smart_sl_state)

    assert Decimal(state["original_size"]) == Decimal("7.5")
    level = state["levels"][0]
    assert Decimal(level["pre_sell_opening_fee"]) == Decimal("1.5")
    assert Decimal(level["pre_sell_slippage"]) == Decimal("0.375")
    assert Decimal(level["pre_sell_funding"]) == Decimal("0.1875")
    # Statuses, prices and counters are untouched: no level is armed or disarmed.
    assert level["status"] == "sold"
    assert level["sell_price"] == "96"
    assert level["reentries"] == 1
    assert state["levels"][1]["status"] == "idle"


async def test_two_manual_closes_compound_on_the_smart_sl_base(db) -> None:
    service = _service()
    async with get_session_factory()() as session:
        pos = _position(smart_sl_state=_smart_sl_state())
        await _persist(session, pos)
        await _close(service, session, pos, pct=50, key="key-aaaa-0001")
        await _close(service, session, pos, pct=50, expected=pos.size, key="key-bbbb-0002")
        state = json.loads(pos.smart_sl_state)

    assert Decimal(state["original_size"]) == Decimal("2.5")


async def test_smart_sl_unchanged_without_manual_closes(db) -> None:
    """Case 10: the engine's own behaviour must be identical when nobody
    intervenes manually."""
    service = _service()
    before = _smart_sl_state()
    now = datetime(2026, 8, 27, tzinfo=UTC)
    async with get_session_factory()() as session:
        pos = _position(smart_sl_state=before)
        await _persist(session, pos)
        await service._check_sl_tp(session, [], [pos], now)

    assert json.loads(pos.smart_sl_state)["original_size"] == "10"


# ── guardian, shadow, breach ───────────────────────────────────────────────


async def test_manual_close_never_reaches_the_regime_guardian(db) -> None:
    """A human reduction is not a regime signal: a full manual close must not
    colour the guardian the way a stop loss does."""
    service = _service()
    recorded: list = []
    service.guardian.record_stop = lambda **kw: recorded.append(kw)  # type: ignore[method-assign]

    async with get_session_factory()() as session:
        pos = _position()
        await _persist(session, pos)
        await _close(service, session, pos, pct=100)

    assert recorded == []


async def test_manual_close_leaves_breach_state_untouched(db) -> None:
    service = _service()
    breach = json.dumps({"l1": {"state": "armed"}})
    async with get_session_factory()() as session:
        pos = _position(breach_state=breach)
        await _persist(session, pos)
        await _close(service, session, pos, pct=50)

    assert pos.breach_state == breach


# ── trade, order and accounting ────────────────────────────────────────────


async def test_close_trade_carries_the_manual_reason_and_the_position_link(db) -> None:
    service = _service()
    async with get_session_factory()() as session:
        pos = _position()
        await _persist(session, pos)
        result = await _close(service, session, pos, pct=50)
        trades = await PerpTradeRepository(session).list_for_user(str(USER_ID))

    closes = [t for t in trades if t.direction == "close"]
    assert len(closes) == 1
    assert closes[0].position_id == pos.position_id
    assert "manual_partial_close" in (closes[0].notes or "")
    assert closes[0].trade_id == result["close_trade_id"]


async def test_costs_are_shared_pro_rata(db) -> None:
    """Half the position closed -> half of the residual costs stay behind."""
    service = _service()
    async with get_session_factory()() as session:
        pos = _position(
            opening_fee_usd=Decimal("2"),
            slippage_usd=Decimal("0.5"),
            funding_accrued_usd=Decimal("1"),
        )
        await _persist(session, pos)
        await _close(service, session, pos, pct=50)

    assert pos.opening_fee_usd == Decimal("1")
    assert pos.slippage_usd == Decimal("0.25")
    assert pos.funding_accrued_usd == Decimal("0.5")


async def test_protection_levels_are_not_touched(db) -> None:
    service = _service()
    async with get_session_factory()() as session:
        pos = _position()
        sl, tp1, tp2 = pos.stop_loss, pos.take_profit_1, pos.take_profit_2
        await _persist(session, pos)
        await _close(service, session, pos, pct=50)

    assert (pos.stop_loss, pos.take_profit_1, pos.take_profit_2) == (sl, tp1, tp2)


# ── refusals ───────────────────────────────────────────────────────────────


async def test_stale_expected_size_is_refused(db) -> None:
    service = _service()
    async with get_session_factory()() as session:
        pos = _position()
        await _persist(session, pos)
        result = await _close(service, session, pos, pct=50, expected=Decimal("99"))

    assert result["outcome"] == "stale_position"
    assert pos.size == SIZE  # nothing was closed


async def test_already_closed_position_is_refused(db) -> None:
    service = _service()
    async with get_session_factory()() as session:
        pos = _position(status="closed")
        await _persist(session, pos)
        result = await _close(service, session, pos, pct=50)

    assert result["outcome"] == "already_closed"


async def test_unknown_position_is_refused(db) -> None:
    service = _service()
    async with get_session_factory()() as session:
        pos = _position()
        await _persist(session, pos)
        result = await service.manual_close_perp_position(
            session,
            position_id="pos_does_not_exist",
            percentage=50,
            expected_size=Decimal("10"),
            idempotency_key="key-none-0001",
        )

    assert result["outcome"] == "not_found"


async def test_missing_venue_reports_execution_failed(db) -> None:
    """The router refuses a position without a registered venue: the caller must
    see a failure, not a silent no-op that looks like success."""
    service = _service()
    async with get_session_factory()() as session:
        pos = _position(venue=None)
        await _persist(session, pos)
        result = await _close(service, session, pos, pct=50)

    assert result["outcome"] == "execution_failed"
    assert pos.size == SIZE


# ── idempotency ────────────────────────────────────────────────────────────


async def test_same_key_replays_the_first_outcome(db) -> None:
    """The retry case: one close, not two."""
    service = _service()
    async with get_session_factory()() as session:
        pos = _position()
        await _persist(session, pos)
        first = await _close(service, session, pos, pct=50, key="key-retry-0001")
        second = await service.manual_close_perp_position(
            session,
            position_id=pos.position_id,
            percentage=50,
            expected_size=SIZE,  # the client retries the ORIGINAL payload
            idempotency_key="key-retry-0001",
        )
        trades = await PerpTradeRepository(session).list_for_user(str(USER_ID))

    assert second == first
    assert pos.size == Decimal("5")  # closed once
    assert len([t for t in trades if t.direction == "close"]) == 1


async def test_same_key_with_a_different_payload_is_refused(db) -> None:
    service = _service()
    async with get_session_factory()() as session:
        pos = _position()
        await _persist(session, pos)
        await _close(service, session, pos, pct=50, key="key-same-00001")
        second = await service.manual_close_perp_position(
            session,
            position_id=pos.position_id,
            percentage=75,  # different request, same key
            expected_size=Decimal("5"),
            idempotency_key="key-same-00001",
        )

    assert second["outcome"] == "key_reused_with_different_payload"
    assert pos.size == Decimal("5")


async def test_a_new_key_on_a_stale_size_is_refused(db) -> None:
    """The double tap: the second tap carries a fresh key, so idempotency cannot
    catch it -- expected_size does."""
    service = _service()
    async with get_session_factory()() as session:
        pos = _position()
        await _persist(session, pos)
        await _close(service, session, pos, pct=50, key="key-tap1-0001")
        second = await service.manual_close_perp_position(
            session,
            position_id=pos.position_id,
            percentage=50,
            expected_size=SIZE,  # what the UI still displayed
            idempotency_key="key-tap2-0002",
        )

    assert second["outcome"] == "stale_position"
    assert pos.size == Decimal("5")


# ── follow-ups raised by the strategy chat (B) ─────────────────────────────


async def test_manual_closes_stay_queryable_and_distinguishable(db) -> None:
    """The shadow-vs-real comparison must be able to exclude manual closes, so
    the reason has to live in a queryable column and keep partial/full apart.

    Guards a real defect: with the generic "auto_close:<reason>_partial" format
    the reader strips "_partial" everywhere, collapsing
    manual_partial_close_partial into a reason that does not exist.
    """
    from backend.app.persistence.views import _close_reason

    service = _service()
    async with get_session_factory()() as session:
        first = _position(position_id="pos_q1")
        second = _position(position_id="pos_q2")
        await _persist(session, first)
        await _persist(session, second)
        await _close(service, session, first, pct=50, key="key-notes-0001")
        await _close(service, session, second, pct=100, key="key-notes-0002")
        trades = await PerpTradeRepository(session).list_for_user(str(USER_ID))

    by_position = {t.position_id: t for t in trades if t.direction == "close"}
    partial, full = by_position["pos_q1"], by_position["pos_q2"]

    assert partial.notes == "manual_close:manual_partial_close"
    assert full.notes == "manual_close:manual_full_close"
    # And they read back as the canonical reasons, not as mangled variants.
    assert _close_reason(partial) == "manual_partial_close"
    assert _close_reason(full) == "manual_full_close"
    # An automatic exit is still told apart from a human one by the prefix.
    assert not partial.notes.startswith("auto_close:")


async def test_full_manual_close_produces_a_chart_snapshot(db) -> None:
    """Same toll already paid by the Smart SL sells: a close without a snapshot
    leaves the trade with no chart in the app."""
    from sqlalchemy import select as _select

    from backend.app.persistence.models.trade_charts import TradeChartSnapshot

    service = _service()
    async with get_session_factory()() as session:
        pos = _position()
        await _persist(session, pos)
        result = await _close(service, session, pos, pct=100)
        snapshots = list(
            (await session.execute(_select(TradeChartSnapshot))).scalars().all()
        )

    assert result["position_status"] == "closed"
    assert any(s.close_trade_id == result["close_trade_id"] for s in snapshots)


async def test_two_manual_closes_then_a_ratchet_step_closes_the_right_share(db) -> None:
    """The case B asked for explicitly.

    Renormalisation must be MULTIPLICATIVE on the current state: after 50% and
    another 50% the ratchet base has to be 0.25x the original, not 0.5x. The
    clamp ``min(1, want_size / pos.size)`` would hide a wrong base by silently
    closing the whole residual, which looks "almost right" until you check the
    quantity.
    """
    service = _service()
    armed = json.dumps({"base_size": "10", "closed_frac": "0.0", "last_step": -1})
    now = datetime(2026, 8, 27, tzinfo=UTC)
    async with get_session_factory()() as session:
        pos = _position(tp1_reached=True, ratchet_state=armed, max_price=Decimal("110"))
        await _persist(session, pos)

        await _close(service, session, pos, pct=50, key="key-half-00001")
        await _close(service, session, pos, pct=50, expected=pos.size, key="key-half-00002")
        assert pos.size == Decimal("2.5")
        assert Decimal(json.loads(pos.ratchet_state)["base_size"]) == Decimal("2.5")

        # First ratchet step: 25% cumulative of the rescaled base.
        pos.current_price = Decimal("115")
        pos.max_price = Decimal("115")
        await service._check_sl_tp(session, [], [pos], now)

    # 25% of 2.5 = 0.625 closed, 1.875 left. NOT the whole residual.
    assert pos.status == "open"
    assert pos.size == Decimal("1.875")
