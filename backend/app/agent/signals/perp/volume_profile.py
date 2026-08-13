"""Perpetual V1 rolling Volume Profile signal."""

from __future__ import annotations

from collections import defaultdict

from backend.app.agent.signals.base import SignalModule, SignalPayload, SignalResult
from backend.app.agent.signals.common.indicators import atr, atr_series, sanitize_candles, vwap
from backend.app.agent.signals.perp.binance_klines import BinanceKlineFeed
from backend.app.core.config import Settings, get_settings

# Periodo ATR usato esclusivamente per modulare la leva in apertura: a 5m sono
# ~6 ore di lookback, abbastanza liscio da leggere il regime di volatilità.
LEVERAGE_ATR_PERIOD = 72


class VolumeProfileSignal(SignalModule[SignalPayload, SignalResult]):
    """Build 24h Volume Profile and detect mean-reversion setups."""

    name = "perp_volume_profile_v1"

    def __init__(
        self,
        settings: Settings | None = None,
        feed: BinanceKlineFeed | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.feed = feed or BinanceKlineFeed(
            futures_base_url=self.settings.binance_futures_base_url,
            timeout_seconds=self.settings.market_data_request_timeout_seconds,
        )

    async def evaluate(self, payload: SignalPayload) -> SignalResult:
        candles = sanitize_candles(payload.get("candles", []))
        if not candles and payload.get("symbol"):
            candles = await self.feed.fetch(
                symbol=str(payload["symbol"]),
                interval=f"{self.settings.perp_volume_profile_candle_minutes}m",
                limit=int(self.settings.perp_volume_profile_window_hours * 60 / self.settings.perp_volume_profile_candle_minutes),
                market="futures",
            )
        window = int(self.settings.perp_volume_profile_window_hours * 60 / self.settings.perp_volume_profile_candle_minutes)
        candles = candles[-window:]
        if len(candles) < max(24, window // 4):
            return _skip(payload, "insufficient_binance_klines")
        total_quote_volume = sum(candle.close * candle.volume for candle in candles)
        if total_quote_volume < self.settings.perp_min_volume_profile_liquidity_usd:
            return _skip(payload, "volume_profile_liquidity_filter")

        profile = _build_profile(candles)
        poc, vah, val = _value_area(profile, self.settings.perp_value_area_pct / 100)
        current = candles[-1].close
        previous = candles[-2]
        current_vwap = vwap(candles)
        current_atr = atr(candles)
        trend_bias = "above_vwap" if current_vwap and current > current_vwap else "below_vwap"

        side: str | None = None
        trigger_price = current
        if previous.close < val and current > previous.high:
            side = "long"
        elif previous.close > vah and current < previous.low:
            side = "short"

        if side == "long" and current_vwap and current < current_vwap * 0.97:
            side = None
        if side == "short" and current_vwap and current > current_vwap * 1.03:
            side = None

        direction_allowed = self.settings.perp_direction_mode
        if side == "long" and direction_allowed == "short":
            side = None
        if side == "short" and direction_allowed == "long":
            side = None

        quality = _quality(side, current, poc, vah, val, current_vwap, current_atr)
        # SL/TP ancorati all'entry (current) via ATR: il R:R è controllato a
        # prescindere dalla leva. TP2 può promuoversi al POC (livello strutturale
        # di volume) quando è più ambizioso del target ATR. Se l'ATR non è
        # disponibile, fallback ai livelli di Volume Profile (previous.low/VAL).
        atr_v = current_atr if (current_atr and current_atr > 0) else None
        sl_mult = self.settings.perp_atr_stop_multiplier
        tp1_mult = self.settings.perp_tp1_atr_multiplier
        tp2_mult = self.settings.perp_tp2_atr_multiplier
        use_poc = self.settings.perp_use_poc_for_tp2
        stop_loss = None
        take_profit_1 = None
        take_profit_2 = None
        # Il trailing non viene più seminato all'apertura: lo gestisce il service
        # da subito (breakeven + trailing dinamico). Resta None → UI "non attivo".
        trailing_stop = None
        use_lowest = getattr(self.settings, "perp_sl_mode", "atr") == "lowest"
        lookback = max(2, int(getattr(self.settings, "perp_structural_stop_lookback_candles", 20)))
        buffer_pct = max(0.0, float(getattr(self.settings, "perp_structural_stop_buffer_pct", 1.10)))
        stop_reference = None
        if side == "long":
            if use_lowest:
                structural_window = candles[-lookback:]
                reference_candle = min(structural_window, key=lambda c: c.low)
                structural_low = reference_candle.low
                stop_loss = structural_low * (1 - buffer_pct / 100)
                stop_reference = {
                    "mode": "lowest",
                    "field": "low",
                    "timestamp": reference_candle.timestamp.isoformat(),
                    "price": structural_low,
                    "lookback_candles": lookback,
                    "buffer_pct": buffer_pct,
                }
            elif atr_v is not None:
                stop_loss = current - atr_v * sl_mult
            else:
                stop_loss = previous.low
            if atr_v is not None:
                take_profit_1 = current + atr_v * tp1_mult
                tp2_atr = current + atr_v * tp2_mult
                take_profit_2 = poc if (use_poc and poc > tp2_atr) else tp2_atr
            else:
                take_profit_1 = val
                take_profit_2 = poc
        elif side == "short":
            if use_lowest:
                structural_window = candles[-lookback:]
                reference_candle = max(structural_window, key=lambda c: c.high)
                structural_high = reference_candle.high
                stop_loss = structural_high * (1 + buffer_pct / 100)
                stop_reference = {
                    "mode": "lowest",
                    "field": "high",
                    "timestamp": reference_candle.timestamp.isoformat(),
                    "price": structural_high,
                    "lookback_candles": lookback,
                    "buffer_pct": buffer_pct,
                }
            elif atr_v is not None:
                stop_loss = current + atr_v * sl_mult
            else:
                stop_loss = previous.high
            if atr_v is not None:
                take_profit_1 = current - atr_v * tp1_mult
                tp2_atr = current - atr_v * tp2_mult
                take_profit_2 = poc if (use_poc and poc < tp2_atr) else tp2_atr
            else:
                take_profit_1 = vah
                take_profit_2 = poc

        # FIX-2: filtro R:R minimo sull'uscita primaria (TP1). Lo stop strutturale
        # (20 candele + buffer) puo' risultare piu' largo di TP1, producendo R:R
        # negativo sull'uscita che chiude il 70% della posizione. Sotto la soglia
        # il segnale viene scartato.
        rr_rejected = False
        min_rr = float(getattr(self.settings, "perp_min_rr", 0.0) or 0.0)
        if side and min_rr > 0 and stop_loss is not None and take_profit_1 is not None:
            risk_dist = abs(current - stop_loss)
            reward_dist = abs(take_profit_1 - current)
            if risk_dist <= 0 or (reward_dist / risk_dist) < min_rr:
                side = None
                rr_rejected = True

        # ATR corrente per la leva (periodo da config). atr_min/atr_max storici sono
        # calcolati nel service su un lookback più lungo; qui la leva è solo placeholder
        # (verrà sovrascritta in evaluate_perp con i mobile settings).
        lev_period = self.settings.perp_leverage_atr_period
        lev_atr = atr(candles, period=lev_period)
        lev_atr_window = atr_series(candles, period=lev_period)
        lev_atr_min = min(lev_atr_window) if lev_atr_window else None
        lev_atr_max = max(lev_atr_window) if lev_atr_window else None
        leverage = _atr_range_leverage(
            min_lev=self.settings.perp_min_leverage,
            max_lev=self.settings.perp_max_leverage,
            atr_value=lev_atr,
            atr_min=lev_atr_min,
            atr_max=lev_atr_max,
        )
        action = f"enter_{side}" if side and quality >= 0.6 else "skip"
        return {
            "signal_id": payload.get("signal_id"),
            "market": "perp",
            "asset": payload.get("asset") or payload.get("symbol"),
            "action": action,
            "side": side,
            "quality": round(quality, 4),
            "confidence": round(quality, 4),
            "price": trigger_price,
            "leverage": leverage,
            "stop_loss": stop_loss,
            "take_profit_1": take_profit_1,
            "take_profit_2": take_profit_2,
            "trailing_stop": trailing_stop,
            "reason": "value_reentry_confirmed" if side else ("rr_below_minimum" if rr_rejected else "perp_filters_not_satisfied"),
            "components": {
                "poc": poc,
                "vah": vah,
                "val": val,
                "vwap": current_vwap,
                "atr": current_atr,
                "atr_lev": lev_atr,
                "atr_lev_min": lev_atr_min,
                "atr_lev_max": lev_atr_max,
                "trend_bias": trend_bias,
                "total_quote_volume": round(total_quote_volume, 2),
                "value_area_pct": self.settings.perp_value_area_pct,
                "stop_reference": stop_reference,
            },
        }


def _build_profile(candles) -> dict[float, float]:
    high = max(candle.high for candle in candles)
    low = min(candle.low for candle in candles)
    tick = max((high - low) / 80, high * 0.0005)
    buckets: dict[float, float] = defaultdict(float)
    for candle in candles:
        typical = (candle.high + candle.low + candle.close) / 3
        bucket = round(round(typical / tick) * tick, 8)
        buckets[bucket] += candle.volume
    return dict(buckets)


def _value_area(profile: dict[float, float], area_pct: float) -> tuple[float, float, float]:
    ordered = sorted(profile.items())
    poc = max(ordered, key=lambda item: item[1])[0]
    total = sum(volume for _, volume in ordered)
    target = total * area_pct
    selected = {poc}
    selected_volume = profile[poc]
    while selected_volume < target and len(selected) < len(ordered):
        candidates = [(price, volume) for price, volume in ordered if price not in selected]
        next_price, next_volume = max(candidates, key=lambda item: item[1])
        selected.add(next_price)
        selected_volume += next_volume
    return poc, max(selected), min(selected)


def _quality(side: str | None, price: float, poc: float, vah: float, val: float, current_vwap: float | None, current_atr: float | None) -> float:
    if side is None:
        return 0.0
    distance_to_poc = abs(price - poc) / price if price > 0 else 1.0
    map_score = max(0.0, 1.0 - distance_to_poc * 10)
    trend_score = 0.6
    if current_vwap:
        if side == "long" and price >= current_vwap:
            trend_score = 0.8
        elif side == "short" and price <= current_vwap:
            trend_score = 0.8
    atr_score = 0.7 if current_atr and current_atr > 0 else 0.4
    value_edge = 0.8 if (side == "long" and price <= poc) or (side == "short" and price >= poc) else 0.55
    return min(1.0, map_score * 0.35 + trend_score * 0.25 + atr_score * 0.15 + value_edge * 0.25)


def _atr_range_leverage(
    *,
    min_lev: int,
    max_lev: int,
    atr_value: float | None,
    atr_min: float | None,
    atr_max: float | None,
) -> int:
    """Leva inversamente proporzionale alla volatilità ATR(72), in apertura del trade.

    - Bassa volatilità (ATR ~ minimo storico)  → leva massima del range.
    - Alta volatilità (ATR ~ massimo storico)   → leva minima del range.
    - Filtro anomalia: ATR corrente oltre il massimo storico → leva minima forzata.
    - Dati insufficienti / volatilità nulla     → leva minima (conservativo).
    """
    lo = max(1, min(min_lev, max_lev))
    hi = max(1, max(min_lev, max_lev))
    if atr_value is None or atr_min is None or atr_max is None:
        return lo
    # Volatilità anomala: oltre il massimo storico → massima prudenza.
    if atr_value > atr_max:
        return lo
    if atr_max <= atr_min:
        # Volatilità piatta nella finestra: nessuna penalità → leva massima.
        return hi
    frac = (atr_value - atr_min) / (atr_max - atr_min)
    frac = min(1.0, max(0.0, frac))
    leverage = hi - frac * (hi - lo)
    return max(lo, min(hi, int(round(leverage))))


def _skip(payload: SignalPayload, reason: str) -> SignalResult:
    return {
        "signal_id": payload.get("signal_id"),
        "market": "perp",
        "asset": payload.get("asset") or payload.get("symbol"),
        "action": "skip",
        "quality": 0.0,
        "reason": reason,
        "components": {},
    }
