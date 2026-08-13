"""Provider-neutral execution contracts for perpetual execution providers.

Mirrors the spot abstraction ([base.py](backend/app/execution/base.py)) for the
perpetual market: a single ``PerpExecutionProvider`` interface with
interchangeable implementations behind a global selector, so a 2nd/3rd/4th perp
DEX can be added without touching the agent or API.

Spot and perp stay separate paths (distinct interfaces/registries): they are
different markets with different venue APIs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.app.execution.models import TransactionResult


class PerpExecutionProviderName(StrEnum):
    """Supported perpetual execution providers (extensible)."""

    BNB_SDK = "bnb_sdk"


PerpDirection = Literal["long", "short"]


class PerpExecutionProviderError(RuntimeError):
    """Raised when a perp execution request cannot be completed."""


class PerpProviderConfigurationError(PerpExecutionProviderError):
    """Raised when a selected perp provider is missing required configuration."""


class PerpCapabilityError(PerpExecutionProviderError):
    """Raised when a perp provider does not yet implement a capability.

    The current BNB SDK path is a signing/submission boundary without a
    configured venue, so high-level open/close/get-position raise this until a
    venue implementation lands (Step 6 / future perp DEX providers).
    """


class PerpOrder(BaseModel):
    """Normalized perpetual order, identical shape across providers."""

    asset: str
    direction: PerpDirection
    size: Decimal
    leverage: Decimal = Decimal(1)
    reduce_only: bool = False
    order_type: Literal["market", "limit"] = "market"
    limit_price: Decimal | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class PerpPositionView(BaseModel):
    """Normalized open perpetual position."""

    asset: str
    direction: PerpDirection
    size: Decimal
    leverage: Decimal
    entry_price: Decimal | None = None
    liquidation_price: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class PerpProviderStatus(BaseModel):
    """Non-secret perp execution provider runtime diagnostics."""

    name: PerpExecutionProviderName
    configured: bool
    network: str
    venue_configured: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class PerpExecutionProvider(ABC):
    """Common high-level interface consumed by the agent, risk engine and API.

    Implementations translate the normalized order into their venue logic (for
    BNB SDK: EIP-712 sign + submit; for a perp DEX: a web3 contract call). The
    high-level methods carry a fail-closed default so a boundary-only provider
    inherits a consistent "not yet available" behaviour without duplication.
    """

    name: PerpExecutionProviderName

    @abstractmethod
    def status(self) -> PerpProviderStatus:
        """Return non-secret runtime diagnostics."""

    async def open_position(self, order: PerpOrder) -> TransactionResult:
        """Open (or add to) a perpetual position."""

        raise PerpCapabilityError(
            f"{self.name} has no configured venue for open_position yet"
        )

    async def close_position(
        self,
        *,
        asset: str,
        reduce_only: bool = True,
    ) -> TransactionResult:
        """Close (fully or partially) a perpetual position."""

        raise PerpCapabilityError(
            f"{self.name} has no configured venue for close_position yet"
        )

    async def get_position(self, *, asset: str) -> PerpPositionView | None:
        """Return the current open position for an asset, if any."""

        raise PerpCapabilityError(
            f"{self.name} has no configured venue for get_position yet"
        )
