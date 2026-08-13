"""Repository for spot and perpetual trade records."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.persistence.models.trades import PerpTrade, SpotTrade


class SpotTradeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, trade: SpotTrade) -> SpotTrade:
        self._session.add(trade)
        await self._session.commit()
        await self._session.refresh(trade)
        return trade

    async def get(self, trade_id: str) -> SpotTrade | None:
        result = await self._session.execute(
            select(SpotTrade).where(SpotTrade.trade_id == trade_id)
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: str,
        *,
        limit: int = 100,
        status: str | None = None,
    ) -> list[SpotTrade]:
        stmt = select(SpotTrade).where(SpotTrade.user_id == user_id)
        if status:
            stmt = stmt.where(SpotTrade.status == status)
        stmt = stmt.order_by(SpotTrade.timestamp_utc.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_closed_for_user(self, user_id: str, *, limit: int | None = None) -> list[SpotTrade]:
        stmt = (
            select(SpotTrade)
            .where(SpotTrade.user_id == user_id)
            .where(SpotTrade.pnl_usd.is_not(None))
            .order_by(SpotTrade.timestamp_utc.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def win_rate(self, user_id: str) -> dict:
        """Win rate sui trade di chiusura (quelli con pnl_usd registrato)."""
        trades = await self.list_for_user(user_id, limit=10_000)
        closed = [t for t in trades if t.pnl_usd is not None]
        if not closed:
            return {"total": 0, "wins": 0, "win_rate_pct": 0.0}
        wins = sum(1 for t in closed if t.pnl_usd > 0)
        return {
            "total": len(closed),
            "wins": wins,
            "win_rate_pct": round(wins / len(closed) * 100, 1),
        }

    async def count_since(
        self,
        user_id: str,
        *,
        since: datetime,
        status: str | None = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(SpotTrade)
            .where(SpotTrade.user_id == user_id)
            .where(SpotTrade.timestamp_utc >= since)
        )
        if status:
            stmt = stmt.where(SpotTrade.status == status)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_closed(self, user_id: str, *, since: datetime | None = None) -> int:
        """Conta posizioni spot chiuse (trade con pnl_usd registrato). `since` filtra per giorno."""
        stmt = (
            select(func.count())
            .select_from(SpotTrade)
            .where(SpotTrade.user_id == user_id)
            .where(SpotTrade.pnl_usd.is_not(None))
        )
        if since is not None:
            stmt = stmt.where(SpotTrade.timestamp_utc >= since)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def first_timestamp_for_user(self, user_id: str) -> datetime | None:
        """Earliest spot trade timestamp for bot activity age."""
        result = await self._session.execute(
            select(func.min(SpotTrade.timestamp_utc)).where(SpotTrade.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def count_today(self, user_id: str, now: datetime) -> int:
        """Conta trade spot dell'utente nel giorno corrente (da mezzanotte UTC)."""
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self._session.execute(
            select(func.count())
            .select_from(SpotTrade)
            .where(SpotTrade.user_id == user_id)
            .where(SpotTrade.timestamp_utc >= start)
        )
        return int(result.scalar_one())

    async def sum_realized_pnl(self, user_id: str, *, since: datetime | None = None) -> Decimal:
        """Somma pnl_usd di tutti i trade spot con pnl registrato."""
        stmt = (
            select(func.sum(SpotTrade.pnl_usd))
            .where(SpotTrade.user_id == user_id)
            .where(SpotTrade.pnl_usd.is_not(None))
        )
        if since is not None:
            stmt = stmt.where(SpotTrade.timestamp_utc >= since)
        result = await self._session.execute(stmt)
        val = result.scalar_one_or_none()
        return Decimal(str(val)) if val is not None else Decimal("0")

    async def sum_fees(self, user_id: str, *, since: datetime | None = None) -> Decimal:
        """Somma fees_quote dei trade spot (fee pagate). `since` filtra per giorno."""
        stmt = (
            select(func.sum(SpotTrade.fees_quote))
            .where(SpotTrade.user_id == user_id)
            .where(SpotTrade.fees_quote.is_not(None))
        )
        if since is not None:
            stmt = stmt.where(SpotTrade.timestamp_utc >= since)
        result = await self._session.execute(stmt)
        val = result.scalar_one_or_none()
        return Decimal(str(val)) if val is not None else Decimal("0")

    async def last_timestamp_for_asset(self, user_id: str, asset: str) -> datetime | None:
        """Timestamp del trade spot piu' recente sull'asset (per cooldown)."""
        result = await self._session.execute(
            select(func.max(SpotTrade.timestamp_utc))
            .where(SpotTrade.user_id == user_id)
            .where(SpotTrade.asset == asset)
        )
        return result.scalar_one_or_none()


class PerpTradeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, trade: PerpTrade) -> PerpTrade:
        self._session.add(trade)
        await self._session.commit()
        await self._session.refresh(trade)
        return trade

    async def get(self, trade_id: str) -> PerpTrade | None:
        result = await self._session.execute(
            select(PerpTrade).where(PerpTrade.trade_id == trade_id)
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: str,
        *,
        limit: int = 100,
        status: str | None = None,
    ) -> list[PerpTrade]:
        stmt = select(PerpTrade).where(PerpTrade.user_id == user_id)
        if status:
            stmt = stmt.where(PerpTrade.status == status)
        stmt = stmt.order_by(PerpTrade.timestamp_utc.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_closed_for_user(self, user_id: str, *, limit: int | None = None) -> list[PerpTrade]:
        stmt = (
            select(PerpTrade)
            .where(PerpTrade.user_id == user_id)
            .where(PerpTrade.pnl_usd.is_not(None))
            .order_by(PerpTrade.timestamp_utc.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_today(self, user_id: str, now: datetime) -> int:
        """Conta trade perp dell'utente nel giorno corrente (da mezzanotte UTC)."""
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self._session.execute(
            select(func.count())
            .select_from(PerpTrade)
            .where(PerpTrade.user_id == user_id)
            .where(PerpTrade.timestamp_utc >= start)
        )
        return int(result.scalar_one())

    async def count_closed(self, user_id: str, *, since: datetime | None = None) -> int:
        """Conta posizioni perp chiuse (trade con pnl_usd registrato). `since` filtra per giorno."""
        stmt = (
            select(func.count())
            .select_from(PerpTrade)
            .where(PerpTrade.user_id == user_id)
            .where(PerpTrade.pnl_usd.is_not(None))
        )
        if since is not None:
            stmt = stmt.where(PerpTrade.timestamp_utc >= since)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def first_timestamp_for_user(self, user_id: str) -> datetime | None:
        """Earliest perp trade timestamp for bot activity age."""
        result = await self._session.execute(
            select(func.min(PerpTrade.timestamp_utc)).where(PerpTrade.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def sum_realized_pnl(self, user_id: str, *, since: datetime | None = None) -> Decimal:
        """Somma pnl_usd di tutti i trade perp con pnl registrato."""
        stmt = (
            select(func.sum(PerpTrade.pnl_usd))
            .where(PerpTrade.user_id == user_id)
            .where(PerpTrade.pnl_usd.is_not(None))
        )
        if since is not None:
            stmt = stmt.where(PerpTrade.timestamp_utc >= since)
        result = await self._session.execute(stmt)
        val = result.scalar_one_or_none()
        return Decimal(str(val)) if val is not None else Decimal("0")

    async def sum_fees(self, user_id: str, *, since: datetime | None = None) -> Decimal:
        """Somma fees_quote dei trade perp (fee pagate). `since` filtra per giorno."""
        stmt = (
            select(func.sum(PerpTrade.fees_quote))
            .where(PerpTrade.user_id == user_id)
            .where(PerpTrade.fees_quote.is_not(None))
            .where(PerpTrade.direction == "open")
        )
        if since is not None:
            stmt = stmt.where(PerpTrade.timestamp_utc >= since)
        result = await self._session.execute(stmt)
        val = result.scalar_one_or_none()
        return Decimal(str(val)) if val is not None else Decimal("0")

    async def last_timestamp_for_asset(self, user_id: str, asset: str) -> datetime | None:
        """Timestamp del trade perp piu' recente sull'asset (per cooldown)."""
        result = await self._session.execute(
            select(func.max(PerpTrade.timestamp_utc))
            .where(PerpTrade.user_id == user_id)
            .where(PerpTrade.asset == asset)
        )
        return result.scalar_one_or_none()

    async def win_rate(self, user_id: str) -> dict:
        """Win rate sui trade di chiusura (quelli con pnl_usd registrato)."""
        trades = await self.list_for_user(user_id, limit=10_000)
        closed = [t for t in trades if t.pnl_usd is not None]
        if not closed:
            return {"total": 0, "wins": 0, "win_rate_pct": 0.0}
        wins = sum(1 for t in closed if t.pnl_usd > 0)
        return {
            "total": len(closed),
            "wins": wins,
            "win_rate_pct": round(wins / len(closed) * 100, 1),
        }
