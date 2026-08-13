"""Dashboard data views: Spot / Perp / Global."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from backend.app.api.dependencies import AdminAccessDep, ReadAccessDep, SessionDep, SettingsDep
from backend.app.persistence.archive import list_archived_runs
from backend.app.persistence.models.decisions import AgentDecision
from backend.app.persistence.models.pnl import PnlSnapshot
from backend.app.persistence.models.positions import PerpPosition, SpotPosition
from backend.app.persistence.models.trade_charts import TradeChartSnapshot
from backend.app.persistence.models.trades import PerpTrade, SpotTrade
from backend.app.persistence.repositories.pnl import PnlRepository
from backend.app.persistence.repositories.trade_charts import TradeChartRepository
from backend.app.persistence.views import ViewService, _close_reason
from backend.app.schemas.views import GlobalView, PerpView, SpotView

router = APIRouter(prefix="/api/v1/views", tags=["views"])


@router.get("/spot")
async def spot_view(
    session: SessionDep,
    settings: SettingsDep,
    _: ReadAccessDep,
) -> SpotView:
    """Open spot positions, history, PnL and win rate."""

    service = ViewService(
        session,
        drawdown_cap_pct=settings.risk_max_drawdown_pct,
        daily_loss_limit_pct=settings.risk_daily_loss_limit_pct,
        min_portfolio_value_usd=settings.min_portfolio_value_usd,
        base_equity_usd=Decimal(str(settings.dry_run_capital_usd)),
    )
    return await service.spot_view(str(settings.default_user_id))


@router.get("/perp")
async def perp_view(
    session: SessionDep,
    settings: SettingsDep,
    _: ReadAccessDep,
) -> PerpView:
    """Open perpetual positions (leverage, liquidation, funding), history, PnL, win rate."""

    service = ViewService(
        session,
        drawdown_cap_pct=settings.risk_max_drawdown_pct,
        daily_loss_limit_pct=settings.risk_daily_loss_limit_pct,
        min_portfolio_value_usd=settings.min_portfolio_value_usd,
        base_equity_usd=Decimal(str(settings.dry_run_capital_usd)),
    )
    return await service.perp_view(str(settings.default_user_id))


@router.get("/global")
async def global_view(
    session: SessionDep,
    settings: SettingsDep,
    _: ReadAccessDep,
) -> GlobalView:
    """Total PnL, capital vs initial, drawdown vs cap, exposure, balance."""

    service = ViewService(
        session,
        drawdown_cap_pct=settings.risk_max_drawdown_pct,
        daily_loss_limit_pct=settings.risk_daily_loss_limit_pct,
        min_portfolio_value_usd=settings.min_portfolio_value_usd,
        base_equity_usd=Decimal(str(settings.dry_run_capital_usd)),
    )
    return await service.global_view(str(settings.default_user_id))


@router.get("/equity-curve")
async def equity_curve(
    session: SessionDep,
    settings: SettingsDep,
    _: ReadAccessDep,
    market: str = Query("global", pattern="^(spot|perp|global)$"),
    range: str = Query("24h", pattern="^(24h|7d|all)$"),
) -> dict:
    """Hourly equity curve with drawdown overlay."""

    user_id = str(settings.default_user_id)
    since = _range_since(range)
    stmt = select(PnlSnapshot).where(PnlSnapshot.user_id == user_id)
    if since:
        stmt = stmt.where(PnlSnapshot.timestamp_utc >= since)
    stmt = stmt.order_by(PnlSnapshot.timestamp_utc.asc())
    snapshots = list((await session.execute(stmt)).scalars().all())
    pnl_repo = PnlRepository(session)
    portfolio = await pnl_repo.get_portfolio(user_id)
    initial = _initial_equity(snapshots, settings, portfolio, market)
    benchmark = await _btc_benchmark(snapshots)
    # Versamenti/prelievi manuali: sono capitale aggiunto, non PnL. Il grafico va
    # misurato contro il capitale versato FINO A QUEL MOMENTO, altrimenti un
    # deposito odierno rebaselina tutta la storia (i punti vecchi sembrano in
    # grossa perdita). Riguarda solo il 'global' (spot/perp non includono la cassa).
    adjustments = (
        sorted(await pnl_repo.list_equity_adjustments(user_id, limit=1000), key=lambda a: a.created_at)
        if market == "global" else []
    )
    total_deposits = sum((Decimal(str(a.amount)) for a in adjustments), Decimal("0"))
    base_initial = initial - total_deposits  # base prima di ogni versamento
    items = []
    for snapshot in snapshots:
        equity = _market_equity(snapshot, market)
        if adjustments:
            contributed = base_initial + _deposits_up_to(adjustments, snapshot.timestamp_utc)
        else:
            contributed = initial
        pnl_usd = equity - contributed
        pnl_pct = (pnl_usd / contributed * Decimal("100")) if contributed > 0 else Decimal("0")
        item = {
            "timestamp_utc": snapshot.timestamp_utc.isoformat(),
            "equity_usd": _q2(equity),
            "pnl_usd": _signed(_q2(pnl_usd)),
            "pnl_pct": _signed(_q2(pnl_pct)),
            "drawdown_pct": _signed(_q2(snapshot.drawdown_pct)),
        }
        btc_pct = benchmark.get(snapshot.timestamp_utc.isoformat())
        if btc_pct is not None:
            item["btc_pct"] = _signed(_q2(btc_pct))
        items.append(item)
    return {
        "market": market,
        "range": range,
        "initial_equity_usd": _q2(initial),
        "benchmark_available": bool(benchmark),
        "items": items,
    }


@router.get("/asset-breakdown")
async def asset_breakdown(
    session: SessionDep,
    settings: SettingsDep,
    _: ReadAccessDep,
    market: str = Query("spot", pattern="^(spot|perp)$"),
) -> dict:
    """PnL breakdown by asset."""

    user_id = str(settings.default_user_id)
    portfolio = await ViewService(
        session,
        drawdown_cap_pct=settings.risk_max_drawdown_pct,
        base_equity_usd=Decimal(str(settings.dry_run_capital_usd)),
    ).global_view(user_id)
    current_equity = Decimal(portfolio.total_equity_usd or 0)
    if market == "spot":
        trades = list((await session.execute(select(SpotTrade).where(SpotTrade.user_id == user_id))).scalars().all())
        positions = list((await session.execute(select(SpotPosition).where(SpotPosition.user_id == user_id))).scalars().all())
    else:
        trades = list((await session.execute(select(PerpTrade).where(PerpTrade.user_id == user_id))).scalars().all())
        positions = list((await session.execute(select(PerpPosition).where(PerpPosition.user_id == user_id))).scalars().all())
    assets = sorted({row.asset for row in trades} | {row.asset for row in positions})
    items = []
    for asset in assets:
        asset_trades = [trade for trade in trades if trade.asset == asset]
        asset_positions = [position for position in positions if position.asset == asset]
        pnl = sum((Decimal(getattr(position, "pnl_unrealized", 0) or 0) for position in asset_positions), Decimal("0"))
        exposure = sum(
            (Decimal(position.size) * Decimal(position.current_price) for position in asset_positions),
            Decimal("0"),
        )
        wins = sum(1 for trade in asset_trades if (trade.notes or "").lower().find("profit") >= 0)
        win_rate = Decimal(wins) / Decimal(len(asset_trades)) * Decimal("100") if asset_trades else Decimal("0")
        pnl_pct = pnl / current_equity * Decimal("100") if current_equity > 0 else Decimal("0")
        allocation_pct = exposure / current_equity * Decimal("100") if current_equity > 0 else Decimal("0")
        items.append(
            {
                "asset": asset,
                "trade_count": len(asset_trades),
                "win_rate_pct": _q2(win_rate),
                "pnl_usd": _signed(_q2(pnl)),
                "pnl_pct": _signed(_q2(pnl_pct)),
                "allocation_pct": _q2(allocation_pct),
            }
        )
    return {"market": market, "items": items}


@router.get("/trade-detail/{trade_id}")
async def trade_detail(
    trade_id: str,
    session: SessionDep,
    settings: SettingsDep,
    _: ReadAccessDep,
    enrich_chart: bool = Query(False),
) -> dict:
    """Return full detail for one spot/perp trade or its open position."""

    from backend.app.api.routes.mobile_agent import _settings_from_runtime

    user_id = str(settings.default_user_id)
    ms, _, _ = _settings_from_runtime(settings)
    post_close_count = ms.post_close_candles
    spot = (await session.execute(select(SpotTrade).where(SpotTrade.user_id == user_id).where(SpotTrade.trade_id == trade_id))).scalar_one_or_none()
    perp = (await session.execute(select(PerpTrade).where(PerpTrade.user_id == user_id).where(PerpTrade.trade_id == trade_id))).scalar_one_or_none()
    if spot is None and perp is None:
        raise HTTPException(status_code=404, detail="trade_not_found")
    chart_repo = TradeChartRepository(session)
    if spot is not None:
        position = await _find_trade_position(session, SpotPosition, spot)
        decision = (await session.execute(select(AgentDecision).where(AgentDecision.trade_id == trade_id))).scalar_one_or_none()
        snapshot = await _load_chart_snapshot(chart_repo, user_id, trade_id, position)
        live = await _live_chart_if_open(snapshot, position, "spot", settings) if enrich_chart else None
        chart_payload = json.loads(snapshot.payload) if snapshot else None
        post_close: list[dict] = []
        if enrich_chart and live is None and snapshot is not None:
            chart_payload = await _enrich_trade_chart_context(chart_payload, spot.asset, "spot", "spot", "long", settings)
            post_close = await _fetch_post_close_candles(chart_payload, spot.asset, "spot", post_close_count)
        return _spot_trade_detail(spot, position, decision, settings, snapshot, live, post_close, chart_payload)
    position = await _find_trade_position(session, PerpPosition, perp)
    decision = (await session.execute(select(AgentDecision).where(AgentDecision.trade_id == trade_id))).scalar_one_or_none()
    snapshot = await _load_chart_snapshot(chart_repo, user_id, trade_id, position)
    live = await _live_chart_if_open(snapshot, position, "perp", settings) if enrich_chart else None
    chart_payload = json.loads(snapshot.payload) if snapshot else None
    post_close = []
    if enrich_chart and live is None and snapshot is not None:
        side = position.side if position is not None else perp.side
        chart_payload = await _enrich_trade_chart_context(chart_payload, perp.asset, "futures", "perp", side, settings)
        post_close = await _fetch_post_close_candles(chart_payload, perp.asset, "futures", post_close_count)
    return _perp_trade_detail(perp, position, decision, settings, snapshot, live, post_close, chart_payload)


async def _find_trade_position(session, model, trade):
    """Trova la posizione del trade: via open_trade_id (apertura) o, per i trade
    di chiusura (cls_<position_id>_<hex>) e di scaling-in (add_<position_id>_<hex>),
    estraendo il position_id dal trade_id."""
    pos = (await session.execute(select(model).where(model.open_trade_id == trade.trade_id))).scalar_one_or_none()
    if pos is not None:
        return pos
    for prefix in ("cls_", "add_", "ssl_"):
        if trade.trade_id.startswith(prefix):
            position_id = trade.trade_id.rsplit("_", 1)[0][len(prefix):]
            return (
                await session.execute(select(model).where(model.position_id == position_id))
            ).scalar_one_or_none()
    return None


async def _load_chart_snapshot(
    chart_repo: TradeChartRepository,
    user_id: str,
    trade_id: str,
    position,
) -> TradeChartSnapshot | None:
    """Lo snapshot e' legato al trade di chiusura (cls_...) o, in fallback, alla posizione."""
    snapshot = await chart_repo.get_for_close_trade(user_id, trade_id)
    if snapshot is None and position is not None:
        snapshot = await chart_repo.get_for_position(user_id, position.position_id)
    return snapshot


async def _live_chart_if_open(snapshot, position, market: str, settings) -> dict | None:
    """Per una posizione ancora aperta costruisce un grafico dal vivo.

    Lo snapshot parziale (TP1) viene ignorato: la posizione è ancora aperta
    e i dati live devono prevalere sul grafico congelato al momento del TP1.
    """
    if position is None or position.status == "closed":
        return None
    try:
        return await asyncio.wait_for(
            _build_live_chart(position, market, settings=settings, timeout_seconds=TRADE_DETAIL_FEED_TIMEOUT_SECONDS),
            timeout=TRADE_DETAIL_CHART_TIMEOUT_SECONDS,
        )
    except Exception:
        return None


_INTERVAL_MINUTES: dict[str, int] = {
    "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "2h": 120, "4h": 240, "6h": 360, "12h": 720, "1d": 1440,
}
POST_CLOSE_CANDLES = 10
TRADE_DETAIL_CHART_TIMEOUT_SECONDS = 4.0
TRADE_DETAIL_FEED_TIMEOUT_SECONDS = 1.5
TRADE_DETAIL_KLINE_CACHE_MAX_AGE_SECONDS = 180


async def _fetch_post_close_candles(chart: dict, asset: str, feed_market: str, count: int = POST_CLOSE_CANDLES) -> list[dict]:
    """Recupera fino a POST_CLOSE_CANDLES candele successive alla chiusura del trade.

    Strategia: fetch delle ultime (candles_in_trade + POST_CLOSE + buffer) candele e
    filtra quelle con timestamp > closed_at. Funziona per trade chiusi di recente
    (entro ~2 giorni con chart 5m, settimane con 1h/4h).
    Ritorna lista vuota se non ci sono ancora candele post-close disponibili o se count=0.
    """
    if count <= 0:
        return []
    try:
        from backend.app.agent.signals.perp.binance_klines import BinanceKlineFeed

        closed_at_str = chart.get("closed_at")
        opened_at_str = chart.get("opened_at")
        interval = chart.get("interval", "5m")
        if not closed_at_str or not opened_at_str or chart.get("live"):
            return []
        closed_at = datetime.fromisoformat(closed_at_str)
        if closed_at.tzinfo is None:
            closed_at = closed_at.replace(tzinfo=UTC)
        opened_at = datetime.fromisoformat(opened_at_str)
        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=UTC)
        interval_min = _INTERVAL_MINUTES.get(interval, 5)
        now = datetime.now(UTC)
        # Aspettiamo almeno 1 periodo chiuso dopo la fine del trade.
        if now < closed_at + timedelta(minutes=interval_min):
            return []
        normalized_snapshot = _normalize_closed_chart(chart) or chart
        chart_candles = _normalize_chart_candles(normalized_snapshot.get("candles", []))
        last_snapshot_ts = chart_candles[-1][0] if chart_candles else None
        post_threshold = max(closed_at, last_snapshot_ts) if last_snapshot_ts is not None else closed_at
        symbol = f"{asset}USDT"
        start_time = post_threshold + timedelta(milliseconds=1)
        candles = await asyncio.wait_for(
            BinanceKlineFeed(timeout_seconds=TRADE_DETAIL_FEED_TIMEOUT_SECONDS).fetch(
                symbol=symbol,
                interval=interval,
                limit=count + 2,
                market=feed_market,  # type: ignore[arg-type]
                start_time=start_time,
            ),
            timeout=TRADE_DETAIL_CHART_TIMEOUT_SECONDS,
        )
        # Teniamo solo candele successive al confine gia' presente nello snapshot.
        # startTime evita di appendere le ultime candele disponibili giorni dopo
        # la chiusura, che deformerebbero i trade storici.
        post = [
            {"t": c.timestamp.isoformat(), "o": c.open, "h": c.high, "l": c.low, "c": c.close}
            for c in candles
            if c.timestamp > post_threshold
        ]
        return post[:count]
    except Exception:
        return []


def _normalize_chart_candles(raw_candles: list[dict]) -> list[tuple[datetime, dict]]:
    normalized: list[tuple[datetime, dict]] = []
    for candle in raw_candles:
        try:
            ts_value = candle.get("t")
            if not ts_value:
                continue
            ts = datetime.fromisoformat(str(ts_value))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            normalized.append((ts, candle))
        except Exception:
            continue
    normalized.sort(key=lambda item: item[0])
    return normalized


def _parse_chart_datetime(value) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
    except Exception:
        return None


def _structural_stop_lookback(settings, market: str) -> int:
    attr = "perp_structural_stop_lookback_candles" if market == "perp" else "spot_structural_stop_lookback_candles"
    try:
        return max(1, int(getattr(settings, attr, 20)))
    except Exception:
        return 20


def _structural_stop_buffer(settings, market: str) -> Decimal:
    attr = "perp_structural_stop_buffer_pct" if market == "perp" else "spot_structural_stop_buffer_pct"
    try:
        return Decimal(str(getattr(settings, attr, 1.10)))
    except Exception:
        return Decimal("1.10")


def _stop_reference_field(market: str, side: str | None) -> str:
    if market == "perp" and str(side or "").lower() == "short":
        return "high"
    return "low"


def _infer_stop_reference_from_chart(chart: dict, market: str, side: str | None, lookback: int) -> dict | None:
    opened_at = _parse_chart_datetime(chart.get("opened_at"))
    if opened_at is None:
        return None
    normalized = _normalize_chart_candles(chart.get("candles", []))
    candidates = [(ts, candle) for ts, candle in normalized if ts <= opened_at]
    if not candidates:
        return None
    window = candidates[-lookback:]
    field = _stop_reference_field(market, side)
    price_key = "h" if field == "high" else "l"

    def price_of(item: tuple[datetime, dict]) -> Decimal:
        return Decimal(str(item[1][price_key]))

    selected_ts, selected = max(window, key=price_of) if field == "high" else min(window, key=price_of)
    return {
        "t": selected_ts.isoformat(),
        "price": str(selected.get(price_key)),
        "field": field,
        "pre_candles": lookback,
        "inferred": True,
    }


def _ensure_stop_reference(chart: dict | None, market: str, side: str | None, lookback: int) -> dict | None:
    if chart is None or chart.get("stop_reference"):
        return chart
    inferred = _infer_stop_reference_from_chart(chart, market, side, lookback)
    if inferred is None:
        return chart
    return {**chart, "stop_reference": inferred}


def _structural_stop_loss_from_reference(chart: dict, settings, market: str, side: str | None) -> str | None:
    reference = chart.get("stop_reference") or {}
    price = reference.get("price")
    if price is None:
        return None
    try:
        reference_price = Decimal(str(price))
    except Exception:
        return None
    field = str(reference.get("field") or _stop_reference_field(market, side)).lower()
    buffer_pct = _structural_stop_buffer(settings, market)
    if field == "high":
        stop_loss = reference_price * (Decimal("1") + buffer_pct / Decimal("100"))
    else:
        stop_loss = reference_price * (Decimal("1") - buffer_pct / Decimal("100"))
    return _fmt_price(stop_loss)


def _apply_display_stop_to_chart(chart: dict | None, position, settings, market: str, side: str | None) -> dict | None:
    if chart is None:
        return chart
    initial_stop_loss = getattr(position, "initial_stop_loss", None) if position is not None else None
    if initial_stop_loss:
        return {**chart, "stop_loss": _fmt_price(initial_stop_loss)}
    structural_stop_loss = _structural_stop_loss_from_reference(chart, settings, market, side)
    if structural_stop_loss:
        return {**chart, "stop_loss": structural_stop_loss}
    return chart


async def _enrich_trade_chart_context(
    chart: dict | None,
    asset: str,
    feed_market: str,
    market: str,
    side: str | None,
    settings,
) -> dict | None:
    """Add pre-open candles and infer the structural SL reference for old snapshots."""

    if chart is None or chart.get("live"):
        return chart
    normalized_chart = _normalize_closed_chart(chart) or chart
    opened_at = _parse_chart_datetime(normalized_chart.get("opened_at"))
    if opened_at is None:
        return _ensure_stop_reference(normalized_chart, market, side, _structural_stop_lookback(settings, market))
    interval = str(normalized_chart.get("interval", "5m"))
    interval_min = _INTERVAL_MINUTES.get(interval, 5)
    lookback = _structural_stop_lookback(settings, market)
    target_start = opened_at - timedelta(minutes=interval_min * lookback)
    existing = _normalize_chart_candles(normalized_chart.get("candles", []))
    has_enough_context = bool(existing and existing[0][0] <= target_start + timedelta(minutes=interval_min))
    if normalized_chart.get("stop_reference") and has_enough_context:
        return normalized_chart

    try:
        from backend.app.agent.signals.perp.binance_klines import BinanceKlineFeed

        closed_at = _parse_chart_datetime(normalized_chart.get("closed_at"))
        limit = int(min(260, max(lookback + len(existing) + 5, lookback + 20)))
        fetched = await asyncio.wait_for(
            BinanceKlineFeed(timeout_seconds=TRADE_DETAIL_FEED_TIMEOUT_SECONDS).fetch(
                symbol=f"{asset}USDT",
                interval=interval,
                limit=limit,
                market=feed_market,  # type: ignore[arg-type]
                start_time=target_start,
            ),
            timeout=TRADE_DETAIL_CHART_TIMEOUT_SECONDS,
        )
        fetched_candles = [
            {"t": c.timestamp.isoformat(), "o": c.open, "h": c.high, "l": c.low, "c": c.close}
            for c in fetched
            if closed_at is None or c.timestamp <= closed_at
        ]
        by_ts = {candle["t"]: candle for candle in fetched_candles}
        by_ts.update({candle["t"]: candle for _, candle in existing})
        merged = _normalize_closed_chart({**normalized_chart, "candles": list(by_ts.values())}) or normalized_chart
    except Exception:
        merged = normalized_chart
    enriched = _ensure_stop_reference(merged, market, side, lookback)
    return _apply_display_stop_to_chart(enriched, None, settings, market, side)


def _normalize_closed_chart(chart: dict | None) -> dict | None:
    """Sort snapshot candles and keep closed charts ending on the close candle."""

    if chart is None:
        return None
    normalized = _normalize_chart_candles(chart.get("candles", []))
    if not normalized:
        return chart
    candles = [candle for _, candle in normalized]
    if chart.get("live"):
        return {**chart, "candles": candles}
    closed_at_str = chart.get("closed_at")
    if not closed_at_str:
        return {**chart, "candles": candles}
    try:
        closed_at = datetime.fromisoformat(str(closed_at_str))
        if closed_at.tzinfo is None:
            closed_at = closed_at.replace(tzinfo=UTC)
    except Exception:
        return {**chart, "candles": candles}
    pre_close = [candle for ts, candle in normalized if ts <= closed_at]
    return {**chart, "candles": pre_close or candles}


async def _build_live_chart(position, market: str, *, settings=None, timeout_seconds: float = TRADE_DETAIL_FEED_TIMEOUT_SECONDS) -> dict | None:
    """Candele OHLC dall'apertura della posizione fino ad ora, con stesso payload
    degli snapshot congelati ma marcato live (closed_at non e' una chiusura reale).

    Best-effort: se il feed non risponde ritorna None e la scheda omette il grafico.
    """
    try:
        from backend.app.agent.service import _auto_chart_interval
        from backend.app.agent.signals.perp.binance_klines import BinanceKlineFeed

        opened_at = position.opened_at
        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=UTC)
        now = datetime.now(UTC)
        duration_min = max(1, int((now - opened_at).total_seconds() / 60))
        interval, per_min = _auto_chart_interval(duration_min)
        stop_reference_time = getattr(position, "stop_reference_time", None)
        if stop_reference_time and stop_reference_time.tzinfo is None:
            stop_reference_time = stop_reference_time.replace(tzinfo=UTC)
        lookback = _structural_stop_lookback(settings, market) if settings is not None else 20
        chart_start = (
            min(opened_at - timedelta(minutes=per_min * lookback), stop_reference_time)
            if stop_reference_time is not None
            else opened_at - timedelta(minutes=per_min * lookback)
        )
        chart_span_min = (
            max(1, int((now - chart_start).total_seconds() / 60))
            if chart_start is not None
            else duration_min
        )
        limit = int(min(260, max(20, (chart_span_min / per_min) * 1.6)))
        feed_market = "futures" if market == "perp" else "spot"
        symbol = f"{position.asset}USDT"
        candles = None if chart_start is not None else _cached_klines(feed_market, symbol, interval, min_limit=limit)
        if candles is None:
            try:
                fetch_kwargs = {"symbol": symbol, "interval": interval, "limit": limit, "market": feed_market}
                if chart_start is not None:
                    fetch_kwargs["start_time"] = chart_start
                candles = await BinanceKlineFeed(timeout_seconds=timeout_seconds).fetch(**fetch_kwargs)
            except Exception:
                candles = await BinanceKlineFeed(timeout_seconds=timeout_seconds).fetch(
                    symbol=symbol, interval=interval, limit=limit, market=feed_market
                )
        if not candles:
            return None
        tp2 = getattr(position, "take_profit_2", None)
        stop_reference_price = getattr(position, "stop_reference_price", None)
        stop_reference_field = getattr(position, "stop_reference_field", None)
        display_stop_loss = getattr(position, "initial_stop_loss", None) or position.stop_loss
        chart = {
            "interval": interval,
            "market": market,
            "side": position.side if market == "perp" else "long",
            "entry_price": str(position.entry_price),
            "exit_price": str(position.current_price),
            "stop_loss": str(display_stop_loss) if display_stop_loss else None,
            "take_profit_1": str(position.take_profit_1) if position.take_profit_1 else None,
            "take_profit_2": str(tp2) if tp2 else None,
            "liquidation_price": (
                str(position.liquidation_price)
                if market == "perp" and getattr(position, "liquidation_price", None)
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
            "live": True,
            "candles": [
                {"t": c.timestamp.isoformat(), "o": c.open, "h": c.high, "l": c.low, "c": c.close}
                for c in candles
            ],
        }
        chart = _ensure_stop_reference(chart, market, chart["side"], lookback)
        return _apply_display_stop_to_chart(chart, position, settings, market, chart["side"])
    except Exception:
        return None


def _cached_klines(market: str, symbol: str, interval: str, *, min_limit: int) -> list | None:
    """Use recent signal-engine kline cache for trade charts before hitting CEX APIs."""

    try:
        from backend.app.agent.signals.perp.binance_klines import get_kline_cache_entry

        entry = get_kline_cache_entry(market=market, symbol=symbol, interval=interval)  # type: ignore[arg-type]
        if entry is None:
            return None
        age = (datetime.now(UTC) - entry.updated_at).total_seconds()
        if age > TRADE_DETAIL_KLINE_CACHE_MAX_AGE_SECONDS:
            return None
        if len(entry.candles) < min_limit:
            return None
        return entry.candles[-min_limit:]
    except Exception:
        return None


@router.get("/operational-stats")
async def operational_stats(
    _: ReadAccessDep,
) -> dict:
    """Return lightweight runtime operational stats."""

    from backend.app.agent.heartbeat import heartbeat

    beats = heartbeat.as_dict()
    return {
        "uptime_pct": "100.00",
        "heartbeat": beats,
        "degraded_count": 0,
        "degraded_reasons": [],
        "last_kill_switch": None,
    }


@router.get("/archived-runs")
async def archived_runs(
    session: SessionDep,
    settings: SettingsDep,
    _: AdminAccessDep,
) -> dict:
    """List archived dry-run datasets excluded from live views."""

    runs = await list_archived_runs(session, user_id=str(settings.default_user_id))
    return {"items": runs, "count": len(runs)}


def _range_since(value: str) -> datetime | None:
    now = datetime.now(UTC)
    if value == "24h":
        return now - timedelta(hours=24)
    if value == "7d":
        return now - timedelta(days=7)
    return None


async def _btc_benchmark(snapshots: list[PnlSnapshot]) -> dict[str, Decimal]:
    """Andamento cumulato % di BTC allineato agli snapshot, per confronto sul grafico equity.

    L'ambiente dry-run usa un clock simulato che non corrisponde alle klines reali
    di Binance: per questo NON allineiamo per timestamp assoluto ma per *offset orario*
    dal primo snapshot (gli snapshot sono orari). Best-effort: se BTC non e' raggiungibile
    ritorna {} e il grafico mostra la sola curva PnL.
    """
    if len(snapshots) < 2:
        return {}
    from backend.app.agent.signals.perp.binance_klines import BinanceKlineFeed

    first_ts = snapshots[0].timestamp_utc
    last_ts = snapshots[-1].timestamp_utc
    span_hours = int(round((last_ts - first_ts).total_seconds() / 3600))
    if span_hours < 1:
        span_hours = 1
    limit = min(1000, span_hours + 2)
    try:
        candles = await BinanceKlineFeed().fetch(
            symbol="BTCUSDT", interval="1h", limit=limit, market="spot"
        )
    except Exception:
        return {}
    if not candles:
        return {}
    base = Decimal(str(candles[0].close))
    if base <= 0:
        return {}
    out: dict[str, Decimal] = {}
    for snapshot in snapshots:
        offset = int(round((snapshot.timestamp_utc - first_ts).total_seconds() / 3600))
        idx = max(0, min(offset, len(candles) - 1))
        close = Decimal(str(candles[idx].close))
        out[snapshot.timestamp_utc.isoformat()] = (close / base - Decimal("1")) * Decimal("100")
    return out


def _initial_equity(snapshots: list[PnlSnapshot], settings, portfolio=None, market: str = "global") -> Decimal:
    """Baseline per il PnL cumulato del grafico.

    Per il market 'global' usa il capitale iniziale configurato
    (portfolio.initial_equity_usd), cosi' il "PnL cumulato" del grafico
    combacia con la "PnL %" della scheda Global. In assenza usa il primo
    snapshot disponibile come fallback. Per spot/perp usa l'equity del primo
    snapshot del mercato specifico.
    """
    if market == "global" and portfolio is not None and portfolio.initial_equity_usd:
        return Decimal(portfolio.initial_equity_usd)
    if snapshots:
        return Decimal(_market_equity(snapshots[0], market))
    return Decimal(str(settings.dry_run_capital_usd))


def _deposits_up_to(adjustments: list, ts) -> Decimal:
    """Somma dei versamenti/prelievi (importi con segno) effettuati fino a `ts`."""
    total = Decimal("0")
    for adjustment in adjustments:
        if adjustment.created_at <= ts:
            total += Decimal(str(adjustment.amount))
        else:
            break  # lista ordinata per created_at asc
    return total


def _market_equity(snapshot: PnlSnapshot, market: str) -> Decimal:
    if market == "spot":
        return Decimal(snapshot.spot_equity_usd)
    if market == "perp":
        return Decimal(snapshot.perp_equity_usd)
    return Decimal(snapshot.total_equity_usd)


def _q2(value) -> str:
    return f"{Decimal(value).quantize(Decimal('0.01'))}"


def _q2_opt(value) -> str | None:
    """Come _q2 ma tollera None (trade pre-migrazione senza colonne fee)."""
    if value is None:
        return None
    return _q2(value)


def _fee_opt(value) -> str | None:
    """Importi piccoli (fee/slippage): virgola fissa fino a 8 decimali, così le
    fee sub-cent dei trade dry-run non vengono arrotondate a 0.00 da _q2."""
    if value is None:
        return None
    return _fmt_price(value)


def _fmt_price(value) -> str:
    """Prezzo come stringa a virgola fissa: niente notazione scientifica,
    minimo 2 decimali, massimo 18, senza zeri finali superflui.

    Es: 100 → "100.00", 0.000123 → "0.000123", 0.0001234567 → "0.00012346".
    Evita il problema di Decimal.normalize() che per i numeri tondi produce
    notazione scientifica ("1E+2").
    """
    decimal = Decimal(str(value))
    with localcontext() as ctx:
        ctx.prec = max(28, len(decimal.as_tuple().digits) + 18)
        quantized = decimal.quantize(Decimal("0.000000000000000001"))
    text = format(quantized, "f")
    if "." in text:
        int_part, frac = text.split(".")
        frac = frac.rstrip("0")
        if len(frac) < 2:
            frac = frac.ljust(2, "0")
        return f"{int_part}.{frac}"
    return f"{text}.00"


def _positive_decimal(value) -> Decimal | None:
    if value is None:
        return None
    decimal = Decimal(str(value))
    return decimal if decimal > 0 else None


def _spot_entry_fallback(trade: SpotTrade, size: Decimal, chart: dict | None) -> Decimal | None:
    if chart:
        chart_entry = _positive_decimal(chart.get("entry_price"))
        if chart_entry is not None:
            return chart_entry
    trade_price = _positive_decimal(trade.price)
    if trade_price is not None:
        return trade_price
    amount_quote = _positive_decimal(trade.amount_quote)
    if amount_quote is not None and size > 0:
        return amount_quote / size
    return None


def _signed(value: str) -> str:
    decimal = Decimal(value)
    return f"{decimal:+.2f}"


def _pnl_pct(pnl: Decimal, entry: Decimal, size: Decimal, leverage: int = 1) -> str:
    margin = entry * size / Decimal(leverage)
    if margin <= 0:
        return "+0.00"
    return _signed(_q2(pnl / margin * Decimal("100")))


def _decision_payload(decision: AgentDecision | None) -> dict | None:
    if decision is None:
        return None
    return {
        "decision_id": decision.decision_id,
        "signal_quality": _q2(decision.signal_quality or 0),
        "confidence": _q2(decision.confidence or 0),
        "action": decision.action,
        "reasoning": decision.reasoning,
    }


def _level(position, attr: str, chart: dict | None, key: str) -> str | None:
    """Livello (SL/TP) dalla posizione, con fallback ai dati congelati nello snapshot.

    Per lo stop_loss usa initial_stop_loss se disponibile: preserva il livello
    originale sotto l'entry anche dopo che il BE ha sovrascritto stop_loss.
    """
    if position is not None:
        if attr == "stop_loss":
            val = getattr(position, "initial_stop_loss", None) or getattr(position, "stop_loss", None)
        else:
            val = getattr(position, attr, None)
        if val:
            return _fmt_price(val)
    if chart and chart.get(key):
        return _fmt_price(chart[key])
    return None


def _smart_sl_detail(position) -> dict:
    """Livelli Smart SL calcolati da original_entry/initial_stop_loss + stato corrente."""
    if position is None or getattr(position, "initial_stop_loss", None) is None:
        return {"original_entry_price": None, "smart_sl_levels": None, "smart_sl_state_summary": None}

    raw = getattr(position, "smart_sl_state", None)
    state = None
    if raw:
        try:
            state = json.loads(raw)
        except (ValueError, KeyError):
            pass

    entry = Decimal(str(state["original_entry"])) if state and "original_entry" in state else Decimal(str(position.entry_price))
    isl = Decimal(str(position.initial_stop_loss))
    is_long = position.side == "long"
    dist = abs(entry - isl)
    if dist == 0:
        return {"original_entry_price": _fmt_price(entry), "smart_sl_levels": None, "smart_sl_state_summary": None}

    fracs = [Decimal("0.333"), Decimal("0.666"), Decimal("1")]
    if is_long:
        prices = [entry - f * dist for f in fracs]
    else:
        prices = [entry + f * dist for f in fracs]

    summary = None
    reentries_exhausted = False
    if state:
        levels_state = state.get("levels", [])
        global_reentries = state.get("global_reentries", 0)
        reentries_exhausted = global_reentries >= 1 or all(
            lv.get("reentries", 0) >= 1 for lv in levels_state
        )
        summary = [
            {
                "status": lv.get("status", "idle"),
                "reentries": lv.get("reentries", 0),
                "fill_price": lv.get("sell_price"),
                "rebuy_fill_price": lv.get("rebuy_fill_price"),
            }
            for lv in levels_state
        ]

    original_tp1 = state.get("original_tp1") if state else None
    original_tp2 = state.get("original_tp2") if state else None
    protection_suspended = state.get("protection_suspended", False) if state else False

    return {
        "original_entry_price": _fmt_price(entry),
        "smart_sl_levels": [_fmt_price(p) for p in prices],
        "smart_sl_state_summary": summary,
        "smart_sl_reentries_exhausted": reentries_exhausted,
        "smart_sl_original_tp1": original_tp1,
        "smart_sl_original_tp2": original_tp2,
        "smart_sl_protection_suspended": protection_suspended,
    }


def _smart_sl_original_entry(position) -> Decimal | None:
    if position is None:
        return None
    raw = getattr(position, "smart_sl_state", None)
    if not raw:
        return None
    try:
        state = json.loads(raw)
        if state.get("original_entry") is None:
            return None
        return Decimal(str(state["original_entry"]))
    except (ValueError, KeyError, TypeError):
        return None


def _breakeven_price(position, is_long: bool) -> str | None:
    """Prezzo di breakeven: valorizzato solo quando lo stop è già stato spostato
    a breakeven (≥ entry per i long, ≤ entry per gli short). Altrimenti None → "---"."""
    if position is None or position.stop_loss is None:
        return None
    stop = Decimal(str(position.stop_loss))
    entry = Decimal(str(position.entry_price))
    active = stop >= entry if is_long else stop <= entry
    return _fmt_price(stop) if active else None


def _stop_reference_price(position, chart: dict | None) -> str | None:
    value = getattr(position, "stop_reference_price", None) if position is not None else None
    if value is None and chart:
        value = (chart.get("stop_reference") or {}).get("price")
    return _fmt_price(value) if value is not None else None


def _trade_stop_reference_field(position, chart: dict | None) -> str | None:
    value = getattr(position, "stop_reference_field", None) if position is not None else None
    if value is None and chart:
        value = (chart.get("stop_reference") or {}).get("field")
    return str(value) if value else None


def _trade_timeline(trade, position, chart: dict | None, is_close: bool) -> tuple[str, str | None]:
    """(opened_at, closed_at) coerenti: lo snapshot e la posizione sono piu' affidabili
    del timestamp del trade (che per un cls_ e' il momento della chiusura, non dell'apertura)."""
    if chart:
        opened_at = str(chart["opened_at"])
    elif position is not None:
        opened_at = position.opened_at.isoformat()
    elif not is_close:
        opened_at = trade.timestamp_utc.isoformat()
    else:
        opened_at = trade.timestamp_utc.isoformat()
    closed_at: str | None
    if chart and not chart.get("live"):
        closed_at = str(chart["closed_at"])
    elif position is not None and position.status == "closed":
        closed_at = position.updated_at.isoformat()
    elif is_close:
        closed_at = trade.timestamp_utc.isoformat()
    else:
        closed_at = None
    return opened_at, closed_at


def _spot_trade_detail(
    trade: SpotTrade,
    position: SpotPosition | None,
    decision: AgentDecision | None,
    settings=None,
    snapshot: TradeChartSnapshot | None = None,
    live_chart: dict | None = None,
    post_close_candles: list[dict] | None = None,
    chart_payload: dict | None = None,
) -> dict:
    # Per posizioni ancora aperte il grafico live prevale sullo snapshot parziale (TP1).
    raw_chart = live_chart if live_chart is not None else (chart_payload if chart_payload is not None else (json.loads(snapshot.payload) if snapshot else None))
    chart = _normalize_closed_chart(raw_chart)
    chart = _apply_display_stop_to_chart(chart, position, settings, "spot", "long")
    if chart is not None and post_close_candles:
        chart = {**chart, "post_close_candles": post_close_candles}
    is_close = trade.trade_id.startswith("cls_")
    size = Decimal(trade.amount) if (is_close or position is None) else Decimal(position.size)
    entry = (
        Decimal(position.entry_price) if position is not None
        else Decimal(str(chart["entry_price"])) if chart
        else Decimal(trade.price)
    )
    if entry <= 0:
        entry = _spot_entry_fallback(trade, size, chart) or entry
    if is_close:
        current = Decimal(trade.price)
    elif position is not None:
        current = Decimal(position.current_price)
    elif chart:
        current = Decimal(str(chart["exit_price"]))
    else:
        current = Decimal(trade.price)
    if current <= 0:
        current = _positive_decimal(chart.get("exit_price") if chart else None) or entry
    if trade.pnl_usd is not None:
        pnl = Decimal(trade.pnl_usd)
    elif position is not None:
        pnl = Decimal(position.pnl_unrealized)
    else:
        pnl = Decimal("0")
    opened_at, closed_at = _trade_timeline(trade, position, chart, is_close)
    return {
        "trade_id": trade.trade_id,
        "asset": trade.asset,
        "market": "spot",
        "direction": trade.side,
        "entry_price": _fmt_price(entry),
        "current_or_exit_price": _fmt_price(current),
        "pnl_usd": _signed(_q2(pnl)),
        "pnl_pct": _pnl_pct(pnl, entry, size),
        "stop_loss": _level(position, "stop_loss", chart, "stop_loss"),
        "take_profit_1": _level(position, "take_profit_1", chart, "take_profit_1"),
        "take_profit_2": _level(position, "take_profit_2", chart, "take_profit_2"),
        "trailing_stop": _fmt_price(position.trailing_stop) if position and position.trailing_stop else None,
        "breakeven_price": _breakeven_price(position, True),
        "size": _fmt_price(size),
        "leverage": None,
        "exposure_usd": _q2(size * entry),
        # Le fee sono pagate all'apertura e salvate sulla posizione: i trade di
        # chiusura (cls_) le hanno a None, quindi si legge prima dalla posizione.
        "fee_mode": (position.fee_mode if position and position.fee_mode else trade.fee_mode),
        "swap_fee_usd": _fee_opt(
            position.swap_fee_usd if position and position.swap_fee_usd is not None else trade.swap_fee_usd
        ),
        "slippage_usd": _fee_opt(
            position.slippage_usd if position and position.slippage_usd is not None else trade.slippage_usd
        ),
        "gas_cost_bnb": str(Decimal(str(trade.gas_cost_bnb)).normalize()) if trade.gas_cost_bnb is not None else None,
        "opened_at": opened_at,
        "closed_at": closed_at,
        "duration_seconds": None,
        "close_reason": _close_reason(trade),
        "decision": _decision_payload(decision),
        "events": [],
        "chart": chart,
        "is_simulated": trade.trade_id.startswith("dry_") or trade.provider == "dry_run",
    }


def _perp_trade_detail(
    trade: PerpTrade,
    position: PerpPosition | None,
    decision: AgentDecision | None,
    settings=None,
    snapshot: TradeChartSnapshot | None = None,
    live_chart: dict | None = None,
    post_close_candles: list[dict] | None = None,
    chart_payload: dict | None = None,
) -> dict:
    # Per posizioni ancora aperte il grafico live prevale sullo snapshot parziale (TP1).
    raw_chart = live_chart if live_chart is not None else (chart_payload if chart_payload is not None else (json.loads(snapshot.payload) if snapshot else None))
    chart = _normalize_closed_chart(raw_chart)
    side = position.side if position is not None else trade.side
    chart = _apply_display_stop_to_chart(chart, position, settings, "perp", side)
    if chart is not None and post_close_candles:
        chart = {**chart, "post_close_candles": post_close_candles}
    is_close = trade.trade_id.startswith("cls_")
    is_ssl = trade.trade_id.startswith("ssl_")
    entry = (
        Decimal(position.entry_price) if position is not None
        else Decimal(str(chart["entry_price"])) if chart
        else Decimal(trade.price)
    )
    if is_close or is_ssl:
        current = Decimal(trade.price)
    elif position is not None:
        current = Decimal(position.current_price)
    elif chart:
        current = Decimal(str(chart["exit_price"]))
    else:
        current = Decimal(trade.price)
    size = Decimal(trade.size) if (is_close or is_ssl or position is None) else Decimal(position.size)
    if trade.pnl_usd is not None:
        pnl = Decimal(trade.pnl_usd)
    elif position is not None:
        pnl = Decimal(position.pnl_unrealized)
    else:
        pnl = Decimal("0")
    leverage = trade.leverage or (position.leverage if position is not None else None)
    opened_at, closed_at = _trade_timeline(trade, position, chart, is_close or is_ssl)

    if is_ssl:
        original_entry = _smart_sl_original_entry(position) or entry
        return {
            "trade_id": trade.trade_id,
            "asset": trade.asset,
            "market": "perp",
            "direction": trade.side,
            "is_smart_sl": True,
            "ssl_action": "sell" if trade.direction == "close" else "rebuy",
            "ssl_level": "all" if "rebuy_all" in (trade.notes or "") else (trade.notes.rsplit("_l", 1)[-1] if trade.notes and "_l" in trade.notes else None),
            "entry_price": _fmt_price(original_entry),
            "original_entry_price": _fmt_price(original_entry),
            "current_position_entry_price": _fmt_price(entry),
            "current_or_exit_price": _fmt_price(current),
            "pnl_usd": _signed(_q2(pnl)),
            "pnl_pct": _pnl_pct(pnl, original_entry, size, leverage or 1),
            "size": _fmt_price(size),
            "leverage": leverage,
            "exposure_usd": _q2(size * current),
            "opened_at": opened_at,
            "closed_at": closed_at,
            "duration_seconds": None,
            "close_reason": _close_reason(trade),
            "decision": None,
            "events": [],
            **_smart_sl_detail(position),
            "chart": None,
            "is_simulated": trade.trade_id.startswith("dry_") or trade.venue == "dry_run",
        }

    return {
        "trade_id": trade.trade_id,
        "asset": trade.asset,
        "market": "perp",
        "direction": trade.side,
        "entry_price": _fmt_price(entry),
        "current_or_exit_price": _fmt_price(current),
        "pnl_usd": _signed(_q2(pnl)),
        "pnl_pct": _pnl_pct(pnl, entry, size, leverage or 1),
        "stop_loss": _level(position, "stop_loss", chart, "stop_loss"),
        "take_profit_1": _level(position, "take_profit_1", chart, "take_profit_1"),
        "take_profit_2": _level(position, "take_profit_2", chart, "take_profit_2"),
        "liquidation_price": _level(position, "liquidation_price", chart, "liquidation_price"),
        "stop_reference_price": _stop_reference_price(position, chart),
        "stop_reference_field": _trade_stop_reference_field(position, chart),
        "trailing_stop": _fmt_price(position.trailing_stop) if position and position.trailing_stop else None,
        "breakeven_price": _breakeven_price(position, (position.side == "long") if position else True),
        "size": _fmt_price(size),
        "leverage": leverage,
        "exposure_usd": _q2(size * entry),
        "fee_mode": position.fee_mode if position else trade.fee_mode,
        "margin_usd": _q2(position.margin_usd) if position and position.margin_usd is not None else None,
        "opening_fee_usd": _fee_opt(position.opening_fee_usd) if position and position.opening_fee_usd is not None else None,
        "taker_fee_usd": _fee_opt(position.taker_fee_usd if position and position.taker_fee_usd is not None else trade.taker_fee_usd),
        "maker_fee_usd": _fee_opt(position.maker_fee_usd if position and position.maker_fee_usd is not None else trade.maker_fee_usd),
        "slippage_usd": _fee_opt(position.slippage_usd if position and position.slippage_usd is not None else trade.slippage_usd),
        "funding_accrued_usd": _fee_opt(position.funding_accrued_usd) if position else None,
        "funding_rate_8h": str(position.funding_rate) if position and position.funding_rate is not None else None,
        "opened_at": opened_at,
        "closed_at": closed_at,
        "duration_seconds": None,
        "close_reason": _close_reason(trade),
        "decision": _decision_payload(decision),
        "events": [{"name": "tp1", "reached": position.tp1_reached}] if position else [],
        **_smart_sl_detail(position),
        "chart": chart,
        "is_simulated": trade.trade_id.startswith("dry_") or trade.venue == "dry_run",
    }
