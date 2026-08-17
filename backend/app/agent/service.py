"""Autonomous agent orchestration for Step 6."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from functools import lru_cache
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.brain import ClaudeMetaController, MetaControllerError
from backend.app.agent.heartbeat import heartbeat
from backend.app.agent.risk import KillSwitchState, RiskDecision, RiskManager, SignalIntent
from backend.app.agent.signals.perp.binance_klines import BinanceKlineFeed, BinanceMarket, get_kline_cache_entry
from backend.app.agent.signals.perp.volume_profile import VolumeProfileSignal, _atr_range_leverage as _perp_atr_range_leverage
from backend.app.agent.signals.spot.momentum import MIN_SPOT_CANDLES, SpotMomentumSignal
from backend.app.agent.watchlist import selected_watchlist, selected_spot_watchlist, selected_perp_watchlist
from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import get_logger
from backend.app.data.market_data.cmc import CMCProvider
from backend.app.execution.models import ExecutionStatus
from backend.app.execution.perp_base import PerpOrder
from backend.app.execution.perp_registry import PerpExecutionRegistry, get_perp_execution_registry
from backend.app.execution.registry import ExecutionProviderRegistry, get_execution_provider_registry
from backend.app.notifications.agent_notifier import get_agent_notifier
from backend.app.persistence.database import get_session_factory
from backend.app.persistence.models.decisions import AgentDecision
from backend.app.persistence.models.pnl import PnlSnapshot
from backend.app.persistence.models.positions import PerpPosition, SpotPosition
from backend.app.persistence.models.trades import PerpTrade, SpotTrade
from backend.app.persistence.repositories.api_usage import ApiUsageRepository
from backend.app.persistence.repositories.decisions import AgentDecisionRepository
from backend.app.persistence.repositories.pnl import PnlRepository
from backend.app.persistence.repositories.positions import PerpPositionRepository, SpotPositionRepository
from backend.app.persistence.models.trade_charts import TradeChartSnapshot
from backend.app.persistence.repositories.trade_charts import TradeChartRepository
from backend.app.persistence.repositories.trades import PerpTradeRepository, SpotTradeRepository
from backend.app.persistence.runtime_state import get_runtime_value, set_runtime_value
from backend.app.schemas.mobile_agent import AgentMobileSettings
from backend.app.execution.perp_fees import fetch_perp_fees, compute_opening_costs, accrue_funding
from backend.app.agent.signals.common.indicators import adx as calc_adx, atr_series, ema, percentile_rank, relative_volume as calc_relative_volume
from backend.app.execution.spot_fees import compute_spot_costs

logger = get_logger("agent.service")

DAILY_TRADE_CHECK_TIME_UTC = time(20, 0, tzinfo=UTC)
DAILY_TRADE_RETRY_UNTIL_UTC = time(23, 30, tzinfo=UTC)
# Stablecoin: niente scansione spot (volatilita' ~0, nessun segnale sensato).
SPOT_EXCLUDED_STABLECOINS = frozenset(
    {"USDT", "USDC", "DAI", "USD1", "TUSD", "FDUSD", "BUSD", "USDP", "USDD", "GUSD", "PYUSD"}
)
HEARTBEAT_TRADE_ASSET = "ETH"
HEARTBEAT_TRADE_PRICE_USD_FALLBACK = Decimal("1")
# Distanza trailing-stop per il perp (coerente col livello generato dal segnale, 1%).
PERP_TRAILING_DISTANCE_PCT = Decimal("1.0")
# TTL cache del regime mercato (BTC 15m): evita un fetch BTC per ogni asset dello scan.
SPOT_REGIME_CACHE_TTL_SECONDS = 90
# TTL cache del filtro BTC trend-shock: un solo fetch per ciclo di scan.
BTC_TREND_SHOCK_CACHE_TTL_SECONDS = 90
# Candele BTC richieste per ADX/NATR (15m) e volume (5m).
BTC_TREND_SHOCK_15M_BARS = 96
BTC_TREND_SHOCK_5M_VOL_LOOKBACK = 50
# Sentinel per la lazy-init del resolver token (distingue "non inizializzato" da "None").
_UNSET = object()


def _estimate_liquidation_price(entry: Decimal, leverage: int, side: str) -> Decimal | None:
    """Stima il prezzo di liquidazione (cross, senza maintenance margin).

    long: entry * (1 - 1/leva); short: entry * (1 + 1/leva).
    """
    if leverage <= 0 or entry <= 0:
        return None
    frac = Decimal(1) / Decimal(leverage)
    liq = entry * (Decimal(1) - frac) if side == "long" else entry * (Decimal(1) + frac)
    return liq.quantize(Decimal("0.00000001"))


def _auto_chart_interval(duration_min: int) -> tuple[str, int]:
    """Intervallo candele in base alla durata del trade -> (interval, minuti per candela)."""
    if duration_min <= 6 * 60:
        return "5m", 5
    if duration_min <= 2 * 24 * 60:
        return "1h", 60
    if duration_min <= 30 * 24 * 60:
        return "4h", 240
    return "1d", 1440


class AgentService:
    """Coordinates signals, risk, brain and execution providers."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        spot_signal: SpotMomentumSignal | None = None,
        perp_signal: VolumeProfileSignal | None = None,
        risk_manager: RiskManager | None = None,
        brain: ClaudeMetaController | None = None,
        spot_registry: ExecutionProviderRegistry | None = None,
        perp_registry: PerpExecutionRegistry | None = None,
        token_resolver: CMCProvider | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.spot_signal = spot_signal or SpotMomentumSignal(self.settings)
        self.perp_signal = perp_signal or VolumeProfileSignal(self.settings)
        self.risk = risk_manager or RiskManager(self.settings)
        self.brain = brain or ClaudeMetaController(self.settings)
        self.spot_registry = spot_registry or get_execution_provider_registry()
        self.perp_registry = perp_registry or get_perp_execution_registry()
        # Feed riusato per il refresh prezzi delle posizioni aperte (no nuova istanza a ogni tick).
        self.price_feed = BinanceKlineFeed(
            timeout_seconds=self.settings.market_data_request_timeout_seconds
        )
        # Resolver indirizzi token (CMC) per lo spot live; lazy, usato solo se serve.
        self._token_resolver_override = token_resolver
        self._token_resolver_cached: CMCProvider | None | object = _UNSET

    @property
    def _ms(self) -> AgentMobileSettings:
        """Mobile-overridable settings: reads from RuntimeState, falls back to config."""
        raw = get_runtime_value(str(self.settings.default_user_id), "mobile_agent_settings")
        if raw:
            try:
                return AgentMobileSettings.model_validate_json(raw)
            except ValueError:
                pass
        cap = self.settings.risk_capital_per_trade_pct
        slippage = self.settings.risk_max_slippage_pct
        cooldown = self.settings.risk_cooldown_minutes
        max_open = self.settings.risk_max_open_positions
        exposure = self.settings.risk_max_total_exposure_pct
        return AgentMobileSettings(
            mode=self.settings.agent_mode,
            markets_enabled=self.settings.markets_enabled,
            execution_mode=self.settings.execution_mode,
            network=self.settings.bsc_network,
            test_scaling_pct=self.settings.test_scaling_pct,
            operating_hours_utc=self.settings.operating_hours_utc,
            daily_loss_limit_pct=self.settings.risk_daily_loss_limit_pct,
            drawdown_cap_pct=self.settings.risk_max_drawdown_pct,
            min_pool_liquidity_usd=self.settings.risk_min_pool_liquidity_usd,
            # Parametri spot
            spot_capital_per_trade_pct=cap,
            spot_per_trade_pct=self.settings.risk_per_trade_pct,
            spot_max_open_positions=max_open,
            spot_max_exposure_pct=exposure,
            spot_cooldown_minutes=cooldown,
            spot_max_slippage_pct=slippage,
            # Parametri perp
            perp_capital_per_trade_pct=cap,
            perp_per_trade_pct=self.settings.risk_per_trade_pct,
            perp_max_open_positions=max_open,
            perp_max_exposure_pct=exposure,
            perp_cooldown_minutes=cooldown,
            perp_max_slippage_pct=slippage,
            perp_fixed_margin_enabled=False,
            perp_fixed_margin_usd=50.0,
            spot_time_stop_enabled=getattr(self.settings, "spot_time_stop_enabled", False),
            perp_time_stop_enabled=getattr(self.settings, "perp_time_stop_enabled", False),
            perp_trend_shock_enabled=getattr(self.settings, "perp_trend_shock_enabled", True),
            perp_trend_shock_adx_threshold=getattr(self.settings, "perp_trend_shock_adx_threshold", 25.0),
            perp_trend_shock_natr_percentile=getattr(self.settings, "perp_trend_shock_natr_percentile", 90.0),
            perp_trend_shock_volume_threshold=getattr(self.settings, "perp_trend_shock_volume_threshold", 2.0),
            perp_trend_shock_recovery_confirmations=getattr(self.settings, "perp_trend_shock_recovery_confirmations", 3),
            perp_smart_sl_enabled=getattr(self.settings, "perp_smart_sl_enabled", True),
            perp_smart_sl_l1_frac=getattr(self.settings, "perp_smart_sl_l1_frac", 0.333),
            perp_smart_sl_l2_frac=getattr(self.settings, "perp_smart_sl_l2_frac", 0.666),
            perp_smart_sl_split_l1=getattr(self.settings, "perp_smart_sl_split_l1", 0.25),
            perp_smart_sl_split_l2=getattr(self.settings, "perp_smart_sl_split_l2", 0.55),
            perp_smart_sl_split_l3=getattr(self.settings, "perp_smart_sl_split_l3", 0.20),
            perp_smart_sl_rebuy_mode=getattr(self.settings, "perp_smart_sl_rebuy_mode", "above_entry"),
            perp_smart_sl_rebuy_above_entry_pct=getattr(self.settings, "perp_smart_sl_rebuy_above_entry_pct", 100.0),
            perp_smart_sl_tp_adjust_after_rebuy=getattr(self.settings, "perp_smart_sl_tp_adjust_after_rebuy", True),
            perp_smart_sl_tp_recovery_delta_pct=getattr(self.settings, "perp_smart_sl_tp_recovery_delta_pct", 7.0),
            perp_smart_sl_split_l1_r2=getattr(self.settings, "perp_smart_sl_split_l1_r2", 0.75),
            perp_smart_sl_split_l2_r2=getattr(self.settings, "perp_smart_sl_split_l2_r2", 0.20),
            perp_smart_sl_split_l3_r2=getattr(self.settings, "perp_smart_sl_split_l3_r2", 0.05),
            perp_smart_sl_delta_l1=getattr(self.settings, "perp_smart_sl_delta_l1", 0.08),
            perp_smart_sl_delta_l2=getattr(self.settings, "perp_smart_sl_delta_l2", 0.16),
            perp_smart_sl_confirmation_candles=getattr(self.settings, "perp_smart_sl_confirmation_candles", 2),
            perp_smart_sl_max_reentries=getattr(self.settings, "perp_smart_sl_max_reentries", 1),
            # Legacy (backward compat)
            capital_per_trade_pct=cap,
            per_trade_pct=self.settings.risk_per_trade_pct,
            max_open_positions=max_open,
            max_total_exposure_pct=exposure,
            max_slippage_pct=slippage,
            cooldown_minutes=cooldown,
            # Spot strategy
            spot_confidence_threshold=self.settings.spot_confidence_threshold,
            spot_volatility_trigger_pct=self.settings.spot_volatility_trigger_pct,
            spot_relative_volume_threshold=self.settings.spot_relative_volume_threshold,
            spot_sl_mode=getattr(self.settings, "spot_sl_mode", "atr"),
            spot_structural_stop_lookback_candles=getattr(self.settings, "spot_structural_stop_lookback_candles", 20),
            spot_structural_stop_buffer_pct=getattr(self.settings, "spot_structural_stop_buffer_pct", 1.10),
            spot_atr_stop_multiplier=self.settings.spot_atr_stop_multiplier,
            spot_trailing_distance_pct=self.settings.spot_trailing_distance_pct,
            spot_partial_take_profit_pct=self.settings.spot_partial_take_profit_pct,
            spot_tp1_close_pct=50.0,
            spot_time_stop_hours=self.settings.spot_time_stop_hours,
            spot_fee_mode="all",
            # Perp strategy
            perp_direction_mode=self.settings.perp_direction_mode,
            perp_min_leverage=self.settings.perp_min_leverage,
            perp_max_leverage=self.settings.perp_max_leverage,
            perp_value_area_pct=self.settings.perp_value_area_pct,
            perp_sl_mode=getattr(self.settings, "perp_sl_mode", "atr"),
            perp_structural_stop_lookback_candles=getattr(self.settings, "perp_structural_stop_lookback_candles", 20),
            perp_structural_stop_buffer_pct=getattr(self.settings, "perp_structural_stop_buffer_pct", 1.10),
            perp_atr_stop_multiplier=self.settings.perp_atr_stop_multiplier,
            perp_trailing_mode=self.settings.perp_trailing_mode,
            perp_trailing_pnl_pct=0.0,
            perp_tp1_close_pct=70.0,
            perp_profit_lock_steps=getattr(
                self.settings, "perp_profit_lock_steps", [(0.50, 0.25), (0.70, 0.50), (0.95, 0.80)]
            ),
            perp_ratchet_breakeven_pct=getattr(self.settings, "perp_ratchet_breakeven_pct", 50.0),
            perp_ratchet_breakeven_after_step=getattr(self.settings, "perp_ratchet_breakeven_after_step", 3),
            perp_ratchet_run_beyond_tp2=getattr(self.settings, "perp_ratchet_run_beyond_tp2", True),
            perp_ratchet_trailing_pct=getattr(self.settings, "perp_ratchet_trailing_pct", 1.0),
            perp_time_stop_hours=self.settings.perp_time_stop_hours,
            post_close_candles=10,
        )

    def status(self) -> dict:
        return {
            "mode": self._ms.mode,
            "markets_enabled": self._ms.markets_enabled,
            "execution_mode": self._ms.execution_mode,
            "kill_switch": self.risk.kill_switch.value,
            "degraded_reasons": sorted(self.risk.degraded_reasons),
            "eligible_token_count": len(self.settings.eligible_tokens),
            "eligible_symbol_count": len(self.risk.eligible_symbols),
            "watchlist_count": len(selected_watchlist(self.settings)),
            "watchlist_spot_count": len(selected_spot_watchlist(self.settings)),
            "watchlist_perp_count": len(selected_perp_watchlist(self.settings)),
            "heartbeat": heartbeat.as_dict(),
        }

    def data_coverage(self) -> dict:
        """Return signal-engine OHLCV cache coverage for eligible active assets."""

        markets = _active_markets(self._ms.markets_enabled)
        items = []
        now = datetime.now(UTC)
        selected_assets = selected_watchlist(self.settings)
        for asset in selected_assets:
            if "spot" in markets:
                items.append(
                    _coverage_item(
                        asset=asset,
                        market="spot",
                        symbol=f"{asset.upper()}USDT",
                        required_candles=MIN_SPOT_CANDLES,
                        source="Binance klines 5m",
                        cache_market="spot",
                        now=now,
                    )
                )
            if "perp" in markets:
                interval = f"{self.settings.perp_volume_profile_candle_minutes}m"
                window = int(
                    self.settings.perp_volume_profile_window_hours
                    * 60
                    / self.settings.perp_volume_profile_candle_minutes
                )
                items.append(
                    _coverage_item(
                        asset=asset,
                        market="perp",
                        symbol=f"{asset.upper()}USDT",
                        required_candles=max(24, window // 4),
                        source="Binance klines 5m",
                        cache_market="futures",
                        now=now,
                        interval=interval,
                    )
                )
        return {
            "generated_at": now.isoformat(),
            "active_markets": sorted(markets),
            "selected_assets": selected_assets,
            "items": items,
        }

    def set_kill_switch(self, state: KillSwitchState) -> dict:
        self.risk.set_kill_switch(state)
        return self.status()

    async def close_all_and_pause(self, session: AsyncSession, *, reason: str = "manual_risk") -> dict:
        """Chiude TUTTE le posizioni aperte (spot + perp) al prezzo di mercato e
        mette l'agente in pausa (hard_stop). Usato dal pulsante Risk dell'app.

        La pausa blocca qualsiasi nuova entrata finche' non si riprende con
        ``set_kill_switch(RUNNING)``. Best-effort sul prezzo: se il feed non
        risponde si usa l'ultimo ``current_price`` memorizzato.
        """
        user_id = str(self.settings.default_user_id)
        spot_positions = await SpotPositionRepository(session).open_for_user(user_id)
        perp_positions = await PerpPositionRepository(session).open_for_user(user_id)
        now = datetime.now(UTC)

        if spot_positions or perp_positions:
            try:
                await self._refresh_position_prices(session, spot_positions, perp_positions)
            except Exception:
                pass

        closed_spot = 0
        for pos in spot_positions:
            if pos.status != "open":
                continue
            await self._close_spot_position(session, pos, pos.current_price, reason, now)
            closed_spot += 1

        closed_perp = 0
        for pos in perp_positions:
            if pos.status != "open":
                continue
            await self._close_perp_position(session, pos, pos.current_price, reason, now)
            closed_perp += 1

        # Pausa l'agente: nessuna nuova entrata fino al resume.
        self.risk.set_kill_switch(KillSwitchState.HARD_STOP)
        await self._update_portfolio_state(session, [], [], now)
        await session.commit()

        logger.info(
            "risk_close_all_and_pause",
            closed_spot=closed_spot, closed_perp=closed_perp, reason=reason,
        )
        return {
            "closed_spot": closed_spot,
            "closed_perp": closed_perp,
            **self.status(),
        }

    async def evaluate_spot(self, payload: dict, session: AsyncSession) -> dict:
        signal = await self.spot_signal.evaluate(payload)
        # Filtro regime mercato: blocca i nuovi ingressi spot in downtrend forte di BTC.
        if signal.get("action") == "enter_long":
            regime = await self._spot_market_regime()
            if regime.get("risk_off"):
                signal["action"] = "skip"
                signal["reason"] = "market_risk_off"
                signal.setdefault("components", {})["market_regime"] = regime
            elif self.settings.market_reversal_filter_enabled:
                reversal = await self._market_reversal_filter()
                signal.setdefault("components", {})["market_reversal"] = reversal
                if not reversal.get("risk_on"):
                    signal["action"] = "skip"
                    signal["reason"] = "market_reversal_waiting"
        return await self._handle_signal(signal, session)

    async def _spot_market_regime(self) -> dict:
        """Regime di mercato su BTC (15m), con isteresi e cache per ciclo.

        Blocca i nuovi buy spot quando BTC è sotto la EMA50 E sta facendo nuovi
        minimi (downtrend forte). Una volta in blocco ci resta finché BTC non
        richiude SOPRA la EMA50 (macchina a stati → niente flip-flop). In caso di
        dati insufficienti non blocca (fail-open).
        """
        if not self.settings.spot_market_regime_filter_enabled:
            return {"risk_off": False, "enabled": False}

        now = datetime.now(UTC)
        cached = getattr(self, "_regime_cache", None)
        if cached and (now - cached["at"]).total_seconds() < SPOT_REGIME_CACHE_TTL_SECONDS:
            return cached["value"]

        period = self.settings.spot_market_regime_ema_period
        lookback = self.settings.spot_market_regime_low_lookback
        try:
            candles = await self.price_feed.fetch(
                symbol=self.settings.spot_market_regime_symbol,
                interval=self.settings.spot_market_regime_interval,
                limit=max(period + 5, lookback + 5),
                market="spot",
            )
        except Exception:
            candles = []

        if len(candles) < max(period + 1, lookback):
            value = {"risk_off": False, "enabled": True, "reason": "insufficient_btc_klines"}
            self._regime_cache = {"at": now, "value": value}
            return value

        closes = [c.close for c in candles]
        ema_value = ema(closes, period)
        btc_close = closes[-1]
        above_ema = ema_value is not None and btc_close > ema_value
        new_low = candles[-1].low <= min(c.low for c in candles[-lookback:])

        prev_off = self._regime_risk_off_persisted()
        if prev_off:
            risk_off = not above_ema            # esce SOLO quando BTC torna sopra la EMA50
        else:
            risk_off = (not above_ema) and new_low  # entra: sotto media E nuovo minimo
        if risk_off != prev_off:
            self._set_regime_persisted(risk_off)

        value = {
            "risk_off": risk_off,
            "enabled": True,
            "btc_price": float(btc_close),
            "ema": float(ema_value) if ema_value is not None else None,
            "above_ema": above_ema,
            "new_low": new_low,
            "reason": "btc_downtrend_new_lows" if risk_off else "ok",
        }
        self._regime_cache = {"at": now, "value": value}
        return value

    def _regime_risk_off_persisted(self) -> bool:
        raw = get_runtime_value(str(self.settings.default_user_id), "spot_market_regime")
        if not raw:
            return False
        try:
            return bool(json.loads(raw).get("risk_off", False))
        except (ValueError, AttributeError):
            return False

    def _set_regime_persisted(self, risk_off: bool) -> None:
        set_runtime_value(
            str(self.settings.default_user_id),
            "spot_market_regime",
            json.dumps({"risk_off": risk_off, "updated_at": datetime.now(UTC).isoformat()}),
        )

    async def _market_reversal_filter(self) -> dict:
        """BTC 15m reversal confirmation used only as an entry filter.

        It never clears other blockers: Spot uses it only after a long signal is
        already present and market_risk_off is false; Perp uses it only to block
        shorts against confirmed BTC recovery.
        """
        if not self.settings.market_reversal_filter_enabled:
            return {"enabled": False, "risk_on": False}

        now = datetime.now(UTC)
        cached = getattr(self, "_market_reversal_cache", None)
        if cached and (now - cached["at"]).total_seconds() < SPOT_REGIME_CACHE_TTL_SECONDS:
            return cached["value"]

        period = max(1, int(self.settings.market_reversal_ema_period))
        confirmations = max(1, int(self.settings.market_reversal_confirmation_candles))
        limit = max(period + confirmations + 3, period + 5)
        try:
            candles = await self.price_feed.fetch(
                symbol=self.settings.market_reversal_symbol,
                interval=self.settings.market_reversal_interval,
                limit=limit,
                market="spot",
            )
        except Exception:
            candles = []

        if len(candles) < period + confirmations + 1:
            value = {"enabled": True, "risk_on": False, "reason": "insufficient_btc_reversal_klines"}
            self._market_reversal_cache = {"at": now, "value": value}
            return value

        closes = [c.close for c in candles]
        ema_now = ema(closes, period)
        ema_prev = ema(closes[:-1], period)
        latest_close = closes[-1]
        green_confirmed = all(c.close > c.open for c in candles[-confirmations:])
        red_confirmed = all(c.close < c.open for c in candles[-confirmations:])
        above_ema = ema_now is not None and latest_close > ema_now
        below_ema = ema_now is not None and latest_close < ema_now
        ema_rising = ema_now is not None and ema_prev is not None and ema_now > ema_prev
        bullish_entry = bool(green_confirmed and above_ema and ema_rising)
        bearish_entry = bool(red_confirmed and below_ema)
        previous_state = self._market_reversal_state_persisted()
        if previous_state == "bullish":
            state = "bearish" if bearish_entry else "bullish"
        elif previous_state == "bearish":
            state = "bullish" if bullish_entry else "bearish"
        elif bullish_entry:
            state = "bullish"
        elif bearish_entry:
            state = "bearish"
        else:
            state = "neutral"
        if state != previous_state:
            self._set_market_reversal_persisted(state)
        risk_on = state == "bullish"
        risk_off = state == "bearish"
        value = {
            "enabled": True,
            "risk_on": risk_on,
            "risk_off": risk_off,
            "state": state,
            "previous_state": previous_state,
            "symbol": self.settings.market_reversal_symbol,
            "interval": self.settings.market_reversal_interval,
            "confirmation_candles": confirmations,
            "btc_price": float(latest_close),
            "ema": float(ema_now) if ema_now is not None else None,
            "ema_rising": ema_rising,
            "green_confirmed": green_confirmed,
            "red_confirmed": red_confirmed,
            "above_ema": above_ema,
            "below_ema": below_ema,
            "bullish_entry": bullish_entry,
            "bearish_entry": bearish_entry,
            "reason": (
                "btc_reversal_confirmed"
                if state == "bullish" and previous_state != "bullish"
                else "btc_reversal_active"
                if state == "bullish"
                else "btc_reversal_bearish_confirmed"
                if state == "bearish" and previous_state != "bearish"
                else "btc_reversal_bearish_active"
                if state == "bearish"
                else "btc_reversal_waiting"
            ),
        }
        self._market_reversal_cache = {"at": now, "value": value}
        return value

    def _market_reversal_state_persisted(self) -> str:
        raw = get_runtime_value(str(self.settings.default_user_id), "market_reversal_filter")
        if not raw:
            return "neutral"
        try:
            payload = json.loads(raw)
            state = str(payload.get("state") or "").strip().lower()
            if state in {"bullish", "bearish", "neutral"}:
                return state
            if payload.get("risk_on") is True:
                return "bullish"
            if payload.get("risk_off") is True:
                return "bearish"
            return "neutral"
        except (ValueError, AttributeError):
            return "neutral"

    def _set_market_reversal_persisted(self, state: str) -> None:
        set_runtime_value(
            str(self.settings.default_user_id),
            "market_reversal_filter",
            json.dumps(
                {
                    "state": state,
                    "risk_on": state == "bullish",
                    "risk_off": state == "bearish",
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ),
        )

    # ── BTC Global Market Regime Filter (trend-shock) ───────────────────

    async def _btc_trend_shock_filter(self) -> dict:
        """Filtro globale BTC: blocca nuove aperture perp quando BTC mostra
        trend forte + volatilita' o volume anomali (score >= 2 su 3).

        Tre stati: NORMAL / BLOCKED / RECOVERING.
        Recovery: 3 check consecutivi con score <= 1 per tornare NORMAL.
        Fail-open: dati insufficienti -> NORMAL.
        """
        ms = self._ms
        if not ms.perp_trend_shock_enabled:
            return {"state": "DISABLED", "enabled": False}

        now = datetime.now(UTC)
        cached = getattr(self, "_trend_shock_cache", None)
        if cached and (now - cached["at"]).total_seconds() < BTC_TREND_SHOCK_CACHE_TTL_SECONDS:
            return cached["value"]

        adx_threshold = ms.perp_trend_shock_adx_threshold
        natr_pct_threshold = ms.perp_trend_shock_natr_percentile
        vol_threshold = ms.perp_trend_shock_volume_threshold
        recovery_needed = max(1, ms.perp_trend_shock_recovery_confirmations)

        try:
            candles_15m = await self.price_feed.fetch(
                symbol="BTCUSDT", interval="15m",
                limit=BTC_TREND_SHOCK_15M_BARS + 30, market="spot",
            )
        except Exception:
            candles_15m = []

        try:
            candles_5m = await self.price_feed.fetch(
                symbol="BTCUSDT", interval="5m",
                limit=BTC_TREND_SHOCK_5M_VOL_LOOKBACK + 5, market="spot",
            )
        except Exception:
            candles_5m = []

        if len(candles_15m) < 30 or len(candles_5m) < 10:
            value = {"state": "NORMAL", "enabled": True, "reason": "insufficient_btc_data"}
            self._trend_shock_cache = {"at": now, "value": value}
            return value

        adx_value, di_plus, di_minus = calc_adx(candles_15m, period=14)

        atr_vals = atr_series(candles_15m, period=14)
        closes_15m = [c.close for c in candles_15m]
        natr_vals = [
            atr_vals[i] / closes_15m[i + 14] * 100 if closes_15m[i + 14] > 0 else 0.0
            for i in range(len(atr_vals))
        ] if atr_vals and len(closes_15m) > 14 else []
        natr_current = natr_vals[-1] if natr_vals else None
        natr_history = natr_vals[-BTC_TREND_SHOCK_15M_BARS:] if natr_vals else []
        natr_pct = percentile_rank(natr_history[:-1], natr_current) if natr_current is not None and len(natr_history) > 1 else None

        rel_vol = calc_relative_volume(candles_5m, lookback=BTC_TREND_SHOCK_5M_VOL_LOOKBACK)

        score = 0
        adx_triggered = adx_value is not None and adx_value >= adx_threshold
        natr_triggered = natr_pct is not None and natr_pct >= natr_pct_threshold
        vol_triggered = rel_vol is not None and rel_vol >= vol_threshold

        if adx_triggered:
            score += 1
        if natr_triggered:
            score += 1
        if vol_triggered:
            score += 1

        direction = None
        if adx_value is not None and di_plus is not None and di_minus is not None:
            if di_plus > di_minus:
                direction = "bullish"
            elif di_minus > di_plus:
                direction = "bearish"

        prev_state = self._trend_shock_state_persisted()
        prev_rc = self._trend_shock_recovery_count()

        if score >= 2:
            new_state = "BLOCKED"
            new_rc = 0
        elif prev_state == "BLOCKED":
            new_state = "RECOVERING"
            new_rc = 1
        elif prev_state == "RECOVERING":
            new_rc = prev_rc + 1
            if new_rc >= recovery_needed:
                new_state = "NORMAL"
                new_rc = 0
            else:
                new_state = "RECOVERING"
        else:
            new_state = "NORMAL"
            new_rc = 0

        if new_state != prev_state or new_rc != prev_rc:
            self._set_trend_shock_persisted(new_state, new_rc)

        value = {
            "state": new_state,
            "enabled": True,
            "score": score,
            "adx": round(adx_value, 2) if adx_value is not None else None,
            "di_plus": round(di_plus, 2) if di_plus is not None else None,
            "di_minus": round(di_minus, 2) if di_minus is not None else None,
            "direction": direction,
            "natr": round(natr_current, 4) if natr_current is not None else None,
            "natr_percentile": round(natr_pct, 1) if natr_pct is not None else None,
            "relative_volume": round(rel_vol, 2) if rel_vol is not None else None,
            "adx_triggered": adx_triggered,
            "natr_triggered": natr_triggered,
            "vol_triggered": vol_triggered,
            "reason": (
                "btc_trend_shock" if new_state == "BLOCKED"
                else "btc_trend_shock_recovering" if new_state == "RECOVERING"
                else "ok"
            ),
        }

        if new_state == "BLOCKED" and prev_state != "BLOCKED":
            logger.info(
                "btc_global_regime_filter_blocked",
                adx=value["adx"], di_plus=value["di_plus"], di_minus=value["di_minus"],
                direction=direction, natr_percentile=value["natr_percentile"],
                relative_volume=value["relative_volume"], score=score,
            )
        elif new_state == "NORMAL" and prev_state in ("BLOCKED", "RECOVERING"):
            logger.info(
                "btc_global_regime_filter_recovered",
                adx=value["adx"], natr_percentile=value["natr_percentile"],
                relative_volume=value["relative_volume"],
            )

        self._trend_shock_cache = {"at": now, "value": value}
        return value

    def _trend_shock_state_persisted(self) -> str:
        raw = get_runtime_value(str(self.settings.default_user_id), "btc_trend_shock")
        if not raw:
            return "NORMAL"
        try:
            return json.loads(raw).get("state", "NORMAL")
        except (ValueError, AttributeError):
            return "NORMAL"

    def _trend_shock_recovery_count(self) -> int:
        raw = get_runtime_value(str(self.settings.default_user_id), "btc_trend_shock")
        if not raw:
            return 0
        try:
            return int(json.loads(raw).get("recovery_count", 0))
        except (ValueError, AttributeError):
            return 0

    def _set_trend_shock_persisted(self, state: str, recovery_count: int = 0) -> None:
        set_runtime_value(
            str(self.settings.default_user_id),
            "btc_trend_shock",
            json.dumps({
                "state": state,
                "recovery_count": recovery_count,
                "updated_at": datetime.now(UTC).isoformat(),
            }),
        )

    async def evaluate_perp(self, payload: dict, session: AsyncSession) -> dict:
        signal = await self.perp_signal.evaluate(payload)
        if (
            signal.get("action") != "skip"
            and signal.get("side") == "short"
            and self.settings.market_reversal_filter_enabled
        ):
            reversal = await self._market_reversal_filter()
            signal.setdefault("components", {})["market_reversal"] = reversal
            if reversal.get("risk_on"):
                signal["action"] = "skip"
                signal["reason"] = "market_reversal_short_blocked"
        if (
            signal.get("action") != "skip"
            and signal.get("side") == "long"
            and self.settings.market_reversal_filter_enabled
        ):
            reversal = await self._market_reversal_filter()
            signal.setdefault("components", {})["market_reversal"] = reversal
            if reversal.get("risk_off"):
                signal["action"] = "skip"
                signal["reason"] = "market_reversal_long_blocked"
        # Filtro shock BTC perp: blocca tutte le nuove aperture quando BTC è in regime anomalo.
        if signal.get("action") != "skip":
            trend_shock = await self._btc_trend_shock_filter()
            signal.setdefault("components", {})["btc_trend_shock"] = trend_shock
            if trend_shock.get("state") == "BLOCKED":
                logger.info(
                    "perp_entry_rejected",
                    asset=signal.get("asset"), candidate_side=signal.get("side"),
                    reason="btc_trend_shock_blocked",
                    score=trend_shock.get("score"),
                    adx=trend_shock.get("adx"),
                    natr_percentile=trend_shock.get("natr_percentile"),
                    relative_volume=trend_shock.get("relative_volume"),
                    entry_price=signal.get("price"),
                    stop_loss=signal.get("stop_loss"),
                    take_profit_1=signal.get("take_profit_1"),
                    take_profit_2=signal.get("take_profit_2"),
                    quality=signal.get("quality"),
                    leverage=signal.get("leverage"),
                )
                signal["action"] = "skip"
                signal["reason"] = "btc_trend_shock_blocked"
        # Il segnale embeds la leva calcolata con il config YAML statico.
        # La sovrascriviamo con i mobile settings (RuntimeState) per rispettare
        # la leva impostata dall'utente nell'app.
        if signal.get("action") != "skip":
            ms = self._ms
            components = signal.get("components") or {}
            atr_now = components.get("atr_lev")
            # Baseline storica più lunga per atr_min/atr_max (vol corrente vs storico ampio):
            # così la leva è graduata e il minimo è riservato alle vere anomalie.
            atr_min, atr_max = await self._perp_leverage_atr_baseline(
                signal.get("asset"), payload, atr_now
            )
            signal["leverage"] = _perp_atr_range_leverage(
                min_lev=ms.perp_min_leverage,
                max_lev=ms.perp_max_leverage,
                atr_value=atr_now,
                atr_min=atr_min,
                atr_max=atr_max,
            )
        return await self._handle_signal(signal, session)

    async def _perp_leverage_atr_baseline(
        self, asset: str | None, payload: dict, atr_now: float | None
    ) -> tuple[float | None, float | None]:
        """Ricava (atr_min, atr_max) della serie ATR su un lookback lungo (giorni), per
        modulare la leva confrontando la vol corrente con uno storico ampio.

        Best-effort: senza ATR corrente o senza dati ritorna (None, None) → leva minima.
        Eseguito solo all'apertura reale (action != skip), una fetch klines per trade.
        """
        if atr_now is None:
            return None, None
        symbol = payload.get("symbol") or (f"{asset}USDT" if asset else None)
        if not symbol:
            return None, None
        minutes = self.settings.perp_volume_profile_candle_minutes
        hours = self.settings.perp_leverage_atr_baseline_hours
        period = self.settings.perp_leverage_atr_period
        limit = min(int(hours * 60 / minutes), 1500)
        try:
            candles = await self.price_feed.fetch(
                symbol=str(symbol), interval=f"{minutes}m", limit=limit, market="futures"
            )
        except Exception:
            return None, None
        series = atr_series(candles, period=period)
        if not series:
            return None, None
        return min(series), max(series)

    async def fast_tick(self, session: AsyncSession) -> dict:
        """Manage open positions; refresh live prices and check SL/TP."""

        heartbeat.beat("agent_fast_tick")
        user_id = str(self.settings.default_user_id)
        spot_positions = await SpotPositionRepository(session).open_for_user(user_id)
        perp_positions = await PerpPositionRepository(session).open_for_user(user_id)
        now = datetime.now(UTC)
        if spot_positions or perp_positions:
            await self._refresh_position_prices(session, spot_positions, perp_positions)
            await self._check_sl_tp(session, spot_positions, perp_positions, now)
        open_spot = [p for p in spot_positions if p.status == "open"]
        open_perp = [p for p in perp_positions if p.status == "open"]
        await self._update_portfolio_state(session, open_spot, open_perp, now)
        await self._check_risk_notifications(session, open_spot, open_perp)
        return {
            "status": "ok",
            "open_spot_positions": len(spot_positions),
            "open_perp_positions": len(perp_positions),
            "kill_switch": self.risk.kill_switch.value,
        }

    async def _refresh_position_prices(
        self,
        session: AsyncSession,
        spot_positions: list,
        perp_positions: list,
    ) -> None:
        """Fetch live Binance prices and update current_price + pnl_unrealized for open positions."""
        now = datetime.now(UTC)

        perp_assets: list[str] = sorted({p.asset for p in perp_positions})
        spot_assets: list[str] = sorted({p.asset for p in spot_positions})

        # Una sola chiamata batch per mercato invece di N richieste seriali.
        perp_prices: dict[str, Decimal] = {}
        if perp_assets:
            try:
                ticker = await self.price_feed.fetch_prices(
                    symbols=[f"{a}USDT" for a in perp_assets], market="futures"
                )
                perp_prices = {a: ticker[f"{a}USDT"] for a in perp_assets if f"{a}USDT" in ticker}
            except Exception:
                pass

        spot_prices: dict[str, Decimal] = {}
        if spot_assets:
            try:
                ticker = await self.price_feed.fetch_prices(
                    symbols=[f"{a}USDT" for a in spot_assets], market="spot"
                )
                spot_prices = {a: ticker[f"{a}USDT"] for a in spot_assets if f"{a}USDT" in ticker}
            except Exception:
                pass

        # Funding rate live (best-effort) per le posizioni perp aperte.
        funding_rates: dict[str, Decimal] = {}
        if perp_assets:
            try:
                funding_rates = await self.price_feed.fetch_funding_rates(assets=perp_assets)
            except Exception:
                pass

        updated = False
        for pos in perp_positions:
            funding = funding_rates.get(pos.asset)
            if funding is not None:
                pos.funding_rate = funding
                pos.updated_at = now
                session.add(pos)
                updated = True
            price = perp_prices.get(pos.asset)
            if price is None:
                continue
            raw_pnl = (price - pos.entry_price) * pos.size if pos.side == "long" else (pos.entry_price - price) * pos.size
            pos.current_price = price
            # Aggiorna funding accrued se la posizione ha fee_mode != "none"
            if pos.funding_rate is not None and pos.fee_mode and pos.fee_mode != "none":
                hours = (now - pos.opened_at.replace(tzinfo=pos.opened_at.tzinfo or UTC)).total_seconds() / 3600
                notional = pos.entry_price * pos.size
                pos.funding_accrued_usd = accrue_funding(pos.funding_rate, notional, hours, pos.side)
            # Detrae la fee di apertura (taker o maker) dal P&L netto.
            # Lo slippage è già nell'entry_price, quindi si sottrae solo la parte
            # "pura" della fee: opening_fee_usd − slippage_usd già incluso nel prezzo.
            fee_deduction = (pos.opening_fee_usd or Decimal("0")) - (pos.slippage_usd or Decimal("0"))
            pos.pnl_unrealized = raw_pnl - fee_deduction + pos.funding_accrued_usd
            # Aggiorna anche il liq price se mancante (posizioni aperte prima del fix).
            if pos.liquidation_price is None:
                pos.liquidation_price = _estimate_liquidation_price(pos.entry_price, pos.leverage, pos.side)
            pos.updated_at = now
            session.add(pos)
            updated = True

        for pos in spot_positions:
            price = spot_prices.get(pos.asset)
            if price is None:
                continue
            pos.current_price = price
            raw_pnl = (price - pos.entry_price) * pos.size
            # Detrae la swap fee dal P&L netto (lo slippage è già nell'entry_price).
            pos.pnl_unrealized = raw_pnl - (pos.swap_fee_usd or Decimal("0"))
            pos.updated_at = now
            session.add(pos)
            updated = True

        if updated:
            await session.commit()

    async def _snapshot_closed_trade(
        self,
        session: AsyncSession,
        pos,
        *,
        market: str,
        exit_price: Decimal,
        close_trade_id: str,
        now: datetime,
    ) -> None:
        """Congela candele + livelli alla chiusura per ridisegnare il grafico nel dettaglio.

        Best-effort: un errore (es. feed irraggiungibile) non blocca la chiusura del trade.
        """
        try:
            opened_at = pos.opened_at
            if opened_at.tzinfo is None:
                opened_at = opened_at.replace(tzinfo=UTC)
            duration_min = max(1, int((now - opened_at).total_seconds() / 60))
            interval, per_min = _auto_chart_interval(duration_min)
            stop_reference_time = getattr(pos, "stop_reference_time", None)
            if stop_reference_time and stop_reference_time.tzinfo is None:
                stop_reference_time = stop_reference_time.replace(tzinfo=UTC)
            lookback_attr = "perp_structural_stop_lookback_candles" if market == "perp" else "spot_structural_stop_lookback_candles"
            try:
                lookback = max(1, int(getattr(self.settings, lookback_attr, 20)))
            except Exception:
                lookback = 20
            chart_start = (
                min(opened_at - timedelta(minutes=per_min * lookback), stop_reference_time)
                if stop_reference_time is not None
                else None
            )
            chart_span_min = (
                max(1, int((now - chart_start).total_seconds() / 60))
                if chart_start is not None
                else duration_min
            )
            limit = int(min(260, max(20, (chart_span_min / per_min) * 1.6)))
            feed_market = "futures" if market == "perp" else "spot"
            try:
                fetch_kwargs = {
                    "symbol": f"{pos.asset}USDT",
                    "interval": interval,
                    "limit": limit,
                    "market": feed_market,
                }
                if chart_start is not None:
                    fetch_kwargs["start_time"] = chart_start
                candles = await self.price_feed.fetch(
                    **fetch_kwargs,
                )
            except Exception:
                candles = await self.price_feed.fetch(
                    symbol=f"{pos.asset}USDT", interval=interval, limit=limit, market=feed_market
                )
            tp2 = getattr(pos, "take_profit_2", None)
            stop_reference_price = getattr(pos, "stop_reference_price", None)
            stop_reference_field = getattr(pos, "stop_reference_field", None)
            display_stop_loss = getattr(pos, "initial_stop_loss", None) or pos.stop_loss
            payload = {
                "interval": interval,
                "market": market,
                "side": pos.side if market == "perp" else "long",
                "entry_price": str(pos.entry_price),
                "exit_price": str(exit_price),
                "stop_loss": str(display_stop_loss) if display_stop_loss else None,
                "take_profit_1": str(pos.take_profit_1) if pos.take_profit_1 else None,
                "take_profit_2": str(tp2) if tp2 else None,
                "liquidation_price": (
                    str(pos.liquidation_price)
                    if market == "perp" and getattr(pos, "liquidation_price", None)
                    else None
                ),
                "opened_at": opened_at.isoformat(),
                "closed_at": now.isoformat(),
                "stop_reference": (
                    {
                        "t": stop_reference_time.isoformat(),
                        "price": str(stop_reference_price) if stop_reference_price else None,
                        "field": stop_reference_field,
                        "pre_candles": lookback,
                    }
                    if stop_reference_time is not None
                    else None
                ),
                "candles": [
                    {"t": c.timestamp.isoformat(), "o": c.open, "h": c.high, "l": c.low, "c": c.close}
                    for c in candles
                ],
            }
            await TradeChartRepository(session).save(
                TradeChartSnapshot(
                    user_id=pos.user_id,
                    position_id=pos.position_id,
                    close_trade_id=close_trade_id,
                    market=market,
                    payload=json.dumps(payload),
                    created_at=now,
                )
            )
        except Exception:
            logger.warning("trade_chart_snapshot_failed", asset=pos.asset, position_id=pos.position_id)

    async def _close_spot_position(
        self,
        session: AsyncSession,
        pos: SpotPosition,
        exit_price: Decimal,
        reason: str,
        now: datetime,
        *,
        partial: bool = False,
    ) -> Decimal:
        """Chiude (totalmente o per la quota TP1) una posizione spot; crea trade di chiusura con pnl_usd."""
        swap_fee = pos.swap_fee_usd or Decimal("0")
        if partial:
            fraction = Decimal(str(self._ms.spot_tp1_close_pct)) / Decimal("100")
            close_size = (pos.size * fraction).quantize(Decimal("0.000001"))
            raw_pnl = (exit_price - pos.entry_price) * close_size
            pnl = raw_pnl - swap_fee * fraction
            pos.size = pos.size - close_size
            pos.tp1_reached = True
            remaining = Decimal("1") - fraction
            pos.pnl_unrealized = (exit_price - pos.entry_price) * pos.size - swap_fee * remaining
            # Scala la fee residua: il close finale userà solo la quota rimasta
            pos.swap_fee_usd = swap_fee * remaining
        else:
            close_size = pos.size
            raw_pnl = (exit_price - pos.entry_price) * close_size
            pnl = raw_pnl - swap_fee
            pos.status = "closed"
            pos.pnl_unrealized = pnl
        pos.current_price = exit_price
        pos.updated_at = now
        session.add(pos)
        close_trade = SpotTrade(
            trade_id=f"cls_{pos.position_id}_{uuid4().hex[:8]}",
            user_id=pos.user_id,
            asset=pos.asset,
            side="sell",
            amount=close_size,
            price=exit_price,
            amount_quote=exit_price * close_size,
            status="confirmed",
            provider="agent",
            timestamp_utc=now,
            notes=f"auto_close:{reason}{'_partial' if partial else ''}",
            pnl_usd=pnl,
        )
        await SpotTradeRepository(session).save(close_trade)
        await self._snapshot_closed_trade(
            session, pos, market="spot", exit_price=exit_price,
            close_trade_id=close_trade.trade_id, now=now,
        )
        logger.info("spot_position_closed", asset=pos.asset, reason=reason, partial=partial, pnl_usd=float(pnl))
        # Notifica chiusura trade (fire-and-forget)
        try:
            notifier = get_agent_notifier()
            pnl_pct = (pnl / (pos.size * pos.entry_price)) * Decimal("100") if pos.size and pos.entry_price else Decimal("0")
            await notifier.notify_trade_closed(
                user_id=str(self.settings.default_user_id),
                trade_id=close_trade.trade_id,
                asset=pos.asset,
                market="spot",
                pnl_usd=pnl,
                pnl_pct=pnl_pct,
                close_reason=reason,
                is_dry_run=self._ms.execution_mode == "dry_run",
            )
        except Exception:
            pass  # le notifiche non bloccano mai l'agente
        return pnl

    async def _maybe_scale_in_spot(
        self,
        session: AsyncSession,
        pos: SpotPosition,
        price: Decimal,
        prev_max: Decimal | None,
        now: datetime,
    ) -> None:
        """E (v3): aggiunge a favore (piramidazione) su una posizione spot vincente.

        Vincoli assoluti: MAI media al ribasso. Aggiunge solo se la posizione è in
        profitto, lo stop è già a breakeven e c'è un nuovo higher-high confermato.
        La size totale resta entro il tetto nominale per trade (risk_capital_per_trade_pct).
        """
        s = self.settings
        if not s.spot_scale_in_enabled:
            return
        if (pos.scale_in_count or 0) >= s.spot_scale_in_max_adds:
            return
        # Mai aggiungere in perdita / non a favore.
        if price <= pos.entry_price:
            return
        # Stop già a breakeven (>= entry).
        if s.spot_scale_in_require_be_stop:
            be_moved = pos.stop_loss is not None and pos.stop_loss >= pos.entry_price
            if not be_moved:
                return
        # Nuovo higher-high confermato rispetto al massimo precedente.
        if s.spot_scale_in_require_new_hh and not (prev_max is not None and price > prev_max):
            return

        current_notional = pos.size * pos.entry_price
        add_notional = current_notional * Decimal(str(s.spot_scale_in_size_fraction))
        # Tetto: il notional totale resta entro il cap nominale per trade.
        portfolio = await PnlRepository(session).get_portfolio(str(self.settings.default_user_id))
        if portfolio is not None and Decimal(portfolio.total_equity_usd) > 0:
            cap = Decimal(portfolio.total_equity_usd) * Decimal(str(s.risk_capital_per_trade_pct)) / Decimal("100")
            room = cap - current_notional
            if room <= 0:
                return
            add_notional = min(add_notional, room)
        if add_notional <= 0:
            return

        # Costi dell'add coerenti con l'ingresso (slippage nel prezzo, swap fee accumulata).
        costs = compute_spot_costs(add_notional, pos.fee_mode or "all")
        add_price = price * (Decimal("1") + costs["slippage_rate"]) if costs["slippage_rate"] > 0 else price
        add_amount = add_notional / add_price

        # Media a favore: nuova entry = media ponderata; stop NON viene mai abbassato.
        new_size = pos.size + add_amount
        pos.entry_price = (pos.size * pos.entry_price + add_amount * add_price) / new_size
        pos.size = new_size
        pos.scale_in_count = (pos.scale_in_count or 0) + 1
        pos.swap_fee_usd = (pos.swap_fee_usd or Decimal("0")) + costs["swap_fee_usd"]
        pos.slippage_usd = (pos.slippage_usd or Decimal("0")) + costs["slippage_usd"]
        pos.updated_at = now
        session.add(pos)

        await SpotTradeRepository(session).save(
            SpotTrade(
                trade_id=f"add_{pos.position_id}_{uuid4().hex[:8]}",
                user_id=pos.user_id,
                asset=pos.asset,
                side="buy",
                amount=add_amount,
                price=add_price,
                amount_quote=add_notional,
                status="confirmed",
                provider="agent",
                timestamp_utc=now,
                notes="scale_in",
                fee_mode=pos.fee_mode,
                swap_fee_usd=costs["swap_fee_usd"],
                slippage_usd=costs["slippage_usd"],
                fees_quote=costs["applied_fee_usd"],
            )
        )
        logger.info("spot_scale_in", asset=pos.asset, add_quote=float(add_notional), adds=pos.scale_in_count)

    async def _spot_time_stop_reason(
        self,
        pos: SpotPosition,
        price: Decimal,
        atr_v: Decimal | None,
        now: datetime,
    ) -> str | None:
        """G (v3): stop temporale. In modalità ATR chiude solo se il prezzo si è mosso
        meno di ``min_move_atr * ATR`` nelle ultime N candele (trade fermo). Fallback orario
        solo se mode='hours'. Best-effort: senza dati candele non chiude."""
        s = self.settings
        opened = pos.opened_at.replace(tzinfo=pos.opened_at.tzinfo or UTC)
        if s.spot_time_stop_mode == "atr":
            if not atr_v or atr_v <= 0:
                return None
            lookback = s.spot_time_stop_lookback_candles
            age_min = (now - opened).total_seconds() / 60
            # Giudica solo dopo che è trascorsa l'intera finestra (candele 5m).
            if age_min < lookback * 5:
                return None
            past_close = self._spot_close_n_candles_ago(pos.asset, lookback)
            if past_close is None:
                return None
            move = abs(price - past_close)
            if move < atr_v * Decimal(str(s.spot_time_stop_min_move_atr)):
                return "time_stop_atr"
            return None
        # Fallback orario (mode='hours').
        if s.spot_time_stop_hours_fallback > 0:
            age_hours = (now - opened).total_seconds() / 3600
            if age_hours >= s.spot_time_stop_hours_fallback:
                return "time_stop"
        return None

    def _spot_close_n_candles_ago(self, asset: str, lookback: int) -> Decimal | None:
        """Prezzo di chiusura ~N candele 5m fa dalla cache klines (best-effort, no HTTP)."""
        try:
            entry = get_kline_cache_entry(market="spot", symbol=f"{asset}USDT", interval="5m")
            if entry is None or len(entry.candles) <= lookback:
                return None
            return Decimal(str(entry.candles[-(lookback + 1)].close))
        except Exception:
            return None

    async def _close_perp_position(
        self,
        session: AsyncSession,
        pos: PerpPosition,
        exit_price: Decimal,
        reason: str,
        now: datetime,
        *,
        partial: bool = False,
        close_fraction: Decimal | None = None,
    ) -> Decimal:
        """Chiude una posizione perp (totale o parziale); crea trade di chiusura con pnl_usd.

        `partial` senza `close_fraction` usa `perp_tp1_close_pct` (chiusura al TP1).
        `close_fraction` (0,1] chiude quella quota della size CORRENTE ed è la via usata
        dagli scalini del ratchet, che chiudono frazioni arbitrarie del residuo.
        """
        is_long = pos.side == "long"
        pnl_per_unit = (exit_price - pos.entry_price) if is_long else (pos.entry_price - exit_price)
        # Fee pura = opening_fee_usd escludendo lo slippage già incluso nell'entry_price.
        fee_only = (pos.opening_fee_usd or Decimal("0")) - (pos.slippage_usd or Decimal("0"))

        f_req = close_fraction if close_fraction is not None else Decimal(str(self._ms.perp_tp1_close_pct)) / Decimal("100")
        f_req = max(Decimal("0"), min(Decimal("1"), f_req))
        # Una quota del 100% (o che lascerebbe una size trascurabile) è una chiusura piena:
        # altrimenti la posizione resterebbe "open" con size 0.
        residual = (pos.size * (Decimal("1") - f_req)).quantize(Decimal("0.000001"))
        if partial and residual <= 0:
            partial = False

        if partial:
            f = f_req
            close_size = (pos.size * f).quantize(Decimal("0.000001"))
            funding_share = pos.funding_accrued_usd * f
            raw_pnl = pnl_per_unit * close_size
            pnl = raw_pnl - fee_only * f + funding_share
            pos.size = pos.size - close_size
            pos.tp1_reached = True
            remaining = Decimal("1") - f
            pos.pnl_unrealized = pnl_per_unit * pos.size - fee_only * remaining + pos.funding_accrued_usd * remaining
            # Scala la fee residua sulla posizione: il close finale userà solo la quota rimasta
            pos.opening_fee_usd = (pos.opening_fee_usd or Decimal("0")) * remaining
            pos.slippage_usd = (pos.slippage_usd or Decimal("0")) * remaining
            pos.funding_accrued_usd = pos.funding_accrued_usd * remaining
        else:
            close_size = pos.size
            raw_pnl = pnl_per_unit * close_size
            pnl = raw_pnl - fee_only + pos.funding_accrued_usd
            pos.status = "closed"
            pos.pnl_unrealized = pnl

        pos.current_price = exit_price
        pos.updated_at = now
        session.add(pos)
        close_trade = PerpTrade(
            trade_id=f"cls_{pos.position_id}_{uuid4().hex[:8]}",
            user_id=pos.user_id,
            asset=pos.asset,
            side=pos.side,
            direction="close",
            size=close_size,
            price=exit_price,
            leverage=pos.leverage,
            status="confirmed",
            venue=pos.venue or "agent",
            timestamp_utc=now,
            notes=f"auto_close:{reason}{'_partial' if partial else ''}",
            pnl_usd=pnl,
        )
        await PerpTradeRepository(session).save(close_trade)
        await self._snapshot_closed_trade(
            session, pos, market="perp", exit_price=exit_price,
            close_trade_id=close_trade.trade_id, now=now,
        )
        # MFE verso TP2 (max progresso raggiunto): serve a ritarare gli scalini profit lock.
        mfe_to_tp2 = None
        if pos.take_profit_2 and pos.max_price is not None:
            _span = (pos.take_profit_2 - pos.entry_price) if is_long else (pos.entry_price - pos.take_profit_2)
            if _span and _span > 0:
                _fav = (pos.max_price - pos.entry_price) if is_long else (pos.entry_price - pos.max_price)
                mfe_to_tp2 = float(max(Decimal("0"), min(Decimal("1"), _fav / _span)))
        logger.info(
            "perp_position_closed",
            asset=pos.asset, reason=reason, partial=partial, pnl_usd=float(pnl), mfe_to_tp2=mfe_to_tp2,
        )
        # Notifica chiusura trade (fire-and-forget)
        try:
            notifier = get_agent_notifier()
            pnl_pct = (pnl / (pos.size * pos.entry_price)) * Decimal("100") if pos.size and pos.entry_price else Decimal("0")
            await notifier.notify_trade_closed(
                user_id=str(self.settings.default_user_id),
                trade_id=close_trade.trade_id,
                asset=pos.asset,
                market="perp",
                pnl_usd=pnl,
                pnl_pct=pnl_pct,
                close_reason=reason,
                is_dry_run=self._ms.execution_mode == "dry_run",
            )
        except Exception:
            pass  # le notifiche non bloccano mai l'agente
        return pnl

    async def _process_smart_sl(
        self,
        session: AsyncSession,
        pos: PerpPosition,
        price: Decimal,
        ms: AgentMobileSettings,
        now: datetime,
    ) -> None:
        """Smart Stop Loss: vende parzialmente su livelli intermedi, ricompra su rimbalzo."""
        if pos.initial_stop_loss is None:
            return
        is_long = pos.side == "long"
        entry = pos.entry_price
        isl = pos.initial_stop_loss
        sl_in_loss = (is_long and pos.stop_loss < entry) or (not is_long and pos.stop_loss > entry)
        if not sl_in_loss:
            return

        # Carica o inizializza lo stato
        if pos.smart_sl_state:
            state = json.loads(pos.smart_sl_state)
        else:
            state = {
                "original_size": str(pos.size),
                "original_entry": str(pos.entry_price),
                "levels": [
                    {"status": "idle", "sell_price": None, "reentries": 0, "confirm_since": None, "rebuy_confirm_since": None},
                    {"status": "idle", "sell_price": None, "reentries": 0, "confirm_since": None, "rebuy_confirm_since": None},
                ],
            }
        if "original_entry" not in state:
            state["original_entry"] = str(pos.entry_price)
        orig_entry = Decimal(state["original_entry"])
        orig_size = Decimal(state["original_size"])

        dist = abs(orig_entry - isl)
        if dist == 0:
            return
        fracs = [ms.perp_smart_sl_l1_frac, ms.perp_smart_sl_l2_frac]
        splits = [ms.perp_smart_sl_split_l1, ms.perp_smart_sl_split_l2]
        deltas = [ms.perp_smart_sl_delta_l1, ms.perp_smart_sl_delta_l2]

        if is_long:
            levels = [orig_entry - Decimal(str(f)) * dist for f in fracs]
        else:
            levels = [orig_entry + Decimal(str(f)) * dist for f in fracs]

        rebuy_mode = ms.perp_smart_sl_rebuy_mode
        confirm_secs = ms.perp_smart_sl_confirmation_candles * 300
        global_reentries = state.get("global_reentries", 0)
        splits_r2 = [ms.perp_smart_sl_split_l1_r2, ms.perp_smart_sl_split_l2_r2]

        changed = False
        for i in range(2):
            lv = state["levels"][i]
            level_price = levels[i]
            use_r2 = rebuy_mode == "above_entry" and lv["status"] == "rebought"
            active_split = splits_r2[i] if use_r2 else splits[i]
            split_size = (orig_size * Decimal(str(active_split))).quantize(Decimal("0.000001"))
            delta_dist = Decimal(str(deltas[i])) * dist

            if lv["status"] in ("idle", "rebought"):
                crossed = (is_long and price <= level_price) or (not is_long and price >= level_price)
                if crossed:
                    if lv.get("confirm_since") is None:
                        lv["confirm_since"] = now.isoformat()
                        changed = True
                        continue
                    cs = datetime.fromisoformat(lv["confirm_since"])
                    elapsed = (now - cs).total_seconds()
                    if elapsed < confirm_secs:
                        continue
                    if pos.size <= split_size:
                        continue
                    sell_price = price
                    pnl_per_unit = (sell_price - orig_entry) if is_long else (orig_entry - sell_price)
                    fee_frac = split_size / pos.size
                    fee_share = ((pos.opening_fee_usd or Decimal("0")) - (pos.slippage_usd or Decimal("0"))) * fee_frac
                    funding_share = pos.funding_accrued_usd * fee_frac
                    pnl = pnl_per_unit * split_size - fee_share + funding_share

                    if "original_tp1" not in state:
                        state["original_tp1"] = str(pos.take_profit_1) if pos.take_profit_1 else None
                        state["original_tp2"] = str(pos.take_profit_2) if pos.take_profit_2 else None

                    close_trade = PerpTrade(
                        trade_id=f"ssl_{pos.position_id}_{uuid4().hex[:8]}",
                        user_id=pos.user_id, asset=pos.asset, side=pos.side,
                        direction="close", size=split_size, price=sell_price,
                        leverage=pos.leverage, status="confirmed",
                        venue=pos.venue or "agent", timestamp_utc=now,
                        notes=f"auto_close:smart_sl_sell_l{i+1}", pnl_usd=pnl,
                    )
                    await PerpTradeRepository(session).save(close_trade)

                    lv["pre_sell_opening_fee"] = str(pos.opening_fee_usd or Decimal("0"))
                    lv["pre_sell_slippage"] = str(pos.slippage_usd or Decimal("0"))
                    lv["pre_sell_funding"] = str(pos.funding_accrued_usd)

                    remaining_frac = (pos.size - split_size) / pos.size
                    pos.size = pos.size - split_size
                    pos.opening_fee_usd = (pos.opening_fee_usd or Decimal("0")) * remaining_frac
                    pos.slippage_usd = (pos.slippage_usd or Decimal("0")) * remaining_frac
                    pos.funding_accrued_usd = pos.funding_accrued_usd * remaining_frac

                    lv["status"] = "sold"
                    lv["sell_price"] = str(sell_price)
                    lv["confirm_since"] = None
                    lv["realized_loss"] = str(Decimal(lv.get("realized_loss", "0")) + pnl)
                    changed = True
                    logger.info("smart_sl_sell", asset=pos.asset, level=i+1, price=float(sell_price), size=float(split_size), pnl=float(pnl))
                    notifier = get_agent_notifier()
                    margin = orig_entry * orig_size / Decimal(max(int(pos.leverage or 1), 1))
                    pnl_pct = pnl / margin * 100 if margin > 0 else Decimal("0")
                    asyncio.create_task(
                        notifier.notify_trade_closed(
                            user_id=pos.user_id, trade_id=close_trade.trade_id,
                            asset=pos.asset, market="perp", pnl_usd=pnl, pnl_pct=pnl_pct,
                            close_reason=f"smart_sl_sell_l{i+1}",
                            is_dry_run=ms.execution_mode == "dry_run",
                        )
                    )
                else:
                    if lv.get("confirm_since") is not None:
                        lv["confirm_since"] = None
                        changed = True

            elif lv["status"] == "sold" and rebuy_mode == "delta" and lv["reentries"] < ms.perp_smart_sl_max_reentries:
                sp = Decimal(lv["sell_price"])
                if is_long:
                    rebuy_price = sp + delta_dist
                    bounced = price >= rebuy_price
                else:
                    rebuy_price = sp - delta_dist
                    bounced = price <= rebuy_price
                if bounced:
                    if lv.get("rebuy_confirm_since") is None:
                        lv["rebuy_confirm_since"] = now.isoformat()
                        changed = True
                        continue
                    rcs = datetime.fromisoformat(lv["rebuy_confirm_since"])
                    r_elapsed = (now - rcs).total_seconds()
                    if r_elapsed < confirm_secs:
                        continue

                    new_entry = (pos.size * pos.entry_price + split_size * price) / (pos.size + split_size)
                    pos.entry_price = new_entry.quantize(Decimal("0.000000000000000001"))
                    pos.size = pos.size + split_size

                    rebuy_trade = PerpTrade(
                        trade_id=f"ssl_{pos.position_id}_{uuid4().hex[:8]}",
                        user_id=pos.user_id, asset=pos.asset, side=pos.side,
                        direction="open", size=split_size, price=price,
                        leverage=pos.leverage, status="confirmed",
                        venue=pos.venue or "agent", timestamp_utc=now,
                        notes=f"auto_close:smart_sl_rebuy_l{i+1}", pnl_usd=Decimal("0"),
                    )
                    await PerpTradeRepository(session).save(rebuy_trade)

                    if lv.get("pre_sell_opening_fee"):
                        pos.opening_fee_usd = Decimal(lv["pre_sell_opening_fee"])
                    if lv.get("pre_sell_slippage"):
                        pos.slippage_usd = Decimal(lv["pre_sell_slippage"])
                    if lv.get("pre_sell_funding"):
                        pos.funding_accrued_usd = Decimal(lv["pre_sell_funding"])

                    lv["status"] = "rebought"
                    lv["reentries"] += 1
                    lv["sell_price"] = None
                    lv["rebuy_confirm_since"] = None
                    lv["rebuy_fill_price"] = str(price)
                    self._adjust_smart_sl_recovery_take_profits(pos, state, ms, is_long)
                    state["protection_suspended"] = True
                    pos.trailing_stop = None
                    changed = True
                    logger.info("smart_sl_rebuy", asset=pos.asset, level=i+1, price=float(price), size=float(split_size))
                    notifier = get_agent_notifier()
                    asyncio.create_task(
                        notifier.notify_trade_closed(
                            user_id=pos.user_id, trade_id=rebuy_trade.trade_id,
                            asset=pos.asset, market="perp", pnl_usd=Decimal("0"), pnl_pct=Decimal("0"),
                            close_reason=f"smart_sl_rebuy_l{i+1}",
                            is_dry_run=ms.execution_mode == "dry_run",
                        )
                    )
                else:
                    if lv.get("rebuy_confirm_since") is not None:
                        lv["rebuy_confirm_since"] = None
                        changed = True

        # --- Rebuy above_entry: ricompra tutto quando prezzo supera original_entry ---
        if rebuy_mode == "above_entry" and global_reentries < ms.perp_smart_sl_max_reentries:
            sold_levels = [i for i in range(2) if state["levels"][i]["status"] == "sold"]
            if sold_levels:
                above = (is_long and price >= orig_entry) or (not is_long and price <= orig_entry)
                if above:
                    if state.get("rebuy_above_confirm_since") is None:
                        state["rebuy_above_confirm_since"] = now.isoformat()
                        changed = True
                    else:
                        rcs = datetime.fromisoformat(state["rebuy_above_confirm_since"])
                        r_elapsed = (now - rcs).total_seconds()
                        if r_elapsed >= confirm_secs:
                            rebuy_pct = Decimal(str(ms.perp_smart_sl_rebuy_above_entry_pct)) / Decimal("100")
                            total_rebuy_size = Decimal("0")
                            for idx in sold_levels:
                                sz = (orig_size * Decimal(str(splits[idx]))).quantize(Decimal("0.000001"))
                                total_rebuy_size += (sz * rebuy_pct).quantize(Decimal("0.000001"))

                            new_entry = (pos.size * pos.entry_price + total_rebuy_size * price) / (pos.size + total_rebuy_size)
                            pos.entry_price = new_entry.quantize(Decimal("0.000000000000000001"))
                            pos.size = pos.size + total_rebuy_size

                            rebuy_trade = PerpTrade(
                                trade_id=f"ssl_{pos.position_id}_{uuid4().hex[:8]}",
                                user_id=pos.user_id, asset=pos.asset, side=pos.side,
                                direction="open", size=total_rebuy_size, price=price,
                                leverage=pos.leverage, status="confirmed",
                                venue=pos.venue or "agent", timestamp_utc=now,
                                notes="auto_close:smart_sl_rebuy_all", pnl_usd=Decimal("0"),
                            )
                            await PerpTradeRepository(session).save(rebuy_trade)

                            max_fee = Decimal("0")
                            max_slip = Decimal("0")
                            max_fund = Decimal("0")
                            for idx in sold_levels:
                                lv = state["levels"][idx]
                                if lv.get("pre_sell_opening_fee"):
                                    v = Decimal(lv["pre_sell_opening_fee"])
                                    if v > max_fee:
                                        max_fee = v
                                if lv.get("pre_sell_slippage"):
                                    v = Decimal(lv["pre_sell_slippage"])
                                    if v > max_slip:
                                        max_slip = v
                                if lv.get("pre_sell_funding"):
                                    v = Decimal(lv["pre_sell_funding"])
                                    if v > max_fund:
                                        max_fund = v
                            if max_fee:
                                pos.opening_fee_usd = max_fee
                            if max_slip:
                                pos.slippage_usd = max_slip
                            if max_fund:
                                pos.funding_accrued_usd = max_fund

                            for idx in sold_levels:
                                lv = state["levels"][idx]
                                lv["status"] = "rebought"
                                lv["reentries"] += 1
                                lv["sell_price"] = None
                                lv["rebuy_confirm_since"] = None
                                lv["rebuy_fill_price"] = str(price)

                            self._adjust_smart_sl_recovery_take_profits(pos, state, ms, is_long)

                            state["global_reentries"] = global_reentries + 1
                            state["rebuy_above_confirm_since"] = None
                            state["protection_suspended"] = True
                            pos.trailing_stop = None
                            changed = True
                            logger.info("smart_sl_rebuy_above_entry", asset=pos.asset, price=float(price), size=float(total_rebuy_size), levels=[i+1 for i in sold_levels])
                            notifier = get_agent_notifier()
                            asyncio.create_task(
                                notifier.notify_trade_closed(
                                    user_id=pos.user_id, trade_id=rebuy_trade.trade_id,
                                    asset=pos.asset, market="perp", pnl_usd=Decimal("0"), pnl_pct=Decimal("0"),
                                    close_reason="smart_sl_rebuy_all",
                                    is_dry_run=ms.execution_mode == "dry_run",
                                )
                            )
                else:
                    if state.get("rebuy_above_confirm_since") is not None:
                        state["rebuy_above_confirm_since"] = None
                        changed = True

        if changed:
            pos.smart_sl_state = json.dumps(state)
            pos.updated_at = now
            session.add(pos)

    def _adjust_smart_sl_recovery_take_profits(
        self,
        pos: PerpPosition,
        state: dict,
        ms: AgentMobileSettings,
        is_long: bool,
    ) -> bool:
        """Move TPs after a Smart SL rebuy so the remaining exits recover net losses."""
        if not ms.perp_smart_sl_tp_adjust_after_rebuy or pos.size <= 0:
            return False

        ssl_losses = Decimal("0")
        for lv_st in state["levels"]:
            ssl_losses += Decimal(lv_st.get("realized_loss", "0"))
        if ssl_losses >= 0:
            return False

        if "original_tp1" not in state:
            state["original_tp1"] = str(pos.take_profit_1) if pos.take_profit_1 else None
            state["original_tp2"] = str(pos.take_profit_2) if pos.take_profit_2 else None

        loss_abs = abs(ssl_losses)
        delta_mult = Decimal("1") + Decimal(str(ms.perp_smart_sl_tp_recovery_delta_pct)) / Decimal("100")
        net_target = loss_abs * delta_mult

        fee_only = (pos.opening_fee_usd or Decimal("0")) - (pos.slippage_usd or Decimal("0"))
        funding = pos.funding_accrued_usd or Decimal("0")
        gross_target = net_target + fee_only - funding
        if gross_target <= 0:
            gross_target = net_target

        tp1_fraction = Decimal(str(ms.perp_tp1_close_pct)) / Decimal("100")
        tp1_size = (pos.size * tp1_fraction).quantize(Decimal("0.000001"))
        tp2_size = pos.size - tp1_size
        if tp1_size <= 0 or tp2_size <= 0:
            return False

        tp1_target_fraction = min(Decimal("0.4"), tp1_fraction * Decimal("0.8"))
        tp1_gross_target = gross_target * tp1_target_fraction
        tp2_gross_target = gross_target - tp1_gross_target
        tp1_dist = tp1_gross_target / tp1_size
        tp2_dist = tp2_gross_target / tp2_size

        if is_long:
            pos.take_profit_1 = pos.entry_price + tp1_dist
            pos.take_profit_2 = pos.entry_price + tp2_dist
        else:
            pos.take_profit_1 = pos.entry_price - tp1_dist
            pos.take_profit_2 = pos.entry_price - tp2_dist

        logger.info(
            "smart_sl_tp_adjusted",
            asset=pos.asset,
            tp1=float(pos.take_profit_1),
            tp2=float(pos.take_profit_2),
            ssl_loss=float(ssl_losses),
            net_target=float(net_target),
            gross_target=float(gross_target),
            tp1_close_pct=float(ms.perp_tp1_close_pct),
        )
        return True

    async def _check_sl_tp(
        self,
        session: AsyncSession,
        spot_positions: list,
        perp_positions: list,
        now: datetime,
    ) -> None:
        """Controlla SL/TP per ogni posizione aperta e chiude quelle che le hanno raggiunte."""
        user_id = str(self.settings.default_user_id)
        notifier = get_agent_notifier()

        for pos in spot_positions:
            if pos.status != "open":
                continue
            price = pos.current_price
            reason: str | None = None
            partial = False
            atr_v = pos.entry_atr
            prev_max = pos.max_price  # E (v3): riferimento higher-high PRIMA dell'update

            # C (v3): aggiorna il massimo dall'ingresso (per il trailing ATR).
            if pos.max_price is None or price > pos.max_price:
                pos.max_price = price
                pos.updated_at = now
                session.add(pos)

            # C (v3): breakeven a +1*ATR — alza lo stop a entry (+costi), non torna più sotto.
            if atr_v and atr_v > 0:
                be_trigger = pos.entry_price + atr_v * Decimal(str(self.settings.spot_breakeven_trigger_atr))
                be_tp1_ok = self._ms.spot_breakeven_mode != "tp1" or pos.tp1_reached
                if self.settings.spot_breakeven_enabled and price >= be_trigger and be_tp1_ok:
                    be_stop = pos.entry_price
                    if self.settings.spot_breakeven_offset_costs and pos.size > 0:
                        # Costi andata+ritorno (×2): coprono anche la fee di chiusura,
                        # così chiudere a breakeven non lascia una mini-perdita.
                        costs = ((pos.swap_fee_usd or Decimal("0")) + (pos.slippage_usd or Decimal("0"))) * 2
                        be_stop = pos.entry_price + costs / pos.size
                    # Cuscinetto extra: alza lo stop a entry+X% MA solo se il prezzo
                    # l'ha già superato (altrimenti lo stop starebbe sopra il prezzo →
                    # chiusura immediata). Copre le fee con un margine confortevole.
                    buf_pct = Decimal(str(self.settings.spot_breakeven_buffer_pct))
                    if buf_pct > 0:
                        buffer_be = pos.entry_price * (Decimal("1") + buf_pct / Decimal("100"))
                        if price > buffer_be and buffer_be > be_stop:
                            be_stop = buffer_be
                    if pos.stop_loss is None or be_stop > pos.stop_loss:
                        pos.stop_loss = be_stop
                        pos.updated_at = now
                        session.add(pos)
                # C (v3): trailing ATR attivo DA SUBITO (max_price - ATR*mult), solo verso l'alto.
                # Il moltiplicatore è cappato al TP1: così l'attivazione del trailing
                # (≈ entry + mult*ATR) non supera mai il TP1, altrimenti il trailing si
                # accenderebbe oltre il primo take-profit (inutile).
                if self._ms.spot_trailing_enabled and self.settings.spot_trailing_active_from_start:
                    trail_mult = min(
                        Decimal(str(self.settings.spot_trailing_atr_multiplier)),
                        Decimal(str(self.settings.spot_tp1_atr_multiplier)),
                    )
                    trail = (pos.max_price or price) - atr_v * trail_mult
                    # Guard: il trailing spot si attiva solo quando supera l'entry
                    # (non deve sostituire lo stop con uno più stretto ma in perdita).
                    if trail >= pos.entry_price and (pos.trailing_stop is None or trail > pos.trailing_stop):
                        pos.trailing_stop = trail
                        pos.updated_at = now
                        session.add(pos)

            # E (v3): scaling-in a favore (solo HH + stop a breakeven; mai in perdita).
            await self._maybe_scale_in_spot(session, pos, price, prev_max, now)

            # Uscite — priorità massima: SL / trailing (il maggiore dei due).
            if self._ms.spot_trailing_enabled and pos.trailing_stop is not None and (pos.stop_loss is None or pos.trailing_stop > pos.stop_loss):
                if price <= pos.trailing_stop:
                    reason = "trailing_stop"
            if reason is None and pos.stop_loss is not None and price <= pos.stop_loss:
                # Se lo stop è già a breakeven (>= entry) la chiusura non è una perdita:
                # etichettala "breakeven" invece di "stop_loss".
                reason = "breakeven" if pos.stop_loss >= pos.entry_price else "stop_loss"
            # TP2 (uscita finale) solo dopo che TP1 e' stato preso.
            if reason is None and pos.tp1_reached and pos.take_profit_2 and price >= pos.take_profit_2:
                reason = "take_profit_2"
            # TP1: chiusura parziale la prima volta che viene raggiunto.
            if reason is None and not pos.tp1_reached and pos.take_profit_1 and price >= pos.take_profit_1:
                reason = "take_profit_1"
                partial = True
            # G (v3): stop temporale ATR-aware — chiude solo i trade davvero fermi.
            if reason is None and self._ms.spot_time_stop_enabled:
                reason = await self._spot_time_stop_reason(pos, price, atr_v, now)
            if reason:
                exit_price = _level_fill_price(pos, reason, price)
                pnl = await self._close_spot_position(session, pos, exit_price, reason, now, partial=partial)
                exposure = pos.entry_price * pos.size
                pnl_pct = pnl / exposure * 100 if exposure > 0 else Decimal("0")
                asyncio.create_task(
                    notifier.notify_trade_closed(
                        user_id=user_id,
                        trade_id=f"cls_{pos.position_id}",
                        asset=pos.asset,
                        market="spot",
                        pnl_usd=pnl,
                        pnl_pct=pnl_pct,
                        close_reason=reason,
                        is_dry_run=self._ms.execution_mode == "dry_run",
                    )
                )

        ms = self._ms
        if (ms.perp_trailing_mode or "largo").lower() == "stretto":
            trail_base = self.settings.perp_trailing_base_atr_stretto
            trail_floor = self.settings.perp_trailing_floor_atr_stretto
        else:
            trail_base = self.settings.perp_trailing_base_atr_largo
            trail_floor = self.settings.perp_trailing_floor_atr_largo
        be_mult = Decimal(str(self.settings.perp_breakeven_trigger_atr))
        # Protezione profitto post-TP1: "trailing" (storico) | "off" | "profit_lock" (ratchet).
        prot_mode = (getattr(ms, "perp_protection_mode", None) or "trailing")
        profit_lock_steps = list(getattr(ms, "perp_profit_lock_steps", None) or [])

        for pos in perp_positions:
            if pos.status != "open":
                continue
            price = pos.current_price
            is_long = pos.side == "long"
            reason = None
            partial = False
            atr_v = pos.entry_atr

            # Estremo favorevole dall'ingresso (per il trailing): max per i long, min per gli short.
            if is_long:
                if pos.max_price is None or price > pos.max_price:
                    pos.max_price = price; pos.updated_at = now; session.add(pos)
            else:
                if pos.max_price is None or price < pos.max_price:
                    pos.max_price = price; pos.updated_at = now; session.add(pos)
            extreme = pos.max_price if pos.max_price is not None else price

            _ssl_suspended = False
            if pos.smart_sl_state:
                try:
                    _ssl_st = json.loads(pos.smart_sl_state)
                    _ssl_suspended = _ssl_st.get("protection_suspended", False)
                except (ValueError, KeyError):
                    pass

            # Protezione ATR — solo se l'ATR è stato congelato all'ingresso (trade nuovi).
            if atr_v and atr_v > 0 and not _ssl_suspended:
                # Breakeven: a +N×ATR lo SL si sposta a entry (+costi), solo verso il sicuro.
                be_trigger = (pos.entry_price + atr_v * be_mult) if is_long else (pos.entry_price - atr_v * be_mult)
                be_tp1_ok = ms.perp_breakeven_mode != "tp1" or pos.tp1_reached
                if self.settings.perp_breakeven_enabled and ((is_long and price >= be_trigger) or (not is_long and price <= be_trigger)) and be_tp1_ok:
                    be_stop = pos.entry_price
                    if self.settings.perp_breakeven_offset_costs and pos.size > 0:
                        # Fee andata+ritorno (×2): copre anche la chiusura.
                        fee_only = ((pos.opening_fee_usd or Decimal("0")) - (pos.slippage_usd or Decimal("0"))) * 2
                        offset = fee_only / pos.size
                        be_stop = pos.entry_price + offset if is_long else pos.entry_price - offset
                    # Profitto minimo fisso a breakeven: il residuo deve chiudere ad
                    # almeno +N$ (oltre alle fee residue). Vince il più protettivo tra
                    # questo e l'offset costi; applicato solo se il prezzo l'ha già
                    # superato (mai oltre il prezzo corrente → niente chiusura immediata).
                    min_profit = Decimal(str(getattr(ms, "perp_breakeven_min_profit_usd", 0) or 0))
                    if min_profit > 0 and pos.size > 0:
                        fee_res = (pos.opening_fee_usd or Decimal("0")) - (pos.slippage_usd or Decimal("0"))
                        dist = (min_profit + fee_res) / pos.size
                        target = pos.entry_price + dist if is_long else pos.entry_price - dist
                        if is_long and price > target and target > be_stop:
                            be_stop = target
                        elif not is_long and price < target and target < be_stop:
                            be_stop = target
                    # Cuscinetto extra entry±X%, applicato solo se il prezzo l'ha superato
                    # (mai oltre il prezzo corrente → niente chiusura immediata).
                    buf_pct = Decimal(str(self.settings.perp_breakeven_buffer_pct))
                    if buf_pct > 0:
                        if is_long:
                            buffer_be = pos.entry_price * (Decimal("1") + buf_pct / Decimal("100"))
                            if price > buffer_be and buffer_be > be_stop:
                                be_stop = buffer_be
                        else:
                            buffer_be = pos.entry_price * (Decimal("1") - buf_pct / Decimal("100"))
                            if price < buffer_be and buffer_be < be_stop:
                                be_stop = buffer_be
                    if is_long and (pos.stop_loss is None or be_stop > pos.stop_loss):
                        pos.stop_loss = be_stop; pos.updated_at = now; session.add(pos)
                    elif not is_long and (pos.stop_loss is None or be_stop < pos.stop_loss):
                        pos.stop_loss = be_stop; pos.updated_at = now; session.add(pos)

                # Trailing da subito, moltiplicatore ATR dinamico sulla leva del trade.
                mult = _perp_trailing_mult(
                    leverage=pos.leverage, min_lev=ms.perp_min_leverage, max_lev=ms.perp_max_leverage,
                    base=trail_base, floor=trail_floor,
                )
                # Cappa il moltiplicatore al TP1: l'attivazione del trailing
                # (≈ entry + mult*ATR) non deve mai superare il primo take-profit,
                # altrimenti il trailing si accende oltre TP1 (quasi a TP2) ed è inutile.
                tp1_cap = Decimal(str(self.settings.perp_tp1_atr_multiplier))
                if mult > tp1_cap:
                    mult = tp1_cap
                pnl_pct = Decimal(str(ms.perp_trailing_pnl_pct))
                if is_long:
                    trail_atr = extreme - atr_v * mult
                    # Se perp_trailing_pnl_pct > 0, calcola anche il trailing a distanza
                    # fissa (% del prezzo dal massimo). Vince il più alto tra i due.
                    if pnl_pct > 0:
                        trail_pnl = extreme * (1 - pnl_pct / Decimal("100"))
                        trail = max(trail_atr, trail_pnl)
                    else:
                        trail = trail_atr
                    # Il trailing si attiva SOLO quando supera l'entry: non deve mai
                    # sostituire lo stop originale con uno stop più stretto ma ancora
                    # in perdita (causa chiusure precoci senza dare spazio alla posizione).
                    if ms.perp_trailing_enabled and trail >= pos.entry_price and (pos.stop_loss is None or trail > pos.stop_loss) and (pos.trailing_stop is None or trail > pos.trailing_stop):
                        pos.trailing_stop = trail; pos.updated_at = now; session.add(pos)
                else:
                    trail_atr = extreme + atr_v * mult
                    if pnl_pct > 0:
                        trail_pnl = extreme * (1 + pnl_pct / Decimal("100"))
                        trail = min(trail_atr, trail_pnl)
                    else:
                        trail = trail_atr
                    # Stesso guard per gli short: trail deve essere <= entry (in profitto).
                    if ms.perp_trailing_enabled and trail <= pos.entry_price and (pos.stop_loss is None or trail < pos.stop_loss) and (pos.trailing_stop is None or trail < pos.trailing_stop):
                        pos.trailing_stop = trail; pos.updated_at = now; session.add(pos)

            # ── Profit Lock Ratchet: dopo il TP1 lavora SOLO nel tratto TP1→TP2. ──
            # Tre meccanismi distinti:
            #  1. uscite parziali agli scalini (quote CUMULATIVE del residuo post-TP1);
            #  2. "breakeven del ratchet": dopo lo scalino configurato, stop fisso a
            #     `perp_ratchet_breakeven_pct` del tratto (scritto su trailing_stop);
            #  3. oltre il TP2 si lascia correre con un trailing percentuale (gestito
            #     più sotto, dove il TP2 chiuderebbe).
            # Usa l'estremo favorevole (max_price) → monotono e immune alle spike.
            if (
                prot_mode == "profit_lock"
                and not _ssl_suspended
                and pos.tp1_reached
                and pos.take_profit_1
                and pos.take_profit_2
                and pos.max_price is not None
            ):
                progress = _ratchet_progress(pos.take_profit_1, pos.take_profit_2, pos.max_price, is_long)
                if progress is not None:
                    try:
                        r_state = json.loads(pos.ratchet_state) if pos.ratchet_state else {}
                    except (TypeError, ValueError):
                        r_state = {}
                    # Riferimento fisso: il residuo nel momento in cui il ratchet si arma.
                    # Le quote degli scalini sono cumulative SU QUESTA base, non a catena.
                    if "base_size" not in r_state:
                        r_state["base_size"] = str(pos.size)
                    base_size = Decimal(r_state["base_size"])
                    already = Decimal(str(r_state.get("closed_frac", "0")))

                    step_idx, cum_frac = _ratchet_level(progress, profit_lock_steps)

                    # 1. Uscita parziale: chiude la differenza rispetto a quanto già chiuso.
                    if step_idx >= 0 and cum_frac > already and pos.size > 0:
                        delta = cum_frac - already
                        want_size = base_size * delta
                        frac_now = min(Decimal("1"), want_size / pos.size) if pos.size > 0 else Decimal("0")
                        if frac_now > 0:
                            thr = Decimal(str(profit_lock_steps[step_idx][0]))
                            level_price = _ratchet_breakeven_price(pos.take_profit_1, pos.take_profit_2, thr, is_long)
                            # Fill al livello dello scalino, non al mercato: se il feed è in
                            # ritardo il prezzo può averlo superato di molto.
                            fill = level_price if ((is_long and price >= level_price) or (not is_long and price <= level_price)) else price
                            pnl_step = await self._close_perp_position(
                                session, pos, fill, "ratchet_step", now, partial=True, close_fraction=frac_now
                            )
                            r_state["closed_frac"] = str(cum_frac)
                            r_state["last_step"] = step_idx
                            logger.info(
                                "ratchet_step_closed",
                                asset=pos.asset,
                                step=step_idx + 1,
                                progress=float(progress),
                                closed_cum_pct=float(cum_frac * 100),
                                size_closed=float(want_size),
                                fill=float(fill),
                                pnl=float(pnl_step),
                            )
                            margin_step = pos.entry_price * base_size / Decimal(max(int(pos.leverage or 1), 1))
                            asyncio.create_task(
                                notifier.notify_trade_closed(
                                    user_id=user_id,
                                    trade_id=f"cls_{pos.position_id}",
                                    asset=pos.asset,
                                    market="perp",
                                    pnl_usd=pnl_step,
                                    pnl_pct=(pnl_step / margin_step * 100) if margin_step > 0 else Decimal("0"),
                                    close_reason="ratchet_step",
                                    is_dry_run=ms.execution_mode == "dry_run",
                                )
                            )

                    # 2. Breakeven del ratchet: si arma solo dallo scalino configurato in poi.
                    be_after = max(1, int(getattr(ms, "perp_ratchet_breakeven_after_step", 3)))
                    if step_idx >= (be_after - 1):
                        be_pct = Decimal(str(getattr(ms, "perp_ratchet_breakeven_pct", 50.0))) / Decimal("100")
                        be_price = _ratchet_breakeven_price(pos.take_profit_1, pos.take_profit_2, be_pct, is_long)
                        improves = (
                            pos.trailing_stop is None
                            or (is_long and be_price > pos.trailing_stop)
                            or (not is_long and be_price < pos.trailing_stop)
                        )
                        # Mai oltre il prezzo corrente → niente chiusura immediata.
                        not_beyond = (be_price < price) if is_long else (be_price > price)
                        if improves and not_beyond:
                            pos.trailing_stop = be_price
                            logger.info(
                                "ratchet_breakeven_armed",
                                asset=pos.asset,
                                step=step_idx + 1,
                                level=float(be_price),
                            )

                    pos.ratchet_state = json.dumps(r_state)
                    pos.updated_at = now
                    session.add(pos)

            # ── Smart Stop Loss (vende parzialmente prima del SL classico) ──
            if ms.perp_smart_sl_enabled and pos.initial_stop_loss is not None:
                await self._process_smart_sl(session, pos, price, ms, now)

            # ── Uscite — trailing/profit_lock (se più protettivo) → stop → TP2 → TP1 → time ──
            if (ms.perp_trailing_enabled or prot_mode == "profit_lock") and pos.trailing_stop is not None and (
                pos.stop_loss is None
                or (is_long and pos.trailing_stop > pos.stop_loss)
                or (not is_long and pos.trailing_stop < pos.stop_loss)
            ):
                if (is_long and price <= pos.trailing_stop) or (not is_long and price >= pos.trailing_stop):
                    reason = "profit_lock" if prot_mode == "profit_lock" else "trailing_stop"

            if reason is None and pos.stop_loss is not None:
                if (is_long and price <= pos.stop_loss) or (not is_long and price >= pos.stop_loss):
                    # Stop già a breakeven (>= entry long / <= entry short) → non è perdita.
                    at_be = pos.stop_loss >= pos.entry_price if is_long else pos.stop_loss <= pos.entry_price
                    reason = "breakeven" if at_be else "stop_loss"

            if reason is None and pos.tp1_reached and pos.take_profit_2:
                at_or_past = (is_long and price >= pos.take_profit_2) or (not is_long and price <= pos.take_profit_2)
                # "Superato di slancio": al controllo il prezzo è GIÀ oltre il TP2 (lo ha
                # attraversato fra un tick e l'altro). In quel caso non si chiude: si lascia
                # correre con un trailing percentuale. Se invece lo tocca esattamente, il
                # TP2 chiude come sempre.
                beyond = (is_long and price > pos.take_profit_2) or (not is_long and price < pos.take_profit_2)
                run_on = prot_mode == "profit_lock" and bool(getattr(ms, "perp_ratchet_run_beyond_tp2", True))
                if at_or_past and beyond and run_on:
                    pct = Decimal(str(getattr(ms, "perp_ratchet_trailing_pct", 1.0))) / Decimal("100")
                    ref = pos.max_price if pos.max_price is not None else price
                    cand = ref * (Decimal("1") - pct) if is_long else ref * (Decimal("1") + pct)
                    improves = (
                        pos.trailing_stop is None
                        or (is_long and cand > pos.trailing_stop)
                        or (not is_long and cand < pos.trailing_stop)
                    )
                    not_beyond = (cand < price) if is_long else (cand > price)
                    if improves and not_beyond:
                        pos.trailing_stop = cand
                        pos.updated_at = now
                        session.add(pos)
                        logger.info(
                            "ratchet_running_beyond_tp2",
                            asset=pos.asset,
                            price=float(price),
                            tp2=float(pos.take_profit_2),
                            trailing=float(cand),
                            pct=float(pct * 100),
                        )
                elif at_or_past:
                    reason = "take_profit_2"

            if reason is None and not pos.tp1_reached and pos.take_profit_1:
                if (is_long and price >= pos.take_profit_1) or (not is_long and price <= pos.take_profit_1):
                    reason = "take_profit_1"
                    partial = True

            if reason is None and ms.perp_time_stop_enabled and ms.perp_time_stop_hours > 0:
                age_hours = (now - pos.opened_at.replace(tzinfo=pos.opened_at.tzinfo or UTC)).total_seconds() / 3600
                if age_hours >= ms.perp_time_stop_hours:
                    reason = "time_stop"

            if reason:
                exit_price = _level_fill_price(pos, reason, price)
                pnl = await self._close_perp_position(session, pos, exit_price, reason, now, partial=partial)
                margin = pos.entry_price * pos.size / Decimal(max(int(pos.leverage or 1), 1))
                pnl_pct = pnl / margin * 100 if margin > 0 else Decimal("0")
                asyncio.create_task(
                    notifier.notify_trade_closed(
                        user_id=user_id,
                        trade_id=f"cls_{pos.position_id}",
                        asset=pos.asset,
                        market="perp",
                        pnl_usd=pnl,
                        pnl_pct=pnl_pct,
                        close_reason=reason,
                        is_dry_run=ms.execution_mode == "dry_run",
                    )
                )

    async def _update_portfolio_state(
        self,
        session: AsyncSession,
        spot_positions: list,
        perp_positions: list,
        now: datetime,
    ) -> None:
        """Ricalcola equity, drawdown ed esposizione e aggiorna PortfolioState."""
        user_id = str(self.settings.default_user_id)
        pnl_repo = PnlRepository(session)
        portfolio = await pnl_repo.get_portfolio(user_id)
        if portfolio is None:
            return

        unrealized = sum((p.pnl_unrealized for p in spot_positions), Decimal("0")) + sum(
            (p.pnl_unrealized for p in perp_positions), Decimal("0")
        )

        spot_repo = SpotTradeRepository(session)
        perp_repo = PerpTradeRepository(session)
        realized_spot = await spot_repo.sum_realized_pnl(user_id)
        realized_perp = await perp_repo.sum_realized_pnl(user_id)
        realized = realized_spot + realized_perp
        total = portfolio.initial_equity_usd + realized + unrealized

        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        daily_realized_spot = await spot_repo.sum_realized_pnl(user_id, since=day_start)
        daily_realized_perp = await perp_repo.sum_realized_pnl(user_id, since=day_start)
        daily_pnl = daily_realized_spot + daily_realized_perp + unrealized
        # % di PnL giornaliero sull'equity (negativo in perdita) per la guardia daily_loss_limit.
        daily_loss_limit_used_pct = (
            (daily_pnl / total * 100).quantize(Decimal("0.01")) if total > 0 else Decimal("0")
        )

        # Esposizione = capitale impegnato (margine), non il nozionale: per il perp
        # si divide per la leva, così riflette quanto si consuma davvero dell'equity
        # (coerente col risk guard, che ragiona già in margine).
        spot_exposure = sum((p.entry_price * p.size for p in spot_positions), Decimal("0"))
        perp_exposure = sum(
            (p.entry_price * p.size / Decimal(max(int(p.leverage or 1), 1)) for p in perp_positions),
            Decimal("0"),
        )
        raw_exposure_pct = (spot_exposure + perp_exposure) / total * 100 if total > 0 else Decimal("0")
        exposure_pct = raw_exposure_pct.quantize(Decimal("0.01"))

        peak = max(portfolio.peak_equity_usd, total)
        drawdown = (peak - total) / peak * 100 if peak > 0 else Decimal("0")
        drawdown_pct = drawdown.quantize(Decimal("0.01"))
        max_drawdown_pct = max(portfolio.max_drawdown_pct, drawdown_pct)

        spot_count = await spot_repo.count_today(user_id, now)
        perp_count = await perp_repo.count_today(user_id, now)

        await pnl_repo.upsert_portfolio(
            user_id,
            total_equity_usd=total,
            peak_equity_usd=peak,
            drawdown_pct=drawdown_pct,
            max_drawdown_pct=max_drawdown_pct,
            exposure_pct=exposure_pct,
            daily_pnl_usd=daily_pnl,
            daily_loss_limit_used_pct=daily_loss_limit_used_pct,
            agent_status=self.risk.kill_switch.value,
            trades_today=spot_count + perp_count,
        )

    async def _snapshot_portfolio_hourly(self, session: AsyncSession, now: datetime) -> None:
        """Crea un PnlSnapshot ogni ora se non già presente per l'ora corrente."""
        user_id = str(self.settings.default_user_id)
        pnl_repo = PnlRepository(session)
        portfolio = await pnl_repo.get_portfolio(user_id)
        if portfolio is None:
            return

        recent = await pnl_repo.recent_for_user(user_id, limit=1)
        if recent:
            last_ts = recent[0].timestamp_utc
            if last_ts.year == now.year and last_ts.month == now.month and last_ts.day == now.day and last_ts.hour == now.hour:
                return

        open_spot = await SpotPositionRepository(session).open_for_user(user_id)
        open_perp = await PerpPositionRepository(session).open_for_user(user_id)
        spot_equity = sum((p.entry_price * p.size for p in open_spot), Decimal("0"))
        perp_equity = sum((p.entry_price * p.size for p in open_perp), Decimal("0"))

        snapshot = PnlSnapshot(
            user_id=user_id,
            timestamp_utc=now.replace(minute=0, second=0, microsecond=0),
            total_equity_usd=portfolio.total_equity_usd,
            spot_equity_usd=spot_equity,
            perp_equity_usd=perp_equity,
            cash_usd=Decimal("0"),
            drawdown_pct=portfolio.drawdown_pct,
            exposure_pct=portfolio.exposure_pct,
            daily_pnl_usd=portfolio.daily_pnl_usd,
            open_spot_positions=len(open_spot),
            open_perp_positions=len(open_perp),
        )
        await pnl_repo.save_snapshot(snapshot)

    async def slow_tick(self, session: AsyncSession, *, now: datetime | None = None) -> dict:
        """Slow scanner tick plus the hard daily Spot trade heartbeat."""

        heartbeat.beat("agent_slow_tick")
        _now = now or datetime.now(UTC)
        trade_heartbeat = await self._daily_trade_heartbeat(session, now=_now)
        markets = _active_markets(self._ms.markets_enabled)
        # Aggiorna il regime mercato una volta per ciclo, così il flag (e il messaggio
        # in app) riflette sempre lo stato reale anche se nessun segnale prova a entrare.
        if "spot" in markets:
            try:
                await self._spot_market_regime()
            except Exception as exc:
                logger.warning("spot_market_regime_error", error=str(exc))
        if "perp" in markets:
            try:
                await self._btc_trend_shock_filter()
            except Exception as exc:
                logger.warning("btc_trend_shock_filter_error", error=str(exc))
        spot_assets = selected_spot_watchlist(self.settings) if "spot" in markets else []
        perp_assets = selected_perp_watchlist(self.settings) if "perp" in markets else []
        selected_assets = list(dict.fromkeys([*spot_assets, *perp_assets]))
        scanner_results = []
        for asset in spot_assets:
            if asset.upper() not in SPOT_EXCLUDED_STABLECOINS:
                try:
                    scanner_results.append(await self.evaluate_spot(_scanner_payload(asset, "spot"), session))
                except Exception as exc:
                    logger.warning("scanner_spot_asset_error", asset=asset, error=str(exc))
        for asset in perp_assets:
            try:
                scanner_results.append(await self.evaluate_perp(_scanner_payload(asset, "perp"), session))
            except Exception as exc:
                logger.warning("scanner_perp_asset_error", asset=asset, error=str(exc))
        try:
            await self._snapshot_portfolio_hourly(session, _now)
        except Exception as exc:
            logger.warning("snapshot_portfolio_hourly_failed", error=str(exc))
        try:
            await self._maybe_send_daily_summary(session, _now)
        except Exception as exc:
            logger.warning("daily_summary_failed", error=str(exc))
        try:
            await self._maybe_notify_app_update(_now)
        except Exception as exc:
            logger.warning("app_update_check_failed", error=str(exc))
        return {
            "status": "idle" if trade_heartbeat["status"] != "executed" else "heartbeat_trade_executed",
            "reason": "watchlist_empty" if not selected_assets else "watchlist_scanned",
            "markets_enabled": self._ms.markets_enabled,
            "watchlist": selected_assets,
            "scanner_results": [_scanner_summary(result) for result in scanner_results],
            "daily_trade_heartbeat": trade_heartbeat,
        }

    _UPDATE_RELEASES_API = "https://api.github.com/repos/DonBinz81/CryptoSentinelV2/releases/latest"

    async def _maybe_notify_app_update(self, now: datetime) -> None:
        """Push FCM quando esce una nuova release APK: arriva anche ad app chiusa.

        Il check in-app scatta solo con l'app aperta; questo copre il resto.
        Throttle in-memory (update_push_check_minutes, default 15); idempotente per
        tag (notify_update_available salva l'ultimo annunciato in RuntimeState).
        Limite noto: il backend non conosce la versione installata sul telefono,
        quindi al massimo un push ridondante per release se hai già aggiornato."""
        if not getattr(self.settings, "update_push_enabled", True):
            return
        interval_min = int(getattr(self.settings, "update_push_check_minutes", 15) or 15)
        last = getattr(self, "_last_update_check", None)
        if last is not None and (now - last).total_seconds() < interval_min * 60:
            return
        self._last_update_check = now
        import httpx

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                self._UPDATE_RELEASES_API,
                headers={"Accept": "application/vnd.github+json"},
            )
        if resp.status_code != 200:
            logger.debug("app_update_check_http", status=resp.status_code)
            return
        release = resp.json()
        tag = str(release.get("tag_name") or "")
        if not tag:
            return
        sent = await get_agent_notifier().notify_update_available(
            user_id=str(self.settings.default_user_id),
            version_tag=tag,
            release_name=release.get("name"),
        )
        if sent:
            logger.info("app_update_push_sent", version=tag)

    async def _handle_signal(self, signal: dict, session: AsyncSession) -> dict:
        if signal.get("action") == "skip":
            skip_reasoning = _build_skip_reasoning(signal, self.settings)
            risk_decision = RiskDecision(False, f"signal_skipped:{signal.get('reason') or 'skip'}")
            brain_decision = self.brain._local_fallback(
                signal, risk_decision.__dict__, reason_prefix="no_signal_skip"
            )
            decision = await self._record_decision(
                session, signal, risk_decision, brain_decision, override_reasoning=skip_reasoning
            )
            return {
                "signal": signal,
                "risk": risk_decision.__dict__,
                "brain": brain_decision.__dict__,
                "decision_id": decision.decision_id,
                "execution": {"status": "skipped", "reason": signal.get("reason") or "signal_skipped"},
            }

        user_id = str(self.settings.default_user_id)
        now = datetime.now(UTC)

        if await self._in_cooldown(session, signal, now):
            risk_decision = RiskDecision(False, "cooldown_active")
            brain_decision = self.brain._local_fallback(
                signal, risk_decision.__dict__, reason_prefix="cooldown"
            )
            decision = await self._record_decision(session, signal, risk_decision, brain_decision)
            return {
                "signal": signal,
                "risk": risk_decision.__dict__,
                "brain": brain_decision.__dict__,
                "decision_id": decision.decision_id,
                "execution": {"status": "skipped", "reason": "cooldown_active"},
            }

        portfolio = await PnlRepository(session).get_portfolio(user_id)
        if portfolio is None and self._ms.execution_mode == "dry_run":
            portfolio = await _initialise_dry_run_portfolio(session, self.settings)
        spot_positions = await SpotPositionRepository(session).open_for_user(user_id)
        perp_positions = await PerpPositionRepository(session).open_for_user(user_id)
        intent = _intent_from_signal(signal, portfolio_total=Decimal(str(getattr(portfolio, "total_equity_usd", 0) or 0)))
        risk_decision = self.risk.evaluate(
            intent,
            portfolio=portfolio,
            open_spot_positions=spot_positions,
            open_perp_positions=perp_positions,
            ms=self._ms,
        )
        brain_decision = await self._brain_decision(session, signal, risk_decision)
        decision = await self._record_decision(session, signal, risk_decision, brain_decision)
        execution = {"status": "skipped", "reason": "brain_or_risk_blocked"}
        if risk_decision.allowed and brain_decision.allows_execution:
            execution = await self._execute_or_simulate(session, signal, risk_decision, brain_decision)
            decision.execution_result = execution["status"]
            decision.trade_id = execution.get("trade_id")
            await session.commit()
        return {
            "signal": signal,
            "risk": risk_decision.__dict__,
            "brain": brain_decision.__dict__,
            "decision_id": decision.decision_id,
            "execution": execution,
        }

    async def _brain_decision(self, session: AsyncSession, signal: dict, risk_decision) -> object:
        try:
            decision, usage = await self.brain.decide(signal=signal, risk=risk_decision.__dict__)
        except MetaControllerError:
            self.risk.mark_degraded("claude_unavailable")
            decision, usage = await self.brain.decide(
                signal={**signal, "quality": 0},
                risk={"allowed": False, "reason": "claude_unavailable"},
            )
        if usage is not None:
            try:
                await ApiUsageRepository(session).record(
                    model=usage.model,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                )
            except Exception:
                pass  # non bloccare il trade per errori di logging
        return decision

    async def _in_cooldown(self, session: AsyncSession, signal: dict, now: datetime) -> bool:
        """True se esiste un trade recente sull'asset entro la finestra di cooldown."""
        ms = self._ms
        market = signal.get("market", "spot")
        minutes = ms.perp_cooldown_minutes if market == "perp" else ms.spot_cooldown_minutes
        asset = signal.get("asset")
        if minutes <= 0 or not asset:
            return False
        user_id = str(self.settings.default_user_id)
        asset = str(asset)
        spot_ts = await SpotTradeRepository(session).last_timestamp_for_asset(user_id, asset)
        perp_ts = await PerpTradeRepository(session).last_timestamp_for_asset(user_id, asset)
        candidates = [t for t in (spot_ts, perp_ts) if t is not None]
        if not candidates:
            return False
        last_ts = max(candidates)
        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=UTC)
        return (now - last_ts) < timedelta(minutes=minutes)

    async def _record_decision(
        self,
        session: AsyncSession,
        signal: dict,
        risk_decision,
        brain_decision,
        *,
        override_reasoning: str | None = None,
    ) -> AgentDecision:
        reasoning = override_reasoning if override_reasoning is not None else f"{brain_decision.reasoning}; risk={risk_decision.reason}"
        decision = AgentDecision(
            decision_id=f"dec_{uuid4().hex}",
            user_id=str(self.settings.default_user_id),
            timestamp_utc=datetime.now(UTC),
            asset=signal.get("asset"),
            market=str(signal.get("market", "spot")),
            signal_quality=Decimal(str(signal.get("quality", 0))),
            confidence=brain_decision.confidence,
            action=brain_decision.action,
            reasoning=reasoning,
            execution_result=None,
            trade_id=None,
        )
        return await AgentDecisionRepository(session).save(decision)

    async def _execute_or_simulate(self, session: AsyncSession, signal: dict, risk_decision, brain_decision) -> dict:
        # H (v3): size_factor dal segnale (anti-spike reduce_size); default 1.0.
        ms = self._ms
        fixed_perp_margin = signal.get("market") == "perp" and ms.perp_fixed_margin_enabled
        size_factor = Decimal("1") if fixed_perp_margin else Decimal(str(signal.get("size_factor", 1) or 1))
        size_multiplier = Decimal("1") if fixed_perp_margin else brain_decision.size_multiplier
        size_quote = risk_decision.size_quote * size_multiplier * size_factor
        if ms.execution_mode == "dry_run":
            execution = await self._simulate_trade(session, signal, size_quote)
        elif signal.get("market") == "spot":
            # In live i parametri on-chain (token + amount) sono assenti dal segnale:
            # li deriviamo dalla mappa token configurata; se mancano, skip esplicito.
            if signal.get("from_asset") and signal.get("to_asset") and signal.get("amount_in_atomic") is not None:
                swap_params: dict | None = {}
            else:
                swap_params = await self._build_spot_swap_params(signal, size_quote)
            if swap_params is None:
                execution = {"status": "skipped", "reason": "spot_token_not_mapped"}
            else:
                execution = await self._execute_spot({**signal, **swap_params}, size_quote)
        else:
            execution = await self._execute_perp(signal, size_quote)

        if execution.get("trade_id") and execution.get("status") in {"prepared", "confirmed"}:
            asyncio.create_task(self._notify_trade_opened(signal, risk_decision, execution))
        return execution

    def _token_resolver(self) -> CMCProvider | None:
        """Resolver CMC per gli indirizzi token (lazy). None se non configurato."""
        if self._token_resolver_override is not None:
            return self._token_resolver_override
        if self._token_resolver_cached is _UNSET:
            try:
                self._token_resolver_cached = (
                    CMCProvider(self.settings) if getattr(self.settings, "cmc_api_key", None) else None
                )
            except Exception:
                self._token_resolver_cached = None
        return self._token_resolver_cached  # type: ignore[return-value]

    async def _resolve_token_address(self, symbol: str) -> str | None:
        """Indirizzo BSC del token: mappa statica (override) poi risoluzione CMC."""
        entry = self.settings.spot_token_map.get(symbol.upper())
        if entry:
            address, _, _decimals = entry.partition(":")
            if address:
                return address
        resolver = self._token_resolver()
        if resolver is not None:
            return await resolver.resolve_contract_address(symbol)
        return None

    async def _build_spot_swap_params(self, signal: dict, size_quote: Decimal) -> dict | None:
        """Costruisce from_asset/to_asset/amount_in_atomic per lo swap spot live.

        Indirizzi token: mappa statica (override .env) con fallback automatico a CMC.
        Ritorna None se non risolvibili (spot live non eseguibile per quell'asset).
        """
        asset = str(signal.get("asset") or "").upper()
        if not asset:
            return None
        to_address = await self._resolve_token_address(asset)
        if not to_address:
            return None
        quote_address = self.settings.spot_quote_token_address
        quote_decimals = int(self.settings.spot_quote_token_decimals)
        if not quote_address:
            # Quote di default: USDT, risolto via CMC se non configurato esplicitamente.
            quote_address = await self._resolve_token_address("USDT")
        if not quote_address:
            return None
        amount_in_atomic = int(size_quote * (Decimal(10) ** quote_decimals))
        if amount_in_atomic <= 0:
            return None
        return {
            "from_asset": quote_address,
            "to_asset": to_address,
            "amount_in_atomic": amount_in_atomic,
        }

    async def _simulate_trade(self, session: AsyncSession, signal: dict, size_quote: Decimal) -> dict:
        now = datetime.now(UTC)
        trade_id = f"dry_{uuid4().hex}"
        price = Decimal(str(signal.get("price", "0")))
        if price <= 0:
            return {"status": "skipped", "reason": "price_unavailable"}
        if signal.get("market") == "perp":
            side = str(signal.get("side") or "long")
            leverage = int(signal.get("leverage") or self._ms.perp_min_leverage)
            fee_mode = self._ms.perp_fee_mode
            notional_usd = size_quote * Decimal(leverage)

            # Fetch fee e funding da PancakeSwap Perps v2 (fallback a costanti se offline)
            fee_snapshot = await fetch_perp_fees(
                asset=str(signal.get("asset", "")),
                size_usd=notional_usd,
                fee_mode=fee_mode,
            )
            costs = compute_opening_costs(fee_snapshot, notional_usd)

            # Applica slippage al prezzo di entrata (solo taker): l'entry effettivo
            # è peggiore del mark price di una frazione price_impact_pct.
            if fee_mode == "taker" and costs["price_impact_pct"] > 0:
                direction_mult = Decimal("1") if side == "long" else Decimal("-1")
                effective_price = price * (
                    Decimal("1") + direction_mult * costs["price_impact_pct"] / Decimal("100")
                )
            else:
                effective_price = price

            # size = contratti controllati: capitale * leva / prezzo effettivo
            leveraged_size = size_quote * Decimal(leverage) / effective_price
            stop_ref = _stop_reference_from_signal(signal)

            await PerpTradeRepository(session).save(
                PerpTrade(
                    trade_id=trade_id,
                    user_id=str(self.settings.default_user_id),
                    asset=str(signal.get("asset")),
                    side=side,
                    direction="open",
                    size=leveraged_size,
                    price=effective_price,
                    leverage=leverage,
                    status=ExecutionStatus.PREPARED.value,
                    timestamp_utc=now,
                    venue="dry_run",
                    signal_id=signal.get("signal_id"),
                    notes="dry_run_step6",
                    fee_mode=fee_mode,
                    taker_fee_usd=costs["taker_fee_usd"],
                    maker_fee_usd=costs["maker_fee_usd"],
                    slippage_usd=costs["slippage_usd"],
                    funding_rate_8h=costs["funding_rate_8h"],
                    fees_quote=costs["applied_fee_usd"],
                    slippage_pct=costs["price_impact_pct"],
                )
            )
            await PerpPositionRepository(session).save(
                PerpPosition(
                    position_id=f"pos_{uuid4().hex}",
                    user_id=str(self.settings.default_user_id),
                    asset=str(signal.get("asset")),
                    side=side,
                    size=leveraged_size,
                    entry_price=effective_price,
                    current_price=effective_price,
                    leverage=leverage,
                    stop_loss=_optional_decimal(signal.get("stop_loss")),
                    initial_stop_loss=_optional_decimal(signal.get("stop_loss")),
                    take_profit_1=_optional_decimal(signal.get("take_profit_1")),
                    take_profit_2=_optional_decimal(signal.get("take_profit_2")),
                    trailing_stop=_optional_decimal(signal.get("trailing_stop")),
                    # Congelati all'ingresso per breakeven + trailing dinamico.
                    entry_atr=_optional_decimal((signal.get("components") or {}).get("atr")),
                    stop_reference_time=stop_ref["time"],
                    stop_reference_price=stop_ref["price"],
                    stop_reference_field=stop_ref["field"],
                    max_price=effective_price,
                    liquidation_price=_estimate_liquidation_price(effective_price, leverage, side),
                    funding_rate=costs["funding_rate_8h"],
                    fee_mode=fee_mode,
                    margin_usd=size_quote,
                    opening_fee_usd=costs["applied_fee_usd"],
                    taker_fee_usd=costs["taker_fee_usd"],
                    maker_fee_usd=costs["maker_fee_usd"],
                    slippage_usd=costs["slippage_usd"],
                    funding_accrued_usd=Decimal("0"),
                    venue="dry_run",
                    open_trade_id=trade_id,
                    opened_at=now,
                    updated_at=now,
                )
            )
            return {"status": "prepared", "mode": "dry_run", "trade_id": trade_id}

        spot_fee_mode = self._ms.spot_fee_mode
        spot_costs = compute_spot_costs(size_quote, spot_fee_mode)

        # Applica slippage al prezzo di acquisto (buy a prezzo leggermente peggiore)
        if spot_fee_mode == "all" and spot_costs["slippage_rate"] > 0:
            effective_spot_price = price * (Decimal("1") + spot_costs["slippage_rate"])
        else:
            effective_spot_price = price

        spot_amount = size_quote / effective_spot_price
        stop_ref = _stop_reference_from_signal(signal)

        await SpotTradeRepository(session).save(
            SpotTrade(
                trade_id=trade_id,
                user_id=str(self.settings.default_user_id),
                asset=str(signal.get("asset")),
                side="buy",
                amount=spot_amount,
                price=effective_spot_price,
                amount_quote=size_quote,
                status=ExecutionStatus.PREPARED.value,
                provider="dry_run",
                timestamp_utc=now,
                signal_id=signal.get("signal_id"),
                notes="dry_run_step6",
                fee_mode=spot_fee_mode,
                swap_fee_usd=spot_costs["swap_fee_usd"],
                slippage_usd=spot_costs["slippage_usd"],
                fees_quote=spot_costs["applied_fee_usd"],
            )
        )
        await SpotPositionRepository(session).save(
            SpotPosition(
                position_id=f"pos_{uuid4().hex}",
                user_id=str(self.settings.default_user_id),
                asset=str(signal.get("asset")),
                size=spot_amount,
                entry_price=effective_spot_price,
                current_price=effective_spot_price,
                stop_loss=_optional_decimal(signal.get("stop_loss")),
                initial_stop_loss=_optional_decimal(signal.get("stop_loss")),
                take_profit_1=_optional_decimal(signal.get("take_profit_1")),
                take_profit_2=_optional_decimal(signal.get("take_profit_2")),
                trailing_stop=_optional_decimal(signal.get("trailing_stop")),
                # C (v3): ATR congelato all'ingresso + max_price per breakeven/trailing ATR.
                entry_atr=_optional_decimal((signal.get("components") or {}).get("atr")),
                stop_reference_time=stop_ref["time"],
                stop_reference_price=stop_ref["price"],
                stop_reference_field=stop_ref["field"],
                max_price=effective_spot_price,
                fee_mode=spot_fee_mode,
                swap_fee_usd=spot_costs["swap_fee_usd"],
                slippage_usd=spot_costs["slippage_usd"],
                open_trade_id=trade_id,
                opened_at=now,
                updated_at=now,
            )
        )
        return {"status": "prepared", "mode": "dry_run", "trade_id": trade_id}

    async def _execute_spot(self, signal: dict, size_quote: Decimal) -> dict:
        if not self.settings.wallet_address:
            return {"status": "skipped", "reason": "wallet_address_missing"}
        from_asset = signal.get("from_asset")
        to_asset = signal.get("to_asset")
        if not from_asset or not to_asset:
            return {"status": "skipped", "reason": "spot_asset_addresses_required"}
        amount_in_atomic = signal.get("amount_in_atomic")
        if amount_in_atomic is None:
            return {"status": "skipped", "reason": "spot_amount_in_atomic_required"}
        quote = await self.spot_registry.active.get_quote(
            amount_in_atomic=int(amount_in_atomic),
            from_asset=str(from_asset),
            to_asset=str(to_asset),
            wallet_address=self.settings.wallet_address,
            slippage_pct=Decimal(str(self._ms.spot_max_slippage_pct)),
        )
        return {"status": "prepared", "provider": self.spot_registry.active_name.value, "quote": quote.model_dump()}

    async def _execute_perp(self, signal: dict, size_quote: Decimal) -> dict:
        order = PerpOrder(
            asset=str(signal.get("asset")),
            direction=str(signal.get("side") or "long"),  # type: ignore[arg-type]
            size=size_quote,
            leverage=Decimal(str(signal.get("leverage") or self._ms.perp_min_leverage)),
        )
        result = await self.perp_registry.active.open_position(order)
        return {"status": result.status.value, "provider": self.perp_registry.active_name.value, "reason": result.reason}

    async def _daily_trade_heartbeat(self, session: AsyncSession, *, now: datetime | None = None) -> dict:
        now = now or datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        now = now.astimezone(UTC)
        user_id = str(self.settings.default_user_id)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        trades_today = await SpotTradeRepository(session).count_since(user_id, since=day_start)
        if trades_today >= self.settings.minimum_trades_per_day:
            return {
                "status": "satisfied",
                "trades_today": trades_today,
                "check_after_utc": DAILY_TRADE_CHECK_TIME_UTC.isoformat(),
                "retry_until_utc": DAILY_TRADE_RETRY_UNTIL_UTC.isoformat(),
            }
        current_time = now.timetz()
        if current_time < DAILY_TRADE_CHECK_TIME_UTC:
            return {
                "status": "waiting",
                "trades_today": trades_today,
                "check_after_utc": DAILY_TRADE_CHECK_TIME_UTC.isoformat(),
                "retry_until_utc": DAILY_TRADE_RETRY_UNTIL_UTC.isoformat(),
            }
        if current_time > DAILY_TRADE_RETRY_UNTIL_UTC:
            return {
                "status": "missed",
                "trades_today": trades_today,
                "reason": "daily_trade_retry_window_closed",
                "check_after_utc": DAILY_TRADE_CHECK_TIME_UTC.isoformat(),
                "retry_until_utc": DAILY_TRADE_RETRY_UNTIL_UTC.isoformat(),
            }
        if self.risk.kill_switch != KillSwitchState.RUNNING:
            return {
                "status": "blocked",
                "trades_today": trades_today,
                "reason": self.risk.kill_switch.value,
                "retry_until_utc": DAILY_TRADE_RETRY_UNTIL_UTC.isoformat(),
            }
        # Dedup: se ETH e' gia' in posizione (spot o perp), non forzare un secondo trade.
        open_spot = await SpotPositionRepository(session).open_for_user(user_id)
        open_perp = await PerpPositionRepository(session).open_for_user(user_id)
        if any(p.asset.upper() == HEARTBEAT_TRADE_ASSET for p in (*open_spot, *open_perp)):
            return {
                "status": "satisfied",
                "trades_today": trades_today,
                "reason": "asset_already_open",
                "retry_until_utc": DAILY_TRADE_RETRY_UNTIL_UTC.isoformat(),
            }
        # Prezzo live via feed riusato; SL/TP derivati dal segnale momentum reale.
        heartbeat_price = HEARTBEAT_TRADE_PRICE_USD_FALLBACK
        try:
            ticker = await self.price_feed.fetch_prices(
                symbols=[f"{HEARTBEAT_TRADE_ASSET}USDT"], market="spot"
            )
            heartbeat_price = ticker.get(f"{HEARTBEAT_TRADE_ASSET}USDT", heartbeat_price)
        except Exception:
            pass
        sl = tp1 = tp2 = trailing = None
        try:
            momentum = await self.spot_signal.evaluate(_scanner_payload(HEARTBEAT_TRADE_ASSET, "spot"))
            if momentum.get("price"):
                heartbeat_price = Decimal(str(momentum["price"]))
            sl = _optional_decimal(momentum.get("stop_loss"))
            tp1 = _optional_decimal(momentum.get("take_profit_1"))
            tp2 = _optional_decimal(momentum.get("take_profit_2"))
            trailing = _optional_decimal(momentum.get("trailing_stop"))
        except Exception:
            pass
        # Fallback: livelli di default se il segnale non li ha forniti (es. storico insufficiente).
        if sl is None:
            sl = heartbeat_price * Decimal("0.98")
        if tp1 is None:
            tp1 = heartbeat_price * Decimal("1.03")
        if tp2 is None:
            tp2 = heartbeat_price * Decimal("1.06")
        if trailing is None:
            trailing = heartbeat_price * Decimal("0.98")
        signal = {
            "signal_id": f"heartbeat_{now.date().isoformat()}",
            "market": "spot",
            "asset": HEARTBEAT_TRADE_ASSET,
            "action": "enter_long",
            "quality": 0.86,
            "confidence": 0.86,
            "price": heartbeat_price,
            "stop_loss": sl,
            "take_profit_1": tp1,
            "take_profit_2": tp2,
            "trailing_stop": trailing,
            "quote_equity": Decimal(str(self.settings.dry_run_capital_usd)),
            "heartbeat_trade": True,
        }
        heartbeat_trade_quote_usd = max(Decimal(str(self.settings.min_trade_size_usd)), Decimal("1"))
        if self._ms.execution_mode == "dry_run":
            execution = await self._simulate_trade(session, signal, heartbeat_trade_quote_usd)
            return {
                "status": "executed",
                "mode": "dry_run",
                "trades_today_before": trades_today,
                "execution": execution,
                "retry_until_utc": DAILY_TRADE_RETRY_UNTIL_UTC.isoformat(),
            }
        from_asset = getattr(self.settings, "heartbeat_trade_from_asset", None)
        to_asset = getattr(self.settings, "heartbeat_trade_to_asset", None)
        amount_in_atomic = getattr(self.settings, "heartbeat_trade_amount_in_atomic", None)
        if not from_asset or not to_asset or amount_in_atomic is None:
            return {
                "status": "blocked",
                "trades_today": trades_today,
                "reason": "heartbeat_trade_live_route_not_configured",
                "retry_until_utc": DAILY_TRADE_RETRY_UNTIL_UTC.isoformat(),
            }
        execution = await self._execute_spot(
            {**signal, "from_asset": from_asset, "to_asset": to_asset, "amount_in_atomic": amount_in_atomic},
            heartbeat_trade_quote_usd,
        )
        return {
            "status": "executed" if execution.get("status") in {"prepared", "confirmed"} else "blocked",
            "mode": self._ms.execution_mode,
            "trades_today_before": trades_today,
            "execution": execution,
            "retry_until_utc": DAILY_TRADE_RETRY_UNTIL_UTC.isoformat(),
        }

    # ------------------------------------------------------------------
    # Integrazione notifiche agente
    # ------------------------------------------------------------------

    async def _notify_trade_opened(self, signal: dict, risk_decision, execution: dict) -> None:
        """Fire-and-forget notifica apertura trade; mai blocca l'agente."""
        try:
            notifier = get_agent_notifier()
            market = str(signal.get("market", "spot"))
            await notifier.notify_trade_opened(
                user_id=str(self.settings.default_user_id),
                trade_id=execution["trade_id"],
                asset=str(signal.get("asset", "")),
                market=market,
                direction=str(signal.get("side") or signal.get("action") or "buy"),
                entry_price=Decimal(str(signal.get("price", "0"))),
                size_usd=risk_decision.size_quote,
                stop_loss=_optional_decimal(signal.get("stop_loss")),
                is_dry_run=self._ms.execution_mode == "dry_run",
            )
        except Exception:
            pass  # le notifiche non bloccano mai l'agente

    async def _check_risk_notifications(self, session: AsyncSession, spot_positions: list, perp_positions: list) -> None:
        """Controlla condizioni di rischio e invia push se necessario."""
        try:
            user_id = str(self.settings.default_user_id)
            portfolio = await PnlRepository(session).get_portfolio(user_id)
            if portfolio is None:
                return
            notifier = get_agent_notifier()

            # Kill switch attivo
            if self.risk.kill_switch != KillSwitchState.RUNNING:
                await notifier.notify_risk_alert(
                    user_id, "kill_switch",
                    f"Kill switch: {self.risk.kill_switch.value}"
                )
                return

            # Drawdown
            drawdown = float(getattr(portfolio, "drawdown_pct", 0) or 0)
            if self.settings.risk_drawdown_alert_enabled and drawdown >= self.settings.risk_notify_drawdown_pct:
                await notifier.notify_risk_alert(
                    user_id, "drawdown",
                    f"Drawdown {drawdown:.1f}% supera soglia {self.settings.risk_notify_drawdown_pct:.0f}%"
                )

            # Portfolio floor
            equity = float(getattr(portfolio, "total_equity_usd", 1) or 1)
            if equity < 1.0:
                await notifier.notify_risk_alert(user_id, "portfolio_floor", "Equity < $1.00")
        except Exception:
            pass  # le notifiche non bloccano mai l'agente

    async def _maybe_send_daily_summary(self, session: AsyncSession, now: datetime) -> None:
        """Invia riepilogo giornaliero una volta al giorno all'ora configurata."""
        try:
            target_h = self.settings.agent_summary_hour_utc
            target_m = self.settings.agent_summary_minute_utc
            if now.hour != target_h or now.minute != target_m:
                return
            user_id = str(self.settings.default_user_id)
            # Anti-spam: verifica se già inviato oggi
            today_key = f"summary_sent_{now.date().isoformat()}"
            if get_runtime_value(user_id, today_key):
                return

            portfolio = await PnlRepository(session).get_portfolio(user_id)
            spot_today = await SpotTradeRepository(session).count_today(user_id, now)
            perp_today = await PerpTradeRepository(session).count_today(user_id, now)

            notifier = get_agent_notifier()
            daily_pnl = Decimal(str(getattr(portfolio, "daily_pnl_usd", "0") or "0")) if portfolio else Decimal("0")
            await notifier.notify_daily_summary(
                user_id=user_id,
                spot_trades=spot_today,
                perp_trades=perp_today,
                daily_pnl_usd=daily_pnl,
                win_rate_pct=0.0,
            )
            set_runtime_value(user_id, today_key, "1")
        except Exception:
            pass  # le notifiche non bloccano mai l'agente


def _intent_from_signal(signal: dict, *, portfolio_total: Decimal) -> SignalIntent:
    return SignalIntent(
        asset=str(signal.get("asset") or ""),
        market=str(signal.get("market") or "spot"),
        side=str(signal.get("side") or signal.get("action") or ""),
        price=Decimal(str(signal.get("price") or "0")),
        stop_loss=_optional_decimal(signal.get("stop_loss")),
        quality=Decimal(str(signal.get("quality") or "0")),
        quote_equity=Decimal(str(signal.get("quote_equity") or portfolio_total or "0")),
        liquidity_usd=_optional_decimal(signal.get("liquidity_usd")),
        leverage=max(int(signal.get("leverage") or 1), 1),  # FIX-1
    )


def _optional_decimal(value) -> Decimal | None:
    if value is None:
        return None
    parsed = Decimal(str(value))
    return parsed if parsed > 0 else None


def _stop_reference_from_signal(signal: dict) -> dict[str, datetime | Decimal | str | None]:
    ref = (signal.get("components") or {}).get("stop_reference")
    if not isinstance(ref, dict):
        return {"time": None, "price": None, "field": None}
    parsed_time = None
    try:
        raw_time = ref.get("timestamp")
        if raw_time:
            parsed_time = datetime.fromisoformat(str(raw_time))
            if parsed_time.tzinfo is None:
                parsed_time = parsed_time.replace(tzinfo=UTC)
            parsed_time = parsed_time.astimezone(UTC)
    except Exception:
        parsed_time = None
    parsed_price = _optional_decimal(ref.get("price"))
    field = str(ref.get("field") or "")[:8] or None
    return {"time": parsed_time, "price": parsed_price, "field": field}


def _ratchet_progress(tp1: Decimal, tp2: Decimal, extreme: Decimal, is_long: bool) -> Decimal | None:
    """Quota del tratto TP1→TP2 percorsa dall'estremo favorevole, clampata in [0,1].

    Il ratchet entra in gioco solo dopo il TP1, quindi lo spazio rilevante è quello che
    resta da percorrere. Misurando dall'entry, con TP1 a 2,5 ATR e TP2 a 4,0 il progresso
    varrebbe già 62,5% appena toccato il TP1 e ogni scalino sotto quella quota scatterebbe
    tutto insieme. Usa l'estremo (max_price long / min short), non il prezzo corrente →
    monotono e immune alle spike. None se il tratto non è definito.
    """
    if tp1 is None or tp2 is None or extreme is None:
        return None
    span = (tp2 - tp1) if is_long else (tp1 - tp2)
    if span <= 0:
        return None
    fav = (extreme - tp1) if is_long else (tp1 - extreme)
    return max(Decimal("0"), min(Decimal("1"), fav / span))


def _ratchet_level(progress: Decimal, steps) -> tuple[int, Decimal]:
    """Ultimo scalino raggiunto e quota CUMULATIVA del residuo da aver chiuso.

    steps = [(soglia_sul_tratto, quota_cumulativa_da_chiudere), ...] crescenti.
    Ritorna (indice, quota); (-1, 0) se non è stato raggiunto nemmeno il primo.
    """
    idx, cum = -1, Decimal("0")
    for i, pair in enumerate(steps):
        thr, frac = Decimal(str(pair[0])), Decimal(str(pair[1]))
        if progress >= thr:
            idx, cum = i, frac
    return idx, cum


def _ratchet_breakeven_price(tp1: Decimal, tp2: Decimal, pct: Decimal, is_long: bool) -> Decimal:
    """Prezzo del 'breakeven del ratchet': punto fisso a `pct` del tratto TP1→TP2."""
    return (tp1 + pct * (tp2 - tp1)) if is_long else (tp1 - pct * (tp1 - tp2))


def _level_fill_price(pos, reason: str, market_price: Decimal) -> Decimal:
    """Prezzo di fill per le chiusure su livello.

    Uno stop/TP/trailing riempie al PROPRIO livello, non al prezzo di mercato:
    se il refresh è in ritardo (feed instabile, prezzo non aggiornato per più
    cicli) il mercato può aver superato di molto il livello, e chiudere a quel
    prezzo gonfia la perdita ben oltre il rischio realmente assunto (critico con
    leva alta). Le chiusure NON su livello (time_stop, manuali) usano il mercato.
    """
    level = None
    if reason == "stop_loss":
        level = pos.stop_loss
    elif reason == "breakeven":
        # Breakeven comes from stop_loss moved to entry/costs. Trailing keeps
        # reason="trailing_stop", even when the trailing level is profitable.
        level = pos.stop_loss
    elif reason in ("trailing_stop", "profit_lock"):
        # Il profit lock scrive lo stop protettivo su trailing_stop, come il trailing.
        level = pos.trailing_stop
    elif reason == "take_profit_1":
        level = pos.take_profit_1
    elif reason == "take_profit_2":
        level = pos.take_profit_2
    if level is None:
        return market_price
    return Decimal(str(level))


def _perp_trailing_mult(
    *, leverage: int, min_lev: int, max_lev: int, base: float, floor: float
) -> Decimal:
    """Moltiplicatore ATR del trailing perp, dinamico sulla leva del trade.

    Interpola linearmente tra `base` (a leva minima → trailing largo) e `floor`
    (a leva massima → trailing stretto): più alta la leva, più stretto il trailing
    in prezzo, così non si restituisce il profitto amplificato dalla leva. Il
    floor resta sopra il rumore (ATR) per evitare il whipsaw.
    """
    lo = min(min_lev, max_lev)
    hi = max(min_lev, max_lev)
    if hi <= lo:
        t = 0.0
    else:
        t = (leverage - lo) / (hi - lo)
        t = min(1.0, max(0.0, t))
    mult = base - t * (base - floor)
    return Decimal(str(mult))


async def _initialise_dry_run_portfolio(session: AsyncSession, settings: Settings):
    capital = Decimal(str(settings.dry_run_capital_usd))
    return await PnlRepository(session).upsert_portfolio(
        str(settings.default_user_id),
        total_equity_usd=capital,
        initial_equity_usd=capital,
        peak_equity_usd=capital,
        agent_status="idle",
    )


def _active_markets(value: str) -> set[str]:
    normalized = value.lower()
    if normalized == "spot":
        return {"spot"}
    if normalized in {"perp", "perpetual"}:
        return {"perp"}
    return {"spot", "perp"}


def _scanner_payload(asset: str, market: str) -> dict:
    symbol = f"{asset.upper()}USDT"
    return {
        "signal_id": f"scan_{market}_{asset.upper()}_{uuid4().hex[:12]}",
        "market": market,
        "asset": asset.upper(),
        "symbol": symbol,
        "quote_asset": "USDT",
    }


def _scanner_summary(result: dict) -> dict:
    signal = result.get("signal") or {}
    risk = result.get("risk") or {}
    execution = result.get("execution") or {}
    return {
        "asset": signal.get("asset"),
        "market": signal.get("market"),
        "action": signal.get("action"),
        "reason": signal.get("reason") or risk.get("reason") or execution.get("reason"),
        "risk_allowed": risk.get("allowed"),
        "execution_status": execution.get("status"),
    }


def _build_skip_reasoning(signal: dict, settings) -> str:
    """Costruisce un reasoning leggibile per i segnali skippati, con valori reali e threshold."""
    reason = signal.get("reason") or "skip"
    components = signal.get("components") or {}
    quality = float(signal.get("quality") or 0)
    price = float(signal.get("price") or 0)

    def _ok(cond: bool) -> str:
        return "✓" if cond else "✗"

    if reason == "spot_filters_not_satisfied":
        trend = float(components.get("trend_structure") or 0)
        rvol = float(components.get("relative_volume") or 0)
        vol_pct = float(components.get("volatility_pct") or 0)
        rsi_v = components.get("rsi")
        ext = float(components.get("vwap_atr_extension") or 0)
        ext_ok = bool(components.get("extension_ok", True))
        thr_rvol = float(settings.spot_relative_volume_threshold)
        thr_vol = float(settings.spot_volatility_trigger_pct)
        thr_ext = float(settings.spot_vwap_atr_extension_limit)
        thr_q = float(settings.spot_confidence_threshold)
        parts = [
            f"trend={trend:.2f}{_ok(trend >= 0.45)}",
            f"rvol={rvol:.2f}{_ok(rvol >= thr_rvol)}(≥{thr_rvol})",
            f"vol%={vol_pct:.2f}{_ok(vol_pct >= thr_vol)}(≥{thr_vol})",
            f"ext={ext:.2f}{_ok(ext_ok)}(≤{thr_ext})",
        ]
        if rsi_v is not None:
            parts.append(f"rsi={float(rsi_v):.0f}{_ok(45 <= float(rsi_v) <= 72)}(45-72)")
        parts.append(f"q={quality:.2f}{_ok(quality >= thr_q)}(≥{thr_q})")
        return "spot_skip: " + " | ".join(parts)

    if reason == "perp_filters_not_satisfied":
        poc = components.get("poc")
        vah = components.get("vah")
        val = components.get("val")
        vwap_v = components.get("vwap")
        trend_bias = components.get("trend_bias", "?")
        side = signal.get("side")
        parts = [
            f"price={price:.5g}",
            f"poc={poc:.5g}" if poc else "poc=?",
            f"val={val:.5g}" if val else "val=?",
            f"vah={vah:.5g}" if vah else "vah=?",
            f"vwap={vwap_v:.5g}" if vwap_v else "vwap=?",
            f"bias={trend_bias}",
            f"side={side or 'none'}",
            f"q={quality:.2f}(≥0.60)",
        ]
        return "perp_skip: " + " | ".join(parts)

    if reason == "insufficient_ohlcv_history":
        count = components.get("candle_count", "?")
        req = components.get("required_candles", "?")
        return f"skip: {count}/{req} candele disponibili"

    return f"skip: {reason}"


def _coverage_item(
    *,
    asset: str,
    market: str,
    symbol: str,
    required_candles: int,
    source: str,
    cache_market: BinanceMarket,
    now: datetime,
    interval: str = "5m",
) -> dict:
    entry = get_kline_cache_entry(market=cache_market, symbol=symbol, interval=interval)
    candles = entry.candles if entry else []
    candle_count = len(candles)
    first_timestamp = candles[0].timestamp if candles else None
    last_timestamp = candles[-1].timestamp if candles else None
    updated_at = entry.updated_at if entry else None
    if candle_count >= required_candles:
        status = "ready"
    elif candle_count > 0:
        status = "warming_up"
    else:
        status = "insufficient"
    return {
        "asset": asset,
        "market": market,
        "symbol": symbol,
        "available_candles": candle_count,
        "required_candles": required_candles,
        "status": status,
        "first_candle_at": first_timestamp.isoformat() if first_timestamp else None,
        "last_candle_at": last_timestamp.isoformat() if last_timestamp else None,
        "updated_at": updated_at.isoformat() if updated_at else None,
        "age_seconds": round((now - updated_at).total_seconds(), 2) if updated_at else None,
        "source": source,
    }


@lru_cache
def get_agent_service() -> AgentService:
    return AgentService(get_settings())


async def run_agent_fast_tick() -> dict:
    async with get_session_factory()() as session:
        return await get_agent_service().fast_tick(session)


async def run_agent_slow_tick() -> dict:
    async with get_session_factory()() as session:
        return await get_agent_service().slow_tick(session)
