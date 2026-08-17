"""Common perp venue contract: the strategy asks, the venue confirms.

Deliberately minimal — only what the dry-run needs today. Execution telemetry
(timestamps, latency, gas, price impact) is not modelled here: it will be shaped
on what a real venue actually returns.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class ExecutionResult:
    """Authoritative outcome of an execution request.

    The economic state of a position must advance only on ``confirmed``: asking
    for a close is not the same as having closed.
    """

    confirmed: bool
    venue: str
    executed_qty: Decimal
    executed_price: Decimal
    # Fees stay with the caller: the dry-run already computes them from the
    # position, and this contract must not change the economics.
    fee: Decimal | None = None
    venue_order_id: str | None = None
    venue_execution_id: str | None = None
    tx_hash: str | None = None
    status: str = "confirmed"
    reason: str | None = None


class PerpVenue(ABC):
    """A place where perp orders are executed (simulated or real)."""

    #: Stable identifier persisted on positions, orders and trades.
    name: str

    @abstractmethod
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
        """Record the order and return what was actually executed.

        ``purpose`` is why the order exists (entry, tp1, tp2, stop_loss, ratchet,
        smart_sl, close): it is persisted so every execution can be traced back to
        the decision that caused it.
        """
