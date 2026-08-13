"""Agent Step 6 status, kill-switch and dry-run evaluation routes."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from pydantic import BaseModel, ConfigDict, Field

from backend.app.agent.risk import KillSwitchState
from backend.app.agent.service import get_agent_service
from backend.app.agent.watchlist import (
    selected_watchlist, set_selected_watchlist,
    selected_spot_watchlist, selected_perp_watchlist, set_market_watchlist,
)
from backend.app.agent.ohlcv_warmup import warmup_selected_watchlist
from backend.app.persistence.models.decisions import AgentDecision
from backend.app.persistence.repositories.api_usage import ApiUsageRepository
from backend.app.persistence.repositories.pnl import PnlRepository
from backend.app.schemas.views import ClaudeUsageView
from backend.app.api.dependencies import AdminAccessDep, ReadAccessDep, SessionDep
from backend.app.core.config import get_settings

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


class KillSwitchRequest(BaseModel):
    state: Literal["running", "soft_stop", "hard_stop", "degraded"]


class AgentWatchlistRequest(BaseModel):
    tokens: list[str] = Field(default_factory=list)


class AgentEvaluateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    market: Literal["spot", "perp"]
    payload: dict[str, Any] = Field(default_factory=dict)

    def normalized_payload(self) -> dict[str, Any]:
        """Accept both nested payloads and the legacy flat evaluation body."""

        normalized = dict(self.payload)
        for key, value in (self.model_extra or {}).items():
            normalized.setdefault(key, value)
        return normalized


@router.get("/status")
async def agent_status(_: ReadAccessDep) -> dict:
    """Return non-sensitive agent status."""

    return get_agent_service().status()


@router.get("/data-coverage")
async def agent_data_coverage(_: ReadAccessDep) -> dict:
    """Return OHLCV cache coverage for agent signal engines."""

    return get_agent_service().data_coverage()


@router.get("/eligible-tokens")
async def agent_eligible_tokens(_: ReadAccessDep) -> dict:
    """Return the configured tradable token universe for client UI gating."""

    service = get_agent_service()
    return {
        "count": len(service.settings.eligible_tokens),
        "tokens": service.settings.eligible_tokens,
    }


@router.get("/watchlist")
async def agent_watchlist(_: ReadAccessDep) -> dict:
    """Return the eligible universe and the operational agent watchlist."""

    service = get_agent_service()
    selected = selected_watchlist(service.settings)
    return {
        "eligible_count": len(service.settings.eligible_tokens),
        "eligible_tokens": service.settings.eligible_tokens,
        "selected_count": len(selected),
        "selected_tokens": selected,
    }


@router.get("/decisions")
async def agent_decisions(
    _: ReadAccessDep,
    session: SessionDep,
    market: str | None = Query(None, pattern="^(spot|perp)$"),
    action: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    """Return paginated agent decision log."""

    service = get_agent_service()
    stmt = select(AgentDecision).where(AgentDecision.user_id == str(service.settings.default_user_id))
    if market:
        stmt = stmt.where(AgentDecision.market == market)
    if action:
        stmt = stmt.where(AgentDecision.action == action)
    stmt = stmt.order_by(AgentDecision.timestamp_utc.desc()).offset(offset).limit(limit)
    rows = list((await session.execute(stmt)).scalars().all())
    return {
        "items": [
            {
                "decision_id": row.decision_id,
                "timestamp_utc": row.timestamp_utc.isoformat(),
                "asset": row.asset,
                "market": row.market,
                "signal_quality": f"{(row.signal_quality or 0):.2f}",
                "confidence": f"{(row.confidence or 0):.2f}",
                "action": row.action,
                "reasoning": row.reasoning,
                "execution_result": row.execution_result,
                "trade_id": row.trade_id,
            }
            for row in rows
        ],
        "limit": limit,
        "offset": offset,
    }


@router.put("/watchlist")
async def set_agent_watchlist(request: AgentWatchlistRequest, _: AdminAccessDep) -> dict:
    """Persist the operational agent watchlist."""

    service = get_agent_service()
    previous = set(selected_watchlist(service.settings))
    try:
        selected = set_selected_watchlist(service.settings, request.tokens)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    added = [token for token in selected if token not in previous]
    # Il warmup OHLCV e' solo un'ottimizzazione di cache: gira in background per non
    # bloccare la risposta. Per i token senza mercato Binance (es. token piccoli della
    # competizione) il fetch va in timeout e bloccava la PUT, facendo "rimbalzare" la
    # selezione nel client. La watchlist e' gia' stata persistita sopra.
    if added:
        asyncio.create_task(warmup_selected_watchlist(service.settings, assets=added))
        warmup = {"status": "scheduled", "assets": added}
    else:
        warmup = {"status": "skipped", "reason": "no_new_tokens", "items": []}
    return {
        "eligible_count": len(service.settings.eligible_tokens),
        "eligible_tokens": service.settings.eligible_tokens,
        "selected_count": len(selected),
        "selected_tokens": selected,
        "warmup": warmup,
    }


@router.get("/watchlist/spot")
async def get_spot_watchlist(_: ReadAccessDep) -> dict:
    service = get_agent_service()
    master = selected_watchlist(service.settings)
    selected = selected_spot_watchlist(service.settings)
    return {"master_tokens": master, "selected_tokens": selected, "selected_count": len(selected)}


@router.put("/watchlist/spot")
async def set_spot_watchlist(request: AgentWatchlistRequest, _: AdminAccessDep) -> dict:
    service = get_agent_service()
    try:
        selected = set_market_watchlist(service.settings, "spot", request.tokens)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"selected_tokens": selected, "selected_count": len(selected)}


@router.get("/watchlist/perp")
async def get_perp_watchlist(_: ReadAccessDep) -> dict:
    service = get_agent_service()
    master = selected_watchlist(service.settings)
    selected = selected_perp_watchlist(service.settings)
    return {"master_tokens": master, "selected_tokens": selected, "selected_count": len(selected)}


@router.put("/watchlist/perp")
async def set_perp_watchlist(request: AgentWatchlistRequest, _: AdminAccessDep) -> dict:
    service = get_agent_service()
    try:
        selected = set_market_watchlist(service.settings, "perp", request.tokens)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    added = [t for t in selected if t not in set(selected_perp_watchlist(service.settings))]
    if added:
        asyncio.create_task(warmup_selected_watchlist(service.settings, assets=added))
    return {"selected_tokens": selected, "selected_count": len(selected)}


@router.put("/kill-switch")
async def set_kill_switch(request: KillSwitchRequest, _: AdminAccessDep) -> dict:
    """Set the process-level agent kill switch."""

    return get_agent_service().set_kill_switch(KillSwitchState(request.state))


@router.post("/risk/close-all")
async def risk_close_all(session: SessionDep, _: AdminAccessDep) -> dict:
    """Risk action: close every open spot/perp position and pause the agent.

    Resume trading afterwards via PUT /kill-switch {state: running}.
    """

    return await get_agent_service().close_all_and_pause(session, reason="manual_risk")


class ResetDbRequest(BaseModel):
    backup_name: str | None = Field(default=None, max_length=120)


@router.post("/dev/reset-db")
async def dev_reset_db(request: ResetDbRequest, session: SessionDep, _: AdminAccessDep) -> dict:
    """Modalità sviluppatore: azzera l'intero dataset di trading (trade, decisioni,
    posizioni, PnL, portfolio, grafici) e riporta l'agente allo stato di default.

    Se ``backup_name`` è valorizzato, salva PRIMA uno snapshot completo recuperabile
    in archived_runs. Le impostazioni e la watchlist NON vengono toccate.

    Reset pulito = anche il kill switch torna a ``running`` (un eventuale hard_stop
    da un precedente \"chiudi tutto & pausa\" resterebbe altrimenti in memoria).
    """

    from backend.app.persistence.archive import reset_all_data

    settings = get_settings()
    label = (request.backup_name or "").strip() or None
    result = await reset_all_data(
        session,
        user_id=str(settings.default_user_id),
        backup_label=label,
        reset_portfolio_capital_usd=Decimal(str(settings.dry_run_capital_usd)),
    )

    # Stato agente al default: riavvia da running e azzera eventuali degraded.
    service = get_agent_service()
    service.risk.set_kill_switch(KillSwitchState.RUNNING)
    service.risk.clear_degraded()
    result["kill_switch"] = service.risk.kill_switch.value
    return result


class EquityAdjustRequest(BaseModel):
    amount: float = Field(..., description="Importo: positivo = versamento, negativo = prelievo")
    note: str | None = Field(default=None, max_length=120)


@router.post("/equity/adjust")
async def adjust_equity(request: EquityAdjustRequest, session: SessionDep, _: AdminAccessDep) -> dict:
    """Versamento (+) o prelievo (-) di liquidità.

    Tratta l'importo come un deposito: alza l'equity e la base (initial_equity)
    dello stesso valore, quindi il PnL (= realized + unrealized) NON cambia.
    """

    try:
        amount = Decimal(str(request.amount))
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=400, detail="amount_not_a_number")
    if amount == 0:
        raise HTTPException(status_code=400, detail="amount_must_be_nonzero")

    settings = get_settings()
    try:
        portfolio, adjustment = await PnlRepository(session).adjust_equity(
            str(settings.default_user_id),
            amount=amount,
            base_capital=Decimal(str(settings.dry_run_capital_usd)),
            note=(request.note or "").strip() or None,
            now=datetime.now(UTC),
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="equity_would_go_negative")

    return {
        "status": "ok",
        "applied": str(amount),
        "total_equity_usd": str(portfolio.total_equity_usd),
        "initial_equity_usd": str(portfolio.initial_equity_usd),
        "adjustment_id": adjustment.id,
        "created_at": adjustment.created_at.isoformat(),
    }


@router.get("/equity/adjustments")
async def equity_adjustments(_: ReadAccessDep, session: SessionDep, limit: int = Query(50, ge=1, le=200)) -> dict:
    """Storico dei versamenti/prelievi manuali (più recenti prima)."""

    settings = get_settings()
    rows = await PnlRepository(session).list_equity_adjustments(
        str(settings.default_user_id), limit=limit
    )
    items = [
        {
            "id": row.id,
            "amount": str(row.amount),
            "balance_after": str(row.balance_after),
            "note": row.note,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]
    return {"items": items, "count": len(items)}


# Cache leggera della summary spesa Claude: evita una query DB a ogni refresh dell'app.
_CLAUDE_USAGE_CACHE: dict[str, object] = {"at": 0.0, "view": None}
_CLAUDE_USAGE_TTL_SECONDS = 300.0


@router.get("/claude-usage", response_model=ClaudeUsageView)
async def claude_usage(_: ReadAccessDep, session: SessionDep) -> ClaudeUsageView:
    """Return cumulative Claude API token usage and estimated cost (cached ~60s)."""
    cached = _CLAUDE_USAGE_CACHE.get("view")
    if cached is not None and (time.monotonic() - float(_CLAUDE_USAGE_CACHE["at"])) < _CLAUDE_USAGE_TTL_SECONDS:
        return cached  # type: ignore[return-value]

    settings = get_settings()
    budget = settings.anthropic_budget_usd
    baseline = settings.anthropic_cost_baseline_usd
    try:
        summary = await ApiUsageRepository(session).summary()
        cost = summary["total_cost_usd"] + baseline
    except Exception:
        summary = {"call_count": 0, "input_tokens": 0, "output_tokens": 0}
        cost = baseline
    view = ClaudeUsageView(
        call_count=summary["call_count"],
        input_tokens=summary["input_tokens"],
        output_tokens=summary["output_tokens"],
        total_cost_usd=round(cost, 6),
        budget_usd=budget,
        budget_pct=round(cost / budget * 100, 1) if budget > 0 else 0.0,
    )
    _CLAUDE_USAGE_CACHE["view"] = view
    _CLAUDE_USAGE_CACHE["at"] = time.monotonic()
    return view


@router.post("/evaluate")
async def evaluate_signal(request: AgentEvaluateRequest, _: AdminAccessDep, session: SessionDep) -> dict:
    """Evaluate an explicit signal payload through signal, risk and brain layers."""

    service = get_agent_service()
    payload = request.normalized_payload()
    try:
        if request.market == "spot":
            return await service.evaluate_spot(payload, session)
        return await service.evaluate_perp(payload, session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
