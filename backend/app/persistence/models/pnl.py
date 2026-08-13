"""ORM models for hourly PnL snapshots and global portfolio state."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PnlSnapshot(Base):
    """Hourly equity snapshot used for PnL charts, drawdown tracking and scoring."""

    __tablename__ = "pnl_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    total_equity_usd: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    spot_equity_usd: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False, default=Decimal("0"))
    perp_equity_usd: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False, default=Decimal("0"))
    cash_usd: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False, default=Decimal("0"))
    drawdown_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=Decimal("0"))
    exposure_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=Decimal("0"))
    daily_pnl_usd: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False, default=Decimal("0"))
    open_spot_positions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_perp_positions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bnb_balance: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)


class PortfolioState(Base):
    """Latest global portfolio state — one row per user, upserted on each update."""

    __tablename__ = "portfolio_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    total_equity_usd: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False, default=Decimal("0"))
    initial_equity_usd: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False, default=Decimal("0"))
    peak_equity_usd: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False, default=Decimal("0"))
    drawdown_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=Decimal("0"))
    max_drawdown_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=Decimal("0"))
    exposure_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=Decimal("0"))
    daily_pnl_usd: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False, default=Decimal("0"))
    daily_loss_limit_used_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=Decimal("0"))
    agent_status: Mapped[str] = mapped_column(String(16), nullable=False, default="idle")
    trades_today: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extra_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
