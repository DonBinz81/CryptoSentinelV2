"""Step 6 agent brain, signal and risk regressions."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from backend.app.agent.brain import ClaudeMetaController
from backend.app.agent.ohlcv_warmup import warmup_selected_watchlist
from backend.app.agent.risk import KillSwitchState, RiskDecision, RiskManager, SignalIntent
from backend.app.agent.service import AgentService
from backend.app.agent.signals.common.indicators import Candle
from backend.app.agent.signals.perp import binance_klines
from backend.app.agent.signals.perp.binance_klines import BinanceKlineCacheEntry, clear_kline_cache
from backend.app.agent.signals.perp.volume_profile import VolumeProfileSignal
from backend.app.agent.signals.spot.momentum import SpotMomentumSignal
from backend.app.agent.watchlist import set_selected_watchlist
from backend.app.api.routes import views as view_routes
from backend.app.persistence.repositories.decisions import AgentDecisionRepository
from backend.app.persistence.repositories.positions import PerpPositionRepository, SpotPositionRepository
from backend.app.persistence.repositories.trade_charts import TradeChartRepository
from backend.app.persistence.models.pnl import PortfolioState
from backend.app.persistence.models.positions import PerpPosition, SpotPosition
from backend.app.persistence.models.trades import PerpTrade, SpotTrade
from backend.app.persistence.repositories.trades import PerpTradeRepository, SpotTradeRepository
from backend.app.persistence.runtime_state import set_runtime_value
from backend.app.schemas.mobile_agent import AgentMobileSettings
from backend.app.persistence.sync_database import (
    create_all_sync,
    init_sync_db,
    reset_sync_db,
)
from backend.app.persistence.database import close_db, get_session_factory, init_db


USER_ID = UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
async def db(tmp_path: Path):
    reset_sync_db()
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'agent.db'}")
    init_sync_db(f"sqlite:///{tmp_path / 'agent.db'}")
    create_all_sync()
    yield
    await close_db()
    reset_sync_db()


def settings(**overrides):
    base = dict(
        default_user_id=USER_ID,
        eligible_tokens=["BTC"] + [f"TOKEN_{i}" for i in range(148)],
        minimum_trades_per_day=1,
        execution_mode="dry_run",
        agent_mode="conservative",
        markets_enabled="both",
        bsc_network="testnet",
        operating_hours_utc="00:00-23:59",
        anthropic_api_key=None,
        anthropic_model="claude-test",
        anthropic_max_tokens=512,
        risk_capital_per_trade_pct=4.0,
        risk_per_trade_pct=1.5,
        risk_max_open_positions=5,
        risk_max_total_exposure_pct=30.0,
        risk_daily_loss_limit_pct=-8.0,
        risk_max_drawdown_pct=-15.0,
        risk_drawdown_alert_enabled=True,
        risk_notify_drawdown_pct=10.0,
        risk_cooldown_minutes=0,
        risk_min_pool_liquidity_usd=50000.0,
        dry_run_capital_usd=200.0,
        min_trade_size_usd=7.0,
        min_portfolio_value_usd=5.0,
        test_scaling_pct=10.0,
        spot_confidence_threshold=0.70,
        spot_volatility_trigger_pct=2.0,
        spot_relative_volume_threshold=1.5,
        spot_atr_stop_multiplier=1.5,
        spot_tp1_atr_multiplier=2.0,
        spot_tp2_atr_multiplier=3.5,
        spot_breakeven_enabled=True,
        spot_breakeven_trigger_atr=1.0,
        spot_breakeven_offset_costs=True,
        spot_breakeven_buffer_pct=0.0,
        spot_trailing_atr_multiplier=2.5,
        spot_trailing_active_from_start=True,
        spot_tp1_close_fraction=0.30,
        spot_scale_in_enabled=True,
        spot_scale_in_size_fraction=0.50,
        spot_scale_in_require_new_hh=True,
        spot_scale_in_require_be_stop=True,
        spot_scale_in_max_adds=1,
        spot_trailing_distance_pct=2.0,
        spot_partial_take_profit_pct=5.0,
        spot_time_stop_hours=6,
        spot_time_stop_mode="atr",
        spot_time_stop_lookback_candles=8,
        spot_time_stop_min_move_atr=0.5,
        spot_time_stop_hours_fallback=6,
        spot_spike_filter_enabled=True,
        spot_spike_atr_ratio_max=3.0,
        spot_spike_atr_avg_period=50,
        spot_spike_action="skip",
        spot_spike_reduced_size_fraction=0.5,
        spot_market_regime_filter_enabled=False,
        spot_market_regime_symbol="BTCUSDT",
        spot_market_regime_interval="15m",
        spot_market_regime_ema_period=50,
        spot_market_regime_low_lookback=12,
        market_reversal_filter_enabled=False,
        market_reversal_symbol="BTCUSDT",
        market_reversal_interval="15m",
        market_reversal_ema_period=10,
        market_reversal_confirmation_candles=2,
        spot_vwap_atr_extension_limit=10.0,
        spot_rsi_weight_pct=15.0,
        spot_trend_structure_weight_pct=30.0,
        spot_relative_volume_weight_pct=30.0,
        spot_btc_context_weight_pct=15.0,
        spot_sentiment_weight_pct=10.0,
        perp_direction_mode="long_short",
        perp_value_area_pct=68.0,
        perp_atr_stop_multiplier=0.8,
        perp_tp1_atr_multiplier=2.5,
        perp_tp2_atr_multiplier=4.0,
        perp_use_poc_for_tp2=True,
        perp_breakeven_enabled=True,
        perp_breakeven_trigger_atr=1.0,
        perp_breakeven_offset_costs=True,
        perp_breakeven_buffer_pct=0.0,
        perp_trailing_base_atr_largo=4.0,
        perp_trailing_floor_atr_largo=2.5,
        perp_trailing_base_atr_stretto=2.5,
        perp_trailing_floor_atr_stretto=1.5,
        perp_trailing_mode="largo",
        perp_time_stop_hours=8,
        perp_dynamic_leverage_enabled=True,
        perp_min_volume_profile_liquidity_usd=100.0,
        perp_default_leverage=2,
        perp_min_leverage=4,
        perp_max_leverage=5,
        perp_leverage_atr_period=72,
        perp_leverage_atr_baseline_hours=120,
        perp_volume_profile_window_hours=24,
        perp_volume_profile_candle_minutes=5,
        binance_futures_base_url="https://fapi.binance.com",
        market_data_request_timeout_seconds=5.0,
        wallet_address=None,
        risk_max_slippage_pct=1.0,
        spot_quote_token_address=None,
        spot_quote_token_decimals=18,
        spot_token_map={},
        cmc_api_key=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def candles(count: int = 80) -> list[Candle]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    values: list[Candle] = []
    price = 100.0
    for index in range(count):
        price += 0.2
        volume = 100.0
        if index == count - 1:
            price *= 1.03
            volume = 500.0
        values.append(
            Candle(
                timestamp=start + timedelta(minutes=5 * index),
                open=price - 0.4,
                high=price + 0.6,
                low=price - 0.8,
                close=price,
                volume=volume,
            )
        )
    return values


class FakeSpotFeed:
    def __init__(self, candle_count: int = 80) -> None:
        self.candle_count = candle_count
        self.calls: list[dict] = []

    async def fetch(self, **kwargs):
        self.calls.append(kwargs)
        return candles(self.candle_count)


@pytest.mark.asyncio
async def test_spot_momentum_signal_enters_on_volume_momentum() -> None:
    signal = await SpotMomentumSignal(settings()).evaluate(
        {"asset": "BTC", "candles": candles(), "btc_context_score": 0.7, "sentiment_score": 0.7}
    )

    assert signal["action"] == "enter_long"
    assert signal["quality"] >= 0.7
    assert signal["components"]["relative_volume"] > 1.5


@pytest.mark.asyncio
async def test_spot_momentum_warms_up_ohlcv_when_payload_has_no_candles() -> None:
    feed = FakeSpotFeed()
    signal = await SpotMomentumSignal(settings(), feed=feed).evaluate(
        {"asset": "CAKE", "btc_context_score": 0.7, "sentiment_score": 0.7}
    )

    assert feed.calls[0]["symbol"] == "CAKEUSDT"
    assert feed.calls[0]["market"] == "spot"
    assert feed.calls[0]["limit"] == 100
    assert signal["asset"] == "CAKE"
    assert signal["reason"] != "insufficient_ohlcv_history"


@pytest.mark.asyncio
async def test_spot_momentum_reports_required_ohlcv_when_warmup_is_short() -> None:
    feed = FakeSpotFeed(candle_count=20)
    signal = await SpotMomentumSignal(settings(), feed=feed).evaluate({"asset": "CAKE"})

    assert signal["reason"] == "insufficient_ohlcv_history"
    assert signal["components"]["candle_count"] == 20
    assert signal["components"]["required_candles"] == 50


@pytest.mark.asyncio
async def test_volume_profile_builds_levels_without_market_provider() -> None:
    profile_candles = candles(120)
    signal = await VolumeProfileSignal(settings()).evaluate({"asset": "BTC", "candles": profile_candles})

    assert signal["market"] == "perp"
    assert signal["components"]["poc"] > 0
    assert signal["components"]["val"] <= signal["components"]["poc"] <= signal["components"]["vah"]


def _breakout_long_candles() -> list[Candle]:
    """78 candele piatte a 100 (value area), poi un retest sotto VAL e un breakout
    sopra il massimo precedente: condizioni per un long del Volume Profile."""
    start = datetime(2026, 1, 1, tzinfo=UTC)
    out: list[Candle] = []
    for i in range(78):
        out.append(Candle(timestamp=start + timedelta(minutes=5 * i), open=100.0, high=100.5, low=99.5, close=100.0, volume=100.0))
    # previous: chiusura sotto la value area low (~99.5)
    out.append(Candle(timestamp=start + timedelta(minutes=5 * 78), open=99.5, high=99.6, low=98.8, close=99.0, volume=120.0))
    # current: breakout sopra previous.high con volume
    out.append(Candle(timestamp=start + timedelta(minutes=5 * 79), open=99.4, high=101.2, low=99.3, close=101.0, volume=500.0))
    return out


@pytest.mark.asyncio
async def test_perp_sl_tp_are_atr_anchored_with_controlled_rr() -> None:
    signal = await VolumeProfileSignal(settings()).evaluate(
        {"asset": "BTC", "candles": _breakout_long_candles()}
    )

    assert signal["side"] == "long"
    entry = signal["price"]
    sl = signal["stop_loss"]
    tp1 = signal["take_profit_1"]
    tp2 = signal["take_profit_2"]
    assert sl is not None and tp1 is not None and tp2 is not None
    # SL sotto l'entry, TP sopra: struttura coerente.
    assert sl < entry < tp1
    # R:R controllato: la distanza al TP1 supera quella allo stop (tp1_mult > sl_mult).
    assert (tp1 - entry) > (entry - sl)
    # TP2 non meno ambizioso del TP1.
    assert tp2 >= tp1


def test_risk_manager_blocks_assets_outside_eligible_universe() -> None:
    manager = RiskManager(settings())
    decision = manager.evaluate(
        SignalIntent(
            asset="NOT_ALLOWED",
            market="spot",
            side="long",
            price=Decimal("100"),
            stop_loss=Decimal("95"),
            quality=Decimal("0.8"),
            quote_equity=Decimal("1000"),
        ),
        portfolio=None,
        open_spot_positions=[],
        open_perp_positions=[],
    )

    assert decision.allowed is False
    assert decision.reason == "asset_not_in_eligible_universe"


def test_risk_manager_uses_settings_eligible_tokens() -> None:
    manager = RiskManager(settings(eligible_tokens=["BabyDoge"] + [f"TOKEN_{i}" for i in range(99)]))
    decision = manager.evaluate(
        SignalIntent(
            asset="BabyDoge",
            market="spot",
            side="long",
            price=Decimal("100"),
            stop_loss=Decimal("95"),
            quality=Decimal("0.8"),
            quote_equity=Decimal("1000"),
        ),
        portfolio=None,
        open_spot_positions=[],
        open_perp_positions=[],
    )

    assert decision.allowed is True
    assert decision.reason == "risk_approved"


def _intent(**overrides) -> SignalIntent:
    payload = dict(
        asset="BTC",
        market="spot",
        side="long",
        price=Decimal("100"),
        stop_loss=Decimal("95"),
        quality=Decimal("0.8"),
        quote_equity=Decimal("1000"),
    )
    payload.update(overrides)
    return SignalIntent(**payload)


def _portfolio(**overrides) -> PortfolioState:
    payload = dict(
        user_id=str(USER_ID),
        total_equity_usd=Decimal("1000"),
        initial_equity_usd=Decimal("1000"),
        peak_equity_usd=Decimal("1000"),
        drawdown_pct=Decimal("0"),
        max_drawdown_pct=Decimal("0"),
        exposure_pct=Decimal("0"),
        daily_pnl_usd=Decimal("0"),
        daily_loss_limit_used_pct=Decimal("0"),
        agent_status="idle",
        trades_today=0,
        updated_at=datetime.now(UTC),
    )
    payload.update(overrides)
    return PortfolioState(**payload)


def _spot_position(index: int = 0, asset: str = "BTC") -> SpotPosition:
    now = datetime.now(UTC)
    return SpotPosition(
        position_id=f"pos-{index}",
        user_id=str(USER_ID),
        asset=asset,
        size=Decimal("1"),
        entry_price=Decimal("100"),
        current_price=Decimal("100"),
        opened_at=now,
        updated_at=now,
    )


def test_risk_engine_daily_loss_limit() -> None:
    decision = RiskManager(settings()).evaluate(
        _intent(),
        portfolio=_portfolio(daily_loss_limit_used_pct=Decimal("-8.1")),
        open_spot_positions=[],
        open_perp_positions=[],
    )

    assert decision.allowed is False
    assert decision.reason == "daily_loss_limit_guard"


def test_risk_engine_max_positions() -> None:
    # Asset diversi tra loro e dall'intent: testa il limite totale, non il dedup per-asset.
    decision = RiskManager(settings(risk_max_open_positions=2)).evaluate(
        _intent(asset="TOKEN_5"),
        portfolio=_portfolio(),
        open_spot_positions=[_spot_position(1, asset="TOKEN_1"), _spot_position(2, asset="TOKEN_2")],
        open_perp_positions=[],
    )

    assert decision.allowed is False
    assert decision.reason == "max_open_positions_guard"


def test_risk_engine_dedup_per_asset() -> None:
    # Un nuovo segnale su un asset gia' in posizione viene bloccato prima del limite totale.
    decision = RiskManager(settings(risk_max_open_positions=5)).evaluate(
        _intent(asset="BTC"),
        portfolio=_portfolio(),
        open_spot_positions=[_spot_position(1, asset="BTC")],
        open_perp_positions=[],
    )

    assert decision.allowed is False
    assert decision.reason == "asset_already_open"


def test_risk_engine_drawdown_cap_positive_convention() -> None:
    # drawdown_pct e' positivo (entita' del calo); cap negativo -15 => blocca a >= 15.
    decision = RiskManager(settings()).evaluate(
        _intent(),
        portfolio=_portfolio(drawdown_pct=Decimal("16")),
        open_spot_positions=[],
        open_perp_positions=[],
    )

    assert decision.allowed is False
    assert decision.reason == "drawdown_cap_guard"


def test_risk_engine_guardia_dollar() -> None:
    decision = RiskManager(settings(min_portfolio_value_usd=5.0)).evaluate(
        _intent(),
        portfolio=_portfolio(total_equity_usd=Decimal("5")),
        open_spot_positions=[],
        open_perp_positions=[],
    )

    assert decision.allowed is False
    assert decision.reason == "portfolio_floor_guard"


def test_risk_engine_size_cap() -> None:
    decision = RiskManager(settings()).evaluate(
        _intent(price=Decimal("100"), stop_loss=Decimal("50")),
        portfolio=_portfolio(total_equity_usd=Decimal("1000")),
        open_spot_positions=[],
        open_perp_positions=[],
    )

    assert decision.allowed is True
    assert decision.size_quote == Decimal("30.00")


def test_risk_engine_uses_200_dry_run_capital_for_natural_size() -> None:
    decision = RiskManager(settings()).evaluate(
        _intent(quote_equity=Decimal("200"), price=Decimal("100"), stop_loss=Decimal("95")),
        portfolio=None,
        open_spot_positions=[],
        open_perp_positions=[],
    )

    assert decision.allowed is True
    assert decision.size_quote == Decimal("8.00")


def test_risk_engine_perp_fixed_margin_overrides_dynamic_size() -> None:
    mobile_settings = AgentMobileSettings(
        perp_fixed_margin_enabled=True,
        perp_fixed_margin_usd=50,
        perp_max_exposure_pct=100,
    )
    decision = RiskManager(settings()).evaluate(
        _intent(market="perp", quote_equity=Decimal("1000"), price=Decimal("100"), stop_loss=Decimal("95")),
        portfolio=_portfolio(total_equity_usd=Decimal("1000")),
        open_spot_positions=[],
        open_perp_positions=[],
        ms=mobile_settings,
    )

    assert decision.allowed is True
    assert decision.size_quote == Decimal("50.0")


def test_risk_engine_blocks_below_minimum_trade_size() -> None:
    decision = RiskManager(settings()).evaluate(
        _intent(quote_equity=Decimal("100"), price=Decimal("100"), stop_loss=Decimal("95")),
        portfolio=None,
        open_spot_positions=[],
        open_perp_positions=[],
    )

    assert decision.allowed is False
    assert decision.reason == "below_minimum_trade_size"
    assert decision.size_quote == Decimal("4.00")


@pytest.mark.asyncio
async def test_meta_controller_fallback_on_timeout(monkeypatch) -> None:
    class TimeoutClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            raise TimeoutError("timeout")

    monkeypatch.setattr("backend.app.agent.brain.meta_controller.httpx.AsyncClient", TimeoutClient)

    decision, _usage = await ClaudeMetaController(settings(anthropic_api_key="configured")).decide(
        signal={"quality": 0.9},
        risk={"allowed": True, "reason": "risk_approved"},
    )

    assert decision.action == "approve"
    assert "claude_unavailable_dry_run" in decision.reasoning


@pytest.mark.asyncio
async def test_meta_controller_reduce() -> None:
    decision, _usage = await ClaudeMetaController(settings()).decide(
        signal={"quality": 0.7},
        risk={"allowed": True, "reason": "risk_approved"},
    )

    assert decision.action == "reduce"
    assert decision.size_multiplier == Decimal("0.5")


def test_kill_switch_soft_stop() -> None:
    manager = RiskManager(settings())
    manager.set_kill_switch(KillSwitchState.SOFT_STOP)

    decision = manager.evaluate(_intent(), portfolio=_portfolio(), open_spot_positions=[], open_perp_positions=[])

    assert decision.allowed is False
    assert decision.reason == "soft_stop"


def test_kill_switch_hard_stop() -> None:
    manager = RiskManager(settings())
    manager.set_kill_switch(KillSwitchState.HARD_STOP)

    decision = manager.evaluate(_intent(), portfolio=_portfolio(), open_spot_positions=[], open_perp_positions=[])

    assert decision.allowed is False
    assert decision.reason == "hard_stop_enabled"


@pytest.mark.asyncio
async def test_agent_service_dry_run_persists_decision_and_trade(db) -> None:
    class FakeSignal:
        async def evaluate(self, payload):
            return {
                "signal_id": "sig-test",
                "market": "spot",
                "asset": "BTC",
                "action": "enter_long",
                "quality": 0.9,
                "confidence": 0.9,
                "price": 100.0,
                "stop_loss": 95.0,
                "quote_equity": 1000.0,
            }

    service = AgentService(
        settings(),
        spot_signal=FakeSignal(),
        perp_signal=VolumeProfileSignal(settings()),
        risk_manager=RiskManager(settings()),
        brain=ClaudeMetaController(settings()),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    async with get_session_factory()() as session:
        result = await service.evaluate_spot({}, session)
        decisions = await AgentDecisionRepository(session).recent_for_user(str(USER_ID))
        trades = await SpotTradeRepository(session).list_for_user(str(USER_ID))

    assert result["execution"]["status"] == "prepared"
    assert len(decisions) == 1
    assert decisions[0].action == "approve"
    assert len(trades) == 1
    assert trades[0].status == "prepared"


@pytest.mark.asyncio
async def test_agent_service_dry_run_persists_perp_decision_and_trade(db) -> None:
    class FakeSignal:
        async def evaluate(self, payload):
            return {
                "signal_id": "sig-perp-test",
                "market": "perp",
                "asset": "BTC",
                "action": "enter_long",
                "side": "long",
                "quality": 0.9,
                "confidence": 0.9,
                "price": 100.0,
                "stop_loss": 95.0,
                "quote_equity": 1000.0,
                "leverage": 2,
            }

    service = AgentService(
        settings(),
        spot_signal=SpotMomentumSignal(settings()),
        perp_signal=FakeSignal(),
        risk_manager=RiskManager(settings()),
        brain=ClaudeMetaController(settings()),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    async with get_session_factory()() as session:
        result = await service.evaluate_perp({}, session)
        decisions = await AgentDecisionRepository(session).recent_for_user(str(USER_ID))
        trades = await PerpTradeRepository(session).list_for_user(str(USER_ID))

    assert result["execution"]["status"] == "prepared"
    assert len(decisions) == 1
    assert decisions[0].market == "perp"
    assert len(trades) == 1
    assert trades[0].status == "prepared"


def test_perp_trade_detail_exposure_uses_notional_once() -> None:
    now = datetime(2026, 7, 27, tzinfo=UTC)
    trade = PerpTrade(
        trade_id="dry_trx_test",
        user_id=str(USER_ID),
        asset="TRX",
        side="long",
        direction="open",
        size=Decimal("669.8183789575523"),
        price=Decimal("0.33076"),
        leverage=25,
        status="prepared",
        timestamp_utc=now,
        venue="dry_run",
    )
    position = PerpPosition(
        position_id="pos_trx_test",
        user_id=str(USER_ID),
        asset="TRX",
        side="long",
        size=Decimal("669.8183789575523"),
        entry_price=Decimal("0.33076"),
        current_price=Decimal("0.33076"),
        leverage=25,
        pnl_unrealized=Decimal("0"),
        status="open",
        margin_usd=Decimal("8.86196508096"),
        stop_reference_price=Decimal("0.3299"),
        stop_reference_field="low",
        opened_at=now,
        updated_at=now,
    )

    detail = view_routes._perp_trade_detail(trade, position, None, settings())

    assert detail["margin_usd"] == "8.86"
    assert detail["exposure_usd"] == "221.55"
    assert detail["stop_reference_price"] == "0.3299"
    assert detail["stop_reference_field"] == "low"


def test_perp_smart_sl_detail_preserves_original_entry() -> None:
    now = datetime(2026, 8, 9, tzinfo=UTC)
    trade = PerpTrade(
        trade_id="ssl_pos_btc_test_abc12345",
        user_id=str(USER_ID),
        asset="BTC",
        side="long",
        direction="close",
        size=Decimal("0.25"),
        price=Decimal("94"),
        leverage=10,
        status="confirmed",
        timestamp_utc=now,
        venue="dry_run",
        notes="auto_close:smart_sl_sell_l1",
        pnl_usd=Decimal("-1.50"),
    )
    position = PerpPosition(
        position_id="pos_btc_test",
        user_id=str(USER_ID),
        asset="BTC",
        side="long",
        size=Decimal("0.75"),
        entry_price=Decimal("97"),
        current_price=Decimal("94"),
        leverage=10,
        pnl_unrealized=Decimal("-2.25"),
        initial_stop_loss=Decimal("90"),
        status="open",
        smart_sl_state=json.dumps(
            {
                "original_size": "1",
                "original_entry": "100",
                "levels": [
                    {"status": "sold", "sell_price": "94", "reentries": 0},
                    {"status": "idle", "sell_price": None, "reentries": 0},
                ],
            }
        ),
        opened_at=now - timedelta(hours=1),
        updated_at=now,
    )

    detail = view_routes._perp_trade_detail(trade, position, None, settings())

    assert detail["is_smart_sl"] is True
    assert detail["entry_price"] == "100.00"
    assert detail["original_entry_price"] == "100.00"
    assert detail["current_position_entry_price"] == "97.00"
    assert detail["current_or_exit_price"] == "94.00"


def test_perp_smart_sl_rebuy_tp_adjustment_uses_actual_tp1_close_pct() -> None:
    service = AgentService(settings(), spot_registry=SimpleNamespace(), perp_registry=SimpleNamespace())
    ms = AgentMobileSettings(
        perp_tp1_close_pct=70.0,
        perp_smart_sl_tp_adjust_after_rebuy=True,
        perp_smart_sl_tp_recovery_delta_pct=7.0,
    )
    position = PerpPosition(
        position_id="pos_dot_rebuy_recovery",
        user_id=str(USER_ID),
        asset="DOT",
        side="long",
        size=Decimal("1640.635253970337316787"),
        entry_price=Decimal("0.7621499999996998"),
        current_price=Decimal("0.762900"),
        leverage=25,
        pnl_unrealized=Decimal("0"),
        opening_fee_usd=Decimal("0.75000000"),
        slippage_usd=Decimal("0"),
        funding_accrued_usd=Decimal("0.05665298490488541343922602065"),
        status="open",
        opened_at=datetime(2026, 8, 14, tzinfo=UTC),
        updated_at=datetime(2026, 8, 14, tzinfo=UTC),
    )
    realized_loss = Decimal("-1.813972005565617162091728961")
    state = {
        "original_size": "1640.635253970337316787",
        "original_entry": "0.761900000000000022",
        "levels": [
            {"status": "rebought", "realized_loss": str(realized_loss)},
            {"status": "idle"},
        ],
    }

    adjusted = service._adjust_smart_sl_recovery_take_profits(position, state, ms, True)

    assert adjusted is True
    assert position.take_profit_1 is not None
    assert position.take_profit_2 is not None
    assert position.entry_price < position.take_profit_1 < position.take_profit_2

    tp1_fraction = Decimal("0.70")
    tp1_size = (position.size * tp1_fraction).quantize(Decimal("0.000001"))
    tp2_size = position.size - tp1_size
    fee_only = position.opening_fee_usd - position.slippage_usd
    funding = position.funding_accrued_usd
    expected_recovery = abs(realized_loss) * Decimal("1.07")
    pnl_tp1 = (position.take_profit_1 - position.entry_price) * tp1_size - fee_only * tp1_fraction + funding * tp1_fraction
    pnl_tp2 = (position.take_profit_2 - position.entry_price) * tp2_size - fee_only * (Decimal("1") - tp1_fraction) + funding * (Decimal("1") - tp1_fraction)

    assert pnl_tp1 + pnl_tp2 >= expected_recovery


def test_spot_trade_detail_preserves_micro_token_prices() -> None:
    now = datetime(2026, 8, 1, tzinfo=UTC)
    entry = Decimal("0.000000001234")
    size = Decimal("32585089141.00486223662884927")
    trade = SpotTrade(
        trade_id="dry_babydoge_test",
        user_id=str(USER_ID),
        asset="BABYDOGE",
        side="buy",
        amount=size,
        price=entry,
        amount_quote=Decimal("40.21"),
        status="prepared",
        timestamp_utc=now,
        provider="dry_run",
    )
    position = SpotPosition(
        position_id="pos_babydoge_test",
        user_id=str(USER_ID),
        asset="BABYDOGE",
        size=size,
        entry_price=entry,
        current_price=entry,
        pnl_unrealized=Decimal("0"),
        status="open",
        stop_loss=Decimal("0.000000001100"),
        initial_stop_loss=Decimal("0.000000001100"),
        take_profit_1=Decimal("0.000000001400"),
        take_profit_2=Decimal("0.000000001600"),
        opened_at=now,
        updated_at=now,
    )

    detail = view_routes._spot_trade_detail(trade, position, None, settings())

    assert detail["entry_price"] == "0.000000001234"
    assert detail["current_or_exit_price"] == "0.000000001234"
    assert detail["stop_loss"] == "0.0000000011"
    assert detail["take_profit_1"] == "0.0000000014"
    assert detail["take_profit_2"] == "0.0000000016"
    assert detail["exposure_usd"] == "40.21"


def test_spot_trade_detail_recovers_zero_entry_from_trade_notional() -> None:
    now = datetime(2026, 8, 1, tzinfo=UTC)
    size = Decimal("32585089141.00486223662884927")
    trade = SpotTrade(
        trade_id="dry_babydoge_recover",
        user_id=str(USER_ID),
        asset="BABYDOGE",
        side="buy",
        amount=size,
        price=Decimal("0"),
        amount_quote=Decimal("40.21"),
        status="prepared",
        timestamp_utc=now,
        provider="dry_run",
    )
    position = SpotPosition(
        position_id="pos_babydoge_recover",
        user_id=str(USER_ID),
        asset="BABYDOGE",
        size=size,
        entry_price=Decimal("0"),
        current_price=Decimal("0"),
        pnl_unrealized=Decimal("0"),
        status="open",
        opened_at=now,
        updated_at=now,
    )

    detail = view_routes._spot_trade_detail(trade, position, None, settings())

    assert detail["entry_price"] == "0.000000001234"
    assert detail["current_or_exit_price"] == "0.000000001234"
    assert detail["exposure_usd"] == "40.21"
    assert detail["pnl_pct"] == "+0.00"


@pytest.mark.asyncio
async def test_perp_fixed_margin_remains_final_margin_when_brain_reduces(db) -> None:
    mobile_settings = AgentMobileSettings(
        perp_fixed_margin_enabled=True,
        perp_fixed_margin_usd=50,
        perp_fee_mode="none",
    )
    set_runtime_value(str(USER_ID), "mobile_agent_settings", mobile_settings.model_dump_json())
    service = AgentService(
        settings(),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    signal = {
        "signal_id": "fixed-margin",
        "market": "perp",
        "asset": "BTC",
        "action": "enter_long",
        "side": "long",
        "quality": 0.7,
        "confidence": 0.7,
        "price": 100,
        "stop_loss": 95,
        "leverage": 10,
        "size_factor": 0.5,
    }
    risk_decision = RiskDecision(True, "risk_approved", size_quote=Decimal("50"))
    brain_decision = SimpleNamespace(size_multiplier=Decimal("0.5"))

    async with get_session_factory()() as session:
        result = await service._execute_or_simulate(session, signal, risk_decision, brain_decision)
        positions = await PerpPositionRepository(session).open_for_user(str(USER_ID))

    assert result["status"] == "prepared"
    assert positions[0].margin_usd == Decimal("50")


@pytest.mark.asyncio
async def test_heartbeat_triggers_at_20utc(db) -> None:
    service = AgentService(
        settings(eligible_tokens=["ETH"] + [f"TOKEN_{i}" for i in range(148)]),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    now = datetime(2026, 6, 22, 20, 0, tzinfo=UTC)
    async with get_session_factory()() as session:
        result = await service.slow_tick(session, now=now)
        trades = await SpotTradeRepository(session).list_for_user(str(USER_ID))

    heartbeat_result = result["daily_trade_heartbeat"]
    assert heartbeat_result["status"] == "executed"
    assert heartbeat_result["mode"] == "dry_run"
    assert len(trades) == 1
    assert trades[0].asset == "ETH"
    assert trades[0].notes == "dry_run_step6"
    assert trades[0].amount_quote == Decimal("7")


@pytest.mark.asyncio
async def test_build_spot_swap_params_maps_token() -> None:
    service = AgentService(
        settings(
            spot_quote_token_address="0xQUOTE",
            spot_quote_token_decimals=18,
            spot_token_map={"ETH": "0xETH:18"},
        ),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    params = await service._build_spot_swap_params({"asset": "ETH"}, Decimal("10"))
    assert params is not None
    assert params["from_asset"] == "0xQUOTE"
    assert params["to_asset"] == "0xETH"
    assert params["amount_in_atomic"] == 10 * 10**18


@pytest.mark.asyncio
async def test_build_spot_swap_params_skips_when_unmapped_and_no_resolver() -> None:
    # Asset non in mappa e nessun resolver CMC (api_key None) => None.
    s1 = AgentService(
        settings(spot_quote_token_address="0xQUOTE", spot_token_map={}),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    assert await s1._build_spot_swap_params({"asset": "ETH"}, Decimal("10")) is None


@pytest.mark.asyncio
async def test_build_spot_swap_params_resolves_via_cmc() -> None:
    # Niente mappa statica: indirizzi risolti dal resolver CMC iniettato.
    class FakeResolver:
        async def resolve_contract_address(self, symbol: str, **_: object) -> str:
            return {"ETH": "0xETHCMC", "USDT": "0xUSDTCMC"}[symbol.upper()]

    service = AgentService(
        settings(spot_quote_token_address=None, spot_token_map={}),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
        token_resolver=FakeResolver(),
    )
    params = await service._build_spot_swap_params({"asset": "ETH"}, Decimal("10"))
    assert params is not None
    assert params["from_asset"] == "0xUSDTCMC"
    assert params["to_asset"] == "0xETHCMC"
    assert params["amount_in_atomic"] == 10 * 10**18


@pytest.mark.asyncio
async def test_close_generates_chart_snapshot(db) -> None:
    service = AgentService(
        settings(),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    now = datetime.now(UTC)

    class FakeFeed:
        async def fetch(self, *, symbol, interval, limit, market):
            return [
                Candle(timestamp=now - timedelta(minutes=5 * i), open=100, high=101, low=99, close=100.5, volume=1.0)
                for i in range(5)
            ]

    service.price_feed = FakeFeed()
    pos = SpotPosition(
        position_id="pos-chart",
        user_id=str(USER_ID),
        asset="BTC",
        size=Decimal("1"),
        entry_price=Decimal("100"),
        current_price=Decimal("103"),
        stop_loss=Decimal("98"),
        take_profit_1=Decimal("103"),
        take_profit_2=Decimal("106"),
        tp1_reached=True,
        status="open",
        opened_at=now - timedelta(hours=2),
        updated_at=now,
    )
    async with get_session_factory()() as session:
        await service._close_spot_position(session, pos, Decimal("103"), "take_profit_2", now)
        snap = await TradeChartRepository(session).get_for_position(str(USER_ID), "pos-chart")

    assert snap is not None
    payload = json.loads(snap.payload)
    assert payload["entry_price"] == "100"
    assert payload["exit_price"] == "103"
    assert len(payload["candles"]) == 5


@pytest.mark.asyncio
async def test_close_chart_snapshot_starts_before_stop_reference(db) -> None:
    service = AgentService(
        settings(),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    now = datetime(2026, 7, 19, 10, 0, tzinfo=UTC)
    opened_at = now - timedelta(hours=1)
    reference_time = opened_at - timedelta(minutes=25)
    expected_start = opened_at - timedelta(minutes=100)
    calls: list[dict] = []

    class FakeFeed:
        async def fetch(self, **kwargs):
            calls.append(kwargs)
            return [
                Candle(timestamp=expected_start + timedelta(minutes=5 * i), open=100, high=101, low=99, close=100.5, volume=1.0)
                for i in range(35)
            ]

    service.price_feed = FakeFeed()
    pos = SpotPosition(
        position_id="pos-chart-ref",
        user_id=str(USER_ID),
        asset="BTC",
        size=Decimal("1"),
        entry_price=Decimal("100"),
        current_price=Decimal("103"),
        stop_loss=Decimal("120"),
        initial_stop_loss=Decimal("98"),
        stop_reference_time=reference_time,
        stop_reference_price=Decimal("97.5"),
        stop_reference_field="low",
        take_profit_1=Decimal("103"),
        take_profit_2=Decimal("106"),
        tp1_reached=True,
        status="open",
        opened_at=opened_at,
        updated_at=now,
    )
    async with get_session_factory()() as session:
        await service._close_spot_position(session, pos, Decimal("103"), "take_profit_2", now)
        snap = await TradeChartRepository(session).get_for_position(str(USER_ID), "pos-chart-ref")

    assert calls[0]["start_time"] == expected_start
    assert snap is not None
    payload = json.loads(snap.payload)
    assert payload["stop_loss"] == "98"
    assert payload["stop_reference"] == {
        "t": reference_time.isoformat(),
        "price": "97.5",
        "field": "low",
        "pre_candles": 20,
    }
    assert payload["candles"][0]["t"] == expected_start.isoformat()


@pytest.mark.asyncio
async def test_closed_trade_chart_trims_snapshot_and_dedupes_post_close(monkeypatch) -> None:
    closed_at = datetime(2026, 7, 18, 10, 57, tzinfo=UTC)
    chart = {
        "interval": "5m",
        "opened_at": datetime(2026, 7, 18, 10, 45, tzinfo=UTC).isoformat(),
        "closed_at": closed_at.isoformat(),
        "candles": [
            {"t": datetime(2026, 7, 18, 10, 55, tzinfo=UTC).isoformat(), "o": 100, "h": 104, "l": 99, "c": 103},
            {"t": datetime(2026, 7, 18, 11, 0, tzinfo=UTC).isoformat(), "o": 103, "h": 105, "l": 102, "c": 104},
            {"t": datetime(2026, 7, 18, 10, 50, tzinfo=UTC).isoformat(), "o": 99, "h": 101, "l": 98, "c": 100},
        ],
    }
    normalized = view_routes._normalize_closed_chart(chart)
    assert [c["t"] for c in normalized["candles"]] == [
        datetime(2026, 7, 18, 10, 50, tzinfo=UTC).isoformat(),
        datetime(2026, 7, 18, 10, 55, tzinfo=UTC).isoformat(),
    ]

    fetched = [
        Candle(timestamp=datetime(2026, 7, 18, 10, 55, tzinfo=UTC), open=100, high=104, low=99, close=103, volume=1),
        Candle(timestamp=datetime(2026, 7, 18, 11, 0, tzinfo=UTC), open=103, high=105, low=102, close=104, volume=1),
        Candle(timestamp=datetime(2026, 7, 18, 11, 5, tzinfo=UTC), open=104, high=106, low=103, close=105, volume=1),
    ]
    calls: list[dict] = []

    class FakeKlineFeed:
        def __init__(self, **_: object) -> None:
            pass

        async def fetch(self, **kwargs):
            calls.append(kwargs)
            return fetched

    monkeypatch.setattr(binance_klines, "BinanceKlineFeed", FakeKlineFeed)
    monkeypatch.setattr(view_routes, "datetime", SimpleNamespace(
        now=lambda _tz: datetime(2026, 7, 18, 11, 10, tzinfo=UTC),
        fromisoformat=datetime.fromisoformat,
    ))

    post = await view_routes._fetch_post_close_candles(normalized, "BTC", "spot", count=5)
    assert calls[0]["start_time"] == closed_at + timedelta(milliseconds=1)
    assert [c["t"] for c in post] == [
        datetime(2026, 7, 18, 11, 0, tzinfo=UTC).isoformat(),
        datetime(2026, 7, 18, 11, 5, tzinfo=UTC).isoformat(),
    ]


@pytest.mark.asyncio
async def test_live_trade_chart_infers_stop_reference_for_legacy_position(monkeypatch) -> None:
    clear_kline_cache()
    now = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    opened_at = datetime(2026, 7, 19, 11, 0, tzinfo=UTC)
    expected_start = opened_at - timedelta(minutes=100)
    reference_time = expected_start + timedelta(minutes=5 * 18)
    calls: list[dict] = []

    class FakeKlineFeed:
        def __init__(self, **_: object) -> None:
            pass

        async def fetch(self, **kwargs):
            calls.append(kwargs)
            out = []
            for index in range(35):
                ts = expected_start + timedelta(minutes=5 * index)
                low = 88.0 if ts == reference_time else 97.0 + index / 100
                out.append(Candle(timestamp=ts, open=100, high=101, low=low, close=100.5, volume=1))
            return out

    monkeypatch.setattr(binance_klines, "BinanceKlineFeed", FakeKlineFeed)
    monkeypatch.setattr(view_routes, "datetime", SimpleNamespace(
        now=lambda _tz: now,
        fromisoformat=datetime.fromisoformat,
    ))
    position = SimpleNamespace(
        asset="BTC",
        side="long",
        entry_price=Decimal("100"),
        current_price=Decimal("101"),
        stop_loss=Decimal("120"),
        initial_stop_loss=Decimal("87"),
        take_profit_1=Decimal("103"),
        take_profit_2=Decimal("106"),
        liquidation_price=None,
        opened_at=opened_at,
    )

    chart = await view_routes._build_live_chart(position, "spot", settings=settings())

    assert calls[0]["start_time"] == expected_start
    assert chart is not None
    assert chart["stop_loss"] == "87.00"
    assert chart["candles"][0]["t"] == expected_start.isoformat()
    assert chart["stop_reference"] == {
        "t": reference_time.isoformat(),
        "price": "88.0",
        "field": "low",
        "pre_candles": 20,
        "inferred": True,
    }


@pytest.mark.asyncio
async def test_closed_trade_chart_enrichment_prepends_legacy_stop_context(monkeypatch) -> None:
    opened_at = datetime(2026, 7, 19, 10, 0, tzinfo=UTC)
    closed_at = datetime(2026, 7, 19, 10, 30, tzinfo=UTC)
    expected_start = opened_at - timedelta(minutes=100)
    reference_time = expected_start + timedelta(minutes=5 * 18)
    chart = {
        "interval": "5m",
        "market": "spot",
        "side": "long",
        "entry_price": "100",
        "exit_price": "102",
        "stop_loss": "92",
        "opened_at": opened_at.isoformat(),
        "closed_at": closed_at.isoformat(),
        "candles": [
            {"t": opened_at.isoformat(), "o": 100, "h": 101, "l": 99, "c": 100.5},
            {"t": (opened_at + timedelta(minutes=5)).isoformat(), "o": 100.5, "h": 102, "l": 100, "c": 101.5},
        ],
    }
    calls: list[dict] = []

    class FakeKlineFeed:
        def __init__(self, **_: object) -> None:
            pass

        async def fetch(self, **kwargs):
            calls.append(kwargs)
            out = []
            for index in range(40):
                ts = expected_start + timedelta(minutes=5 * index)
                low = 91.0 if ts == reference_time else 98.0 + index / 100
                out.append(Candle(timestamp=ts, open=100, high=101, low=low, close=100.5, volume=1))
            return out

    monkeypatch.setattr(binance_klines, "BinanceKlineFeed", FakeKlineFeed)

    enriched = await view_routes._enrich_trade_chart_context(chart, "BTC", "spot", "spot", "long", settings())

    assert calls[0]["start_time"] == expected_start
    assert enriched is not None
    assert enriched["candles"][0]["t"] == expected_start.isoformat()
    assert enriched["stop_reference"] == {
        "t": reference_time.isoformat(),
        "price": "91.0",
        "field": "low",
        "pre_candles": 20,
        "inferred": True,
    }


@pytest.mark.asyncio
async def test_spot_trailing_active_from_start(db) -> None:
    # v3 (C): il trailing è attivo DA SUBITO, non più solo dopo TP1.
    service = AgentService(
        settings(),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    now = datetime.now(UTC)

    def _pos(position_id: str, tp1: bool) -> SpotPosition:
        # entry 100, trailing a 99, prezzo a 98 (sotto il trailing): chiude per trailing.
        # stop_loss basso (90) e nessun TP per isolare il solo trailing.
        return SpotPosition(
            position_id=position_id,
            user_id=str(USER_ID),
            asset="BTC",
            size=Decimal("1"),
            entry_price=Decimal("100"),
            current_price=Decimal("98"),
            stop_loss=Decimal("90"),
            trailing_stop=Decimal("99"),
            tp1_reached=tp1,
            status="open",
            opened_at=now,
            updated_at=now,
        )

    pos_no_tp1 = _pos("p-no-tp1", tp1=False)
    pos_tp1 = _pos("p-tp1", tp1=True)
    async with get_session_factory()() as session:
        await service._check_sl_tp(session, [pos_no_tp1, pos_tp1], [], now)

    # Il trailing chiude in entrambi i casi: non è più gated dal TP1.
    assert pos_no_tp1.status == "closed"
    assert pos_tp1.status == "closed"


@pytest.mark.asyncio
async def test_heartbeat_skips_when_eth_already_open(db) -> None:
    service = AgentService(
        settings(eligible_tokens=["ETH"] + [f"TOKEN_{i}" for i in range(148)]),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    now = datetime(2026, 6, 22, 20, 0, tzinfo=UTC)
    async with get_session_factory()() as session:
        await SpotPositionRepository(session).save(_spot_position(0, asset="ETH"))
        result = await service.slow_tick(session, now=now)

    heartbeat_result = result["daily_trade_heartbeat"]
    assert heartbeat_result["status"] == "satisfied"
    assert heartbeat_result["reason"] == "asset_already_open"


@pytest.mark.asyncio
async def test_agent_service_does_not_run_risk_universe_on_skipped_signal(db) -> None:
    class SkippedSignal:
        async def evaluate(self, payload):
            return {
                "signal_id": "sig-skip",
                "market": "spot",
                "asset": payload.get("asset"),
                "action": "skip",
                "quality": 0.0,
                "reason": "insufficient_ohlcv_history",
                "components": {},
            }

    service = AgentService(
        settings(),
        spot_signal=SkippedSignal(),
        perp_signal=VolumeProfileSignal(settings()),
        risk_manager=RiskManager(settings()),
        brain=ClaudeMetaController(settings()),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    async with get_session_factory()() as session:
        result = await service.evaluate_spot({"asset": "CAKE"}, session)

    assert result["signal"]["asset"] == "CAKE"
    assert result["risk"]["reason"] == "signal_skipped:insufficient_ohlcv_history"
    assert result["execution"]["reason"] == "insufficient_ohlcv_history"


@pytest.mark.asyncio
async def test_agent_service_data_coverage_reports_cached_spot_candles(db) -> None:
    clear_kline_cache()
    cfg = settings(markets_enabled="spot", eligible_tokens=["CAKE"] + [f"TOKEN_{i}" for i in range(99)])
    set_selected_watchlist(cfg, ["CAKE"])
    binance_klines._KLINE_CACHE[("spot", "CAKEUSDT", "5m")] = BinanceKlineCacheEntry(
        market="spot",
        symbol="CAKEUSDT",
        interval="5m",
        candles=candles(80),
        updated_at=datetime.now(UTC),
    )
    service = AgentService(
        cfg,
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )

    coverage = service.data_coverage()
    cake = next(item for item in coverage["items"] if item["asset"] == "CAKE")

    assert cake["market"] == "spot"
    assert cake["available_candles"] == 80
    assert cake["required_candles"] == 50
    assert cake["status"] == "ready"
    assert cake["first_candle_at"] is not None
    assert cake["last_candle_at"] is not None
    assert cake["source"] == "Binance klines 5m"


@pytest.mark.asyncio
async def test_agent_service_data_coverage_reports_cache_miss(db) -> None:
    clear_kline_cache()
    cfg = settings(markets_enabled="spot", eligible_tokens=["CAKE"] + [f"TOKEN_{i}" for i in range(99)])
    set_selected_watchlist(cfg, ["CAKE"])
    service = AgentService(
        cfg,
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )

    coverage = service.data_coverage()
    cake = next(item for item in coverage["items"] if item["asset"] == "CAKE")

    assert cake["available_candles"] == 0
    assert cake["status"] == "insufficient"
    assert cake["updated_at"] is None


@pytest.mark.asyncio
async def test_watchlist_warmup_populates_data_coverage_cache(db) -> None:
    clear_kline_cache()
    cfg = settings(markets_enabled="both", eligible_tokens=["CAKE"] + [f"TOKEN_{i}" for i in range(99)])
    set_selected_watchlist(cfg, ["CAKE"])

    class FakeFeed:
        def __init__(self) -> None:
            self.calls = []

        async def fetch(self, **kwargs):
            self.calls.append(kwargs)
            payload = candles(288)
            binance_klines._KLINE_CACHE[(kwargs["market"], kwargs["symbol"], kwargs["interval"])] = BinanceKlineCacheEntry(
                market=kwargs["market"],
                symbol=kwargs["symbol"],
                interval=kwargs["interval"],
                candles=payload,
                updated_at=datetime.now(UTC),
            )
            return payload

    feed = FakeFeed()
    result = await warmup_selected_watchlist(cfg, feed=feed)
    service = AgentService(
        cfg,
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    coverage = service.data_coverage()
    cake_items = [item for item in coverage["items"] if item["asset"] == "CAKE"]

    assert result["loaded"] == 2
    assert len(feed.calls) == 2
    assert all(call["limit"] >= 288 for call in feed.calls)
    assert {item["market"] for item in cake_items} == {"spot", "perp"}
    assert all(item["available_candles"] == 288 for item in cake_items)
    assert all(item["status"] == "ready" for item in cake_items)


class _FakeResp:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def get(self, url, params=None):
        return _FakeResp(self._payload)


@pytest.mark.asyncio
async def test_kucoin_spot_kline_parsing_maps_close_before_high() -> None:
    from backend.app.agent.signals.perp.cex_fallback import _kucoin_klines

    # KuCoin spot row: [time(sec), open, close, high, low, volume, turnover]
    payload = {"data": [["1700000000", "100", "105", "110", "95", "10", "1000"]]}
    candles = await _kucoin_klines(_FakeClient(payload), "ETHUSDT", "5m", 100, False)
    assert len(candles) == 1
    c = candles[0]
    assert (c.open, c.close, c.high, c.low) == (100.0, 105.0, 110.0, 95.0)


@pytest.mark.asyncio
async def test_bitget_spot_kline_parsing() -> None:
    from backend.app.agent.signals.perp.cex_fallback import _bitget_klines

    # Bitget row: [ts(ms), open, high, low, close, baseVol, quoteVol]
    payload = {"data": [["1700000000000", "100", "110", "95", "105", "10", "1000"]]}
    candles = await _bitget_klines(_FakeClient(payload), "ETHUSDT", "5m", 100, False)
    assert len(candles) == 1
    c = candles[0]
    assert (c.open, c.high, c.low, c.close) == (100.0, 110.0, 95.0, 105.0)


def test_estimate_liquidation_price() -> None:
    from backend.app.agent.service import _estimate_liquidation_price

    assert _estimate_liquidation_price(Decimal("100"), 2, "long") == Decimal("50.00000000")
    assert _estimate_liquidation_price(Decimal("100"), 2, "short") == Decimal("150.00000000")
    assert _estimate_liquidation_price(Decimal("100"), 0, "long") is None


def test_level_fill_price_caps_loss_to_stop_level() -> None:
    """Su chiusura per stop, il fill è al livello dello stop, non al prezzo di
    mercato gappato (che con feed in ritardo gonfierebbe la perdita)."""
    from backend.app.agent.service import _level_fill_price

    short = SimpleNamespace(
        stop_loss=Decimal("6.149714e-05"),
        trailing_stop=Decimal("6.13e-05"),
        take_profit_1=Decimal("6.0e-05"),
        take_profit_2=Decimal("5.858e-05"),
    )
    gapped_market = Decimal("6.189e-05")  # ha superato lo stop di 0.64%

    # stop_loss → riempie al livello dello stop, non al mercato gappato.
    assert _level_fill_price(short, "stop_loss", gapped_market) == Decimal("6.149714e-05")
    # TP usano il proprio livello.
    assert _level_fill_price(short, "take_profit_1", gapped_market) == Decimal("6.0e-05")
    assert _level_fill_price(short, "take_profit_2", gapped_market) == Decimal("5.858e-05")
    assert _level_fill_price(short, "trailing_stop", gapped_market) == Decimal("6.13e-05")
    # time_stop (non su livello) → prezzo di mercato.
    assert _level_fill_price(short, "time_stop", gapped_market) == gapped_market
    # livello assente → fallback al mercato.
    no_level = SimpleNamespace(stop_loss=None, trailing_stop=None, take_profit_1=None, take_profit_2=None)
    assert _level_fill_price(no_level, "stop_loss", gapped_market) == gapped_market


def test_fetch_prices_resolves_1000_prefixed_futures_symbol(monkeypatch) -> None:
    """LUNC su futures è 1000LUNCUSDT (prezzo ×1000): il refresh deve risolverlo
    e riportarlo al prezzo unitario (÷1000), senza dipendere dal fallback CEX."""
    import asyncio

    import httpx

    from backend.app.agent.signals.perp.binance_klines import BinanceKlineFeed

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload
            self.status_code = 200

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None):
            syms = params["symbols"]
            # Prima chiamata: LUNCUSDT non esiste su futures → vuoto.
            if '"LUNCUSDT"' in syms and "1000" not in syms:
                return FakeResponse([])
            # Seconda chiamata: variante 1000LUNCUSDT con prezzo ×1000.
            if "1000LUNCUSDT" in syms:
                return FakeResponse([{"symbol": "1000LUNCUSDT", "price": "0.06189"}])
            return FakeResponse([])

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    feed = BinanceKlineFeed()
    prices = asyncio.run(feed.fetch_prices(symbols=["LUNCUSDT"], market="futures"))

    assert "LUNCUSDT" in prices
    assert prices["LUNCUSDT"] == Decimal("0.06189") / Decimal("1000")


# ── Strategia SPOT v3 — criteri di accettazione (§5 del piano) ────────────────


@pytest.mark.asyncio
async def test_spot_breakeven_prevents_loss_after_one_atr(db) -> None:
    """§5.2: un trade che tocca +1*ATR e poi ritraccia NON chiude in perdita."""
    # Scaling-in disattivato per isolare il solo breakeven.
    service = AgentService(
        settings(spot_scale_in_enabled=False),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    now = datetime.now(UTC)
    pos = SpotPosition(
        position_id="p-be",
        user_id=str(USER_ID),
        asset="BTC",
        size=Decimal("1"),
        entry_price=Decimal("100"),
        current_price=Decimal("111"),       # >= entry + 1*ATR(10) -> breakeven
        stop_loss=Decimal("78"),            # entry - 2.2*ATR
        take_profit_1=Decimal("130"),       # lontani: non scattano
        take_profit_2=Decimal("140"),
        entry_atr=Decimal("10"),
        max_price=Decimal("100"),
        swap_fee_usd=Decimal("0"),
        slippage_usd=Decimal("0"),
        scale_in_count=0,
        status="open",
        opened_at=now,
        updated_at=now,
    )
    async with get_session_factory()() as session:
        await service._check_sl_tp(session, [pos], [], now)
        # Lo stop è salito a breakeven (>= entry) e la posizione resta aperta.
        assert pos.status == "open"
        assert pos.stop_loss >= pos.entry_price
        # Ritraccia sopra il breakeven: non chiude (non più in perdita).
        pos.current_price = Decimal("101")
        await service._check_sl_tp(session, [pos], [], now)
        assert pos.status == "open"


@pytest.mark.asyncio
async def test_spot_breakeven_toggle_disables_stop_lift(db) -> None:
    """If Spot breakeven is disabled, the loop must not move the stop to entry."""
    service = AgentService(
        settings(spot_breakeven_enabled=False, spot_scale_in_enabled=False),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    now = datetime.now(UTC)
    pos = SpotPosition(
        position_id="p-be-off",
        user_id=str(USER_ID),
        asset="BTC",
        size=Decimal("1"),
        entry_price=Decimal("100"),
        current_price=Decimal("111"),
        stop_loss=Decimal("78"),
        take_profit_1=Decimal("130"),
        take_profit_2=Decimal("140"),
        entry_atr=Decimal("10"),
        max_price=Decimal("100"),
        swap_fee_usd=Decimal("0"),
        slippage_usd=Decimal("0"),
        scale_in_count=0,
        status="open",
        opened_at=now,
        updated_at=now,
    )
    async with get_session_factory()() as session:
        await service._check_sl_tp(session, [pos], [], now)
        assert pos.status == "open"
        assert pos.stop_loss == Decimal("78")


@pytest.mark.asyncio
async def test_spot_small_pump_below_one_atr_locks_breakeven_not_loss(db) -> None:
    """Scenario DEXE: un pump sotto +1*ATR (qui +0.7) deve comunque armare il
    breakeven con soglia 0.6, così il rientro chiude a pari, non in perdita."""
    service = AgentService(
        settings(spot_breakeven_trigger_atr=0.6, spot_scale_in_enabled=False),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    now = datetime.now(UTC)
    pos = SpotPosition(
        position_id="p-be-small",
        user_id=str(USER_ID),
        asset="BTC",
        size=Decimal("1"),
        entry_price=Decimal("100"),
        current_price=Decimal("107"),       # +0.7*ATR: sotto +1*ATR ma sopra la soglia 0.6
        stop_loss=Decimal("78"),            # entry - 2.2*ATR
        take_profit_1=Decimal("130"),
        take_profit_2=Decimal("140"),
        entry_atr=Decimal("10"),
        max_price=Decimal("100"),
        swap_fee_usd=Decimal("0"),
        slippage_usd=Decimal("0"),
        scale_in_count=0,
        status="open",
        opened_at=now,
        updated_at=now,
    )
    async with get_session_factory()() as session:
        await service._check_sl_tp(session, [pos], [], now)
        # Breakeven armato anche se il pump è < 1*ATR.
        assert pos.stop_loss >= pos.entry_price
        # Rientro all'entrata: chiude a pari (non in perdita).
        pos.current_price = Decimal("100")
        await service._check_sl_tp(session, [pos], [], now)
        assert pos.status == "closed"


@pytest.mark.asyncio
async def test_spot_spike_filter_rejects_signal() -> None:
    """§5.3: quando ATR_now supera la soglia (ratio_max) il segnale è rifiutato."""
    base = candles()
    # Baseline senza filtro: lo stesso scenario entra.
    enter = await SpotMomentumSignal(settings(spot_spike_filter_enabled=False)).evaluate(
        {"asset": "BTC", "candles": base, "btc_context_score": 0.7, "sentiment_score": 0.7}
    )
    assert enter["action"] == "enter_long"
    # Con filtro e soglia 0: qualsiasi ATR positivo supera la soglia -> skip.
    spiked = await SpotMomentumSignal(settings(spot_spike_atr_ratio_max=0.0)).evaluate(
        {"asset": "BTC", "candles": base, "btc_context_score": 0.7, "sentiment_score": 0.7}
    )
    assert spiked["action"] == "skip"
    assert spiked["reason"] == "volatility_spike"


def test_perp_atr_range_leverage_is_graduated() -> None:
    """La leva perp è graduata sull'ATR (non bimodale) e il minimo è riservato alle anomalie."""
    from backend.app.agent.signals.perp.volume_profile import _atr_range_leverage

    # Vol corrente a metà dello storico -> leva intermedia (né min né max).
    mid = _atr_range_leverage(min_lev=4, max_lev=40, atr_value=3.0, atr_min=2.0, atr_max=4.0)
    assert 4 < mid < 40
    # Vol minima storica -> leva massima.
    assert _atr_range_leverage(min_lev=4, max_lev=40, atr_value=2.0, atr_min=2.0, atr_max=4.0) == 40
    # Vol oltre il massimo storico (anomalia) -> leva minima.
    assert _atr_range_leverage(min_lev=4, max_lev=40, atr_value=5.0, atr_min=2.0, atr_max=4.0) == 4
    # Dati insufficienti -> leva minima (conservativo).
    assert _atr_range_leverage(min_lev=4, max_lev=40, atr_value=None, atr_min=None, atr_max=None) == 4


@pytest.mark.asyncio
async def test_spot_scale_in_never_adds_in_loss_or_without_breakeven(db) -> None:
    """§5.4: lo scaling-in NON scatta mai in perdita o senza stop a breakeven."""
    service = AgentService(settings(), spot_registry=SimpleNamespace(), perp_registry=SimpleNamespace())
    now = datetime.now(UTC)

    def _pos(pid: str, current: Decimal, stop: Decimal) -> SpotPosition:
        return SpotPosition(
            position_id=pid,
            user_id=str(USER_ID),
            asset="BTC",
            size=Decimal("1"),
            entry_price=Decimal("100"),
            current_price=current,
            stop_loss=stop,
            entry_atr=Decimal("10"),
            max_price=Decimal("100"),
            scale_in_count=0,
            fee_mode="all",
            status="open",
            opened_at=now,
            updated_at=now,
        )

    async with get_session_factory()() as session:
        # (a) in perdita (price <= entry): nessuna aggiunta.
        loss = _pos("p-loss", Decimal("95"), Decimal("100"))
        await service._maybe_scale_in_spot(session, loss, Decimal("95"), Decimal("90"), now)
        assert loss.scale_in_count == 0
        assert loss.size == Decimal("1")

        # (b) in profitto ma stop NON a breakeven: nessuna aggiunta.
        no_be = _pos("p-nobe", Decimal("115"), Decimal("90"))
        await service._maybe_scale_in_spot(session, no_be, Decimal("115"), Decimal("105"), now)
        assert no_be.scale_in_count == 0
        assert no_be.size == Decimal("1")

        # (c) controllo positivo: profitto + stop a breakeven + nuovo HH -> aggiunge.
        ok = _pos("p-ok", Decimal("115"), Decimal("100"))
        await service._maybe_scale_in_spot(session, ok, Decimal("115"), Decimal("110"), now)
        assert ok.scale_in_count == 1
        assert ok.size > Decimal("1")


# ── Protezione PERP — breakeven + trailing dinamico sulla leva ────────────────


def test_perp_trailing_mult_scales_inverse_with_leverage() -> None:
    """Il moltiplicatore ATR del trailing va da base (leva min) a floor (leva max):
    più alta la leva, più stretto il trailing in prezzo."""
    from backend.app.agent.service import _perp_trailing_mult

    at_min = _perp_trailing_mult(leverage=4, min_lev=4, max_lev=40, base=4.0, floor=2.5)
    at_max = _perp_trailing_mult(leverage=40, min_lev=4, max_lev=40, base=4.0, floor=2.5)
    mid = _perp_trailing_mult(leverage=22, min_lev=4, max_lev=40, base=4.0, floor=2.5)
    assert at_min == Decimal("4.0")
    assert at_max == Decimal("2.5")
    assert at_max < mid < at_min  # leva alta -> più stretto


def _perp_pos(pid: str, current: Decimal, *, stop: Decimal, leverage: int = 4) -> PerpPosition:
    now = datetime.now(UTC)
    return PerpPosition(
        position_id=pid,
        user_id=str(USER_ID),
        asset="DOGE",
        side="long",
        size=Decimal("1"),
        entry_price=Decimal("100"),
        current_price=current,
        leverage=leverage,
        stop_loss=stop,
        take_profit_1=Decimal("120"),   # lontani: non scattano
        take_profit_2=Decimal("130"),
        entry_atr=Decimal("2"),
        max_price=None,
        funding_accrued_usd=Decimal("0"),
        tp1_reached=False,
        status="open",
        opened_at=now,
        updated_at=now,
    )


class _OfflineFeed:
    async def fetch(self, **kwargs):
        raise RuntimeError("offline")

    async def fetch_prices(self, **kwargs):
        return {}


@pytest.mark.asyncio
async def test_perp_breakeven_moves_stop_to_entry(db) -> None:
    """A +1*ATR lo SL perp sale a entry: il trade non può più chiudere in perdita."""
    service = AgentService(settings(), spot_registry=SimpleNamespace(), perp_registry=SimpleNamespace())
    service.price_feed = _OfflineFeed()
    now = datetime.now(UTC)
    # entry 100, ATR 2 -> breakeven a 102; stop iniziale 97 (entry-1.5*ATR).
    pos = _perp_pos("perp-be", Decimal("102.5"), stop=Decimal("97"))
    async with get_session_factory()() as session:
        await service._check_sl_tp(session, [], [pos], now)
        assert pos.status == "open"
        assert pos.stop_loss == Decimal("100")        # salito a entry (no costi)
        assert pos.trailing_stop is None              # ancora "non attivo"


@pytest.mark.asyncio
async def test_perp_breakeven_toggle_disables_stop_lift(db) -> None:
    """If Perp breakeven is disabled, the loop must not move the stop to entry."""
    service = AgentService(
        settings(perp_breakeven_enabled=False),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    service.price_feed = _OfflineFeed()
    now = datetime.now(UTC)
    pos = _perp_pos("perp-be-off", Decimal("102.5"), stop=Decimal("97"))
    async with get_session_factory()() as session:
        await service._check_sl_tp(session, [], [pos], now)
        assert pos.status == "open"
        assert pos.stop_loss == Decimal("97")


@pytest.mark.asyncio
async def test_drawdown_alert_toggle_disables_notification(db, monkeypatch) -> None:
    """Disabling the drawdown alert toggle suppresses drawdown risk notifications."""
    service = AgentService(
        settings(risk_drawdown_alert_enabled=False, risk_notify_drawdown_pct=10.0),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    calls: list[tuple[str, str]] = []

    class FakeNotifier:
        async def notify_risk_alert(self, user_id: str, alert_type: str, detail: str) -> bool:
            del user_id
            calls.append((alert_type, detail))
            return True

    monkeypatch.setattr("backend.app.agent.service.get_agent_notifier", lambda: FakeNotifier())

    async with get_session_factory()() as session:
        session.add(_portfolio(drawdown_pct=Decimal("12")))
        await session.commit()
        await service._check_risk_notifications(session, [], [])

    assert calls == []


@pytest.mark.asyncio
async def test_perp_trailing_inactive_until_protective_then_activates(db) -> None:
    """Il trailing resta None finché non supera lo stop (UI 'non attivo'), poi si attiva
    e chiude se il prezzo ci rientra."""
    service = AgentService(settings(), spot_registry=SimpleNamespace(), perp_registry=SimpleNamespace())
    service.price_feed = _OfflineFeed()
    now = datetime.now(UTC)
    pos = _perp_pos("perp-trail", Decimal("103"), stop=Decimal("97"), leverage=4)  # mult=base=4.0

    async with get_session_factory()() as session:
        # mult cappato al TP1 (=2.5). +1*ATR: breakeven a 100.
        # trail = 103 - 2.5*2 = 98 < 100 -> resta None.
        await service._check_sl_tp(session, [], [pos], now)
        assert pos.status == "open"
        assert pos.stop_loss == Decimal("100")
        assert pos.trailing_stop is None

        # Sale a 110: trail = 110 - 2.5*2 = 105 > stop 100 -> trailing si attiva.
        pos.current_price = Decimal("110")
        await service._check_sl_tp(session, [], [pos], now)
        assert pos.trailing_stop == Decimal("105")
        assert pos.status == "open"

        # Ritraccia a 104 (sotto il trailing 105): chiude per trailing.
        pos.current_price = Decimal("104")
        await service._check_sl_tp(session, [], [pos], now)
        assert pos.status == "closed"


# ── Filtro regime mercato (SPOT) ─────────────────────────────────────────────


def _btc_candles(closes: list[float]) -> list[Candle]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Candle(timestamp=base + timedelta(minutes=15 * i), open=c, high=c + 0.2, low=c - 0.2, close=c, volume=100.0)
        for i, c in enumerate(closes)
    ]


def _btc_green_candles(closes: list[float]) -> list[Candle]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Candle(timestamp=base + timedelta(minutes=15 * i), open=c - 0.5, high=c + 0.2, low=c - 0.8, close=c, volume=100.0)
        for i, c in enumerate(closes)
    ]


def _btc_candles_with_red_tail(closes: list[float], red_tail: int) -> list[Candle]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    split = len(closes) - red_tail
    return [
        Candle(
            timestamp=base + timedelta(minutes=15 * i),
            open=c + 0.5 if i >= split else c - 0.5,
            high=c + 0.8,
            low=c - 0.8,
            close=c,
            volume=100.0,
        )
        for i, c in enumerate(closes)
    ]


@pytest.mark.asyncio
async def test_spot_market_regime_blocks_and_reactivates_only_above_ema(db) -> None:
    """Blocca in downtrend forte (sotto EMA + nuovo minimo), resta bloccato per
    isteresi finché BTC non richiude sopra la EMA (niente flip-flop)."""
    service = AgentService(
        settings(spot_market_regime_filter_enabled=True, spot_market_regime_ema_period=10, spot_market_regime_low_lookback=5),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )

    class FakeFeed:
        def __init__(self) -> None:
            self.candles: list[Candle] = []

        async def fetch(self, **kwargs):
            return self.candles

    feed = FakeFeed()
    service.price_feed = feed

    # 1. Downtrend forte (sotto EMA + nuovo minimo) -> blocca.
    feed.candles = _btc_candles([100 - i for i in range(20)])
    service._regime_cache = None
    assert (await service._spot_market_regime())["risk_off"] is True

    # 2. Isteresi: ancora sotto EMA ma SENZA nuovo minimo -> resta bloccato.
    feed.candles = _btc_candles([100 - i for i in range(15)] + [86, 86, 86, 86, 87])
    service._regime_cache = None
    assert (await service._spot_market_regime())["risk_off"] is True

    # 3. BTC richiude sopra la EMA -> sblocca.
    feed.candles = _btc_candles([100 - i for i in range(15)] + [90, 98, 106, 114, 122, 130])
    service._regime_cache = None
    assert (await service._spot_market_regime())["risk_off"] is False


@pytest.mark.asyncio
async def test_spot_market_regime_disabled_never_blocks(db) -> None:
    service = AgentService(
        settings(spot_market_regime_filter_enabled=False),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    regime = await service._spot_market_regime()
    assert regime["risk_off"] is False
    assert regime["enabled"] is False


@pytest.mark.asyncio
async def test_market_reversal_filter_does_not_unblock_spot_risk_off(db) -> None:
    class FakeSignal:
        async def evaluate(self, payload):
            return {
                "signal_id": "spot-risk-off",
                "market": "spot",
                "asset": "BTC",
                "action": "enter_long",
                "quality": 0.9,
                "confidence": 0.9,
                "price": 100.0,
                "stop_loss": 95.0,
                "quote_equity": 1000.0,
            }

    class FakeFeed:
        async def fetch(self, **kwargs):
            return _btc_candles([100 - i for i in range(20)])

    cfg = settings(
        spot_market_regime_filter_enabled=True,
        spot_market_regime_ema_period=10,
        spot_market_regime_low_lookback=5,
        market_reversal_filter_enabled=True,
    )
    service = AgentService(
        cfg,
        spot_signal=FakeSignal(),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    service.price_feed = FakeFeed()

    async with get_session_factory()() as session:
        result = await service.evaluate_spot({}, session)

    assert result["signal"]["action"] == "skip"
    assert result["signal"]["reason"] == "market_risk_off"
    assert "market_reversal" not in result["signal"].get("components", {})


@pytest.mark.asyncio
async def test_market_reversal_filter_waits_for_two_green_btc_candles_on_spot(db) -> None:
    class FakeSignal:
        async def evaluate(self, payload):
            return {
                "signal_id": "spot-reversal-wait",
                "market": "spot",
                "asset": "BTC",
                "action": "enter_long",
                "quality": 0.9,
                "confidence": 0.9,
                "price": 100.0,
                "stop_loss": 95.0,
                "quote_equity": 1000.0,
            }

    class FakeFeed:
        async def fetch(self, **kwargs):
            return _btc_candles([100, 100.2, 100.1, 100.3, 100.2, 100.4, 100.3, 100.5, 100.4, 100.6, 100.5, 100.4, 100.3])

    cfg = settings(spot_market_regime_filter_enabled=False, market_reversal_filter_enabled=True)
    service = AgentService(
        cfg,
        spot_signal=FakeSignal(),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    service.price_feed = FakeFeed()

    async with get_session_factory()() as session:
        result = await service.evaluate_spot({}, session)

    assert result["signal"]["action"] == "skip"
    assert result["signal"]["reason"] == "market_reversal_waiting"
    assert result["signal"]["components"]["market_reversal"]["risk_on"] is False


@pytest.mark.asyncio
async def test_market_reversal_filter_blocks_perp_short_on_btc_recovery(db) -> None:
    class FakeSignal:
        async def evaluate(self, payload):
            return {
                "signal_id": "perp-short-reversal",
                "market": "perp",
                "asset": "BTC",
                "action": "enter_short",
                "side": "short",
                "quality": 0.9,
                "confidence": 0.9,
                "price": 100.0,
                "stop_loss": 105.0,
                "quote_equity": 1000.0,
                "leverage": 2,
                "components": {},
            }

    class FakeFeed:
        async def fetch(self, **kwargs):
            return _btc_green_candles([100 + i for i in range(20)])

    cfg = settings(market_reversal_filter_enabled=True)
    service = AgentService(
        cfg,
        perp_signal=FakeSignal(),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    service.price_feed = FakeFeed()

    async with get_session_factory()() as session:
        result = await service.evaluate_perp({}, session)

    assert result["signal"]["action"] == "skip"
    assert result["signal"]["reason"] == "market_reversal_short_blocked"
    assert result["signal"]["components"]["market_reversal"]["risk_on"] is True


@pytest.mark.asyncio
async def test_market_reversal_filter_stays_on_until_two_red_below_ema(db) -> None:
    class FakeFeed:
        def __init__(self) -> None:
            self.candles: list[Candle] = []

        async def fetch(self, **kwargs):
            return self.candles

    cfg = settings(market_reversal_filter_enabled=True)
    service = AgentService(
        cfg,
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    feed = FakeFeed()
    service.price_feed = feed

    feed.candles = _btc_green_candles([100 + i for i in range(20)])
    service._market_reversal_cache = None
    first = await service._market_reversal_filter()
    assert first["risk_on"] is True
    assert first["reason"] == "btc_reversal_confirmed"

    feed.candles = _btc_candles_with_red_tail([100 + i for i in range(18)] + [105], red_tail=1)
    service._market_reversal_cache = None
    still_on = await service._market_reversal_filter()
    assert still_on["risk_on"] is True
    assert still_on["reason"] == "btc_reversal_active"

    feed.candles = _btc_candles_with_red_tail([100 + i for i in range(18)] + [105, 104], red_tail=2)
    service._market_reversal_cache = None
    off = await service._market_reversal_filter()
    assert off["risk_on"] is False
    assert off["risk_off"] is True
    assert off["reason"] == "btc_reversal_bearish_confirmed"


@pytest.mark.asyncio
async def test_market_reversal_filter_blocks_perp_long_on_btc_selloff(db) -> None:
    class FakeSignal:
        async def evaluate(self, payload):
            return {
                "signal_id": "perp-long-selloff",
                "market": "perp",
                "asset": "BTC",
                "action": "enter_long",
                "side": "long",
                "quality": 0.9,
                "confidence": 0.9,
                "price": 100.0,
                "stop_loss": 95.0,
                "quote_equity": 1000.0,
                "leverage": 2,
                "components": {},
            }

    class FakeFeed:
        async def fetch(self, **kwargs):
            return _btc_candles_with_red_tail([100 + i for i in range(18)] + [105, 104], red_tail=2)

    cfg = settings(market_reversal_filter_enabled=True)
    service = AgentService(
        cfg,
        perp_signal=FakeSignal(),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    service.price_feed = FakeFeed()

    async with get_session_factory()() as session:
        result = await service.evaluate_perp({}, session)

    assert result["signal"]["action"] == "skip"
    assert result["signal"]["reason"] == "market_reversal_long_blocked"
    assert result["signal"]["components"]["market_reversal"]["risk_off"] is True


# ── Breakeven: copertura fee + cuscinetto % ──────────────────────────────────


@pytest.mark.asyncio
async def test_spot_breakeven_buffer_locks_profit_above_entry(db) -> None:
    """Col buffer 2% lo stop sale a entry+2% (quando il prezzo l'ha superato):
    chiudere lì è un piccolo profitto, non una mini-perdita da fee."""
    service = AgentService(
        settings(spot_breakeven_buffer_pct=2.0, spot_scale_in_enabled=False),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    now = datetime.now(UTC)
    pos = SpotPosition(
        position_id="p-bebuf",
        user_id=str(USER_ID),
        asset="BTC",
        size=Decimal("1"),
        entry_price=Decimal("100"),
        current_price=Decimal("112"),     # > trigger (+1*ATR=110) e > buffer (+2%=102)
        stop_loss=Decimal("78"),
        take_profit_1=Decimal("130"),
        take_profit_2=Decimal("140"),
        entry_atr=Decimal("10"),
        max_price=Decimal("100"),
        swap_fee_usd=Decimal("0"),
        slippage_usd=Decimal("0"),
        scale_in_count=0,
        status="open",
        opened_at=now,
        updated_at=now,
    )
    async with get_session_factory()() as session:
        await service._check_sl_tp(session, [pos], [], now)
        assert pos.stop_loss == Decimal("102")   # entry + 2%, non solo entry
        assert pos.status == "open"
        # Ritraccia a 101 (sotto il buffer 102): chiude in piccolo profitto.
        pos.current_price = Decimal("101")
        await service._check_sl_tp(session, [pos], [], now)
        assert pos.status == "closed"


@pytest.mark.asyncio
async def test_perp_breakeven_buffer_not_applied_below_buffer(db) -> None:
    """Il buffer NON deve scattare se il prezzo non l'ha ancora superato (niente
    chiusura immediata): a breakeven lo stop sta a entry+costi, non a entry+2%."""
    service = AgentService(
        settings(perp_breakeven_buffer_pct=2.0),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    service.price_feed = _OfflineFeed()
    now = datetime.now(UTC)
    # entry 100, ATR 1 -> trigger +1*ATR=101; buffer +2%=102.
    pos = PerpPosition(
        position_id="perp-bebuf",
        user_id=str(USER_ID),
        asset="DOGE",
        side="long",
        size=Decimal("1"),
        entry_price=Decimal("100"),
        current_price=Decimal("101.5"),   # > trigger 101 ma < buffer 102
        leverage=4,
        stop_loss=Decimal("97"),
        take_profit_1=Decimal("130"),
        take_profit_2=Decimal("140"),
        entry_atr=Decimal("1"),
        max_price=None,
        funding_accrued_usd=Decimal("0"),
        tp1_reached=False,
        status="open",
        opened_at=now,
        updated_at=now,
    )
    async with get_session_factory()() as session:
        await service._check_sl_tp(session, [], [pos], now)
        # Breakeven scattato ma sotto il buffer: stop a entry (no fee), NON a 102.
        assert pos.stop_loss == Decimal("100")
        assert pos.status == "open"
        # Sopra il buffer (103 > 102): ora lo stop sale a entry+2% = 102.
        pos.current_price = Decimal("103")
        await service._check_sl_tp(session, [], [pos], now)
        assert pos.stop_loss == Decimal("102")
        assert pos.status == "open"


@pytest.mark.asyncio
async def test_spot_close_at_breakeven_is_labeled_breakeven(db) -> None:
    """Se lo stop che chiude è già a breakeven (>= entry) il motivo è 'breakeven',
    non 'stop_loss' (chiusura in pari/profitto, non perdita)."""
    service = AgentService(
        settings(spot_scale_in_enabled=False),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    now = datetime.now(UTC)
    pos = SpotPosition(
        position_id="p-belabel",
        user_id=str(USER_ID),
        asset="BTC",
        size=Decimal("1"),
        entry_price=Decimal("100"),
        current_price=Decimal("100"),   # rientra all'entry
        stop_loss=Decimal("100"),       # stop già a breakeven
        take_profit_1=Decimal("130"),
        take_profit_2=Decimal("140"),
        entry_atr=Decimal("10"),
        max_price=Decimal("112"),
        swap_fee_usd=Decimal("0"),
        slippage_usd=Decimal("0"),
        scale_in_count=0,
        status="open",
        opened_at=now,
        updated_at=now,
    )
    async with get_session_factory()() as session:
        await service._check_sl_tp(session, [pos], [], now)
        assert pos.status == "closed"
        trades = await SpotTradeRepository(session).list_for_user(str(USER_ID))
        closes = [t for t in trades if t.trade_id.startswith("cls_")]
        assert closes and "auto_close:breakeven" in (closes[0].notes or "")


@pytest.mark.asyncio
async def test_spot_trailing_above_entry_labeled_trailing_stop(db) -> None:
    """Spot: a profitable trailing_stop exit keeps close reason as trailing_stop."""
    service = AgentService(
        settings(spot_scale_in_enabled=False),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    now = datetime.now(UTC)
    pos = SpotPosition(
        position_id="p-tr-be",
        user_id=str(USER_ID),
        asset="ETH",
        size=Decimal("1"),
        entry_price=Decimal("100"),
        current_price=Decimal("104"),   # rientra sul trailing
        stop_loss=Decimal("95"),
        trailing_stop=Decimal("104"),   # profitable trailing exit
        take_profit_1=Decimal("130"),
        take_profit_2=Decimal("140"),
        entry_atr=Decimal("10"),
        max_price=Decimal("115"),
        swap_fee_usd=Decimal("0"),
        slippage_usd=Decimal("0"),
        scale_in_count=0,
        status="open",
        opened_at=now,
        updated_at=now,
    )
    async with get_session_factory()() as session:
        await service._check_sl_tp(session, [pos], [], now)
        assert pos.status == "closed"
        trades = await SpotTradeRepository(session).list_for_user(str(USER_ID))
        closes = [t for t in trades if t.trade_id.startswith("cls_")]
        assert closes and "auto_close:trailing_stop" in (closes[0].notes or "")


@pytest.mark.asyncio
async def test_perp_long_trailing_above_entry_labeled_trailing_stop(db) -> None:
    """Perp long: a profitable trailing_stop exit keeps close reason as trailing_stop."""
    service = AgentService(
        settings(spot_scale_in_enabled=False),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    now = datetime.now(UTC)
    pos = PerpPosition(
        position_id="perp-tr-be",
        user_id=str(USER_ID),
        asset="BTC",
        side="long",
        size=Decimal("1"),
        entry_price=Decimal("100"),
        current_price=Decimal("105"),   # rientra sul trailing
        leverage=5,
        stop_loss=Decimal("95"),
        trailing_stop=Decimal("105"),   # profitable trailing exit
        take_profit_1=Decimal("130"),
        take_profit_2=Decimal("140"),
        entry_atr=Decimal("5"),
        max_price=Decimal("120"),
        funding_accrued_usd=Decimal("0"),
        tp1_reached=False,
        status="open",
        opened_at=now,
        updated_at=now,
    )
    async with get_session_factory()() as session:
        await service._check_sl_tp(session, [], [pos], now)
        assert pos.status == "closed"
        trades = await PerpTradeRepository(session).list_for_user(str(USER_ID))
        closes = [t for t in trades if t.trade_id.startswith("cls_")]
        assert closes and "auto_close:trailing_stop" in (closes[0].notes or "")


@pytest.mark.asyncio
async def test_perp_short_trailing_below_entry_labeled_trailing_stop(db) -> None:
    """Perp short: a profitable trailing_stop exit keeps close reason as trailing_stop."""
    service = AgentService(
        settings(spot_scale_in_enabled=False),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    now = datetime.now(UTC)
    pos = PerpPosition(
        position_id="perp-short-tr",
        user_id=str(USER_ID),
        asset="AVAX",
        side="short",
        size=Decimal("1"),
        entry_price=Decimal("100"),
        current_price=Decimal("95"),
        leverage=5,
        stop_loss=Decimal("105"),
        trailing_stop=Decimal("95"),
        take_profit_1=Decimal("80"),
        take_profit_2=Decimal("70"),
        entry_atr=Decimal("5"),
        max_price=Decimal("88"),
        funding_accrued_usd=Decimal("0"),
        tp1_reached=False,
        status="open",
        opened_at=now,
        updated_at=now,
    )
    async with get_session_factory()() as session:
        await service._check_sl_tp(session, [], [pos], now)
        assert pos.status == "closed"
        trades = await PerpTradeRepository(session).list_for_user(str(USER_ID))
        closes = [t for t in trades if t.trade_id.startswith("cls_")]
        assert closes and "auto_close:trailing_stop" in (closes[0].notes or "")


@pytest.mark.asyncio
async def test_start_time_kline_fetch_does_not_populate_latest_cache(monkeypatch) -> None:
    import httpx

    from backend.app.agent.signals.perp.binance_klines import BinanceKlineFeed, get_kline_cache_entry

    clear_kline_cache()
    calls: list[dict] = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return [[
                int(datetime(2026, 7, 8, 12, 5, tzinfo=UTC).timestamp() * 1000),
                "100",
                "102",
                "99",
                "101",
                "10",
            ]]

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None):
            calls.append(params or {})
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    feed = BinanceKlineFeed()
    candles = await feed.fetch(
        symbol="BTCUSDT",
        interval="5m",
        limit=3,
        market="spot",
        start_time=datetime(2026, 7, 8, 12, 0, tzinfo=UTC),
    )

    assert len(candles) == 1
    assert "startTime" in calls[0]
    assert get_kline_cache_entry(market="spot", symbol="BTCUSDT", interval="5m") is None
