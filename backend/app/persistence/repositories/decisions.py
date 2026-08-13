"""Repository for agent decision records."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.persistence.models.decisions import AgentDecision


class AgentDecisionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, decision: AgentDecision) -> AgentDecision:
        self._session.add(decision)
        await self._session.commit()
        await self._session.refresh(decision)
        return decision

    async def get(self, decision_id: str) -> AgentDecision | None:
        result = await self._session.execute(
            select(AgentDecision).where(AgentDecision.decision_id == decision_id)
        )
        return result.scalar_one_or_none()

    async def recent_for_user(
        self,
        user_id: str,
        *,
        limit: int = 50,
        market: str | None = None,
    ) -> list[AgentDecision]:
        stmt = select(AgentDecision).where(AgentDecision.user_id == user_id)
        if market:
            stmt = stmt.where(AgentDecision.market == market)
        stmt = stmt.order_by(AgentDecision.timestamp_utc.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
