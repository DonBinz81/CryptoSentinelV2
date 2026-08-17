"""Dry-run venue: same contract as a real one, instant confirmation.

It writes a real row in ``perp_orders`` (created -> confirmed) so the
POSITION -> ORDER -> EXECUTION chain exists from day one and is exercised every
day by the dry-run, instead of being tested for the first time on a live venue.

It computes nothing economic: quantity and price are what the strategy decided,
and fees stay where they are today. Introducing this layer must not move a cent.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.logging import get_logger
from backend.app.execution.venues.base import ExecutionResult, PerpVenue
from backend.app.persistence.models.orders import PerpOrder

logger = get_logger("execution.venue.dry_run")

DRY_RUN_VENUE = "dry_run"


class DryRunPerpVenue(PerpVenue):
    """Simulated venue: the order is confirmed in full, immediately."""

    name = DRY_RUN_VENUE

    async def execute(
        self,
        session: AsyncSession,
        *,
        position_id: str,
        user_id: str,
        purpose: str,
        qty: Decimal,
        price: Decimal,
    ) -> ExecutionResult:
        now = datetime.now(UTC)
        order = PerpOrder(
            order_id=f"ord_{uuid4().hex[:16]}",
            position_id=position_id,
            user_id=user_id,
            venue=self.name,
            purpose=purpose,
            status="created",
            requested_qty=qty,
            filled_qty=Decimal("0"),
            created_at=now,
            updated_at=now,
        )
        session.add(order)

        # A simulated venue fills instantly and in full: created -> confirmed
        # within the same call. On a real venue these are two distinct moments.
        order.status = "confirmed"
        order.filled_qty = qty
        order.updated_at = now

        logger.info(
            "dry_run_order_confirmed",
            order_id=order.order_id,
            position_id=position_id,
            purpose=purpose,
            qty=float(qty),
            price=float(price),
        )
        return ExecutionResult(
            confirmed=True,
            venue=self.name,
            executed_qty=qty,
            executed_price=price,
            venue_order_id=order.order_id,
        )
