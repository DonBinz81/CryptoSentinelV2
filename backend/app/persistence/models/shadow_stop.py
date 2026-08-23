"""Shadow-stop run table (NOTE/91): one row per perp position, tracking what
David's tight-stop + confirmed-reclaim rule would have done. Diagnostics
only — the trading engine never reads this back.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.persistence.models.base import Base


class ShadowStopRun(Base):
    """Live simulation state for one position, advanced one closed 5m candle
    at a time. ``state_json`` is the full state dict from shadow_stop.py —
    self-contained, so a run can be replayed or inspected without other
    tables. ``outcome``/``pnl_virtual_pct`` are denormalized for quick reads.
    """

    __tablename__ = "shadow_stop_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    position_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    asset: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    tp1: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    entry_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    buffer_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    max_reentries: Mapped[int] = mapped_column(Integer, nullable=False)
    state_json: Mapped[str] = mapped_column(Text, nullable=False)
    events_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    outcome: Mapped[str | None] = mapped_column(String(24), nullable=True)
    pnl_virtual_pct: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    last_candle_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
