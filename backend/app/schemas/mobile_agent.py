"""Schemas for the additive mobile agent extension."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class AgentMobileSettings(BaseModel):
    mode: str = "conservative"
    markets_enabled: str = "both"
    execution_mode: str = "dry_run"
    network: str = "testnet"
    test_scaling_pct: float = Field(default=10.0, ge=1.0, le=100.0)
    operating_hours_utc: str = "00:00-23:59"
    # --- Parametri globali (si applicano a entrambi i mercati) ---
    drawdown_alert_enabled: bool = True
    daily_loss_limit_pct: float = Field(default=-8.0, ge=-50.0, lt=0.0)
    drawdown_cap_pct: float = Field(default=-15.0, ge=-50.0, lt=0.0)
    min_pool_liquidity_usd: float = Field(default=50000.0, ge=0.0)
    market_reversal_filter_enabled: bool = True
    spot_breakeven_enabled: bool = True
    perp_breakeven_enabled: bool = True
    spot_trailing_enabled: bool = True
    perp_trailing_enabled: bool = True
    spot_time_stop_enabled: bool = False
    perp_time_stop_enabled: bool = False
    spot_breakeven_mode: str = Field(default="atr", pattern="^(atr|tp1)$")
    perp_breakeven_mode: str = Field(default="atr", pattern="^(atr|tp1)$")
    spot_sl_mode: str = Field(default="atr", pattern="^(atr|lowest)$")
    perp_sl_mode: str = Field(default="atr", pattern="^(atr|lowest)$")
    spot_structural_stop_lookback_candles: int = Field(default=20, ge=2, le=100)
    spot_structural_stop_buffer_pct: float = Field(default=1.10, ge=0.0, le=20.0)
    perp_structural_stop_lookback_candles: int = Field(default=20, ge=2, le=100)
    perp_structural_stop_buffer_pct: float = Field(default=1.10, ge=0.0, le=20.0)
    # Filtro shock BTC perp
    perp_trend_shock_enabled: bool = True
    perp_trend_shock_adx_threshold: float = Field(default=25.0, ge=10.0, le=60.0)
    perp_trend_shock_natr_percentile: float = Field(default=90.0, ge=50.0, le=99.0)
    perp_trend_shock_volume_threshold: float = Field(default=2.0, ge=1.0, le=10.0)
    perp_trend_shock_recovery_confirmations: int = Field(default=3, ge=1, le=10)
    # Smart Stop Loss perp
    perp_smart_sl_enabled: bool = True
    perp_smart_sl_l1_frac: float = Field(default=0.333, ge=0.1, le=0.5)
    perp_smart_sl_l2_frac: float = Field(default=0.666, ge=0.4, le=0.9)
    perp_smart_sl_split_l1: float = Field(default=0.25, ge=0.05, le=0.5)
    perp_smart_sl_split_l2: float = Field(default=0.55, ge=0.1, le=0.7)
    perp_smart_sl_split_l3: float = Field(default=0.20, ge=0.05, le=0.5)
    perp_smart_sl_rebuy_mode: str = Field(default="above_entry", pattern=r"^(above_entry|delta)$")
    perp_smart_sl_rebuy_above_entry_pct: float = Field(default=100.0, ge=10.0, le=100.0)
    perp_smart_sl_tp_adjust_after_rebuy: bool = True
    perp_smart_sl_tp_recovery_delta_pct: float = Field(default=7.0, ge=0.0, le=100.0)
    perp_smart_sl_split_l1_r2: float = Field(default=0.75, ge=0.2, le=0.95)
    perp_smart_sl_split_l2_r2: float = Field(default=0.20, ge=0.05, le=0.5)
    perp_smart_sl_split_l3_r2: float = Field(default=0.05, ge=0.0, le=0.3)
    perp_smart_sl_delta_l1: float = Field(default=0.08, ge=0.02, le=0.5)
    perp_smart_sl_delta_l2: float = Field(default=0.16, ge=0.02, le=0.5)
    perp_smart_sl_confirmation_candles: int = Field(default=2, ge=1, le=10)
    perp_smart_sl_max_reentries: int = Field(default=1, ge=0, le=5)

    # --- Parametri SPOT ---
    spot_capital_per_trade_pct: float = Field(default=6.0, gt=0.0, le=100.0)
    spot_per_trade_pct: float = Field(default=1.5, gt=0.0, le=20.0)
    spot_max_open_positions: int = Field(default=3, ge=1, le=20)
    spot_max_exposure_pct: float = Field(default=30.0, gt=0.0, le=100.0)
    spot_cooldown_minutes: int = Field(default=30, ge=0, le=1440)
    spot_max_slippage_pct: float = Field(default=1.0, gt=0.0, le=20.0)

    # --- Parametri PERP ---
    perp_capital_per_trade_pct: float = Field(default=4.0, gt=0.0, le=100.0)
    perp_per_trade_pct: float = Field(default=1.5, gt=0.0, le=20.0)
    perp_max_open_positions: int = Field(default=5, ge=1, le=20)
    perp_max_exposure_pct: float = Field(default=20.0, gt=0.0, le=100.0)
    perp_cooldown_minutes: int = Field(default=15, ge=0, le=1440)
    perp_max_slippage_pct: float = Field(default=0.5, gt=0.0, le=20.0)
    perp_fixed_margin_enabled: bool = False
    perp_fixed_margin_usd: float = Field(default=50.0, gt=0.0, le=100000.0)

    # --- Campi legacy (mantenuti per backward-compat con settings salvati prima del refactor) ---
    capital_per_trade_pct: float = Field(default=6.0, gt=0.0, le=100.0)
    per_trade_pct: float = Field(default=1.5, gt=0.0, le=20.0)
    max_open_positions: int = Field(default=3, ge=1, le=20)
    max_total_exposure_pct: float = Field(default=30.0, gt=0.0, le=100.0)
    max_slippage_pct: float = Field(default=1.0, gt=0.0, le=20.0)
    cooldown_minutes: int = Field(default=30, ge=0, le=1440)
    spot_confidence_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    spot_volatility_trigger_pct: float = Field(default=3.0, ge=0.0, le=100.0)
    spot_relative_volume_threshold: float = Field(default=1.8, ge=0.0, le=100.0)
    spot_atr_stop_multiplier: float = Field(default=1.5, gt=0.0, le=20.0)
    spot_trailing_distance_pct: float = Field(default=2.0, ge=0.0, le=100.0)
    spot_partial_take_profit_pct: float = Field(default=50.0, ge=0.0, le=100.0)
    spot_tp1_close_pct: float = Field(default=50.0, ge=1.0, le=99.0)
    spot_time_stop_hours: int = Field(default=6, ge=0, le=168)
    perp_direction_mode: str = "long_short"
    # Leva modulata dinamicamente sull'ATR(72) in apertura: bassa volatilità → max,
    # alta volatilità → min. Range configurabile dall'utente.
    perp_min_leverage: int = Field(default=4, ge=1, le=50)
    perp_max_leverage: int = Field(default=40, ge=1, le=50)
    perp_value_area_pct: float = Field(default=68.0, ge=50.0, le=90.0)
    perp_atr_stop_multiplier: float = Field(default=0.8, gt=0.0, le=20.0)
    # Ampiezza del trailing perp: "largo" lascia correre (restituisce di più),
    # "stretto" blocca prima. Il moltiplicatore effettivo scala con la leva del trade.
    perp_trailing_mode: str = Field(default="largo", pattern="^(largo|stretto)$")
    # Se > 0, viene calcolato anche un trailing a distanza fissa dal massimo (% del prezzo).
    # Vince il più protettivo tra ATR e questa %. Con 0 si usa solo l'ATR.
    perp_trailing_pnl_pct: float = Field(default=0.0, ge=0.0, le=20.0)
    perp_tp1_close_pct: float = Field(default=70.0, ge=1.0, le=99.0)
    perp_time_stop_hours: int = Field(default=8, ge=0, le=168)
    perp_fee_mode: str = Field(default="taker", pattern="^(taker|maker|none)$")
    spot_fee_mode: str = Field(default="all", pattern="^(all|none)$")
    # Candele successive alla chiusura mostrate nel grafico del trade. 0 = disattivato.
    post_close_candles: int = Field(default=10, ge=0, le=50)

    @model_validator(mode="after")
    def _check_leverage_range(self) -> "AgentMobileSettings":
        if self.perp_min_leverage > self.perp_max_leverage:
            raise ValueError("perp_min_leverage must be <= perp_max_leverage")
        return self


class AgentMobileSettingsResponse(BaseModel):
    settings: AgentMobileSettings
    source: str
    persisted: bool


class CredentialCheck(BaseModel):
    name: str
    configured: bool
    status: str


class CredentialValidationResponse(BaseModel):
    checks: list[CredentialCheck]
    lock_expires_at: str
    lock_ttl_seconds: int


class WalletAssetBalance(BaseModel):
    asset: str
    balance: str
    decimals: int
    source: str


class WalletNetworkView(BaseModel):
    network: str
    address: str | None = None
    configured: bool
    role: str
    balance_status: str = "not_configured"
    balances: list[WalletAssetBalance] = Field(default_factory=list)


class MobileWalletView(BaseModel):
    networks: list[WalletNetworkView]
