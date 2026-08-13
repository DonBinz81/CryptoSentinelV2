"""Repository for x402 daily spend budget persistence."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.persistence.models.x402 import X402DailyBudget


class X402BudgetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load_today(self, user_id: str) -> Decimal:
        """Return already-spent USD for today.  Returns 0 if no record exists."""
        today = datetime.now(UTC).date()
        result = await self._session.execute(
            select(X402DailyBudget)
            .where(X402DailyBudget.user_id == user_id)
            .where(X402DailyBudget.budget_date == today)
        )
        record = result.scalar_one_or_none()
        return record.spent_usd if record else Decimal("0")

    async def save(self, user_id: str, spent_usd: Decimal) -> None:
        """Upsert the current day's spend total."""
        today = datetime.now(UTC).date()
        now = datetime.now(UTC)
        result = await self._session.execute(
            select(X402DailyBudget)
            .where(X402DailyBudget.user_id == user_id)
            .where(X402DailyBudget.budget_date == today)
        )
        record = result.scalar_one_or_none()
        if record is None:
            record = X402DailyBudget(
                user_id=user_id,
                budget_date=today,
                spent_usd=spent_usd,
                updated_at=now,
            )
            self._session.add(record)
        else:
            record.spent_usd = spent_usd
            record.updated_at = now
        await self._session.commit()
