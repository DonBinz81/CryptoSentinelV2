"""Positioning telemetry tables (NOTE/76-78, deployed per NOTE/81).

Binance's futures positioning endpoints (open interest, long/short ratios,
taker flow) retain only ~30 days of history: without archiving them at trade
time, the evidence behind the two surviving conditional leads (per-pair OI
build-up and Brain confidence) becomes unrecoverable. These tables freeze that
evidence as it happens. Diagnostics only: nothing in the trading path reads
them back.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.persistence.models.base import Base


class EntryTelemetry(Base):
    """One row per perp position opening: pair positioning at entry time."""

    __tablename__ = "entry_telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    position_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    asset: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Per-pair positioning at entry; NULL = that fetch failed (visible absence).
    oi_d24_pct: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    ls_ratio: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    ls_d24_pct: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    taker_4h: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    brain_confidence: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    error: Mapped[str | None] = mapped_column(String(200), nullable=True)


class PositionTelemetry(Base):
    """Periodic snapshot (slow tick) of each open perp position's pair OI."""

    __tablename__ = "position_telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    position_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open_interest: Mapped[Decimal | None] = mapped_column(Numeric(30, 8), nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(30, 12), nullable=True)
    adverse_pct: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
