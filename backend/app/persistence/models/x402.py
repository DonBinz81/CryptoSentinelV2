"""ORM model for x402 daily spend budget."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class X402DailyBudget(Base):
    """Persists the cumulative x402 spend per user per UTC day.

    A single row is upserted each time a payment is reserved or rolled back so
    the daily cap survives process restarts.
    """

    __tablename__ = "x402_daily_budget"
    __table_args__ = (UniqueConstraint("user_id", "budget_date", name="uq_x402_user_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    budget_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    spent_usd: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False, default=Decimal("0"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
