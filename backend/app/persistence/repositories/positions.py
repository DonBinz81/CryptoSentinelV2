"""Repository for open spot and perpetual positions."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.persistence.models.positions import PerpPosition, SpotPosition


class SpotPositionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, position: SpotPosition) -> SpotPosition:
        self._session.add(position)
        await self._session.commit()
        await self._session.refresh(position)
        return position

    async def get(self, position_id: str) -> SpotPosition | None:
        result = await self._session.execute(
            select(SpotPosition).where(SpotPosition.position_id == position_id)
        )
        return result.scalar_one_or_none()

    async def open_for_user(self, user_id: str) -> list[SpotPosition]:
        result = await self._session.execute(
            select(SpotPosition)
            .where(SpotPosition.user_id == user_id)
            .where(SpotPosition.status == "open")
            .order_by(SpotPosition.opened_at.desc())
        )
        return list(result.scalars().all())

    async def history_for_user(self, user_id: str, *, limit: int = 50) -> list[SpotPosition]:
        result = await self._session.execute(
            select(SpotPosition)
            .where(SpotPosition.user_id == user_id)
            .order_by(SpotPosition.opened_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


class PerpPositionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, position: PerpPosition) -> PerpPosition:
        self._session.add(position)
        await self._session.commit()
        await self._session.refresh(position)
        return position

    async def get(self, position_id: str) -> PerpPosition | None:
        result = await self._session.execute(
            select(PerpPosition).where(PerpPosition.position_id == position_id)
        )
        return result.scalar_one_or_none()

    async def open_for_user(self, user_id: str) -> list[PerpPosition]:
        result = await self._session.execute(
            select(PerpPosition)
            .where(PerpPosition.user_id == user_id)
            .where(PerpPosition.status == "open")
            .order_by(PerpPosition.opened_at.desc())
        )
        return list(result.scalars().all())

    async def history_for_user(self, user_id: str, *, limit: int = 50) -> list[PerpPosition]:
        result = await self._session.execute(
            select(PerpPosition)
            .where(PerpPosition.user_id == user_id)
            .order_by(PerpPosition.opened_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
