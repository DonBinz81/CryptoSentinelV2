"""Perp order model — the missing link between a position and its executions.

Deliberately minimal: only the fields needed to represent the request and its
outcome. Execution telemetry (timestamps, latency, gas, price impact, network)
is NOT added here — it will be shaped on what the real venue actually returns,
not designed upfront on theory.

Lifecycle, identical for dry-run and live so both share one architecture:

    created -> submitted -> confirmed        (or rejected / cancelled)

In dry-run the venue confirms immediately, so an order is created and confirmed
within the same call; the row still exists, which is what makes the
POSITION -> ORDER -> EXECUTION chain real from day one.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.persistence.models.base import Base


class PerpOrder(Base):
    """A request sent to a venue on behalf of a perp position."""

    __tablename__ = "perp_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    position_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # Where the order is sent. For perp positions this is fixed at entry and must
    # match position.venue for every later order (reduce, close, protection).
    venue: Mapped[str] = mapped_column(String(64), nullable=False)

    # Why the order exists: entry | tp1 | tp2 | stop_loss | ratchet | smart_sl | close
    purpose: Mapped[str] = mapped_column(String(24), nullable=False)

    # created | submitted | confirmed | rejected | cancelled
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="created")

    requested_qty: Mapped[Decimal] = mapped_column(Numeric(30, 18), nullable=False)
    filled_qty: Mapped[Decimal] = mapped_column(Numeric(30, 18), nullable=False, default=Decimal("0"))

    # Identifiers produced by the venue: an order id, a transaction hash, or neither
    # (dry-run). Nullable because different venues expose different things.
    venue_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tx_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
