"""Shared technical-indicator helpers for agent signal modules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Iterable


@dataclass(frozen=True)
class Candle:
    """Normalized OHLCV candle used by the signal engine."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


def sanitize_candles(raw: Iterable[object]) -> list[Candle]:
    """Convert dict/model candle-like values into validated candles."""

    candles: list[Candle] = []
    for item in raw:
        getter = item.get if isinstance(item, dict) else lambda key, default=None: getattr(item, key, default)
        timestamp = getter("timestamp")
        if not isinstance(timestamp, datetime):
            continue
        try:
            candle = Candle(
                timestamp=timestamp,
                open=float(getter("open")),
                high=float(getter("high")),
                low=float(getter("low")),
                close=float(getter("close")),
                volume=max(0.0, float(getter("volume") or 0.0)),
            )
        except (TypeError, ValueError):
            continue
        if all(isfinite(value) and value > 0 for value in (candle.open, candle.high, candle.low, candle.close)):
            candles.append(candle)
    return sorted(candles, key=lambda candle: candle.timestamp)


def ema(values: list[float], period: int) -> float | None:
    """Return the latest exponential moving average."""

    if period <= 0 or len(values) < period:
        return None
    alpha = 2 / (period + 1)
    current = sum(values[:period]) / period
    for value in values[period:]:
        current = value * alpha + current * (1 - alpha)
    return current


def vwap(candles: list[Candle]) -> float | None:
    """Return volume-weighted average price using typical price."""

    total_volume = sum(candle.volume for candle in candles)
    if total_volume <= 0:
        return None
    weighted = sum(((candle.high + candle.low + candle.close) / 3) * candle.volume for candle in candles)
    return weighted / total_volume


def atr(candles: list[Candle], period: int = 14) -> float | None:
    """Return latest Average True Range."""

    if len(candles) < period + 1:
        return None
    true_ranges: list[float] = []
    previous_close = candles[0].close
    for candle in candles[1:]:
        true_ranges.append(
            max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
        )
        previous_close = candle.close
    return sum(true_ranges[-period:]) / period


def atr_series(candles: list[Candle], period: int = 14) -> list[float]:
    """Serie ATR a finestra mobile (un valore per ogni posizione della finestra).

    L'ultimo valore coincide con ``atr(candles, period)``. Usata per ricavare
    minimo/massimo storico dell'ATR nella finestra disponibile.
    """
    if len(candles) < period + 1:
        return []
    true_ranges: list[float] = []
    previous_close = candles[0].close
    for candle in candles[1:]:
        true_ranges.append(
            max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
        )
        previous_close = candle.close
    out: list[float] = []
    for end in range(period, len(true_ranges) + 1):
        window = true_ranges[end - period : end]
        out.append(sum(window) / period)
    return out


def rsi(closes: list[float], period: int = 14) -> float | None:
    """Return latest Relative Strength Index."""

    if len(closes) < period + 1:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for previous, current in zip(closes[-period - 1 : -1], closes[-period:]):
        delta = current - previous
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    average_gain = sum(gains) / period
    average_loss = sum(losses) / period
    if average_loss == 0:
        return 100.0
    rs = average_gain / average_loss
    return 100 - (100 / (1 + rs))


def relative_volume(candles: list[Candle], lookback: int = 100) -> float | None:
    """Return current candle volume divided by recent average volume."""

    if len(candles) < 2:
        return None
    previous = candles[-lookback - 1 : -1] if len(candles) > lookback else candles[:-1]
    average = sum(candle.volume for candle in previous) / len(previous)
    if average <= 0:
        return None
    return candles[-1].volume / average


def adx(candles: list[Candle], period: int = 14) -> tuple[float | None, float | None, float | None]:
    """Return (ADX, DI+, DI-) using Wilder's smoothing.

    Requires at least ``2 * period + 1`` candles. Returns ``(None, None, None)``
    when data is insufficient.
    """
    if len(candles) < 2 * period + 1:
        return None, None, None

    plus_dm: list[float] = []
    minus_dm: list[float] = []
    tr_list: list[float] = []

    for i in range(1, len(candles)):
        high_diff = candles[i].high - candles[i - 1].high
        low_diff = candles[i - 1].low - candles[i].low
        plus_dm.append(max(high_diff, 0.0) if high_diff > low_diff else 0.0)
        minus_dm.append(max(low_diff, 0.0) if low_diff > high_diff else 0.0)
        tr_list.append(
            max(
                candles[i].high - candles[i].low,
                abs(candles[i].high - candles[i - 1].close),
                abs(candles[i].low - candles[i - 1].close),
            )
        )

    smoothed_tr = sum(tr_list[:period])
    smoothed_plus = sum(plus_dm[:period])
    smoothed_minus = sum(minus_dm[:period])

    for i in range(period, len(tr_list)):
        smoothed_tr = smoothed_tr - smoothed_tr / period + tr_list[i]
        smoothed_plus = smoothed_plus - smoothed_plus / period + plus_dm[i]
        smoothed_minus = smoothed_minus - smoothed_minus / period + minus_dm[i]

    if smoothed_tr == 0:
        return None, None, None

    di_plus = 100.0 * smoothed_plus / smoothed_tr
    di_minus = 100.0 * smoothed_minus / smoothed_tr
    di_sum = di_plus + di_minus
    if di_sum == 0:
        return 0.0, di_plus, di_minus

    dx_list: list[float] = []
    s_tr = sum(tr_list[:period])
    s_plus = sum(plus_dm[:period])
    s_minus = sum(minus_dm[:period])
    for i in range(period, len(tr_list)):
        s_tr = s_tr - s_tr / period + tr_list[i]
        s_plus = s_plus - s_plus / period + plus_dm[i]
        s_minus = s_minus - s_minus / period + minus_dm[i]
        if s_tr == 0:
            continue
        dp = 100.0 * s_plus / s_tr
        dm = 100.0 * s_minus / s_tr
        ds = dp + dm
        if ds > 0:
            dx_list.append(100.0 * abs(dp - dm) / ds)

    if len(dx_list) < period:
        return None, None, None

    adx_value = sum(dx_list[:period]) / period
    for dx in dx_list[period:]:
        adx_value = (adx_value * (period - 1) + dx) / period

    return adx_value, di_plus, di_minus


def percentile_rank(values: list[float], current: float) -> float:
    """Return the percentile rank (0-100) of *current* within *values*."""
    if not values:
        return 0.0
    count_below = sum(1 for v in values if v < current)
    return count_below / len(values) * 100.0


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))
