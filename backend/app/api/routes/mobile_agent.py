"""Additive mobile endpoints for Step 7 agent views and setup."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter

from backend.app.api.dependencies import AdminAccessDep, ReadAccessDep, SettingsDep
from backend.app.core.config import Settings
from backend.app.execution.rpc import MultiRpcClient, RpcUnavailableError
from backend.app.execution.rpc_selection import ordered_bsc_rpc_urls
from backend.app.persistence.runtime_state import get_runtime_value, set_runtime_value
from backend.app.schemas.mobile_agent import (
    AgentMobileSettings,
    AgentMobileSettingsResponse,
    CredentialCheck,
    CredentialValidationResponse,
    MobileWalletView,
    WalletAssetBalance,
    WalletNetworkView,
)

router = APIRouter(prefix="/api/v1/mobile/agent", tags=["mobile-agent"])
SETTINGS_KEY = "mobile_agent_settings"

# Mapping mobile_field → Settings attribute name (solo parametri globali e di strategia;
# i parametri risk market-specific vengono letti direttamente dall'_ms nel risk manager).
_MOBILE_TO_SETTINGS: dict[str, str] = {
    "drawdown_alert_enabled": "risk_drawdown_alert_enabled",
    "daily_loss_limit_pct": "risk_daily_loss_limit_pct",
    "drawdown_cap_pct": "risk_max_drawdown_pct",
    "min_pool_liquidity_usd": "risk_min_pool_liquidity_usd",
    "market_reversal_filter_enabled": "market_reversal_filter_enabled",
    "spot_breakeven_enabled": "spot_breakeven_enabled",
    "perp_breakeven_enabled": "perp_breakeven_enabled",
    "spot_sl_mode": "spot_sl_mode",
    "perp_sl_mode": "perp_sl_mode",
    "spot_structural_stop_lookback_candles": "spot_structural_stop_lookback_candles",
    "spot_structural_stop_buffer_pct": "spot_structural_stop_buffer_pct",
    "perp_structural_stop_lookback_candles": "perp_structural_stop_lookback_candles",
    "perp_structural_stop_buffer_pct": "perp_structural_stop_buffer_pct",
    "spot_time_stop_enabled": "spot_time_stop_enabled",
    "perp_time_stop_enabled": "perp_time_stop_enabled",
    "spot_confidence_threshold": "spot_confidence_threshold",
    "spot_atr_stop_multiplier": "spot_atr_stop_multiplier",
    "spot_time_stop_hours": "spot_time_stop_hours_fallback",
    "perp_min_leverage": "perp_min_leverage",
    "perp_max_leverage": "perp_max_leverage",
    "perp_value_area_pct": "perp_value_area_pct",
    "perp_atr_stop_multiplier": "perp_atr_stop_multiplier",
    "perp_time_stop_hours": "perp_time_stop_hours",
    "test_scaling_pct": "test_scaling_pct",
}


def apply_mobile_settings_to_config(mobile: AgentMobileSettings, settings: Settings) -> None:
    """Applica i parametri di AgentMobileSettings al Settings live dell'agente.

    Permette di cambiare i parametri di rischio/strategia senza riavviare il backend.
    """
    for mobile_field, settings_field in _MOBILE_TO_SETTINGS.items():
        value = getattr(mobile, mobile_field, None)
        if value is not None and hasattr(settings, settings_field):
            try:
                object.__setattr__(settings, settings_field, value)
            except Exception:
                pass  # campo frozen o non applicabile, ignora silenziosamente
ONBOARDING_LOCK_SECONDS = 600
WEI_PER_BNB = 10**18


def _settings_from_runtime(settings: SettingsDep) -> tuple[AgentMobileSettings, str, bool]:
    user_id = str(settings.default_user_id)
    raw = get_runtime_value(user_id, SETTINGS_KEY)
    if raw:
        try:
            return AgentMobileSettings.model_validate_json(raw), "runtime", True
        except ValueError:
            pass
    return _settings_from_config(settings), "config", False


def _settings_from_config(settings: SettingsDep) -> AgentMobileSettings:
    cap = settings.risk_capital_per_trade_pct
    slippage = settings.risk_max_slippage_pct
    cooldown = settings.risk_cooldown_minutes
    max_open = settings.risk_max_open_positions
    exposure = settings.risk_max_total_exposure_pct
    per_trade = settings.risk_per_trade_pct
    return AgentMobileSettings(
        mode=settings.agent_mode,
        markets_enabled=settings.markets_enabled,
        execution_mode=settings.execution_mode,
        network=settings.bsc_network,
        test_scaling_pct=settings.test_scaling_pct,
        operating_hours_utc=settings.operating_hours_utc,
        drawdown_alert_enabled=settings.risk_drawdown_alert_enabled,
        daily_loss_limit_pct=settings.risk_daily_loss_limit_pct,
        drawdown_cap_pct=settings.risk_max_drawdown_pct,
        min_pool_liquidity_usd=settings.risk_min_pool_liquidity_usd,
        market_reversal_filter_enabled=settings.market_reversal_filter_enabled,
        spot_breakeven_enabled=settings.spot_breakeven_enabled,
        perp_breakeven_enabled=settings.perp_breakeven_enabled,
        spot_trailing_enabled=True,
        perp_trailing_enabled=True,
        spot_time_stop_enabled=getattr(settings, "spot_time_stop_enabled", False),
        perp_time_stop_enabled=getattr(settings, "perp_time_stop_enabled", False),
        spot_breakeven_mode="atr",
        perp_breakeven_mode="atr",
        spot_sl_mode=getattr(settings, "spot_sl_mode", "atr"),
        perp_sl_mode=getattr(settings, "perp_sl_mode", "atr"),
        spot_structural_stop_lookback_candles=getattr(settings, "spot_structural_stop_lookback_candles", 20),
        spot_structural_stop_buffer_pct=getattr(settings, "spot_structural_stop_buffer_pct", 1.10),
        perp_structural_stop_lookback_candles=getattr(settings, "perp_structural_stop_lookback_candles", 20),
        perp_structural_stop_buffer_pct=getattr(settings, "perp_structural_stop_buffer_pct", 1.10),
        # Parametri spot (default = valore condiviso dal YAML)
        spot_capital_per_trade_pct=cap,
        spot_per_trade_pct=per_trade,
        spot_max_open_positions=max_open,
        spot_max_exposure_pct=exposure,
        spot_cooldown_minutes=cooldown,
        spot_max_slippage_pct=slippage,
        # Parametri perp (default = valore condiviso dal YAML)
        perp_capital_per_trade_pct=cap,
        perp_per_trade_pct=per_trade,
        perp_max_open_positions=max_open,
        perp_max_exposure_pct=exposure,
        perp_cooldown_minutes=cooldown,
        perp_max_slippage_pct=slippage,
        perp_fixed_margin_enabled=False,
        perp_fixed_margin_usd=50.0,
        # Legacy
        capital_per_trade_pct=cap,
        per_trade_pct=per_trade,
        max_open_positions=max_open,
        max_total_exposure_pct=exposure,
        max_slippage_pct=slippage,
        cooldown_minutes=cooldown,
        # Spot strategy
        spot_confidence_threshold=settings.spot_confidence_threshold,
        spot_volatility_trigger_pct=settings.spot_volatility_trigger_pct,
        spot_relative_volume_threshold=settings.spot_relative_volume_threshold,
        spot_atr_stop_multiplier=settings.spot_atr_stop_multiplier,
        spot_trailing_distance_pct=settings.spot_trailing_distance_pct,
        spot_partial_take_profit_pct=settings.spot_partial_take_profit_pct,
        spot_tp1_close_pct=50.0,
        spot_time_stop_hours=settings.spot_time_stop_hours,
        # Perp strategy
        perp_direction_mode=settings.perp_direction_mode,
        perp_min_leverage=settings.perp_min_leverage,
        perp_max_leverage=settings.perp_max_leverage,
        perp_value_area_pct=settings.perp_value_area_pct,
        perp_atr_stop_multiplier=settings.perp_atr_stop_multiplier,
        perp_trailing_mode=settings.perp_trailing_mode,
        perp_trailing_pnl_pct=0.0,
        perp_tp1_close_pct=70.0,
        perp_time_stop_hours=settings.perp_time_stop_hours,
        post_close_candles=10,
    )


@router.get("/settings", response_model=AgentMobileSettingsResponse)
async def mobile_agent_settings(
    settings: SettingsDep,
    _: ReadAccessDep,
) -> AgentMobileSettingsResponse:
    """Return the mobile agent settings contract without exposing secrets."""

    payload, source, persisted = _settings_from_runtime(settings)
    return AgentMobileSettingsResponse(settings=payload, source=source, persisted=persisted)


@router.put("/settings", response_model=AgentMobileSettingsResponse)
async def update_mobile_agent_settings(
    request: AgentMobileSettings,
    settings: SettingsDep,
    _: AdminAccessDep,
) -> AgentMobileSettingsResponse:
    """Persist the mobile agent settings and apply them immediately to the live agent."""

    serialized = request.model_dump_json()
    set_runtime_value(str(settings.default_user_id), SETTINGS_KEY, serialized)
    # Applica subito al Settings singleton: nessun riavvio necessario.
    apply_mobile_settings_to_config(request, settings)
    return AgentMobileSettingsResponse(settings=request, source="runtime", persisted=True)


@router.post("/onboarding/validate", response_model=CredentialValidationResponse)
async def validate_mobile_onboarding(
    settings: SettingsDep,
    _: AdminAccessDep,
) -> CredentialValidationResponse:
    """Validate mobile onboarding prerequisites without returning secret values."""

    configured = {
        "CMC": bool(settings.cmc_api_key),
        "TWAK": bool(settings.twak_access_id and settings.twak_hmac_secret),
        "Claude": bool(settings.anthropic_api_key),
        "Wallet": bool(settings.wallet_address and settings.wallet_encrypted_private_key_path),
        "BSC RPC": bool(settings.bsc_rpc_urls),
        "FCM": bool(settings.fcm_enabled and settings.fcm_project_id and settings.fcm_credentials_path),
        "x402": bool(settings.x402_enabled and settings.x402_usdc_wallet_address),
    }
    checks = [
        CredentialCheck(
            name=name,
            configured=is_configured,
            status="ready" if is_configured else "missing",
        )
        for name, is_configured in configured.items()
    ]
    expires_at = datetime.now(UTC) + timedelta(seconds=ONBOARDING_LOCK_SECONDS)
    set_runtime_value(
        str(settings.default_user_id),
        "mobile_onboarding_lock_expires_at",
        expires_at.isoformat(),
    )
    return CredentialValidationResponse(
        checks=checks,
        lock_expires_at=expires_at.isoformat(),
        lock_ttl_seconds=ONBOARDING_LOCK_SECONDS,
    )


@router.get("/wallet", response_model=MobileWalletView)
async def mobile_wallet(
    settings: SettingsDep,
    _: ReadAccessDep,
) -> MobileWalletView:
    """Return a non-sensitive multi-network wallet summary for mobile."""

    bsc_balances, bsc_balance_status = await _bsc_balances(settings)
    networks = [
        WalletNetworkView(
            network=f"BSC {settings.bsc_network}",
            address=settings.wallet_address,
            configured=bool(settings.wallet_address),
            role="gas+trading",
            balance_status=bsc_balance_status,
            balances=bsc_balances,
        ),
        WalletNetworkView(
            network="Base",
            address=settings.x402_usdc_wallet_address,
            configured=bool(settings.x402_usdc_wallet_address),
            role="x402 USDC",
            balance_status="rpc_not_configured" if settings.x402_usdc_wallet_address else "not_configured",
            balances=[],
        ),
    ]
    return MobileWalletView(networks=networks)


async def _bsc_balances(settings: SettingsDep) -> tuple[list[WalletAssetBalance], str]:
    if not settings.wallet_address:
        return [], "not_configured"
    if not settings.bsc_rpc_urls:
        return [], "rpc_not_configured"
    client = MultiRpcClient(
        ordered_bsc_rpc_urls(settings),
        settings.bsc_rpc_timeout_seconds,
        settings.tatum_rpc_api_key,
    )
    try:
        raw_balance = await asyncio.wait_for(
            client.call("eth_getBalance", [settings.wallet_address, "latest"]),
            timeout=4.0,
        )
        balance_wei = int(str(raw_balance), 16)
    except (RpcUnavailableError, ValueError, TypeError, asyncio.TimeoutError):
        return [], "unavailable"

    if balance_wei <= 0:
        return [], "empty"
    balance = balance_wei / WEI_PER_BNB
    return [
        WalletAssetBalance(
            asset="BNB",
            balance=f"{balance:.8f}".rstrip("0").rstrip("."),
            decimals=18,
            source="native",
        )
    ], "ok"
