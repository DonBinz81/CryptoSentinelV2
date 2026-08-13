"""Read-side query service that assembles dashboard views from the DB."""

from __future__ import annotations

import json
from collections import OrderedDict
from datetime import UTC, datetime
from decimal import Decimal
from math import sqrt
from statistics import mean, stdev

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.persistence.runtime_state import get_runtime_value

from backend.app.persistence.repositories.pnl import PnlRepository
from backend.app.persistence.repositories.positions import (
    PerpPositionRepository,
    SpotPositionRepository,
)
from backend.app.persistence.repositories.trades import (
    PerpTradeRepository,
    SpotTradeRepository,
)
from backend.app.schemas.views import (
    GlobalView,
    PerpPositionView,
    PerpTradeView,
    PerpView,
    PnlPoint,
    RiskGuardrailView,
    SpotPositionView,
    SpotTradeView,
    SpotView,
)


def _market_risk_off(user_id: str) -> bool:
    """Legge il flag regime mercato persistito dall'agente (vedi service._spot_market_regime)."""
    raw = get_runtime_value(user_id, "spot_market_regime")
    if not raw:
        return False
    try:
        return bool(json.loads(raw).get("risk_off", False))
    except (ValueError, AttributeError):
        return False


def _smart_sl_view_fields(pos) -> dict:
    raw = getattr(pos, "smart_sl_state", None)
    if not raw:
        return {"smart_sl_active": False, "smart_sl_levels_sold": None}
    try:
        state = json.loads(raw)
        levels = state.get("levels", [])
        sold = [lv.get("status") == "sold" for lv in levels]
        return {"smart_sl_active": True, "smart_sl_levels_sold": sold}
    except (ValueError, KeyError):
        return {"smart_sl_active": False, "smart_sl_levels_sold": None}


class ViewService:
    """Assembles the Spot / Perp / Global dashboard payloads."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        drawdown_cap_pct: float = -15.0,
        daily_loss_limit_pct: float = -8.0,
        min_portfolio_value_usd: float = 5.0,
        base_equity_usd: Decimal | float | str = Decimal("0"),
    ) -> None:
        self._session = session
        self._drawdown_cap_pct = drawdown_cap_pct
        self._daily_loss_limit_pct = daily_loss_limit_pct
        self._min_portfolio_value_usd = min_portfolio_value_usd
        self._base_equity_usd = Decimal(str(base_equity_usd))

    async def _bot_active_days(self, user_id: str) -> int:
        spot_first = await SpotTradeRepository(self._session).first_timestamp_for_user(user_id)
        perp_first = await PerpTradeRepository(self._session).first_timestamp_for_user(user_id)
        candidates = [ts for ts in (spot_first, perp_first) if ts is not None]
        if not candidates:
            return 0
        first_ts = min(candidates)
        if first_ts.tzinfo is None:
            first_ts = first_ts.replace(tzinfo=UTC)
        return max(1, (datetime.now(UTC).date() - first_ts.date()).days + 1)

    async def spot_view(self, user_id: str) -> SpotView:
        pos_repo = SpotPositionRepository(self._session)
        trade_repo = SpotTradeRepository(self._session)
        positions = await pos_repo.open_for_user(user_id)
        history_trades = await trade_repo.list_closed_for_user(user_id)
        win = await trade_repo.win_rate(user_id)
        unrealized = sum((p.pnl_unrealized for p in positions), Decimal("0"))
        realized = await trade_repo.sum_realized_pnl(user_id)
        from datetime import UTC, datetime as _dt
        day_start_spot = _dt.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        spot_trade_count_tot = await trade_repo.count_closed(user_id)
        spot_trade_count_today = await trade_repo.count_closed(user_id, since=day_start_spot)
        bot_active_days = await self._bot_active_days(user_id)
        return SpotView(
            market_risk_off=_market_risk_off(user_id),
            open_positions=[
                SpotPositionView(
                    position_id=p.position_id,
                    open_trade_id=p.open_trade_id,
                    asset=p.asset,
                    size=p.size,
                    entry_price=p.entry_price,
                    current_price=p.current_price,
                    pnl_unrealized=p.pnl_unrealized,
                    pnl_pct=_position_pnl_pct(p.pnl_unrealized, p.entry_price, p.size),
                    stop_loss=p.stop_loss,
                    take_profit_1=p.take_profit_1,
                    take_profit_2=p.take_profit_2,
                    fee_mode=p.fee_mode,
                    swap_fee_usd=p.swap_fee_usd,
                    slippage_usd=p.slippage_usd,
                    status=p.status,
                    opened_at=p.opened_at.isoformat(),
                )
                for p in positions
            ],
            history=[
                SpotTradeView(
                    trade_id=t.trade_id,
                    asset=t.asset,
                    side=t.side,
                    amount=t.amount,
                    price=t.price,
                    pnl_usd=_fmt_pnl(t.pnl_usd),
                    pnl_pct=_pnl_pct_str(t.pnl_usd, _spot_trade_entry_price(t), t.amount),
                    entry_price=_spot_trade_entry_price(t),
                    current_or_exit_price=t.price,
                    status=t.status,
                    close_reason=_close_reason(t),
                    tx_hash=t.tx_hash,
                    timestamp_utc=t.timestamp_utc.isoformat(),
                    block_timestamp_utc=t.block_timestamp_utc.isoformat() if t.block_timestamp_utc else None,
                    is_simulated=_is_spot_dry_run(t),
                )
                for t in history_trades
            ],
            realized_pnl_usd=realized,
            unrealized_pnl_usd=unrealized,
            win_rate_pct=win["win_rate_pct"],
            trade_count=spot_trade_count_tot,
            trade_count_today=spot_trade_count_today,
            bot_active_days=bot_active_days,
        )

    async def perp_view(self, user_id: str) -> PerpView:
        pos_repo = PerpPositionRepository(self._session)
        trade_repo = PerpTradeRepository(self._session)
        positions = await pos_repo.open_for_user(user_id)
        history_trades = await trade_repo.list_closed_for_user(user_id)
        win = await trade_repo.win_rate(user_id)
        unrealized = sum((p.pnl_unrealized for p in positions), Decimal("0"))
        realized = await trade_repo.sum_realized_pnl(user_id)
        history_positions = await pos_repo.history_for_user(user_id, limit=200)
        entry_by_position_id = {p.position_id: p.entry_price for p in history_positions}
        from datetime import UTC, datetime as _dt
        day_start = _dt.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        trade_count_tot = await trade_repo.count_closed(user_id)
        trade_count_today = await trade_repo.count_closed(user_id, since=day_start)
        bot_active_days = await self._bot_active_days(user_id)
        return PerpView(
            open_positions=[
                PerpPositionView(
                    position_id=p.position_id,
                    open_trade_id=p.open_trade_id,
                    asset=p.asset,
                    side=p.side,
                    size=p.size,
                    entry_price=p.entry_price,
                    current_price=p.current_price,
                    leverage=p.leverage,
                    pnl_unrealized=p.pnl_unrealized,
                    pnl_pct=_position_pnl_pct(p.pnl_unrealized, p.entry_price, p.size, p.leverage),
                    stop_loss=p.stop_loss,
                    take_profit_1=p.take_profit_1,
                    take_profit_2=p.take_profit_2,
                    liquidation_price=p.liquidation_price,
                    funding_rate=p.funding_rate,
                    fee_mode=p.fee_mode,
                    margin_usd=p.margin_usd,
                    opening_fee_usd=p.opening_fee_usd,
                    taker_fee_usd=p.taker_fee_usd,
                    maker_fee_usd=p.maker_fee_usd,
                    slippage_usd=p.slippage_usd,
                    funding_accrued_usd=p.funding_accrued_usd,
                    **_smart_sl_view_fields(p),
                    status=p.status,
                    opened_at=p.opened_at.isoformat(),
                )
                for p in positions
            ],
            history=[
                PerpTradeView(
                    trade_id=t.trade_id,
                    position_id=_perp_trade_position_id(t, history_positions),
                    asset=t.asset,
                    side=t.side,
                    direction=t.direction,
                    size=t.size,
                    price=t.price,
                    pnl_usd=_fmt_pnl(t.pnl_usd),
                    pnl_pct=_pnl_pct_str(
                        t.pnl_usd,
                        _perp_trade_entry_price(t, entry_by_position_id),
                        t.size,
                        t.leverage or 1,
                    ),
                    entry_price=_perp_trade_entry_price(t, entry_by_position_id),
                    current_or_exit_price=t.price,
                    leverage=t.leverage,
                    status=t.status,
                    close_reason=_close_reason(t),
                    tx_hash=t.tx_hash,
                    timestamp_utc=t.timestamp_utc.isoformat(),
                    block_timestamp_utc=t.block_timestamp_utc.isoformat() if t.block_timestamp_utc else None,
                    is_simulated=_is_perp_dry_run(t),
                )
                for t in history_trades
            ],
            realized_pnl_usd=realized,
            unrealized_pnl_usd=unrealized,
            win_rate_pct=win["win_rate_pct"],
            trade_count=trade_count_tot,
            trade_count_today=trade_count_today,
            bot_active_days=bot_active_days,
        )

    async def global_view(self, user_id: str) -> GlobalView:
        pnl_repo = PnlRepository(self._session)
        spot_pos = SpotPositionRepository(self._session)
        perp_pos = PerpPositionRepository(self._session)
        spot_trade_repo = SpotTradeRepository(self._session)
        perp_trade_repo = PerpTradeRepository(self._session)
        portfolio = await pnl_repo.get_portfolio(user_id)
        snapshots = await pnl_repo.recent_for_user(user_id, limit=168)
        open_spot = await spot_pos.open_for_user(user_id)
        open_perp = await perp_pos.open_for_user(user_id)

        # Esposizione = margine impegnato (capitale che consumi dall'equity), non il
        # nozionale: per il perp si divide per la leva. Spot = entry*size (no leva).
        spot_exposure_usd = sum(
            (Decimal(p.entry_price) * Decimal(p.size) for p in open_spot), Decimal("0")
        )
        perp_exposure_usd = sum(
            (Decimal(p.entry_price) * Decimal(p.size) / Decimal(max(int(p.leverage or 1), 1)) for p in open_perp),
            Decimal("0"),
        )
        unrealized = (
            sum((p.pnl_unrealized for p in open_spot), Decimal("0"))
            + sum((p.pnl_unrealized for p in open_perp), Decimal("0"))
        )
        realized_spot = await spot_trade_repo.sum_realized_pnl(user_id)
        realized_perp = await perp_trade_repo.sum_realized_pnl(user_id)
        realized = realized_spot + realized_perp
        fees_spot = await spot_trade_repo.sum_fees(user_id)
        fees_perp = await perp_trade_repo.sum_fees(user_id)
        total_fees_usd = fees_spot + fees_perp

        if portfolio is None:
            base_equity = self._base_equity_usd
            return GlobalView(
                total_equity_usd=base_equity,
                initial_equity_usd=base_equity,
                pnl_total_usd=realized + unrealized,
                pnl_total_pct=0.0,
                realized_pnl_usd=realized,
                unrealized_pnl_usd=unrealized,
                drawdown_pct=Decimal("0"),
                max_drawdown_pct=Decimal("0"),
                sharpe_status="insufficient_data",
                sharpe_ratio=None,
                drawdown_cap_pct=self._drawdown_cap_pct,
                exposure_pct=Decimal("0"),
                spot_exposure_usd=spot_exposure_usd,
                perp_exposure_usd=perp_exposure_usd,
                total_fees_usd=total_fees_usd,
                daily_pnl_usd=Decimal("0"),
                daily_pnl_net_pct=0.0,
                pnl_total_net_pct=0.0,
                agent_status="idle",
                trades_today=0,
                open_spot_positions=len(open_spot),
                open_perp_positions=len(open_perp),
                risk_guardrail=None,
                pnl_history=[],
            )

        # Calcola total_equity direttamente dalla fonte, non dal DB cache
        # (evita sfasature tra fast_tick aggiornamenti e letture API)
        total_equity = portfolio.initial_equity_usd + realized + unrealized
        pnl_total = realized + unrealized
        initial = portfolio.initial_equity_usd
        sharpe = _daily_sharpe(snapshots)
        pnl_pct = float(pnl_total / initial * 100) if initial > 0 else 0.0
        # pnl_usd nei trade è già al netto delle fee: % giornaliero e globale
        # si calcolano direttamente dai valori già netti.
        daily_pnl = portfolio.daily_pnl_usd
        daily_pnl_net_pct = float(daily_pnl / initial * 100) if initial > 0 else 0.0
        return GlobalView(
            total_equity_usd=total_equity,
            initial_equity_usd=portfolio.initial_equity_usd,
            pnl_total_usd=pnl_total,
            pnl_total_pct=round(pnl_pct, 2),
            realized_pnl_usd=realized,
            unrealized_pnl_usd=unrealized,
            drawdown_pct=portfolio.drawdown_pct,
            max_drawdown_pct=portfolio.max_drawdown_pct,
            sharpe_status=sharpe["status"],
            sharpe_ratio=sharpe["ratio"],
            drawdown_cap_pct=self._drawdown_cap_pct,
            exposure_pct=portfolio.exposure_pct,
            spot_exposure_usd=spot_exposure_usd,
            perp_exposure_usd=perp_exposure_usd,
            total_fees_usd=total_fees_usd,
            daily_pnl_usd=daily_pnl,
            daily_pnl_net_pct=round(daily_pnl_net_pct, 2),
            pnl_total_net_pct=round(pnl_pct, 2),
            agent_status=portfolio.agent_status,
            trades_today=portfolio.trades_today,
            open_spot_positions=len(open_spot),
            open_perp_positions=len(open_perp),
            risk_guardrail=_risk_guardrail(
                total_equity=total_equity,
                drawdown_pct=portfolio.drawdown_pct,
                drawdown_cap_pct=self._drawdown_cap_pct,
                daily_loss_used_pct=portfolio.daily_loss_limit_used_pct,
                daily_loss_limit_pct=self._daily_loss_limit_pct,
                min_portfolio_value_usd=self._min_portfolio_value_usd,
            ),
            pnl_history=[
                PnlPoint(
                    timestamp_utc=s.timestamp_utc.isoformat(),
                    total_equity_usd=s.total_equity_usd,
                    drawdown_pct=s.drawdown_pct,
                )
                for s in reversed(snapshots)
            ],
        )


def _risk_guardrail(
    *,
    total_equity: Decimal,
    drawdown_pct: Decimal,
    drawdown_cap_pct: float,
    daily_loss_used_pct: Decimal,
    daily_loss_limit_pct: float,
    min_portfolio_value_usd: float,
) -> RiskGuardrailView:
    drawdown_cap = abs(Decimal(str(drawdown_cap_pct)))
    daily_cap = Decimal(str(daily_loss_limit_pct))
    floor = Decimal(str(min_portfolio_value_usd))
    if total_equity <= floor:
        return RiskGuardrailView(
            blocked=True,
            reason="portfolio_floor_guard",
            title="Trading blocked: portfolio floor",
            detail=f"Equity {total_equity:.2f} USD is at or below the safety floor {floor:.2f} USD.",
            drawdown_pct=drawdown_pct,
            drawdown_cap_pct=drawdown_cap_pct,
            daily_loss_used_pct=daily_loss_used_pct,
            daily_loss_limit_pct=daily_loss_limit_pct,
            min_portfolio_value_usd=min_portfolio_value_usd,
        )
    if drawdown_pct >= drawdown_cap:
        return RiskGuardrailView(
            blocked=True,
            reason="drawdown_cap_guard",
            title="Trading blocked: drawdown cap",
            detail=f"Drawdown {drawdown_pct:.2f}% is above the cap {drawdown_cap:.2f}%. New entries are suspended.",
            drawdown_pct=drawdown_pct,
            drawdown_cap_pct=drawdown_cap_pct,
            daily_loss_used_pct=daily_loss_used_pct,
            daily_loss_limit_pct=daily_loss_limit_pct,
            min_portfolio_value_usd=min_portfolio_value_usd,
        )
    if daily_loss_used_pct <= daily_cap:
        return RiskGuardrailView(
            blocked=True,
            reason="daily_loss_limit_guard",
            title="Trading blocked: daily loss limit",
            detail=f"Daily PnL {daily_loss_used_pct:.2f}% is below the limit {daily_cap:.2f}%. New entries are suspended.",
            drawdown_pct=drawdown_pct,
            drawdown_cap_pct=drawdown_cap_pct,
            daily_loss_used_pct=daily_loss_used_pct,
            daily_loss_limit_pct=daily_loss_limit_pct,
            min_portfolio_value_usd=min_portfolio_value_usd,
        )
    return RiskGuardrailView(
        blocked=False,
        drawdown_pct=drawdown_pct,
        drawdown_cap_pct=drawdown_cap_pct,
        daily_loss_used_pct=daily_loss_used_pct,
        daily_loss_limit_pct=daily_loss_limit_pct,
        min_portfolio_value_usd=min_portfolio_value_usd,
    )


def _fmt_pnl(pnl: Decimal | None) -> str:
    if pnl is None:
        return "+0.00"
    sign = "+" if pnl >= 0 else ""
    return f"{sign}{pnl:.2f}"


def _pnl_pct_str(pnl: Decimal | None, price: Decimal, size: Decimal, leverage: int = 1) -> str:
    if pnl is None or price <= 0 or size <= 0:
        return "+0.00"
    margin = price * size / Decimal(leverage)
    return _format_signed_pct(pnl / margin * 100)


def _format_signed_pct(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):+.2f}"


def _position_pnl_pct(pnl: Decimal, entry_price: Decimal, size: Decimal, leverage: int = 1) -> str:
    margin = entry_price * size / Decimal(leverage)
    if margin <= 0:
        return "+0.00"
    return _format_signed_pct(pnl / margin * Decimal("100"))


def _spot_trade_entry_price(t) -> Decimal:
    """Ricava il prezzo di ingresso per trade di chiusura spot (sell) usando pnl_usd.
    pnl = (exit - entry) * size  →  entry = exit - pnl / size
    """
    if t.side == "sell" and t.pnl_usd is not None and t.amount > Decimal("0"):
        return t.price - t.pnl_usd / t.amount
    return t.price


def _perp_trade_entry_price(t, entry_by_position_id: dict[str, Decimal] | None = None) -> Decimal:
    """Ricava il prezzo di ingresso per trade di chiusura perp (direction='close').
    Long:  pnl = (exit - entry) * size  →  entry = exit - pnl / size
    Short: pnl = (entry - exit) * size  →  entry = exit + pnl / size
    """
    if t.direction == "close" and entry_by_position_id:
        position_id = _position_id_from_close_trade(t.trade_id)
        if position_id and position_id in entry_by_position_id:
            return _clean_decimal(entry_by_position_id[position_id])
    if t.direction == "close" and t.pnl_usd is not None and t.size > Decimal("0"):
        if t.side == "long":
            return _clean_decimal(t.price - t.pnl_usd / t.size)
        else:
            return _clean_decimal(t.price + t.pnl_usd / t.size)
    return _clean_decimal(t.price)


def _clean_decimal(value: Decimal) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.00000001")).normalize()


def _position_id_from_close_trade(trade_id: str) -> str | None:
    for prefix in ("cls_", "ssl_"):
        if trade_id.startswith(prefix):
            return trade_id.rsplit("_", 1)[0][len(prefix):]
    return None


def _perp_trade_position_id(t, positions: list) -> str | None:
    close_position_id = _position_id_from_close_trade(t.trade_id)
    if close_position_id:
        return close_position_id
    if t.direction == "open":
        for position in positions:
            if position.open_trade_id == t.trade_id:
                return position.position_id
    return None


def _close_reason(trade) -> str | None:
    """Estrae il motivo di chiusura pulito dalle note (es. 'take_profit_1').

    Le chiusure automatiche salvano notes='auto_close:<reason>' (con '_partial'
    per le chiusure parziali). I trade Smart SL usano 'smart_sl:<action>'.
    """
    notes = trade.notes or ""
    prefix = "auto_close:"
    if notes.startswith(prefix):
        reason = notes[len(prefix):].replace("_partial", "")
        return reason or None
    ssl_prefix = "smart_sl:"
    if notes.startswith(ssl_prefix):
        return "smart_sl_" + notes[len(ssl_prefix):]
    return None


def _is_spot_dry_run(trade) -> bool:
    return trade.trade_id.startswith("dry_") or trade.provider == "dry_run" or "dry_run" in (trade.notes or "")


def _is_perp_dry_run(trade) -> bool:
    return trade.trade_id.startswith("dry_") or trade.venue == "dry_run" or "dry_run" in (trade.notes or "")


def _daily_sharpe(snapshots) -> dict[str, str | None]:
    if len(snapshots) < 2:
        return {"status": "insufficient_data", "ratio": None}

    daily_equity: OrderedDict[str, Decimal] = OrderedDict()
    for snapshot in sorted(snapshots, key=lambda row: row.timestamp_utc):
        daily_equity[snapshot.timestamp_utc.date().isoformat()] = Decimal(snapshot.total_equity_usd)

    values = list(daily_equity.values())
    returns: list[float] = []
    for previous, current in zip(values, values[1:], strict=False):
        if previous > 0:
            returns.append(float((current - previous) / previous))
    if len(returns) < 7:
        return {"status": "insufficient_data", "ratio": None}
    volatility = stdev(returns)
    if volatility == 0:
        return {"status": "insufficient_data", "ratio": None}
    ratio = mean(returns) / volatility * sqrt(365)
    return {"status": "ready", "ratio": f"{Decimal(str(ratio)).quantize(Decimal('0.01'))}"}
