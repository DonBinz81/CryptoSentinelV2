from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.app.agent.signals.common.indicators import Candle
from backend.app.agent.signals.perp.volume_profile import VolumeProfileSignal
from backend.app.agent.signals.spot.momentum import SpotMomentumSignal


def _candles(count: int, *, base: float = 100.0, volume: float = 1000.0) -> list[Candle]:
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


def _spot_settings(sl_mode: str = "atr") -> SimpleNamespace:
    return SimpleNamespace(
        market_data_request_timeout_seconds=1.0,
        spot_relative_volume_threshold=0.1,
        spot_vwap_atr_extension_limit=100.0,
        spot_trend_structure_weight_pct=30.0,
        spot_relative_volume_weight_pct=30.0,
        spot_btc_context_weight_pct=15.0,
        spot_rsi_weight_pct=15.0,
        spot_sentiment_weight_pct=10.0,
        spot_volatility_trigger_pct=0.0,
        spot_confidence_threshold=0.0,
        spot_spike_filter_enabled=False,
        spot_spike_atr_ratio_max=3.0,
        spot_spike_atr_avg_period=50,
        spot_spike_action="skip",
        spot_spike_reduced_size_fraction=0.5,
        spot_sl_mode=sl_mode,
        spot_structural_stop_lookback_candles=20,
        spot_structural_stop_buffer_pct=1.10,
        spot_atr_stop_multiplier=2.2,
        spot_tp1_atr_multiplier=2.0,
        spot_tp2_atr_multiplier=3.5,
        spot_trailing_atr_multiplier=2.5,
    )


def _perp_settings(sl_mode: str = "atr", direction: str = "long_short") -> SimpleNamespace:
    return SimpleNamespace(
        binance_futures_base_url="https://example.invalid",
        market_data_request_timeout_seconds=1.0,
        perp_volume_profile_candle_minutes=5,
        perp_volume_profile_window_hours=2,
        perp_min_volume_profile_liquidity_usd=1.0,
        perp_value_area_pct=68.0,
        perp_direction_mode=direction,
        perp_sl_mode=sl_mode,
        perp_structural_stop_lookback_candles=20,
        perp_structural_stop_buffer_pct=1.10,
        perp_atr_stop_multiplier=0.8,
        perp_tp1_atr_multiplier=2.5,
        perp_tp2_atr_multiplier=4.0,
        perp_use_poc_for_tp2=False,
        perp_leverage_atr_period=72,
        perp_min_leverage=4,
        perp_max_leverage=40,
    )


@pytest.mark.asyncio
async def test_spot_lowest_stop_mode_uses_last_20_candle_low_with_downside_buffer() -> None:
    candles = _candles(60)
    candles[-19] = Candle(candles[-19].timestamp, 101.0, 102.0, 88.25, 101.5, 1000.0)
    candles[-7] = Candle(candles[-7].timestamp, 101.0, 102.0, 91.25, 101.5, 1000.0)

    result = await SpotMomentumSignal(_spot_settings("lowest")).evaluate(
        {"asset": "ETH", "candles": candles, "btc_context_score": 1.0, "sentiment_score": 1.0}
    )

    assert result["stop_loss"] == pytest.approx(88.25 * 0.989)
    ref = result["components"]["stop_reference"]
    assert ref["field"] == "low"
    assert ref["timestamp"] == candles[-19].timestamp.isoformat()
    assert ref["price"] == pytest.approx(88.25)


@pytest.mark.asyncio
async def test_perp_lowest_stop_mode_uses_low_for_long_and_high_for_short() -> None:
    long_candles = _candles(30, base=100.0, volume=2000.0)
    long_candles[-2] = Candle(long_candles[-2].timestamp, 96.0, 97.0, 89.5, 90.0, 2000.0)
    long_candles[-1] = Candle(long_candles[-1].timestamp, 98.0, 99.0, 97.5, 98.5, 2000.0)

    long_result = await VolumeProfileSignal(_perp_settings("lowest")).evaluate(
        {"asset": "ETH", "symbol": "ETHUSDT", "candles": long_candles}
    )

    assert long_result["side"] == "long"
    assert long_result["stop_loss"] == pytest.approx(min(candle.low for candle in long_candles[-20:]) * 0.989)
    long_ref = long_result["components"]["stop_reference"]
    assert long_ref["field"] == "low"
    assert long_ref["timestamp"] == long_candles[-2].timestamp.isoformat()

    short_candles = _candles(30, base=100.0, volume=2000.0)
    short_candles[-2] = Candle(short_candles[-2].timestamp, 104.0, 111.5, 103.0, 110.0, 2000.0)
    short_candles[-1] = Candle(short_candles[-1].timestamp, 102.0, 103.0, 101.5, 102.0, 2000.0)

    short_result = await VolumeProfileSignal(_perp_settings("lowest")).evaluate(
        {"asset": "ETH", "symbol": "ETHUSDT", "candles": short_candles}
    )

    assert short_result["side"] == "short"
    assert short_result["stop_loss"] == pytest.approx(max(candle.high for candle in short_candles[-20:]) * 1.011)
    short_ref = short_result["components"]["stop_reference"]
    assert short_ref["field"] == "high"
    assert short_ref["timestamp"] == short_candles[-2].timestamp.isoformat()
