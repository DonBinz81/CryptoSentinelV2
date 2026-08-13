"""ORM model for frozen trade chart snapshots (redrawn in the trade detail)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class TradeChartSnapshot(Base):
    """Candele + livelli congelati alla chiusura di un trade, per ridisegnare il grafico.

    Salviamo i dati (non un'immagine): leggero e fedele anche a distanza di tempo.
    """

    __tablename__ = "trade_chart_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    position_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    close_trade_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    market: Mapped[str] = mapped_column(String(8), nullable=False)  # spot / perp
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # JSON: candele + livelli
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
