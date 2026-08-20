"""Risk cap on the perp fixed margin (NOTE/60 §2).

The fixed margin used to override the FIX-1 risk bound unconditionally: the
loss at stop became margin*leverage*stop_distance, detached from per_trade_pct
(LINK 2026-08-19: budget 15.2$, actual stop loss 27.5$). Capped, the fixed
value is a target that can never exceed the per-trade risk budget.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest

from backend.app.agent.risk import RiskManager, SignalIntent
from backend.app.persistence.models.pnl import PortfolioState
from backend.app.schemas.mobile_agent import AgentMobileSettings

# Reuse the battle-tested Settings builder instead of duplicating its required
# fields (gas reserve floors etc. made a hand-rolled copy fail validation).
from backend.tests.unit.test_agent_step6 import settings as _base_settings

USER_ID = UUID("00000000-0000-0000-0000-000000000001")


def _settings(**overrides):
    payload = dict(
        eligible_tokens=["LINK"] + [f"TOKEN_{i}" for i in range(149)],
        min_trade_size_usd=7.0,
    )
    payload.update(overrides)
    return _base_settings(**payload)


def _portfolio() -> PortfolioState:
    return PortfolioState(
        user_id=str(USER_ID),
        total_equity_usd=Decimal("1013.54"),
        initial_equity_usd=Decimal("1013.54"),
        peak_equity_usd=Decimal("1013.54"),
        drawdown_pct=Decimal("0"),
        max_drawdown_pct=Decimal("0"),
        exposure_pct=Decimal("0"),
        daily_pnl_usd=Decimal("0"),
        daily_loss_limit_used_pct=Decimal("0"),
        agent_status="running",
        trades_today=0,
    )


def _ms(**overrides) -> AgentMobileSettings:
    base = dict(
        perp_fixed_margin_enabled=True,
        perp_fixed_margin_usd=50.0,
        perp_per_trade_pct=1.5,
        perp_max_exposure_pct=100.0,
    )
    base.update(overrides)
    return AgentMobileSettings(**base)


def _link_intent(**overrides) -> SignalIntent:
    # The real LINK short of 2026-08-19: entry 9.504, SL 9.657 (sd 1.61%), lev 33.
    payload = dict(
        asset="LINK",
        market="perp",
        side="short",
        price=Decimal("9.504"),
        stop_loss=Decimal("9.65707"),
        quality=Decimal("0.7"),
        quote_equity=Decimal("1013.54"),
        leverage=33,
    )
    payload.update(overrides)
    return SignalIntent(**payload)


def test_cap_bites_and_loss_at_stop_equals_budget():
    """Regression on the real LINK numbers: 27.5$ loss becomes <= 15.2$ budget."""
    decision = RiskManager(_settings()).evaluate(
        _link_intent(), portfolio=_portfolio(),
        open_spot_positions=[], open_perp_positions=[], ms=_ms(),
    )
    assert decision.allowed is True
    assert decision.reason == "risk_approved_fixed_margin_capped"
    assert decision.size_quote < Decimal("50")
    # Loss at stop = margin * leverage * stop_distance == equity * per_trade_pct.
    sd = abs(Decimal("9.504") - Decimal("9.65707")) / Decimal("9.504")
    loss_at_stop = decision.size_quote * Decimal("33") * sd
    budget = Decimal("1013.54") * Decimal("1.5") / Decimal("100")
    assert abs(loss_at_stop - budget) < Decimal("0.01")


def test_fixed_margin_within_budget_passes_whole():
    """Tight stop / low leverage: the risk bound is far above 50 -> no cap."""
    decision = RiskManager(_settings()).evaluate(
        _link_intent(leverage=1, stop_loss=Decimal("9.03")),  # sd ~5%, lev 1 -> bound ~304
        portfolio=_portfolio(),
        open_spot_positions=[], open_perp_positions=[], ms=_ms(),
    )
    assert decision.allowed is True
    assert decision.reason == "risk_approved"
    assert decision.size_quote == Decimal("50.0")


def test_cap_below_minimum_trade_size_rejects():
    """Fail closed: a capped margin under the minimum is a rejection, not a tiny trade."""
    decision = RiskManager(_settings()).evaluate(
        _link_intent(quote_equity=Decimal("200"), leverage=30, stop_loss=Decimal("9.694")),
        # equity 200 * 1.5% = 3$ budget; sd 2%, lev 30 -> bound = 5$ < 7$ minimum
        portfolio=None,
        open_spot_positions=[], open_perp_positions=[], ms=_ms(),
    )
    assert decision.allowed is False
    assert decision.reason == "below_minimum_trade_size"


def test_no_stop_loss_keeps_legacy_passthrough():
    """Documented limit: without a stop distance there is no bound to cap with.

    Perp signals always carry a structural stop, so this path is theoretical;
    the test pins the behavior down so a future change is a conscious one.
    """
    decision = RiskManager(_settings()).evaluate(
        _link_intent(stop_loss=None),
        portfolio=_portfolio(),
        open_spot_positions=[], open_perp_positions=[], ms=_ms(),
    )
    assert decision.allowed is True
    assert decision.reason == "risk_approved"
    assert decision.size_quote == Decimal("50.0")
