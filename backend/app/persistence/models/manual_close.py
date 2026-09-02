"""Idempotency ledger for human-initiated position closes.

A manual close is the one operation a user can fire twice by accident: a double
tap, a retry after an HTTP timeout, a phone that reconnects and replays. Each
attempt carries an ``Idempotency-Key``; this table is what makes a replay return
the first outcome instead of closing another slice of the position.

Lifecycle of a row:

``in_progress`` -> ``confirmed`` when the close completed
                -> ``failed``    when it was rejected or the venue refused

A replay of a key in ``confirmed`` or ``failed`` returns the stored response. A
replay of a key still ``in_progress`` means the first attempt has not finished:
the caller is told to wait rather than being allowed to run a second close.

``payload_fingerprint`` stores a hash of the meaningful request fields, so the
same key sent with a DIFFERENT payload can be rejected instead of silently
returning the wrong outcome.

Limit, stated on purpose: in dry-run the venue writes through the same session,
so the ledger row, the order, the trade and the position all commit or roll back
together. With a real venue the network call sits outside the transaction, and a
crash between "venue confirmed" and "commit" leaves the ledger without the
close it caused. Closing that gap needs reconciliation against the venue and
belongs to the live execution layer (NOTE/68), not here.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

#: Ledger states.
STATUS_IN_PROGRESS = "in_progress"
STATUS_CONFIRMED = "confirmed"
STATUS_FAILED = "failed"


class ManualCloseRequest(Base):
    """One row per ``Idempotency-Key`` presented to the manual close endpoint."""

    __tablename__ = "manual_close_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    idempotency_key: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    position_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    #: Always "perp" in this first version; the column exists so adding spot
    #: later does not need a migration on a table that will hold history.
    market: Mapped[str] = mapped_column(String(8), nullable=False, default="perp")

    requested_percentage: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_size: Mapped[Decimal | None] = mapped_column(Numeric(30, 18), nullable=True)
    payload_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_IN_PROGRESS)
    #: Business outcome kept next to the transport status: confirmed, rejected,
    #: stale_position, already_closed, execution_failed.
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: Serialised response, replayed verbatim to a repeated key.
    response_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    close_trade_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    venue_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
