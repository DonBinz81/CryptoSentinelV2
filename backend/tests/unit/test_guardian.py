"""Unit tests for the regime guardian (NOTE/61).

The guardian is a pure state machine over injected timestamps: no DB is
required (RuntimeState helpers degrade silently in tests, so persistence
becomes a no-op and state lives in memory).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.app.agent.guardian import (
    GREEN,
    RED,
    YELLOW,
    GuardianConfig,
    RegimeGuardian,
)
from backend.app.agent.service import _CapitalPreservationView
from backend.app.schemas.mobile_agent import AgentMobileSettings

T0 = datetime(2026, 8, 19, 0, 0, tzinfo=UTC)
CFG = GuardianConfig(enabled=True, window_hours=6.0, yellow_stops=1, red_stops=2, reentry_hours=6.0)


def _guardian() -> RegimeGuardian:
    g = RegimeGuardian("test-user")
    g._loaded = True  # skip RuntimeState lookup: memory-only for tests
    return g


def _h(hours: float) -> timedelta:
    return timedelta(hours=hours)


class TestEscalation:
    def test_starts_green(self):
        assert _guardian().state == GREEN

    def test_first_stop_goes_yellow(self):
        g = _guardian()
        change = g.record_stop(asset="NEAR", pnl_usd=-5.13, now=T0, cfg=CFG)
        assert g.state == YELLOW
        assert change is not None and change.previous == GREEN and change.current == YELLOW

    def test_second_stop_in_window_goes_red(self):
        g = _guardian()
        g.record_stop(asset="NEAR", pnl_usd=-5.13, now=T0, cfg=CFG)
        change = g.record_stop(asset="LINK", pnl_usd=-27.53, now=T0 + _h(3), cfg=CFG)
        assert g.state == RED
        assert change is not None and change.current == RED

    def test_stops_outside_window_do_not_count(self):
        g = _guardian()
        g.record_stop(asset="NEAR", pnl_usd=-5.0, now=T0, cfg=CFG)
        # 7h later the first stop is out of the 6h window: still YELLOW, not RED.
        change = g.record_stop(asset="LINK", pnl_usd=-27.0, now=T0 + _h(7), cfg=CFG)
        assert g.stops_in_window(T0 + _h(7), CFG) == 1
        assert g.state == YELLOW
        assert change is None  # YELLOW -> YELLOW: no transition

    def test_stop_while_red_keeps_red_and_refreshes_anchor(self):
        g = _guardian()
        g.record_stop(asset="A", pnl_usd=-1, now=T0, cfg=CFG)
        g.record_stop(asset="B", pnl_usd=-2, now=T0 + _h(1), cfg=CFG)
        assert g.state == RED
        assert g.record_stop(asset="C", pnl_usd=-3, now=T0 + _h(2), cfg=CFG) is None
        # De-escalation counts from the LAST stop (T0+2h), not the first.
        assert g.evaluate(now=T0 + _h(7), cfg=CFG) is None
        assert g.state == RED
        change = g.evaluate(now=T0 + _h(8), cfg=CFG)
        assert change is not None and change.current == YELLOW


class TestDeEscalation:
    def test_red_steps_down_one_state_at_a_time(self):
        g = _guardian()
        g.record_stop(asset="A", pnl_usd=-1, now=T0, cfg=CFG)
        g.record_stop(asset="B", pnl_usd=-2, now=T0 + _h(1), cfg=CFG)
        # 6h clean after the last stop -> YELLOW
        change = g.evaluate(now=T0 + _h(7), cfg=CFG)
        assert change is not None and (change.previous, change.current) == (RED, YELLOW)
        # another 6h clean -> GREEN
        change = g.evaluate(now=T0 + _h(13), cfg=CFG)
        assert change is not None and (change.previous, change.current) == (YELLOW, GREEN)

    def test_single_stop_yellow_recovers_after_reentry_hours(self):
        g = _guardian()
        g.record_stop(asset="A", pnl_usd=-1, now=T0, cfg=CFG)
        assert g.evaluate(now=T0 + _h(5.9), cfg=CFG) is None
        change = g.evaluate(now=T0 + _h(6), cfg=CFG)
        assert change is not None and change.current == GREEN

    def test_no_bounce_when_window_longer_than_reentry(self):
        # Window 12h, reentry 3h: after the RED->YELLOW step-down, the old
        # stops are still inside the window but must NOT re-escalate.
        cfg = GuardianConfig(True, window_hours=12.0, yellow_stops=1, red_stops=2, reentry_hours=3.0)
        g = _guardian()
        g.record_stop(asset="A", pnl_usd=-1, now=T0, cfg=cfg)
        g.record_stop(asset="B", pnl_usd=-2, now=T0 + _h(1), cfg=cfg)
        assert g.state == RED
        change = g.evaluate(now=T0 + _h(4), cfg=cfg)
        assert change is not None and change.current == YELLOW
        # Immediate re-evaluation: stays YELLOW (stops are older than the change).
        assert g.evaluate(now=T0 + _h(4.1), cfg=cfg) is None
        assert g.state == YELLOW

    def test_new_stop_after_stepdown_re_escalates(self):
        cfg = GuardianConfig(True, window_hours=12.0, yellow_stops=1, red_stops=2, reentry_hours=3.0)
        g = _guardian()
        g.record_stop(asset="A", pnl_usd=-1, now=T0, cfg=cfg)
        g.record_stop(asset="B", pnl_usd=-2, now=T0 + _h(1), cfg=cfg)
        g.evaluate(now=T0 + _h(4), cfg=cfg)  # RED -> YELLOW
        change = g.record_stop(asset="C", pnl_usd=-3, now=T0 + _h(5), cfg=cfg)
        assert change is not None and change.current == RED


class TestDisabled:
    def test_disabled_records_but_never_escalates(self):
        cfg = GuardianConfig(enabled=False, window_hours=6.0, yellow_stops=1, red_stops=2, reentry_hours=6.0)
        g = _guardian()
        assert g.record_stop(asset="A", pnl_usd=-1, now=T0, cfg=cfg) is None
        assert g.state == GREEN

    def test_disabling_clears_a_stale_red(self):
        g = _guardian()
        g.record_stop(asset="A", pnl_usd=-1, now=T0, cfg=CFG)
        g.record_stop(asset="B", pnl_usd=-2, now=T0 + _h(1), cfg=CFG)
        assert g.state == RED
        off = GuardianConfig(enabled=False, window_hours=6.0, yellow_stops=1, red_stops=2, reentry_hours=6.0)
        change = g.evaluate(now=T0 + _h(2), cfg=off)
        assert change is not None and change.current == GREEN

    def test_snapshot_reports_green_when_disabled(self):
        g = _guardian()
        g.record_stop(asset="A", pnl_usd=-1, now=T0, cfg=CFG)
        off = GuardianConfig(enabled=False, window_hours=6.0, yellow_stops=1, red_stops=2, reentry_hours=6.0)
        assert g.snapshot(T0 + _h(0.1), off)["state"] == GREEN


class TestExplanationPersistence:
    """Chat C (NOTE/61 §6-bis) needs the Brain's explanation available for the
    app banner whenever it is opened, not just alive in a single push."""

    def test_explanation_attaches_to_its_own_transition(self):
        g = _guardian()
        change = g.record_stop(asset="A", pnl_usd=-1, now=T0, cfg=CFG)
        g.record_explanation(text="Prudenza: primo stop.", at=T0 + timedelta(seconds=2), for_change_at=change.changed_at)
        snap = g.snapshot(T0 + timedelta(minutes=1), CFG)
        assert snap["explanation"] == "Prudenza: primo stop."
        assert snap["explained_at"] is not None

    def test_new_transition_clears_previous_explanation_immediately(self):
        # The banner must never show YELLOW's text while already RED, even
        # before the (async) Brain call for RED has returned.
        g = _guardian()
        c1 = g.record_stop(asset="A", pnl_usd=-1, now=T0, cfg=CFG)
        g.record_explanation(text="Prudenza.", at=T0, for_change_at=c1.changed_at)
        g.record_stop(asset="B", pnl_usd=-2, now=T0 + _h(1), cfg=CFG)  # -> RED
        snap = g.snapshot(T0 + _h(1), CFG)
        assert snap["state"] == RED
        assert snap["explanation"] is None
        assert snap["explained_at"] is None

    def test_stale_explanation_for_superseded_transition_is_dropped(self):
        # Simulates a slow Brain call: by the time it returns, a newer
        # transition has already happened. The old text must not attach.
        g = _guardian()
        c1 = g.record_stop(asset="A", pnl_usd=-1, now=T0, cfg=CFG)
        g.record_stop(asset="B", pnl_usd=-2, now=T0 + _h(1), cfg=CFG)  # -> RED, c1 superseded
        g.record_explanation(text="Testo vecchio della gialla.", at=T0 + _h(1.1), for_change_at=c1.changed_at)
        snap = g.snapshot(T0 + _h(1), CFG)
        assert snap["explanation"] is None

    def test_failed_explain_leaves_field_null_not_empty_string(self):
        g = _guardian()
        g.record_stop(asset="A", pnl_usd=-1, now=T0, cfg=CFG)
        # record_explanation is simply never called (explain() failed upstream).
        snap = g.snapshot(T0 + timedelta(minutes=1), CFG)
        assert snap["explanation"] is None


class TestCapitalPreservationView:
    def test_defense_values_substitute_management_knobs(self):
        ms = AgentMobileSettings(
            perp_tp1_close_pct=50.0,
            perp_smart_sl_confirmation_candles=3,
            perp_trailing_enabled=True,
            perp_defense_tp1_close_pct=100.0,
            perp_defense_smart_sl_confirmation_candles=0,
            perp_defense_trailing_enabled=False,
        )
        view = _CapitalPreservationView(ms)
        assert view.perp_tp1_close_pct == 100.0
        assert view.perp_smart_sl_confirmation_candles == 0
        assert view.perp_trailing_enabled is False
        assert [tuple(s) for s in view.perp_profit_lock_steps] == [
            (0.30, 0.50), (0.50, 0.80), (0.70, 1.00),
        ]

    def test_everything_else_passes_through(self):
        ms = AgentMobileSettings(perp_ratchet_breakeven_pct=42.0, perp_max_leverage=35)
        view = _CapitalPreservationView(ms)
        assert view.perp_ratchet_breakeven_pct == 42.0
        assert view.perp_max_leverage == 35
        assert view.execution_mode == ms.execution_mode

    def test_user_settings_are_never_mutated(self):
        ms = AgentMobileSettings(perp_tp1_close_pct=50.0)
        _ = _CapitalPreservationView(ms).perp_tp1_close_pct
        assert ms.perp_tp1_close_pct == 50.0


class TestSchemaValidation:
    def test_red_stops_must_be_gte_yellow(self):
        import pytest

        with pytest.raises(ValueError):
            AgentMobileSettings(perp_guardian_yellow_stops=3, perp_guardian_red_stops=2)

    def test_defense_steps_validated_like_ratchet_steps(self):
        import pytest

        with pytest.raises(ValueError):
            AgentMobileSettings(perp_defense_profit_lock_steps=[(0.5, 0.8), (0.3, 0.9)])


class TestGuardianYellowScaling:
    """YELLOW must rebuild the FROZEN RiskDecision, never mutate it (the first
    version raised FrozenInstanceError on every YELLOW approval, so YELLOW
    silently blocked all perp entries instead of halving them)."""

    def test_yellow_halves_an_approved_decision(self):
        from decimal import Decimal

        from backend.app.agent.risk import RiskDecision
        from backend.app.agent.service import _apply_guardian_yellow

        original = RiskDecision(
            True, "risk_approved",
            size_quote=Decimal("50"), risk_amount_quote=Decimal("15.2"),
        )
        out = _apply_guardian_yellow(
            original, factor=Decimal("0.5"), min_trade_size=Decimal("7")
        )
        assert out.allowed is True
        assert out.size_quote == Decimal("25")
        assert out.risk_amount_quote == Decimal("7.6")
        assert out.reason == "risk_approved_guardian_yellow"
        # the input (frozen) is untouched
        assert original.size_quote == Decimal("50") and original.reason == "risk_approved"

    def test_yellow_rejects_below_minimum_size(self):
        from decimal import Decimal

        from backend.app.agent.risk import RiskDecision
        from backend.app.agent.service import _apply_guardian_yellow

        out = _apply_guardian_yellow(
            RiskDecision(True, "risk_approved", size_quote=Decimal("12")),
            factor=Decimal("0.5"), min_trade_size=Decimal("7"),
        )
        assert out.allowed is False
        assert out.reason == "guardian_yellow_below_min_size"
