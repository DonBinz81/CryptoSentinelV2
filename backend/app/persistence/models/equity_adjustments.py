"""ORM model for manual equity adjustments (deposits / withdrawals)."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class EquityAdjustment(Base):
    """Versamento (+) o prelievo (-) manuale di liquidità.

    Aggiorna l'equity come un deposito/prelievo, NON è PnL: alza la base
    (initial_equity) così il rendimento resta corretto. Ogni movimento lascia
    una riga qui per tracciabilità.
    """

    __tablename__ = "equity_adjustments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)          # +versamento / -prelievo
    balance_after: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)   # total_equity dopo il movimento
    note: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
