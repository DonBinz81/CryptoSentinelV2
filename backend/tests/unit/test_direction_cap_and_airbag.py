"""Direction cap + stop airbag (NOTE/127): the anti-cluster package.

The cap rejects a perp entry when too many same-side positions are open;
the airbag halves the OTHER same-side positions when one takes a full stop,
once per cooldown window, leaving opposite-side positions untouched.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.tests.unit.test_agent_step6 import (  # riusa fixture e helper del banco
    AgentService,
    _OfflineFeed,
    _perp_pos,
    db,  # noqa: F401  (fixture)
    get_session_factory,
    settings,
)
from backend.app.persistence.runtime_state import set_runtime_value


def _svc(**overrides):
    service = AgentService(
        settings(**overrides),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    service.price_feed = _OfflineFeed()
    return service


# ---------------------------------------------------------------- direction cap

def test_direction_cap_rejects_third_same_side() -> None:
    from backend.app.agent.risk.manager import RiskManager, SignalIntent

    manager = RiskManager(settings())
    ms = SimpleNamespace(
        perp_direction_cap=2,
        perp_capital_per_trade_pct=8.0, perp_per_trade_pct=2.0,
        spot_capital_per_trade_pct=8.0, spot_per_trade_pct=1.5,
        perp_max_open_positions=10, spot_max_open_positions=5,
        perp_max_exposure_pct=80.0, spot_max_exposure_pct=25.0,
        min_pool_liquidity_usd=0.0, drawdown_cap_pct=-20.0,
        daily_loss_limit_pct=-8.0, perp_fixed_margin_enabled=False,
        perp_fixed_margin_usd=50.0,
    )
    portfolio = SimpleNamespace(
        total_equity_usd=Decimal("1000"), drawdown_pct=Decimal("0"),
        daily_loss_limit_used_pct=Decimal("0"),
    )
    open_perp = [
        SimpleNamespace(asset="ETH", side="long", margin_usd=Decimal("20"),
                        entry_price=Decimal("1"), size=Decimal("20"), leverage=20),
        SimpleNamespace(asset="XRP", side="long", margin_usd=Decimal("20"),
                        entry_price=Decimal("1"), size=Decimal("20"), leverage=20),
    ]
    def _intent(side):
        return SignalIntent(asset="BTC", market="perp", side=side,
                            price=Decimal("1"), stop_loss=Decimal("0.95"),
                            quality=Decimal("0.8"), quote_equity=Decimal("1000"),
                            leverage=20)
    intent = _intent("long")
    decision = manager.evaluate(intent, portfolio=portfolio, ms=ms,
                                open_spot_positions=[], open_perp_positions=open_perp)
    assert not decision.allowed and decision.reason == "direction_cap_guard"

    short_intent = _intent("short")
    assert manager.evaluate(short_intent, portfolio=portfolio, ms=ms,
                            open_spot_positions=[], open_perp_positions=open_perp).allowed

    ms.perp_direction_cap = 0
    assert manager.evaluate(intent, portfolio=portfolio, ms=ms,
                            open_spot_positions=[], open_perp_positions=open_perp).allowed


# ---------------------------------------------------------------------- airbag

@pytest.mark.asyncio
async def test_airbag_halves_same_side_only(db, monkeypatch) -> None:  # noqa: F811
    service = _svc(perp_stop_airbag_enabled=True)
    now = datetime.now(UTC)
    stopped = _perp_pos("stopped", Decimal("95"), stop=Decimal("96"))  # long, sotto stop
    ally = _perp_pos("ally", Decimal("100"), stop=Decimal("90"))
    ally.asset = "ALLY"; ally.position_id = "pos-ally"
    enemy = _perp_pos("enemy", Decimal("100"), stop=Decimal("110"))
    enemy.asset = "ENEMY"; enemy.position_id = "pos-enemy"; enemy.side = "short"

    async def fake_open_for_user(self, user_id):
        return [ally, enemy]
    monkeypatch.setattr(
        "backend.app.persistence.repositories.positions.PerpPositionRepository.open_for_user",
        fake_open_for_user,
    )
    calls = []
    real_close = service._close_perp_position

    async def spy_close(session, pos, price, reason, when, **kw):
        if reason == "stop_airbag":
            calls.append((pos.asset, kw.get("close_fraction"), kw.get("set_tp1_reached")))
            return Decimal("0")
        return await real_close(session, pos, price, reason, when, **kw)
    monkeypatch.setattr(service, "_close_perp_position", spy_close)

    async with get_session_factory()() as session:
        await service._stop_airbag(session, stopped, now)

    assert calls == [("ALLY", Decimal("0.5"), False)]  # stesso lato sì, short no


@pytest.mark.asyncio
async def test_airbag_cooldown_and_toggle(db, monkeypatch) -> None:  # noqa: F811
    service = _svc(perp_stop_airbag_enabled=True)
    now = datetime.now(UTC)
    stopped = _perp_pos("stopped2", Decimal("95"), stop=Decimal("96"))
    ally = _perp_pos("ally2", Decimal("100"), stop=Decimal("90"))
    ally.asset = "ALLY2"; ally.position_id = "pos-ally2"

    async def fake_open_for_user(self, user_id):
        return [ally]
    monkeypatch.setattr(
        "backend.app.persistence.repositories.positions.PerpPositionRepository.open_for_user",
        fake_open_for_user,
    )
    calls = []

    async def spy_close(session, pos, price, reason, when, **kw):
        calls.append(pos.asset); return Decimal("0")
    monkeypatch.setattr(service, "_close_perp_position", spy_close)

    async with get_session_factory()() as session:
        await service._stop_airbag(session, stopped, now)
        await service._stop_airbag(session, stopped, now)  # dentro il cooldown
    assert calls == ["ALLY2"]  # una sola volta

    # toggle off: nessuna azione anche fuori cooldown
    service_off = _svc()
    uid = str(service_off.settings.default_user_id)
    set_runtime_value(uid, "mobile_agent_settings", json.dumps({"perp_stop_airbag_enabled": False}))
    set_runtime_value(uid, "stop_airbag_last", json.dumps({"at": "2000-01-01T00:00:00+00:00"}))
    calls.clear()
    monkeypatch.setattr(service_off, "_close_perp_position", spy_close)
    async with get_session_factory()() as session:
        await service_off._stop_airbag(session, stopped, now)
    assert calls == []
