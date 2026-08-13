"""Repository for frozen trade chart snapshots."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.persistence.models.trade_charts import TradeChartSnapshot


class TradeChartRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, snapshot: TradeChartSnapshot) -> TradeChartSnapshot:
        self._session.add(snapshot)
        await self._session.commit()
        await self._session.refresh(snapshot)
        return snapshot

    async def get_for_close_trade(self, user_id: str, close_trade_id: str) -> TradeChartSnapshot | None:
        result = await self._session.execute(
            select(TradeChartSnapshot)
            .where(TradeChartSnapshot.user_id == user_id)
            .where(TradeChartSnapshot.close_trade_id == close_trade_id)
        )
        return result.scalar_one_or_none()

    async def get_for_position(self, user_id: str, position_id: str) -> TradeChartSnapshot | None:
        result = await self._session.execute(
            select(TradeChartSnapshot)
            .where(TradeChartSnapshot.user_id == user_id)
            .where(TradeChartSnapshot.position_id == position_id)
            .order_by(TradeChartSnapshot.created_at.desc())
        )
        return result.scalars().first()
