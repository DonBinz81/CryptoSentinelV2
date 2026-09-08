"""VWAP extension gate on perp entries (NOTE/120-122).

The gate rejects mean-reversion entries taken too many ATRs beyond the 24h
close-weighted vwap in the trade's direction. It must be causal (closed
candles only) and fail-open.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.app.agent.signals.common.indicators import Candle
from backend.app.agent.signals.perp.volume_profile import VolumeProfileSignal


def _candles(count: int, *, base: float = 100.0, volume: float = 2000.0) -> list[Candle]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Candle(
            timestamp=start + timedelta(minutes=5 * index),
            open=base + index * 0.05,
            high=base + index * 0.05 + 1.0,
            low=base + index * 0.05 - 1.0,
            close=base + index * 0.05,
            volume=volume,
        )
        for index in range(count)
    ]


def _long_setup() -> list[Candle]:
    candles = _candles(30)
    candles[-2] = Candle(candles[-2].timestamp, 96.0, 97.0, 89.5, 90.0, 2000.0)
    candles[-1] = Candle(candles[-1].timestamp, 98.0, 99.0, 97.5, 98.5, 2000.0)
    return candles


def _settings(ext_limit: float) -> SimpleNamespace:
    return SimpleNamespace(
        binance_futures_base_url="https://example.invalid",
        market_data_request_timeout_seconds=1.0,
        perp_volume_profile_candle_minutes=5,
        perp_volume_profile_window_hours=2,
        perp_value_area_pct=68.0,
        perp_direction_mode="long_short",
        perp_min_leverage=4,
        perp_max_leverage=40,
        perp_leverage_atr_period=72,
        perp_atr_stop_multiplier=0.8,
        perp_tp1_atr_multiplier=2.0,
        perp_tp2_atr_multiplier=3.0,
        perp_use_poc_for_tp2=True,
        perp_min_volume_profile_liquidity_usd=0.0,
        perp_sl_mode="lowest",
        perp_structural_stop_lookback_candles=20,
        perp_structural_stop_buffer_pct=1.10,
        perp_min_rr=0.0,
        perp_vwap_atr_extension_limit=ext_limit,
    )


@pytest.mark.asyncio
async def test_gate_rejects_overextended_long() -> None:
    """Entry far below the causal vwap (in ATRs) must be rejected with its
    own reason, so the skip is attributable in agent_decisions."""
    result = await VolumeProfileSignal(_settings(0.5)).evaluate(
        {"asset": "ETH", "symbol": "ETHUSDT", "candles": _long_setup()}
    )
    assert result["side"] is None
    assert result["action"] == "skip"
    assert result["reason"] == "vwap_extension_rejected"
    assert result["components"]["vwap_ext"] is not None
    assert result["components"]["vwap_ext"] >= 0.5


@pytest.mark.asyncio
async def test_gate_passes_within_limit_and_reports_extension() -> None:
    result = await VolumeProfileSignal(_settings(3.5)).evaluate(
        {"asset": "ETH", "symbol": "ETHUSDT", "candles": _long_setup()}
    )
    assert result["side"] == "long"
    assert result["components"]["vwap_ext"] is not None
    assert result["components"]["vwap_ext"] < 3.5
    assert result["components"]["vwap_ext_limit"] == 3.5


@pytest.mark.asyncio
async def test_gate_zero_disables() -> None:
    result = await VolumeProfileSignal(_settings(0.0)).evaluate(
        {"asset": "ETH", "symbol": "ETHUSDT", "candles": _long_setup()}
    )
    assert result["side"] == "long"
    assert result["components"]["vwap_ext"] is None
    assert result["components"]["vwap_ext_limit"] is None


@pytest.mark.asyncio
async def test_gate_vwap_is_causal_ignores_forming_candle() -> None:
    """A huge-volume forming candle must NOT move the gate's vwap: the gate
    reads closed candles only (the backtest validated this construction, and
    an intra-candle volume spike must not flip the decision mid-bar)."""
    base = _long_setup()
    inflated = list(base)
    last = inflated[-1]
    inflated[-1] = Candle(last.timestamp, last.open, last.high, last.low, last.close, last.volume * 1000)

    r_base = await VolumeProfileSignal(_settings(3.5)).evaluate(
        {"asset": "ETH", "symbol": "ETHUSDT", "candles": base}
    )
    r_inflated = await VolumeProfileSignal(_settings(3.5)).evaluate(
        {"asset": "ETH", "symbol": "ETHUSDT", "candles": inflated}
    )
    assert r_base["components"]["vwap_ext"] == r_inflated["components"]["vwap_ext"]
