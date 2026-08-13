"""Archive dry-run data before resetting live analytics."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.persistence.models.archives import ArchivedRun
from backend.app.persistence.models.decisions import AgentDecision
from backend.app.persistence.models.pnl import PnlSnapshot, PortfolioState
from backend.app.persistence.models.positions import PerpPosition, SpotPosition
from backend.app.persistence.models.trade_charts import TradeChartSnapshot
from backend.app.persistence.models.trades import PerpTrade, SpotTrade


DEFAULT_ARCHIVE_LABEL = "pre_500_reset_2026_06_20"


async def archive_dry_run_records(
    session: AsyncSession,
    *,
    user_id: str,
    archive_label: str = DEFAULT_ARCHIVE_LABEL,
    delete_live: bool = True,
    reset_portfolio_capital_usd: Decimal | None = None,
) -> ArchivedRun:
    """Copy current simulated records into one archive row and remove them from live tables."""

    archived_at = datetime.now(UTC)
    spot_trades = await _scalars(session, _spot_dry_run_select(user_id))
    perp_trades = await _scalars(session, _perp_dry_run_select(user_id))
    decisions = await _scalars(session, _decision_dry_run_select(user_id))
    snapshots = await _scalars(session, select(PnlSnapshot).where(PnlSnapshot.user_id == user_id))
    portfolio = (
        await session.execute(select(PortfolioState).where(PortfolioState.user_id == user_id))
    ).scalar_one_or_none()
    payload = {
        "spot_trades": [_model_payload(row) for row in spot_trades],
        "perp_trades": [_model_payload(row) for row in perp_trades],
        "agent_decisions": [_model_payload(row) for row in decisions],
        "pnl_snapshots": [_model_payload(row) for row in snapshots],
        "portfolio_state": [_model_payload(portfolio)] if portfolio is not None else [],
    }
    archive = ArchivedRun(
        run_id=f"arch_{archived_at.strftime('%Y%m%dT%H%M%S')}_{uuid4().hex[:10]}",
        user_id=user_id,
        archive_label=archive_label,
        archived_at=archived_at,
        is_simulated=True,
        payload_json=json.dumps(payload, default=_json_default, separators=(",", ":")),
    )
    session.add(archive)

    if delete_live:
        await session.execute(delete(SpotTrade).where(SpotTrade.id.in_([row.id for row in spot_trades])))
        await session.execute(delete(PerpTrade).where(PerpTrade.id.in_([row.id for row in perp_trades])))
        await session.execute(delete(AgentDecision).where(AgentDecision.id.in_([row.id for row in decisions])))
        await session.execute(delete(PnlSnapshot).where(PnlSnapshot.id.in_([row.id for row in snapshots])))
        if portfolio is not None and reset_portfolio_capital_usd is not None:
            portfolio.total_equity_usd = reset_portfolio_capital_usd
            portfolio.initial_equity_usd = reset_portfolio_capital_usd
            portfolio.peak_equity_usd = reset_portfolio_capital_usd
            portfolio.drawdown_pct = Decimal("0")
            portfolio.max_drawdown_pct = Decimal("0")
            portfolio.exposure_pct = Decimal("0")
            portfolio.daily_pnl_usd = Decimal("0")
            portfolio.daily_loss_limit_used_pct = Decimal("0")
            portfolio.agent_status = "idle"
            portfolio.trades_today = 0
            portfolio.updated_at = archived_at

    await session.commit()
    await session.refresh(archive)
    return archive


async def reset_all_data(
    session: AsyncSession,
    *,
    user_id: str,
    backup_label: str | None = None,
    reset_portfolio_capital_usd: Decimal | None = None,
) -> dict:
    """Azzera l'intero dataset di trading dell'utente.

    Cancella trade, decisioni, posizioni aperte, snapshot PnL, portfolio e grafici
    congelati. Se ``backup_label`` è valorizzato, salva PRIMA uno snapshot completo
    (tutti i record, non solo i dry-run) in ``archived_runs``, così è recuperabile.
    Non tocca: archived_runs, runtime_state (impostazioni), device token, alert.
    """

    archived_at = datetime.now(UTC)
    spot_trades = await _scalars(session, select(SpotTrade).where(SpotTrade.user_id == user_id))
    perp_trades = await _scalars(session, select(PerpTrade).where(PerpTrade.user_id == user_id))
    decisions = await _scalars(session, select(AgentDecision).where(AgentDecision.user_id == user_id))
    snapshots = await _scalars(session, select(PnlSnapshot).where(PnlSnapshot.user_id == user_id))
    spot_positions = await _scalars(session, select(SpotPosition).where(SpotPosition.user_id == user_id))
    perp_positions = await _scalars(session, select(PerpPosition).where(PerpPosition.user_id == user_id))
    charts = await _scalars(session, select(TradeChartSnapshot).where(TradeChartSnapshot.user_id == user_id))
    portfolio = (
        await session.execute(select(PortfolioState).where(PortfolioState.user_id == user_id))
    ).scalar_one_or_none()

    counts = {
        "spot_trades": len(spot_trades),
        "perp_trades": len(perp_trades),
        "agent_decisions": len(decisions),
        "pnl_snapshots": len(snapshots),
        "spot_positions": len(spot_positions),
        "perp_positions": len(perp_positions),
        "trade_chart_snapshots": len(charts),
        "portfolio_state": 1 if portfolio is not None else 0,
    }

    archived_run_id: str | None = None
    if backup_label:
        payload = {
            "spot_trades": [_model_payload(row) for row in spot_trades],
            "perp_trades": [_model_payload(row) for row in perp_trades],
            "agent_decisions": [_model_payload(row) for row in decisions],
            "pnl_snapshots": [_model_payload(row) for row in snapshots],
            "spot_positions": [_model_payload(row) for row in spot_positions],
            "perp_positions": [_model_payload(row) for row in perp_positions],
            "portfolio_state": [_model_payload(portfolio)] if portfolio is not None else [],
        }
        archive = ArchivedRun(
            run_id=f"arch_{archived_at.strftime('%Y%m%dT%H%M%S')}_{uuid4().hex[:10]}",
            user_id=user_id,
            archive_label=backup_label,
            archived_at=archived_at,
            is_simulated=True,
            payload_json=json.dumps(payload, default=_json_default, separators=(",", ":")),
        )
        session.add(archive)
        archived_run_id = archive.run_id

    await session.execute(delete(SpotTrade).where(SpotTrade.user_id == user_id))
    await session.execute(delete(PerpTrade).where(PerpTrade.user_id == user_id))
    await session.execute(delete(AgentDecision).where(AgentDecision.user_id == user_id))
    await session.execute(delete(PnlSnapshot).where(PnlSnapshot.user_id == user_id))
    await session.execute(delete(SpotPosition).where(SpotPosition.user_id == user_id))
    await session.execute(delete(PerpPosition).where(PerpPosition.user_id == user_id))
    await session.execute(delete(TradeChartSnapshot).where(TradeChartSnapshot.user_id == user_id))
    await session.execute(delete(PortfolioState).where(PortfolioState.user_id == user_id))
    if reset_portfolio_capital_usd is not None:
        session.add(
            PortfolioState(
                user_id=user_id,
                total_equity_usd=reset_portfolio_capital_usd,
                initial_equity_usd=reset_portfolio_capital_usd,
                peak_equity_usd=reset_portfolio_capital_usd,
                drawdown_pct=Decimal("0"),
                max_drawdown_pct=Decimal("0"),
                exposure_pct=Decimal("0"),
                daily_pnl_usd=Decimal("0"),
                daily_loss_limit_used_pct=Decimal("0"),
                agent_status="idle",
                trades_today=0,
                updated_at=archived_at,
            )
        )

    await session.commit()
    return {
        "status": "ok",
        "archived_run_id": archived_run_id,
        "backup_label": backup_label if archived_run_id else None,
        "deleted": counts,
        "portfolio_reset": reset_portfolio_capital_usd is not None,
        "reset_portfolio_capital_usd": (
            str(reset_portfolio_capital_usd) if reset_portfolio_capital_usd is not None else None
        ),
    }


async def list_archived_runs(session: AsyncSession, *, user_id: str) -> list[dict]:
    result = await session.execute(
        select(ArchivedRun)
        .where(ArchivedRun.user_id == user_id)
        .order_by(ArchivedRun.archived_at.desc())
    )
    rows = result.scalars().all()
    return [
        {
            "run_id": row.run_id,
            "archive_label": row.archive_label,
            "archived_at": row.archived_at.isoformat(),
            "is_simulated": row.is_simulated,
            "counts": _archive_counts(row.payload_json),
        }
        for row in rows
    ]


async def _scalars(session: AsyncSession, statement) -> list:
    result = await session.execute(statement)
    return list(result.scalars().all())


def _spot_dry_run_select(user_id: str):
    return select(SpotTrade).where(SpotTrade.user_id == user_id).where(
        or_(
            SpotTrade.trade_id.like("dry_%"),
            SpotTrade.provider == "dry_run",
            SpotTrade.notes.like("%dry_run%"),
        )
    )


def _perp_dry_run_select(user_id: str):
    return select(PerpTrade).where(PerpTrade.user_id == user_id).where(
        or_(
            PerpTrade.trade_id.like("dry_%"),
            PerpTrade.venue == "dry_run",
            PerpTrade.notes.like("%dry_run%"),
        )
    )


def _decision_dry_run_select(user_id: str):
    return select(AgentDecision).where(AgentDecision.user_id == user_id).where(
        or_(
            AgentDecision.trade_id.like("dry_%"),
            AgentDecision.reasoning.like("%dry_run%"),
        )
    )


def _model_payload(row) -> dict:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def _json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _archive_counts(payload_json: str) -> dict[str, int]:
    try:
        payload = json.loads(payload_json)
    except ValueError:
        return {}
    return {key: len(value) for key, value in payload.items() if isinstance(value, list)}
