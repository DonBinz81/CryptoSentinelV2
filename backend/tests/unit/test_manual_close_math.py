"""Unit tests for the pure manual-close logic.

These run on the developer machine: the module under test imports neither
``web3`` nor the database layer, which is the whole point of keeping it
separate (the Windows ARM64 workstation cannot install the ckzg/web3 chain).
Everything that needs ``agent.service`` is covered by the VPS suite instead.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from backend.app.agent.manual_close import (
    ALLOWED_PERCENTAGES,
    MANUAL_FULL_CLOSE,
    MANUAL_PARTIAL_CLOSE,
    ManualCloseError,
    build_close_plan,
    renormalize_ratchet_state,
    renormalize_smart_sl_state,
    renormalize_states_json,
    sizes_match,
    validate_percentage,
)


# ── percentages ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("pct", ALLOWED_PERCENTAGES)
def test_allowed_percentages_are_accepted(pct: int) -> None:
    assert validate_percentage(pct) == pct


@pytest.mark.parametrize("pct", [0, 1, 10, 24, 26, 99, 101, -50, None, "abc", 12.5])
def test_other_percentages_are_rejected(pct: object) -> None:
    with pytest.raises(ManualCloseError):
        validate_percentage(pct)


def test_percentage_accepts_numeric_string() -> None:
    """The API layer may hand over a string; 50 and "50" are the same request."""
    assert validate_percentage("50") == 50


# ── quantities on the residual size ────────────────────────────────────────


@pytest.mark.parametrize(
    ("pct", "expected_close", "expected_remaining"),
    [
        (25, "25.000000", "75.000000"),
        (50, "50.000000", "50.000000"),
        (75, "75.000000", "25.000000"),
        (100, "100", "0"),
    ],
)
def test_presets_on_a_round_size(pct: int, expected_close: str, expected_remaining: str) -> None:
    plan = build_close_plan(Decimal("100"), pct)
    assert plan.close_qty == Decimal(expected_close)
    assert plan.remaining_qty == Decimal(expected_remaining)


def test_full_close_is_flagged_and_named() -> None:
    plan = build_close_plan(Decimal("12.5"), 100)
    assert plan.is_full is True
    assert plan.forced_full is False
    assert plan.close_reason == MANUAL_FULL_CLOSE
    assert plan.remaining_qty == Decimal("0")


def test_partial_close_is_named_and_keeps_the_position() -> None:
    plan = build_close_plan(Decimal("12.5"), 50)
    assert plan.is_full is False
    assert plan.close_reason == MANUAL_PARTIAL_CLOSE
    assert plan.remaining_qty > 0


def test_quantities_always_add_up_to_the_original_size() -> None:
    """No dust may appear or vanish: the residual is derived by subtraction."""
    for size in ("100", "12.345678", "0.000007", "3.333333333333333333"):
        for pct in ALLOWED_PERCENTAGES:
            plan = build_close_plan(Decimal(size), pct)
            assert plan.close_qty + plan.remaining_qty == Decimal(size), (size, pct)


def test_percentage_applies_to_the_residual_not_the_original() -> None:
    """50% after 50% closes a quarter of the original, not another half."""
    first = build_close_plan(Decimal("100"), 50)
    second = build_close_plan(first.remaining_qty, 50)
    assert second.close_qty == Decimal("25.000000")
    assert second.remaining_qty == Decimal("25.000000")


def test_zero_or_negative_size_is_rejected() -> None:
    for size in ("0", "-1"):
        with pytest.raises(ManualCloseError):
            build_close_plan(Decimal(size), 50)


# ── the untradeable-residual rule ──────────────────────────────────────────


def test_tiny_residual_is_promoted_to_a_full_close_and_flagged() -> None:
    """A residual below the quantum cannot be traded: close it all, and say so."""
    plan = build_close_plan(Decimal("0.000001"), 75)
    assert plan.is_full is True
    assert plan.forced_full is True
    assert plan.close_reason == MANUAL_FULL_CLOSE
    assert plan.close_qty == Decimal("0.000001")
    assert plan.remaining_qty == Decimal("0")


def test_residual_exactly_at_the_quantum_stays_a_partial_close() -> None:
    plan = build_close_plan(Decimal("0.000004"), 75)
    assert plan.is_full is False
    assert plan.forced_full is False
    assert plan.close_qty == Decimal("0.000003")
    assert plan.remaining_qty == Decimal("0.000001")


# ── stale-size detection ───────────────────────────────────────────────────


def test_sizes_match_on_equal_values() -> None:
    assert sizes_match(Decimal("12.345678"), Decimal("12.345678")) is True
    assert sizes_match("12.345678", Decimal("12.345678")) is True


def test_sizes_match_ignores_digits_below_the_quantum() -> None:
    """Sub-quantum digits are not tradeable: they must not cause a false 409."""
    assert sizes_match(Decimal("12.3456780000001"), Decimal("12.345678")) is True


def test_sizes_do_not_match_when_the_position_moved() -> None:
    assert sizes_match(Decimal("12.345678"), Decimal("6.172839")) is False


def test_missing_expectation_is_not_a_match() -> None:
    """No expected_size means the guard cannot do its job: reject, never pass."""
    assert sizes_match(None, Decimal("10")) is False


# ── ratchet renormalisation ────────────────────────────────────────────────


def test_ratchet_base_size_is_scaled_and_stage_is_preserved() -> None:
    state = {"base_size": "100", "closed_frac": "0.25", "last_step": 0}
    out = renormalize_ratchet_state(state, Decimal("0.60"))
    assert Decimal(out["base_size"]) == Decimal("60.00")
    assert out["closed_frac"] == "0.25"
    assert out["last_step"] == 0


def test_ratchet_example_from_the_specification() -> None:
    """base 100, closed_frac 0.25, manual close of 40% of the 75 residual."""
    state = {"base_size": "100", "closed_frac": "0.25", "last_step": 0}
    out = renormalize_ratchet_state(state, Decimal("0.60"))
    new_base = Decimal(out["base_size"])
    theoretical_residual = new_base * (Decimal("1") - Decimal(out["closed_frac"]))
    assert new_base == Decimal("60.00")
    assert theoretical_residual == Decimal("45.0000")


def test_ratchet_not_armed_is_left_alone() -> None:
    """Without base_size the ratchet has not armed: it will freeze the reduced
    residual later, which is already the right base."""
    assert renormalize_ratchet_state({}, Decimal("0.5")) == {}
    assert renormalize_ratchet_state(None, Decimal("0.5")) is None


def test_two_consecutive_manual_closes_compound_on_the_ratchet() -> None:
    state = {"base_size": "100", "closed_frac": "0.25", "last_step": 1}
    once = renormalize_ratchet_state(state, Decimal("0.5"))
    twice = renormalize_ratchet_state(once, Decimal("0.5"))
    assert Decimal(twice["base_size"]) == Decimal("25.00")
    assert twice["closed_frac"] == "0.25"
    assert twice["last_step"] == 1


def test_ratchet_renormalisation_does_not_mutate_the_input() -> None:
    state = {"base_size": "100", "closed_frac": "0.25"}
    renormalize_ratchet_state(state, Decimal("0.5"))
    assert state["base_size"] == "100"


# ── Smart SL renormalisation ───────────────────────────────────────────────


def _smart_sl_state() -> dict:
    return {
        "original_size": "100",
        "original_entry": "1.5",
        "original_tp1": "1.8",
        "global_reentries": 1,
        "protection_suspended": True,
        "levels": [
            {
                "status": "sold",
                "sell_price": "1.42",
                "reentries": 1,
                "realized_loss": "-5.5",
                "pre_sell_opening_fee": "2.0",
                "pre_sell_slippage": "0.5",
                "pre_sell_funding": "0.25",
            },
            {"status": "idle", "sell_price": None, "reentries": 0},
        ],
    }


def test_smart_sl_original_size_is_scaled() -> None:
    out = renormalize_smart_sl_state(_smart_sl_state(), Decimal("0.75"))
    assert Decimal(out["original_size"]) == Decimal("75.00")


def test_smart_sl_pre_sell_cost_snapshots_are_scaled() -> None:
    """They are restored as ABSOLUTE values by the rebuy paths: unscaled, a
    future rebuy would reinstate costs belonging to the larger position."""
    out = renormalize_smart_sl_state(_smart_sl_state(), Decimal("0.75"))
    level = out["levels"][0]
    assert Decimal(level["pre_sell_opening_fee"]) == Decimal("1.500")
    assert Decimal(level["pre_sell_slippage"]) == Decimal("0.375")
    assert Decimal(level["pre_sell_funding"]) == Decimal("0.1875")


def test_smart_sl_statuses_prices_and_counters_are_preserved() -> None:
    out = renormalize_smart_sl_state(_smart_sl_state(), Decimal("0.5"))
    assert out["levels"][0]["status"] == "sold"
    assert out["levels"][1]["status"] == "idle"
    assert out["levels"][0]["sell_price"] == "1.42"
    assert out["levels"][0]["reentries"] == 1
    assert out["levels"][0]["realized_loss"] == "-5.5"
    assert out["global_reentries"] == 1
    assert out["original_entry"] == "1.5"
    assert out["original_tp1"] == "1.8"
    assert out["protection_suspended"] is True


def test_smart_sl_idle_level_without_snapshots_survives() -> None:
    out = renormalize_smart_sl_state(_smart_sl_state(), Decimal("0.5"))
    assert out["levels"][1] == {"status": "idle", "sell_price": None, "reentries": 0}


def test_smart_sl_two_consecutive_manual_closes_compound() -> None:
    once = renormalize_smart_sl_state(_smart_sl_state(), Decimal("0.5"))
    twice = renormalize_smart_sl_state(once, Decimal("0.5"))
    assert Decimal(twice["original_size"]) == Decimal("25.00")
    assert Decimal(twice["levels"][0]["pre_sell_opening_fee"]) == Decimal("0.50")


def test_smart_sl_next_sell_uses_the_new_base() -> None:
    """The engine computes split_size = original_size * split. After a 25%
    manual close the L1 sell must shrink by the same factor."""
    split_l1 = Decimal("0.35")
    before = Decimal(_smart_sl_state()["original_size"]) * split_l1
    out = renormalize_smart_sl_state(_smart_sl_state(), Decimal("0.75"))
    after = Decimal(out["original_size"]) * split_l1
    assert before == Decimal("35.00")
    assert after == Decimal("26.2500")
    assert after == before * Decimal("0.75")


def test_smart_sl_renormalisation_does_not_mutate_the_input() -> None:
    state = _smart_sl_state()
    renormalize_smart_sl_state(state, Decimal("0.5"))
    assert state["original_size"] == "100"
    assert state["levels"][0]["pre_sell_opening_fee"] == "2.0"


def test_smart_sl_empty_state_is_left_alone() -> None:
    assert renormalize_smart_sl_state(None, Decimal("0.5")) is None
    assert renormalize_smart_sl_state({}, Decimal("0.5")) == {}


# ── JSON wrapper ───────────────────────────────────────────────────────────


def test_json_wrapper_scales_both_states() -> None:
    ratchet_json = json.dumps({"base_size": "100", "closed_frac": "0.25"})
    smart_json = json.dumps(_smart_sl_state())
    new_ratchet, new_smart = renormalize_states_json(ratchet_json, smart_json, Decimal("0.5"))
    assert Decimal(json.loads(new_ratchet)["base_size"]) == Decimal("50.0")
    assert Decimal(json.loads(new_smart)["original_size"]) == Decimal("50.0")


def test_json_wrapper_preserves_unreadable_blobs() -> None:
    """A manual close must never be the operation that destroys a state it
    could not parse."""
    broken = "{not json"
    new_ratchet, new_smart = renormalize_states_json(broken, broken, Decimal("0.5"))
    assert new_ratchet == broken
    assert new_smart == broken


def test_json_wrapper_handles_absent_states() -> None:
    assert renormalize_states_json(None, None, Decimal("0.5")) == (None, None)
