"""ATR cap on the perp stop distance (NOTE/131-132).

The structural stop keeps its fixed % buffer, but when its distance from
entry exceeds ``perp_max_stop_atr`` ATRs the stop is pulled to
``entry -/+ K*ATR``. 0 disables the cap; when the structural stop is
already inside the cap nothing changes.
"""
from __future__ import annotations

import pytest

from backend.app.agent.signals.common.indicators import Candle
from backend.app.agent.signals.perp.volume_profile import VolumeProfileSignal

from backend.tests.unit.test_signal_stop_loss_modes import _candles, _perp_settings


def _long_candles() -> list[Candle]:
    candles = _candles(30, base=100.0, volume=2000.0)
    candles[-2] = Candle(candles[-2].timestamp, 96.0, 97.0, 89.5, 90.0, 2000.0)
    candles[-1] = Candle(candles[-1].timestamp, 98.0, 99.0, 97.5, 98.5, 2000.0)
    return candles


def _short_candles() -> list[Candle]:
    candles = _candles(30, base=100.0, volume=2000.0)
    candles[-2] = Candle(candles[-2].timestamp, 104.0, 111.5, 103.0, 110.0, 2000.0)
    candles[-1] = Candle(candles[-1].timestamp, 102.0, 103.0, 101.5, 102.0, 2000.0)
    return candles


def _settings(max_stop_atr: float):
    settings = _perp_settings("lowest")
    settings.perp_max_stop_atr = max_stop_atr
    return settings


@pytest.mark.asyncio
async def test_cap_pulls_long_stop_to_k_atr_when_structural_is_farther() -> None:
    result = await VolumeProfileSignal(_settings(3.0)).evaluate(
        {"asset": "ETH", "symbol": "ETHUSDT", "candles": _long_candles()}
    )

    assert result["side"] == "long"
    atr_v = result["components"]["atr"]
    structural = 89.5 * 0.989
    assert 98.5 - structural > 3.0 * atr_v  # premise: the cap must bind here
    assert result["stop_loss"] == pytest.approx(98.5 - 3.0 * atr_v)
    assert result["components"]["stop_capped"] is True
    assert result["components"]["stop_dist_atr"] == pytest.approx(3.0, abs=0.01)
    assert result["components"]["stop_reference"]["capped_at_atr"] == 3.0


@pytest.mark.asyncio
async def test_cap_pulls_short_stop_symmetrically() -> None:
    result = await VolumeProfileSignal(_settings(3.0)).evaluate(
        {"asset": "ETH", "symbol": "ETHUSDT", "candles": _short_candles()}
    )

    assert result["side"] == "short"
    atr_v = result["components"]["atr"]
    assert result["stop_loss"] == pytest.approx(102.0 + 3.0 * atr_v)
    assert result["components"]["stop_capped"] is True


@pytest.mark.asyncio
async def test_cap_leaves_structural_stop_when_already_inside() -> None:
    result = await VolumeProfileSignal(_settings(50.0)).evaluate(
        {"asset": "ETH", "symbol": "ETHUSDT", "candles": _long_candles()}
    )

    assert result["side"] == "long"
    assert result["stop_loss"] == pytest.approx(89.5 * 0.989)
    assert result["components"]["stop_capped"] is False
    assert "capped_at_atr" not in result["components"]["stop_reference"]


@pytest.mark.asyncio
async def test_cap_zero_disables() -> None:
    result = await VolumeProfileSignal(_settings(0.0)).evaluate(
        {"asset": "ETH", "symbol": "ETHUSDT", "candles": _long_candles()}
    )

    assert result["side"] == "long"
    assert result["stop_loss"] == pytest.approx(89.5 * 0.989)
    assert result["components"]["stop_capped"] is False
