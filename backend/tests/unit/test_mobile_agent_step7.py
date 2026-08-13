"""Step 7 additive mobile agent endpoint regressions."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from backend.app.api.routes.mobile_agent import (
    mobile_agent_settings,
    mobile_wallet,
    update_mobile_agent_settings,
    validate_mobile_onboarding,
)
from backend.app.core.security.auth import AuthScope
from backend.app.persistence.sync_database import (
    create_all_sync,
    init_sync_db,
    reset_sync_db,
)
from backend.app.schemas.mobile_agent import AgentMobileSettings

USER_ID = UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def sync_db(tmp_path: Path):
    reset_sync_db()
    init_sync_db(f"sqlite:///{tmp_path / 'mobile_agent.db'}")
    create_all_sync()
    yield
    reset_sync_db()


def settings(**overrides):
    base = dict(
        default_user_id=USER_ID,
        agent_mode="conservative",
        markets_enabled="both",
        execution_mode="dry_run",
        bsc_network="testnet",
        test_scaling_pct=10.0,
        operating_hours_utc="00:00-23:59",
        risk_capital_per_trade_pct=4.0,
        risk_per_trade_pct=1.5,
        risk_max_open_positions=5,
        risk_max_total_exposure_pct=30.0,
        risk_daily_loss_limit_pct=-8.0,
        risk_max_drawdown_pct=-15.0,
        risk_drawdown_alert_enabled=True,
        risk_min_pool_liquidity_usd=50000.0,
        market_reversal_filter_enabled=True,
        market_reversal_symbol="BTCUSDT",
        market_reversal_interval="15m",
        market_reversal_ema_period=10,
        market_reversal_confirmation_candles=2,
        risk_max_slippage_pct=1.0,
        risk_cooldown_minutes=30,
        spot_confidence_threshold=0.7,
        spot_volatility_trigger_pct=3.0,
        spot_relative_volume_threshold=1.8,
        spot_breakeven_enabled=True,
        spot_sl_mode="atr",
        spot_structural_stop_lookback_candles=20,
        spot_structural_stop_buffer_pct=1.10,
        spot_atr_stop_multiplier=1.5,
        spot_tp1_atr_multiplier=2.0,
        spot_tp2_atr_multiplier=3.5,
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
        spot_partial_take_profit_pct=50.0,
        spot_time_stop_enabled=False,
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
        perp_direction_mode="long_short",
        perp_default_leverage=2,
        perp_dynamic_leverage_enabled=True,
        perp_min_leverage=4,
        perp_max_leverage=40,
        perp_leverage_atr_period=72,
        perp_leverage_atr_baseline_hours=120,
        perp_value_area_pct=68.0,
        perp_atr_stop_multiplier=0.8,
        perp_breakeven_enabled=True,
        perp_trailing_mode="largo",
        perp_breakeven_trigger_atr=1.0,
        perp_breakeven_offset_costs=True,
        perp_breakeven_buffer_pct=0.0,
        perp_trailing_base_atr_largo=4.0,
        perp_trailing_floor_atr_largo=2.5,
        perp_trailing_base_atr_stretto=2.5,
        perp_trailing_floor_atr_stretto=1.5,
        perp_tp1_atr_multiplier=2.5,
        perp_tp2_atr_multiplier=4.0,
        perp_use_poc_for_tp2=True,
        perp_sl_mode="atr",
        perp_structural_stop_lookback_candles=20,
        perp_structural_stop_buffer_pct=1.10,
        perp_time_stop_enabled=False,
        perp_time_stop_hours=8,
        cmc_api_key="configured",
        twak_access_id="configured",
        twak_hmac_secret="configured",
        anthropic_api_key=None,
        wallet_address="0x0000000000000000000000000000000000000001",
        wallet_encrypted_private_key_path="configured",
        bsc_rpc_urls=["https://rpc.example"],
        bsc_rpc_timeout_seconds=8.0,
        tatum_rpc_api_key=None,
        fcm_enabled=True,
        fcm_project_id="project",
        fcm_credentials_path="configured",
        x402_enabled=True,
        x402_usdc_wallet_address="0x0000000000000000000000000000000000000002",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_mobile_agent_settings_are_persisted(sync_db) -> None:
    initial = await mobile_agent_settings(settings(), AuthScope.READ)
    assert initial.source == "config"
    assert initial.persisted is False
    assert initial.settings.drawdown_alert_enabled is True
    assert initial.settings.market_reversal_filter_enabled is True
    assert initial.settings.spot_breakeven_enabled is True
    assert initial.settings.perp_breakeven_enabled is True
    assert initial.settings.spot_time_stop_enabled is False
    assert initial.settings.perp_time_stop_enabled is False
    assert initial.settings.perp_fixed_margin_enabled is False
    assert initial.settings.perp_fixed_margin_usd == 50.0

    payload = AgentMobileSettings(
        mode="semi_autonomous",
        markets_enabled="spot",
        test_scaling_pct=25,
        drawdown_alert_enabled=False,
        market_reversal_filter_enabled=False,
        spot_breakeven_enabled=False,
        perp_breakeven_enabled=True,
        spot_time_stop_enabled=True,
        perp_time_stop_enabled=True,
        spot_time_stop_hours=12,
        perp_time_stop_hours=10,
        spot_sl_mode="lowest",
        perp_sl_mode="lowest",
        spot_structural_stop_buffer_pct=1.25,
        perp_structural_stop_buffer_pct=1.35,
        perp_fixed_margin_enabled=True,
        perp_fixed_margin_usd=75,
    )
    live_settings = settings()
    updated = await update_mobile_agent_settings(payload, live_settings, AuthScope.ADMIN)
    assert updated.persisted is True
    assert live_settings.spot_sl_mode == "lowest"
    assert live_settings.perp_sl_mode == "lowest"
    assert live_settings.spot_structural_stop_buffer_pct == 1.25
    assert live_settings.perp_structural_stop_buffer_pct == 1.35
    assert live_settings.spot_time_stop_enabled is True
    assert live_settings.perp_time_stop_enabled is True
    assert live_settings.spot_time_stop_hours_fallback == 12
    assert live_settings.perp_time_stop_hours == 10

    loaded = await mobile_agent_settings(settings(), AuthScope.READ)
    assert loaded.source == "runtime"
    assert loaded.settings.mode == "semi_autonomous"
    assert loaded.settings.markets_enabled == "spot"
    assert loaded.settings.test_scaling_pct == 25
    assert loaded.settings.drawdown_alert_enabled is False
    assert loaded.settings.market_reversal_filter_enabled is False
    assert loaded.settings.spot_breakeven_enabled is False
    assert loaded.settings.spot_time_stop_enabled is True
    assert loaded.settings.perp_time_stop_enabled is True
    assert loaded.settings.perp_breakeven_enabled is True
    assert loaded.settings.spot_sl_mode == "lowest"
    assert loaded.settings.perp_sl_mode == "lowest"
    assert loaded.settings.spot_structural_stop_buffer_pct == 1.25
    assert loaded.settings.perp_structural_stop_buffer_pct == 1.35
    assert loaded.settings.perp_fixed_margin_enabled is True
    assert loaded.settings.perp_fixed_margin_usd == 75.0


@pytest.mark.asyncio
async def test_onboarding_validation_returns_status_only(sync_db) -> None:
    response = await validate_mobile_onboarding(settings(), AuthScope.ADMIN)
    checks = {check.name: check for check in response.checks}

    assert response.lock_ttl_seconds == 600
    assert checks["CMC"].configured is True
    assert checks["Claude"].configured is False
    assert checks["CMC"].status == "ready"
    assert checks["Claude"].status == "missing"


@pytest.mark.asyncio
async def test_mobile_wallet_exposes_bsc_and_base_without_keys() -> None:
    response = await mobile_wallet(settings(bsc_rpc_urls=[]), AuthScope.READ)

    assert [network.network for network in response.networks] == ["BSC testnet", "Base"]
    assert response.networks[0].role == "gas+trading"
    assert response.networks[1].role == "x402 USDC"
    assert all(network.configured for network in response.networks)
    assert response.networks[0].balance_status == "rpc_not_configured"
    assert response.networks[0].balances == []


@pytest.mark.asyncio
async def test_mobile_wallet_includes_positive_bnb_balance(monkeypatch) -> None:
    async def fake_call(self, method, params=None):
        del self, params
        assert method == "eth_getBalance"
        return hex(1234000000000000000)

    monkeypatch.setattr("backend.app.execution.rpc.MultiRpcClient.call", fake_call)

    response = await mobile_wallet(settings(), AuthScope.READ)

    assert response.networks[0].balance_status == "ok"
    assert response.networks[0].balances[0].asset == "BNB"
    assert response.networks[0].balances[0].balance == "1.234"
