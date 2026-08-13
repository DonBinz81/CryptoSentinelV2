"""Application settings for the FastAPI backend."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import yaml
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_DIR = PROJECT_ROOT / "configs"
HARD_MIN_PORTFOLIO_VALUE_USD = 1.0
HARD_MIN_TRADES_PER_DAY = 1
HARD_ELIGIBLE_TOKEN_MIN_COUNT = 100
HARD_ELIGIBLE_TOKEN_MAX_COUNT = 200
HARD_MAX_DRAWDOWN_CAP_PCT = -15.0
HARD_COMPETITION_CONTRACT = "0x212c61b9b72c95d95bf29cf032f5e5635629aed5"
HARD_COMPETITION_CHAIN_ID = 56

FUNCTIONAL_CONFIG_FILES = (
    "risk.yaml",
    "strategy_spot.yaml",
    "strategy_perp.yaml",
    "eligible_tokens.yaml",
)

SECTION_FIELD_MAP: dict[str, dict[str, str]] = {
    "app": {
        "env": "app_env",
        "name": "app_name",
        "version": "app_version",
        "default_user_id": "default_user_id",
    },
    "api": {
        "host": "api_host",
        "port": "api_port",
        "base_url": "api_base_url",
        "cors_origins": "cors_origins",
    },
    "dashboard": {
        "port": "dashboard_port",
    },
    "database": {
        "url": "database_url",
        "echo": "database_echo",
        "pool_size": "database_pool_size",
        "max_overflow": "database_max_overflow",
        "backup_enabled": "db_backup_enabled",
        "backup_dir": "db_backup_dir",
        "backup_interval_hours": "db_backup_interval_hours",
        "backup_retention_days": "db_backup_retention_days",
    },
    "logging": {
        "level": "log_level",
        "format": "log_format",
        "file_enabled": "log_file_enabled",
        "file_path": "log_file_path",
        "retention_days": "log_retention_days",
        "decision_retention_days": "decision_log_retention_days",
    },
    "agent": {
        "mode": "agent_mode",
        "markets_enabled": "markets_enabled",
        "execution_mode": "execution_mode",
        "heartbeat_interval_seconds": "heartbeat_interval_seconds",
        "test_scaling_pct": "test_scaling_pct",
        "operating_hours_utc": "operating_hours_utc",
    },
    "bsc": {
        "network": "bsc_network",
        "chain_id": "bsc_chain_id",
        "rpc_urls": "bsc_rpc_urls",
        "explorer_base_url": "bsc_explorer_base_url",
        "rpc_timeout_seconds": "bsc_rpc_timeout_seconds",
        "receipt_timeout_seconds": "bsc_receipt_timeout_seconds",
        "receipt_poll_seconds": "bsc_receipt_poll_seconds",
        "max_transaction_attempts": "bsc_max_transaction_attempts",
        "required_confirmations": "bsc_required_confirmations",
    },
    "competition": {
        "contract_address": "competition_contract_address",
        "chain_id": "competition_chain_id",
        "rpc_urls": "competition_rpc_urls",
        "explorer_base_url": "competition_explorer_base_url",
    },
    "wallet": {
        "address": "wallet_address",
        "addresses": "wallet_addresses",
        "key_kdf": "wallet_key_kdf",
        "key_rotation_days": "wallet_key_rotation_days",
    },
    "cmc": {
        "base_url": "cmc_base_url",
        "mcp_enabled": "cmc_mcp_enabled",
        "mcp_server_url": "cmc_mcp_server_url",
        "credit_warning_threshold": "cmc_credit_warning_threshold",
        "credit_critical_threshold": "cmc_credit_critical_threshold",
        "monthly_credit_limit": "cmc_monthly_credit_limit",
    },
    "market_data": {
        "provider": "market_data_provider",
        "alert_provider": "market_data_alert_provider",
        "cache_ttl_seconds": "market_data_cache_ttl_seconds",
        "request_timeout_seconds": "market_data_request_timeout_seconds",
        "coingecko_base_url": "coingecko_base_url",
        "coingecko_requests_per_minute": "coingecko_requests_per_minute",
        "cmc_requests_per_minute": "cmc_requests_per_minute",
    },
    "anthropic": {
        "model": "anthropic_model",
        "max_tokens": "anthropic_max_tokens",
        "daily_cost_limit_usd": "anthropic_daily_cost_limit_usd",
    },
    "twak": {
        "cli_path": "twak_cli_path",
        "api_base_url": "twak_api_base_url",
        "chain": "twak_chain",
        "autonomous_mode": "twak_autonomous_mode",
        "approval_policy": "twak_approval_policy",
        "allowed_spenders": "twak_allowed_spenders",
    },
    "execution": {
        "provider": "execution_provider",
        "pancakeswap_router_address_mainnet": "pancakeswap_router_address_mainnet",
        "pancakeswap_router_address_testnet": "pancakeswap_router_address_testnet",
        "pancakeswap_wbnb_address_mainnet": "pancakeswap_wbnb_address_mainnet",
        "pancakeswap_wbnb_address_testnet": "pancakeswap_wbnb_address_testnet",
    },
    "perp_execution": {
        "bnb_ai_agent_sdk_enabled": "bnb_ai_agent_sdk_enabled",
        "provider": "perp_execution_provider",
        "order_submit_url": "perp_order_submit_url",
        "allowed_verifying_contracts": "perp_allowed_verifying_contracts",
    },
    "x402": {
        "enabled": "x402_enabled",
        "network": "x402_network",
        "usdc_wallet_address": "x402_usdc_wallet_address",
        "daily_spend_limit_usd": "x402_daily_spend_limit_usd",
        "max_payment_per_call_usd": "x402_max_payment_per_call_usd",
        "agentdata_base_url": "agentdata_base_url",
        "fallback_base_urls": "x402_fallback_base_urls",
    },
    "fcm": {
        "enabled": "fcm_enabled",
        "project_id": "fcm_project_id",
        "critical_topic": "fcm_critical_topic",
        "token_store_path": "fcm_token_store_path",
        "notify_dry_run_trades": "notify_dry_run_trades",
        "spot_topic": "fcm_spot_topic",
        "perp_topic": "fcm_perp_topic",
        "risk_topic": "fcm_risk_topic",
        "summary_topic": "fcm_summary_topic",
        "summary_hour_utc": "agent_summary_hour_utc",
        "summary_minute_utc": "agent_summary_minute_utc",
        "risk_drawdown_alert_enabled": "risk_drawdown_alert_enabled",
        "risk_notify_drawdown_pct": "risk_notify_drawdown_pct",
    },
    "risk": {
        "capital_per_trade_pct": "risk_capital_per_trade_pct",
        "per_trade_pct": "risk_per_trade_pct",
        "max_open_positions": "risk_max_open_positions",
        "max_total_exposure_pct": "risk_max_total_exposure_pct",
        "daily_loss_limit_pct": "risk_daily_loss_limit_pct",
        "max_drawdown_pct": "risk_max_drawdown_pct",
        "min_pool_liquidity_usd": "risk_min_pool_liquidity_usd",
        "max_slippage_pct": "risk_max_slippage_pct",
        "correlation_limit": "risk_correlation_limit",
        "cooldown_minutes": "risk_cooldown_minutes",
        "bnb_gas_reserve_pct": "bnb_gas_reserve_pct",
        "bnb_gas_reserve_min": "bnb_gas_reserve_min",
        "min_portfolio_value_usd": "min_portfolio_value_usd",
        "minimum_trades_per_day": "minimum_trades_per_day",
        "dry_run_capital_usd": "dry_run_capital_usd",
        "min_trade_size_usd": "min_trade_size_usd",
    },
    "spot": {
        "confidence_threshold": "spot_confidence_threshold",
        "volatility_trigger_pct": "spot_volatility_trigger_pct",
        "relative_volume_threshold": "spot_relative_volume_threshold",
        "atr_stop_multiplier": "spot_atr_stop_multiplier",
        "sl_mode": "spot_sl_mode",
        "structural_stop_lookback_candles": "spot_structural_stop_lookback_candles",
        "structural_stop_buffer_pct": "spot_structural_stop_buffer_pct",
        "tp1_atr_multiplier": "spot_tp1_atr_multiplier",
        "tp2_atr_multiplier": "spot_tp2_atr_multiplier",
        "breakeven_enabled": "spot_breakeven_enabled",
        "breakeven_trigger_atr": "spot_breakeven_trigger_atr",
        "breakeven_offset_costs": "spot_breakeven_offset_costs",
        "breakeven_buffer_pct": "spot_breakeven_buffer_pct",
        "trailing_atr_multiplier": "spot_trailing_atr_multiplier",
        "trailing_active_from_start": "spot_trailing_active_from_start",
        "tp1_close_fraction": "spot_tp1_close_fraction",
        "scale_in_enabled": "spot_scale_in_enabled",
        "scale_in_size_fraction": "spot_scale_in_size_fraction",
        "scale_in_require_new_hh": "spot_scale_in_require_new_hh",
        "scale_in_require_be_stop": "spot_scale_in_require_be_stop",
        "scale_in_max_adds": "spot_scale_in_max_adds",
        "time_stop_enabled": "spot_time_stop_enabled",
        "time_stop_mode": "spot_time_stop_mode",
        "time_stop_lookback_candles": "spot_time_stop_lookback_candles",
        "time_stop_min_move_atr": "spot_time_stop_min_move_atr",
        "time_stop_hours_fallback": "spot_time_stop_hours_fallback",
        "spike_filter_enabled": "spot_spike_filter_enabled",
        "spike_atr_ratio_max": "spot_spike_atr_ratio_max",
        "spike_atr_avg_period": "spot_spike_atr_avg_period",
        "spike_action": "spot_spike_action",
        "spike_reduced_size_fraction": "spot_spike_reduced_size_fraction",
        "market_regime_filter_enabled": "spot_market_regime_filter_enabled",
        "market_regime_symbol": "spot_market_regime_symbol",
        "market_regime_interval": "spot_market_regime_interval",
        "market_regime_ema_period": "spot_market_regime_ema_period",
        "market_regime_low_lookback": "spot_market_regime_low_lookback",
        "market_reversal_filter_enabled": "market_reversal_filter_enabled",
        "market_reversal_symbol": "market_reversal_symbol",
        "market_reversal_interval": "market_reversal_interval",
        "market_reversal_ema_period": "market_reversal_ema_period",
        "market_reversal_confirmation_candles": "market_reversal_confirmation_candles",
        "trailing_distance_pct": "spot_trailing_distance_pct",
        "partial_take_profit_pct": "spot_partial_take_profit_pct",
        "time_stop_hours": "spot_time_stop_hours",
        "vwap_atr_extension_limit": "spot_vwap_atr_extension_limit",
        "rsi_weight_pct": "spot_rsi_weight_pct",
        "trend_structure_weight_pct": "spot_trend_structure_weight_pct",
        "relative_volume_weight_pct": "spot_relative_volume_weight_pct",
        "btc_context_weight_pct": "spot_btc_context_weight_pct",
        "sentiment_weight_pct": "spot_sentiment_weight_pct",
    },
    "perp": {
        "direction_mode": "perp_direction_mode",
        "value_area_pct": "perp_value_area_pct",
        "atr_stop_multiplier": "perp_atr_stop_multiplier",
        "sl_mode": "perp_sl_mode",
        "structural_stop_lookback_candles": "perp_structural_stop_lookback_candles",
        "structural_stop_buffer_pct": "perp_structural_stop_buffer_pct",
        "tp1_atr_multiplier": "perp_tp1_atr_multiplier",
        "tp2_atr_multiplier": "perp_tp2_atr_multiplier",
        "use_poc_for_tp2": "perp_use_poc_for_tp2",
        "breakeven_enabled": "perp_breakeven_enabled",
        "breakeven_trigger_atr": "perp_breakeven_trigger_atr",
        "breakeven_offset_costs": "perp_breakeven_offset_costs",
        "breakeven_buffer_pct": "perp_breakeven_buffer_pct",
        "trailing_base_atr_largo": "perp_trailing_base_atr_largo",
        "trailing_floor_atr_largo": "perp_trailing_floor_atr_largo",
        "trailing_base_atr_stretto": "perp_trailing_base_atr_stretto",
        "trailing_floor_atr_stretto": "perp_trailing_floor_atr_stretto",
        "trailing_mode": "perp_trailing_mode",
        "time_stop_enabled": "perp_time_stop_enabled",
        "time_stop_hours": "perp_time_stop_hours",
        "dynamic_leverage_enabled": "perp_dynamic_leverage_enabled",
        "min_volume_profile_liquidity_usd": "perp_min_volume_profile_liquidity_usd",
        "default_leverage": "perp_default_leverage",
        "min_leverage": "perp_min_leverage",
        "max_leverage": "perp_max_leverage",
        "leverage_atr_period": "perp_leverage_atr_period",
        "leverage_atr_baseline_hours": "perp_leverage_atr_baseline_hours",
        "volume_profile_window_hours": "perp_volume_profile_window_hours",
        "volume_profile_candle_minutes": "perp_volume_profile_candle_minutes",
        "trend_shock_enabled": "perp_trend_shock_enabled",
        "trend_shock_adx_threshold": "perp_trend_shock_adx_threshold",
        "trend_shock_natr_percentile": "perp_trend_shock_natr_percentile",
        "trend_shock_volume_threshold": "perp_trend_shock_volume_threshold",
        "trend_shock_recovery_confirmations": "perp_trend_shock_recovery_confirmations",
        "smart_sl_enabled": "perp_smart_sl_enabled",
        "smart_sl_l1_frac": "perp_smart_sl_l1_frac",
        "smart_sl_l2_frac": "perp_smart_sl_l2_frac",
        "smart_sl_split_l1": "perp_smart_sl_split_l1",
        "smart_sl_split_l2": "perp_smart_sl_split_l2",
        "smart_sl_split_l3": "perp_smart_sl_split_l3",
        "smart_sl_rebuy_mode": "perp_smart_sl_rebuy_mode",
        "smart_sl_rebuy_above_entry_pct": "perp_smart_sl_rebuy_above_entry_pct",
        "smart_sl_tp_adjust_after_rebuy": "perp_smart_sl_tp_adjust_after_rebuy",
        "smart_sl_tp_recovery_delta_pct": "perp_smart_sl_tp_recovery_delta_pct",
        "smart_sl_split_l1_r2": "perp_smart_sl_split_l1_r2",
        "smart_sl_split_l2_r2": "perp_smart_sl_split_l2_r2",
        "smart_sl_split_l3_r2": "perp_smart_sl_split_l3_r2",
        "smart_sl_delta_l1": "perp_smart_sl_delta_l1",
        "smart_sl_delta_l2": "perp_smart_sl_delta_l2",
        "smart_sl_confirmation_candles": "perp_smart_sl_confirmation_candles",
        "smart_sl_max_reentries": "perp_smart_sl_max_reentries",
    },
    "signal_engine": {
        "binance_futures_base_url": "binance_futures_base_url",
        "binance_futures_ws_url": "binance_futures_ws_url",
        "whale_flow_provider_url": "whale_flow_provider_url",
    },
}


def _config_dir() -> Path:
    """Return the config directory, allowing test/runtime override without reading secrets."""

    return Path(os.environ.get("CONFIG_DIR", DEFAULT_CONFIG_DIR)).resolve()


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML mapping from disk; missing files are treated as empty."""

    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Configuration file must contain a mapping: {path}")
    return payload


def _merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge nested dictionaries, with override taking precedence."""

    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _flatten_config(payload: dict[str, Any]) -> dict[str, Any]:
    """Flatten documented YAML sections into Settings field names."""

    flattened: dict[str, Any] = {}
    for section, values in payload.items():
        if section == "eligible_tokens":
            flattened["eligible_tokens"] = values
            continue
        if not isinstance(values, dict):
            continue
        field_map = SECTION_FIELD_MAP.get(section, {})
        for key, value in values.items():
            field_name = field_map.get(key)
            if field_name is not None:
                flattened[field_name] = value
    return flattened


def load_yaml_settings(config_dir: Path | None = None) -> dict[str, Any]:
    """Load functional defaults and local instance configuration.

    Precedence is explicit:
    1. Environment variables and .env, handled by pydantic-settings.
    2. configs/instance.yaml, local and gitignored.
    3. Versioned functional defaults in configs/*.yaml.
    """

    root = config_dir or _config_dir()
    merged: dict[str, Any] = {}
    for file_name in FUNCTIONAL_CONFIG_FILES:
        merged = _merge_dicts(merged, _load_yaml(root / file_name))
    merged = _merge_dicts(merged, _load_yaml(root / "instance.yaml"))
    return _flatten_config(merged)


class Settings(BaseSettings):
    """Typed runtime configuration merged from environment and YAML files."""

    app_env: str = Field(default="development", alias="APP_ENV")
    app_name: str = Field(default="CryptoSentinel Agent Backend", alias="APP_NAME")
    app_version: str = Field(default="0.1.0-step4ext", alias="APP_VERSION")
    api_host: str = Field(default="127.0.0.1", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    api_base_url: str = Field(default="http://127.0.0.1:8000", alias="API_BASE_URL")
    cors_origins: list[str] = Field(default_factory=list, alias="CORS_ORIGINS")
    dashboard_port: int = Field(default=5176, alias="DASHBOARD_PORT")
    default_user_id: UUID = Field(
        default=UUID("00000000-0000-0000-0000-000000000001"),
        alias="DEFAULT_USER_ID",
    )

    api_read_token: str | None = Field(default=None, alias="API_READ_TOKEN")
    api_admin_token: str | None = Field(default=None, alias="API_ADMIN_TOKEN")
    api_device_token: str | None = Field(default=None, alias="API_DEVICE_TOKEN")
    api_alerts_token: str | None = Field(default=None, alias="API_ALERTS_TOKEN")
    token_hash_pepper: str | None = Field(default=None, alias="TOKEN_HASH_PEPPER")

    database_url: str = Field(default="sqlite+aiosqlite:///./backend/local.db", alias="DATABASE_URL")
    database_echo: bool = Field(default=False, alias="DATABASE_ECHO")
    database_pool_size: int = Field(default=5, alias="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=10, alias="DATABASE_MAX_OVERFLOW")
    db_backup_enabled: bool = Field(default=True, alias="DB_BACKUP_ENABLED")
    db_backup_dir: str = Field(default="backend/storage/backups", alias="DB_BACKUP_DIR")
    db_backup_interval_hours: int = Field(default=6, alias="DB_BACKUP_INTERVAL_HOURS")
    db_backup_retention_days: int = Field(default=7, alias="DB_BACKUP_RETENTION_DAYS")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: Literal["json", "console"] = Field(default="json", alias="LOG_FORMAT")
    log_file_enabled: bool = Field(default=True, alias="LOG_FILE_ENABLED")
    log_file_path: str = Field(default="logs/backend.log", alias="LOG_FILE_PATH")
    log_retention_days: int = Field(default=14, alias="LOG_RETENTION_DAYS")
    decision_log_retention_days: int = Field(default=30, alias="DECISION_LOG_RETENTION_DAYS")

    cmc_api_key: str | None = Field(default=None, alias="CMC_API_KEY")
    tatum_rpc_api_key: str | None = Field(default=None, alias="TATUM_RPC_API_KEY")
    cmc_base_url: str = Field(default="https://pro-api.coinmarketcap.com", alias="CMC_BASE_URL")
    cmc_mcp_enabled: bool = Field(default=False, alias="CMC_MCP_ENABLED")
    cmc_mcp_server_url: str | None = Field(default=None, alias="CMC_MCP_SERVER_URL")
    cmc_credit_warning_threshold: int = Field(default=20, alias="CMC_CREDIT_WARNING_THRESHOLD")
    cmc_credit_critical_threshold: int = Field(default=10, alias="CMC_CREDIT_CRITICAL_THRESHOLD")
    cmc_monthly_credit_limit: int = Field(default=15_000, alias="CMC_MONTHLY_CREDIT_LIMIT")
    market_data_provider: Literal["cmc", "coingecko"] = Field(default="coingecko", alias="MARKET_DATA_PROVIDER")
    market_data_alert_provider: Literal["cmc", "coingecko"] = Field(
        default="coingecko",
        alias="MARKET_DATA_ALERT_PROVIDER",
    )
    market_data_cache_ttl_seconds: int = Field(default=60, alias="MARKET_DATA_CACHE_TTL_SECONDS")
    market_data_request_timeout_seconds: float = Field(
        default=15.0,
        alias="MARKET_DATA_REQUEST_TIMEOUT_SECONDS",
    )
    coingecko_base_url: str = Field(
        default="https://api.coingecko.com/api/v3",
        alias="COINGECKO_BASE_URL",
    )
    coingecko_requests_per_minute: int = Field(default=25, alias="COINGECKO_REQUESTS_PER_MINUTE")
    cmc_requests_per_minute: int = Field(default=30, alias="CMC_REQUESTS_PER_MINUTE")

    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-haiku-4-5-20251001", alias="ANTHROPIC_MODEL")
    anthropic_max_tokens: int = Field(default=1024, alias="ANTHROPIC_MAX_TOKENS")
    anthropic_daily_cost_limit_usd: float = Field(default=10.0, alias="ANTHROPIC_DAILY_COST_LIMIT_USD")
    anthropic_budget_usd: float = Field(default=5.0, alias="ANTHROPIC_BUDGET_USD")
    # Spesa pregressa non tracciata dal DB (es. chiamate fatte prima del tracking),
    # sommata al costo registrato per allinearsi alla console Anthropic.
    anthropic_cost_baseline_usd: float = Field(default=0.0, alias="ANTHROPIC_COST_BASELINE_USD")

    bsc_network: str = Field(default="testnet", alias="BSC_NETWORK")
    bsc_chain_id: int = Field(default=97, alias="BSC_CHAIN_ID")
    bsc_rpc_urls: list[str] = Field(default_factory=list, alias="BSC_RPC_URLS")
    bsc_explorer_base_url: str | None = Field(default=None, alias="BSC_EXPLORER_BASE_URL")
    bsc_rpc_timeout_seconds: float = Field(default=8.0, alias="BSC_RPC_TIMEOUT_SECONDS")
    bsc_receipt_timeout_seconds: float = Field(default=90.0, alias="BSC_RECEIPT_TIMEOUT_SECONDS")
    bsc_receipt_poll_seconds: float = Field(default=3.0, alias="BSC_RECEIPT_POLL_SECONDS")
    bsc_max_transaction_attempts: int = Field(default=2, alias="BSC_MAX_TRANSACTION_ATTEMPTS")
    bsc_required_confirmations: int = Field(default=1, alias="BSC_REQUIRED_CONFIRMATIONS")
    competition_contract_address: str = Field(
        default=HARD_COMPETITION_CONTRACT,
        alias="COMPETITION_CONTRACT_ADDRESS",
    )
    competition_chain_id: int = Field(default=56, alias="COMPETITION_CHAIN_ID")
    competition_rpc_urls: list[str] = Field(default_factory=list, alias="COMPETITION_RPC_URLS")
    competition_explorer_base_url: str = Field(
        default="https://bscscan.com",
        alias="COMPETITION_EXPLORER_BASE_URL",
    )

    wallet_address: str | None = Field(default=None, alias="WALLET_ADDRESS")
    wallet_addresses: list[str] = Field(default_factory=list, alias="WALLET_ADDRESSES")
    wallet_encrypted_private_key_path: str | None = Field(default=None, alias="WALLET_ENCRYPTED_PRIVATE_KEY_PATH")
    wallet_key_passphrase_env: str | None = Field(default=None, alias="WALLET_KEY_PASSPHRASE_ENV")
    wallet_key_kdf: str = Field(default="scrypt", alias="WALLET_KEY_KDF")
    wallet_key_rotation_days: int = Field(default=7, alias="WALLET_KEY_ROTATION_DAYS")

    twak_access_id: str | None = Field(default=None, alias="TWAK_ACCESS_ID")
    twak_hmac_secret: str | None = Field(default=None, alias="TWAK_HMAC_SECRET")
    twak_cli_path: str = Field(default="twak", alias="TWAK_CLI_PATH")
    twak_api_base_url: str = Field(
        default="https://tws.trustwallet.com",
        alias="TWAK_API_BASE_URL",
    )
    twak_chain: str = Field(default="bsctestnet", alias="TWAK_CHAIN")
    twak_autonomous_mode: bool = Field(default=False, alias="TWAK_AUTONOMOUS_MODE")
    twak_approval_policy: Literal["exact"] = Field(default="exact", alias="TWAK_APPROVAL_POLICY")
    twak_allowed_spenders: list[str] = Field(default_factory=list, alias="TWAK_ALLOWED_SPENDERS")

    execution_provider: Literal["twak", "pancakeswap"] = Field(
        default="twak", alias="EXECUTION_PROVIDER"
    )
    pancakeswap_router_address_mainnet: str = Field(
        default="0x10ED43C718714eb63d5aA57B78B54704E256024E",
        alias="PANCAKESWAP_ROUTER_ADDRESS_MAINNET",
    )
    pancakeswap_router_address_testnet: str = Field(
        default="0xD99D1c33F9fC3444f8101754aBC46c52416550D1",
        alias="PANCAKESWAP_ROUTER_ADDRESS_TESTNET",
    )
    pancakeswap_wbnb_address_mainnet: str = Field(
        default="0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
        alias="PANCAKESWAP_WBNB_ADDRESS_MAINNET",
    )
    pancakeswap_wbnb_address_testnet: str = Field(
        default="0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd",
        alias="PANCAKESWAP_WBNB_ADDRESS_TESTNET",
    )
    # Routing token per l'esecuzione spot in LIVE (in dry-run non vengono usati).
    # Indirizzi on-chain reali: NON hardcodati: vanno forniti via .env (vuoti = spot live disabilitato).
    spot_quote_token_address: str | None = Field(default=None, alias="SPOT_QUOTE_TOKEN_ADDRESS")
    spot_quote_token_decimals: int = Field(default=18, alias="SPOT_QUOTE_TOKEN_DECIMALS")
    # Mappa symbol -> "address" oppure "address:decimals" (decimals default 18). JSON in env.
    spot_token_map: dict[str, str] = Field(default_factory=dict, alias="SPOT_TOKEN_MAP")

    bnb_ai_agent_sdk_enabled: bool = Field(default=False, alias="BNB_AI_AGENT_SDK_ENABLED")
    perp_execution_provider: Literal["bnb_sdk"] = Field(
        default="bnb_sdk", alias="PERP_EXECUTION_PROVIDER"
    )
    perp_order_submit_url: str | None = Field(default=None, alias="PERP_ORDER_SUBMIT_URL")
    perp_allowed_verifying_contracts: list[str] = Field(
        default_factory=list,
        alias="PERP_ALLOWED_VERIFYING_CONTRACTS",
    )

    x402_enabled: bool = Field(default=False, alias="X402_ENABLED")
    x402_network: str = Field(default="bsc", alias="X402_NETWORK")
    x402_usdc_wallet_address: str | None = Field(default=None, alias="X402_USDC_WALLET_ADDRESS")
    x402_daily_spend_limit_usd: float = Field(default=5.0, alias="X402_DAILY_SPEND_LIMIT_USD")
    x402_max_payment_per_call_usd: float = Field(default=0.25, alias="X402_MAX_PAYMENT_PER_CALL_USD")
    agentdata_base_url: str | None = Field(default=None, alias="AGENTDATA_BASE_URL")
    x402_fallback_base_urls: list[str] = Field(default_factory=list, alias="X402_FALLBACK_BASE_URLS")

    fcm_enabled: bool = Field(default=False, alias="FCM_ENABLED")
    fcm_project_id: str | None = Field(default=None, alias="FCM_PROJECT_ID")
    fcm_credentials_path: str | None = Field(default=None, alias="FCM_CREDENTIALS_PATH")
    fcm_critical_topic: str | None = Field(default=None, alias="FCM_CRITICAL_TOPIC")
    fcm_token_store_path: str = Field(default="backend/storage/fcm_tokens.json", alias="FCM_TOKEN_STORE_PATH")
    notify_dry_run_trades: bool = Field(default=False, alias="NOTIFY_DRY_RUN_TRADES")
    fcm_spot_topic: str = Field(default="cryptosentinel-spot", alias="FCM_SPOT_TOPIC")
    fcm_perp_topic: str = Field(default="cryptosentinel-perp", alias="FCM_PERP_TOPIC")
    fcm_risk_topic: str = Field(default="cryptosentinel-risk", alias="FCM_RISK_TOPIC")
    fcm_summary_topic: str = Field(default="cryptosentinel-summary", alias="FCM_SUMMARY_TOPIC")
    agent_summary_hour_utc: int = Field(default=23, alias="AGENT_SUMMARY_HOUR_UTC")
    agent_summary_minute_utc: int = Field(default=55, alias="AGENT_SUMMARY_MINUTE_UTC")
    risk_drawdown_alert_enabled: bool = Field(default=True, alias="RISK_DRAWDOWN_ALERT_ENABLED")
    risk_notify_drawdown_pct: float = Field(default=10.0, alias="RISK_NOTIFY_DRAWDOWN_PCT")

    agent_mode: str = Field(default="conservative", alias="AGENT_MODE")
    markets_enabled: str = Field(default="both", alias="MARKETS_ENABLED")
    execution_mode: str = Field(default="dry_run", alias="EXECUTION_MODE")
    heartbeat_interval_seconds: int = Field(default=5, alias="HEARTBEAT_INTERVAL_SECONDS")
    test_scaling_pct: float = Field(default=10.0, alias="TEST_SCALING_PCT")
    operating_hours_utc: str = Field(default="00:00-23:59", alias="OPERATING_HOURS_UTC")

    bnb_gas_reserve_pct: float = Field(default=15.0, alias="BNB_GAS_RESERVE_PCT")
    bnb_gas_reserve_min: float | None = Field(default=None, alias="BNB_GAS_RESERVE_MIN")
    min_portfolio_value_usd: float = Field(default=5.0, alias="MIN_PORTFOLIO_VALUE_USD")
    minimum_trades_per_day: int = Field(default=1, alias="MINIMUM_TRADES_PER_DAY")
    dry_run_capital_usd: float = Field(default=500.0, alias="DRY_RUN_CAPITAL_USD")
    min_trade_size_usd: float = Field(default=7.0, alias="MIN_TRADE_SIZE_USD")
    risk_capital_per_trade_pct: float = Field(default=6.0, alias="RISK_CAPITAL_PER_TRADE_PCT")
    risk_per_trade_pct: float = Field(default=1.5, alias="RISK_PER_TRADE_PCT")
    risk_max_open_positions: int = Field(default=3, alias="RISK_MAX_OPEN_POSITIONS")
    risk_max_total_exposure_pct: float = Field(default=30.0, alias="RISK_MAX_TOTAL_EXPOSURE_PCT")
    risk_daily_loss_limit_pct: float = Field(default=-8.0, alias="RISK_DAILY_LOSS_LIMIT_PCT")
    risk_max_drawdown_pct: float = Field(default=-15.0, alias="RISK_MAX_DRAWDOWN_PCT")
    risk_min_pool_liquidity_usd: float = Field(default=50000.0, alias="RISK_MIN_POOL_LIQUIDITY_USD")
    risk_max_slippage_pct: float = Field(default=1.0, alias="RISK_MAX_SLIPPAGE_PCT")
    risk_correlation_limit: float = Field(default=0.8, alias="RISK_CORRELATION_LIMIT")
    risk_cooldown_minutes: int = Field(default=30, alias="RISK_COOLDOWN_MINUTES")

    spot_confidence_threshold: float = Field(default=0.55, alias="SPOT_CONFIDENCE_THRESHOLD")
    spot_volatility_trigger_pct: float = Field(default=0.4, alias="SPOT_VOLATILITY_TRIGGER_PCT")
    spot_relative_volume_threshold: float = Field(default=1.3, alias="SPOT_RELATIVE_VOLUME_THRESHOLD")
    spot_atr_stop_multiplier: float = Field(default=2.2, alias="SPOT_ATR_STOP_MULTIPLIER")
    spot_sl_mode: str = Field(default="atr", alias="SPOT_SL_MODE")
    spot_structural_stop_lookback_candles: int = Field(default=20, alias="SPOT_STRUCTURAL_STOP_LOOKBACK_CANDLES")
    spot_structural_stop_buffer_pct: float = Field(default=1.10, alias="SPOT_STRUCTURAL_STOP_BUFFER_PCT")
    spot_tp1_atr_multiplier: float = Field(default=2.0, alias="SPOT_TP1_ATR_MULTIPLIER")
    spot_tp2_atr_multiplier: float = Field(default=3.5, alias="SPOT_TP2_ATR_MULTIPLIER")
    spot_breakeven_enabled: bool = Field(default=True, alias="SPOT_BREAKEVEN_ENABLED")
    spot_breakeven_trigger_atr: float = Field(default=0.6, alias="SPOT_BREAKEVEN_TRIGGER_ATR")
    spot_breakeven_offset_costs: bool = Field(default=True, alias="SPOT_BREAKEVEN_OFFSET_COSTS")
    # Cuscinetto extra del breakeven, in % sul prezzo di entry: lo stop si alza a
    # entry+X% (si applica solo se il prezzo l'ha già superato → niente chiusura
    # immediata). Garantisce di coprire le fee con margine. 0 = disattivato.
    spot_breakeven_buffer_pct: float = Field(default=0.1, alias="SPOT_BREAKEVEN_BUFFER_PCT")
    spot_trailing_atr_multiplier: float = Field(default=2.5, alias="SPOT_TRAILING_ATR_MULTIPLIER")
    spot_trailing_active_from_start: bool = Field(default=True, alias="SPOT_TRAILING_ACTIVE_FROM_START")
    spot_tp1_close_fraction: float = Field(default=0.30, alias="SPOT_TP1_CLOSE_FRACTION")
    spot_scale_in_enabled: bool = Field(default=True, alias="SPOT_SCALE_IN_ENABLED")
    spot_scale_in_size_fraction: float = Field(default=0.50, alias="SPOT_SCALE_IN_SIZE_FRACTION")
    spot_scale_in_require_new_hh: bool = Field(default=True, alias="SPOT_SCALE_IN_REQUIRE_NEW_HH")
    spot_scale_in_require_be_stop: bool = Field(default=True, alias="SPOT_SCALE_IN_REQUIRE_BE_STOP")
    spot_scale_in_max_adds: int = Field(default=1, alias="SPOT_SCALE_IN_MAX_ADDS")
    spot_time_stop_enabled: bool = Field(default=False, alias="SPOT_TIME_STOP_ENABLED")
    spot_time_stop_mode: str = Field(default="atr", alias="SPOT_TIME_STOP_MODE")  # atr | hours
    spot_time_stop_lookback_candles: int = Field(default=8, alias="SPOT_TIME_STOP_LOOKBACK_CANDLES")
    spot_time_stop_min_move_atr: float = Field(default=0.5, alias="SPOT_TIME_STOP_MIN_MOVE_ATR")
    spot_time_stop_hours_fallback: int = Field(default=6, alias="SPOT_TIME_STOP_HOURS_FALLBACK")
    spot_spike_filter_enabled: bool = Field(default=True, alias="SPOT_SPIKE_FILTER_ENABLED")
    spot_spike_atr_ratio_max: float = Field(default=3.0, alias="SPOT_SPIKE_ATR_RATIO_MAX")
    spot_spike_atr_avg_period: int = Field(default=50, alias="SPOT_SPIKE_ATR_AVG_PERIOD")
    spot_spike_action: str = Field(default="skip", alias="SPOT_SPIKE_ACTION")  # skip | reduce_size
    spot_spike_reduced_size_fraction: float = Field(default=0.5, alias="SPOT_SPIKE_REDUCED_SIZE_FRACTION")
    # Filtro regime mercato: blocca i nuovi buy spot quando BTC è in downtrend
    # forte (sotto EMA50 sul 15m E fa nuovi minimi). Sblocco solo se BTC richiude
    # sopra la EMA50 (macchina a stati con isteresi → niente flip-flop).
    spot_market_regime_filter_enabled: bool = Field(default=True, alias="SPOT_MARKET_REGIME_FILTER_ENABLED")
    spot_market_regime_symbol: str = Field(default="BTCUSDT", alias="SPOT_MARKET_REGIME_SYMBOL")
    spot_market_regime_interval: str = Field(default="15m", alias="SPOT_MARKET_REGIME_INTERVAL")
    spot_market_regime_ema_period: int = Field(default=50, alias="SPOT_MARKET_REGIME_EMA_PERIOD")
    spot_market_regime_low_lookback: int = Field(default=12, alias="SPOT_MARKET_REGIME_LOW_LOOKBACK")
    # Filtro inversione mercato: conferma risk-on BTC prima di nuove entrate e blocca
    # short perp contro una risalita confermata. Non sblocca mai lo spot se altri
    # guardrail/regimi lo stanno gia' bloccando.
    market_reversal_filter_enabled: bool = Field(default=True, alias="MARKET_REVERSAL_FILTER_ENABLED")
    market_reversal_symbol: str = Field(default="BTCUSDT", alias="MARKET_REVERSAL_SYMBOL")
    market_reversal_interval: str = Field(default="15m", alias="MARKET_REVERSAL_INTERVAL")
    market_reversal_ema_period: int = Field(default=10, alias="MARKET_REVERSAL_EMA_PERIOD")
    market_reversal_confirmation_candles: int = Field(default=2, alias="MARKET_REVERSAL_CONFIRMATION_CANDLES")
    spot_trailing_distance_pct: float = Field(default=2.0, alias="SPOT_TRAILING_DISTANCE_PCT")
    spot_partial_take_profit_pct: float = Field(default=3.0, alias="SPOT_PARTIAL_TAKE_PROFIT_PCT")
    spot_time_stop_hours: int = Field(default=6, alias="SPOT_TIME_STOP_HOURS")
    spot_vwap_atr_extension_limit: float = Field(default=1.2, alias="SPOT_VWAP_ATR_EXTENSION_LIMIT")
    spot_rsi_weight_pct: float = Field(default=15.0, alias="SPOT_RSI_WEIGHT_PCT")
    spot_trend_structure_weight_pct: float = Field(default=30.0, alias="SPOT_TREND_STRUCTURE_WEIGHT_PCT")
    spot_relative_volume_weight_pct: float = Field(default=30.0, alias="SPOT_RELATIVE_VOLUME_WEIGHT_PCT")
    spot_btc_context_weight_pct: float = Field(default=15.0, alias="SPOT_BTC_CONTEXT_WEIGHT_PCT")
    spot_sentiment_weight_pct: float = Field(default=10.0, alias="SPOT_SENTIMENT_WEIGHT_PCT")

    perp_direction_mode: str = Field(default="long_short", alias="PERP_DIRECTION_MODE")
    perp_value_area_pct: float = Field(default=68.0, alias="PERP_VALUE_AREA_PCT")
    # SL/TP ancorati all'entry via ATR (R:R controllato a prescindere dalla leva).
    perp_atr_stop_multiplier: float = Field(default=0.8, alias="PERP_ATR_STOP_MULTIPLIER")
    perp_tp1_atr_multiplier: float = Field(default=2.5, alias="PERP_TP1_ATR_MULTIPLIER")
    perp_tp2_atr_multiplier: float = Field(default=4.0, alias="PERP_TP2_ATR_MULTIPLIER")
    # Se True, TP2 usa il POC (livello strutturale di volume) quando è più ambizioso
    # del target ATR; altrimenti resta sul target ATR. Garantisce R:R minimo.
    perp_use_poc_for_tp2: bool = Field(default=True, alias="PERP_USE_POC_FOR_TP2")
    perp_sl_mode: str = Field(default="atr", alias="PERP_SL_MODE")
    perp_structural_stop_lookback_candles: int = Field(default=20, alias="PERP_STRUCTURAL_STOP_LOOKBACK_CANDLES")
    perp_structural_stop_buffer_pct: float = Field(default=1.10, alias="PERP_STRUCTURAL_STOP_BUFFER_PCT")
    perp_min_rr: float = Field(default=1.2, alias="PERP_MIN_RR")  # FIX-2: R:R minimo TP1 vs SL (0 = disattivo)
    # ── Protezione posizione perp (breakeven + trailing dinamico sulla leva) ──────
    # Breakeven: a +N×ATR dall'entry lo SL sale a entry (+costi), niente più perdita.
    perp_breakeven_enabled: bool = Field(default=True, alias="PERP_BREAKEVEN_ENABLED")
    perp_breakeven_trigger_atr: float = Field(default=1.0, alias="PERP_BREAKEVEN_TRIGGER_ATR")
    perp_breakeven_offset_costs: bool = Field(default=True, alias="PERP_BREAKEVEN_OFFSET_COSTS")
    # Cuscinetto extra del breakeven, in % sul prezzo di entry (vedi spot). Su perp
    # con leva può cadere oltre i TP: in quel caso non scatta (i TP chiudono prima)
    # e resta valida la copertura fee andata+ritorno. 0 = disattivato.
    perp_breakeven_buffer_pct: float = Field(default=0.1, alias="PERP_BREAKEVEN_BUFFER_PCT")
    # Trailing ATR dinamico: il moltiplicatore scala con la leva del trade tra base
    # (leva minima → largo) e floor (leva massima → stretto). Due preset Largo/Stretto.
    perp_trailing_base_atr_largo: float = Field(default=4.0, alias="PERP_TRAILING_BASE_ATR_LARGO")
    perp_trailing_floor_atr_largo: float = Field(default=2.5, alias="PERP_TRAILING_FLOOR_ATR_LARGO")
    perp_trailing_base_atr_stretto: float = Field(default=2.5, alias="PERP_TRAILING_BASE_ATR_STRETTO")
    perp_trailing_floor_atr_stretto: float = Field(default=1.5, alias="PERP_TRAILING_FLOOR_ATR_STRETTO")
    perp_trailing_mode: str = Field(default="largo", alias="PERP_TRAILING_MODE")  # largo|stretto
    perp_time_stop_enabled: bool = Field(default=False, alias="PERP_TIME_STOP_ENABLED")
    perp_time_stop_hours: int = Field(default=8, alias="PERP_TIME_STOP_HOURS")
    perp_dynamic_leverage_enabled: bool = Field(default=True, alias="PERP_DYNAMIC_LEVERAGE_ENABLED")
    perp_min_volume_profile_liquidity_usd: float = Field(
        default=50000.0,
        alias="PERP_MIN_VOLUME_PROFILE_LIQUIDITY_USD",
    )
    perp_default_leverage: int = Field(default=2, alias="PERP_DEFAULT_LEVERAGE")  # legacy
    # Range leva modulata sull'ATR(72) in apertura (bassa vol → max, alta vol → min).
    perp_min_leverage: int = Field(default=4, alias="PERP_MIN_LEVERAGE")
    perp_max_leverage: int = Field(default=40, alias="PERP_MAX_LEVERAGE")
    # Baseline storica per atr_min/atr_max della leva: periodo ATR e finestra di lookback.
    perp_leverage_atr_period: int = Field(default=72, alias="PERP_LEVERAGE_ATR_PERIOD")
    perp_leverage_atr_baseline_hours: int = Field(default=120, alias="PERP_LEVERAGE_ATR_BASELINE_HOURS")
    perp_volume_profile_window_hours: int = Field(default=24, alias="PERP_VOLUME_PROFILE_WINDOW_HOURS")
    perp_volume_profile_candle_minutes: int = Field(default=5, alias="PERP_VOLUME_PROFILE_CANDLE_MINUTES")
    # Filtro shock BTC perp
    perp_trend_shock_enabled: bool = Field(default=True, alias="PERP_TREND_SHOCK_ENABLED")
    perp_trend_shock_adx_threshold: float = Field(default=25.0, alias="PERP_TREND_SHOCK_ADX_THRESHOLD")
    perp_trend_shock_natr_percentile: float = Field(default=90.0, alias="PERP_TREND_SHOCK_NATR_PERCENTILE")
    perp_trend_shock_volume_threshold: float = Field(default=2.0, alias="PERP_TREND_SHOCK_VOLUME_THRESHOLD")
    perp_trend_shock_recovery_confirmations: int = Field(default=3, alias="PERP_TREND_SHOCK_RECOVERY_CONFIRMATIONS")
    # Smart Stop Loss
    perp_smart_sl_enabled: bool = Field(default=True, alias="PERP_SMART_SL_ENABLED")
    perp_smart_sl_l1_frac: float = Field(default=0.333, alias="PERP_SMART_SL_L1_FRAC")
    perp_smart_sl_l2_frac: float = Field(default=0.666, alias="PERP_SMART_SL_L2_FRAC")
    perp_smart_sl_split_l1: float = Field(default=0.25, alias="PERP_SMART_SL_SPLIT_L1")
    perp_smart_sl_split_l2: float = Field(default=0.55, alias="PERP_SMART_SL_SPLIT_L2")
    perp_smart_sl_split_l3: float = Field(default=0.20, alias="PERP_SMART_SL_SPLIT_L3")
    perp_smart_sl_rebuy_mode: str = Field(default="above_entry", alias="PERP_SMART_SL_REBUY_MODE")
    perp_smart_sl_rebuy_above_entry_pct: float = Field(default=100.0, alias="PERP_SMART_SL_REBUY_ABOVE_ENTRY_PCT")
    perp_smart_sl_tp_adjust_after_rebuy: bool = Field(default=True, alias="PERP_SMART_SL_TP_ADJUST_AFTER_REBUY")
    perp_smart_sl_tp_recovery_delta_pct: float = Field(default=7.0, alias="PERP_SMART_SL_TP_RECOVERY_DELTA_PCT")
    perp_smart_sl_split_l1_r2: float = Field(default=0.75, alias="PERP_SMART_SL_SPLIT_L1_R2")
    perp_smart_sl_split_l2_r2: float = Field(default=0.20, alias="PERP_SMART_SL_SPLIT_L2_R2")
    perp_smart_sl_split_l3_r2: float = Field(default=0.05, alias="PERP_SMART_SL_SPLIT_L3_R2")
    perp_smart_sl_delta_l1: float = Field(default=0.08, alias="PERP_SMART_SL_DELTA_L1")
    perp_smart_sl_delta_l2: float = Field(default=0.16, alias="PERP_SMART_SL_DELTA_L2")
    perp_smart_sl_confirmation_candles: int = Field(default=2, alias="PERP_SMART_SL_CONFIRMATION_CANDLES")
    perp_smart_sl_max_reentries: int = Field(default=1, alias="PERP_SMART_SL_MAX_REENTRIES")

    binance_futures_base_url: str | None = Field(default=None, alias="BINANCE_FUTURES_BASE_URL")
    binance_futures_ws_url: str | None = Field(default=None, alias="BINANCE_FUTURES_WS_URL")
    whale_flow_provider_url: str | None = Field(default=None, alias="WHALE_FLOW_PROVIDER_URL")

    eligible_tokens: list[str] = Field(default_factory=list, alias="ELIGIBLE_TOKENS")

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
        populate_by_name=True,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: Any,
        env_settings: Any,
        dotenv_settings: Any,
        file_secret_settings: Any,
    ) -> tuple[Any, ...]:
        """Use explicit precedence: environment/.env override YAML defaults."""

        return env_settings, dotenv_settings, init_settings, file_secret_settings

    @field_validator("database_url", mode="before")
    @classmethod
    def default_database_url(cls, value: str | None) -> str:
        if not value or not str(value).strip():
            return "sqlite+aiosqlite:///./backend/local.db"
        return str(value).strip()

    @field_validator("twak_cli_path", mode="before")
    @classmethod
    def default_twak_cli_path(cls, value: str | None) -> str:
        if not value or not str(value).strip():
            return "twak"
        return str(value).strip()

    @field_validator("twak_api_base_url", mode="before")
    @classmethod
    def default_twak_api_base_url(cls, value: str | None) -> str:
        if not value or not str(value).strip():
            return "https://tws.trustwallet.com"
        return str(value).strip()

    @field_validator(
        "cors_origins",
        "bsc_rpc_urls",
        "competition_rpc_urls",
        "wallet_addresses",
        "twak_allowed_spenders",
        "perp_allowed_verifying_contracts",
        "x402_fallback_base_urls",
        mode="before",
    )
    @classmethod
    def split_string_list(cls, value: str | list[str] | None) -> list[str]:
        """Parse comma-separated list values from environment variables."""

        if value is None or value == "":
            return []
        if isinstance(value, list):
            return value
        return [item.strip() for item in value.split(",") if item.strip()]

    @field_validator("eligible_tokens", mode="before")
    @classmethod
    def split_eligible_tokens(cls, value: str | list[str] | None) -> list[str]:
        """Parse and deduplicate eligible token lists from YAML or environment overrides."""

        if value is None or value == "":
            return []
        if isinstance(value, list):
            tokens = [str(token).strip() for token in value if str(token).strip()]
        else:
            tokens = [token.strip() for token in value.split(",") if token.strip()]
        return list(dict.fromkeys(tokens))

    @model_validator(mode="after")
    def validate_hard_guardrails(self) -> "Settings":
        """Reject startup if non-disablable qualification guardrails are violated."""

        if self.min_portfolio_value_usd <= HARD_MIN_PORTFOLIO_VALUE_USD:
            raise ValueError("min_portfolio_value_usd must stay above the hard $1 qualification floor")
        if self.minimum_trades_per_day < HARD_MIN_TRADES_PER_DAY:
            raise ValueError("minimum_trades_per_day must be at least 1")
        if self.risk_max_drawdown_pct < HARD_MAX_DRAWDOWN_CAP_PCT or self.risk_max_drawdown_pct >= 0:
            raise ValueError("risk_max_drawdown_pct must be negative and no looser than -15%")
        if not HARD_ELIGIBLE_TOKEN_MIN_COUNT <= len(self.eligible_tokens) <= HARD_ELIGIBLE_TOKEN_MAX_COUNT:
            raise ValueError("eligible_tokens must contain between 100 and 200 unique competition-eligible entries")
        if self.bnb_gas_reserve_pct < 15:
            raise ValueError("bnb_gas_reserve_pct cannot be lower than the hard 15% reserve")
        if self.bnb_gas_reserve_min is None or self.bnb_gas_reserve_min <= 0:
            raise ValueError("bnb_gas_reserve_min must be a positive non-tradable floor")
        if self.bsc_max_transaction_attempts < 1 or self.bsc_max_transaction_attempts > 3:
            raise ValueError("bsc_max_transaction_attempts must be between 1 and 3")
        if self.bsc_required_confirmations < 1:
            raise ValueError("bsc_required_confirmations must be at least 1")
        if self.execution_mode == "live" and self.bsc_network != "testnet":
            raise ValueError("Step 4 live execution is restricted to BSC testnet")
        if self.competition_contract_address.lower() != HARD_COMPETITION_CONTRACT:
            raise ValueError("competition_contract_address must match the official competition contract")
        if self.competition_chain_id != HARD_COMPETITION_CHAIN_ID:
            raise ValueError("competition_chain_id must remain BSC mainnet chain 56")
        if self.x402_enabled and self.x402_network.lower() != "bsc":
            raise ValueError("x402 may only be enabled on BSC")
        return self

    @property
    def auth_configured(self) -> bool:
        """Return whether both read and admin tokens are configured."""

        return bool(self.api_read_token and self.api_admin_token)

    @property
    def is_https_enabled(self) -> bool:
        """Return whether the public API URL is configured as HTTPS."""

        return self.api_base_url.lower().startswith("https://")

    @property
    def twak_rest_configured(self) -> bool:
        """Return whether Trust Wallet REST credentials are present."""

        return bool(self.twak_access_id and self.twak_hmac_secret)


@lru_cache
def get_settings() -> Settings:
    """Return cached settings for dependency injection."""

    return Settings(**load_yaml_settings())
