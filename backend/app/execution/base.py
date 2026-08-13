"""Provider-neutral execution contracts shared by every spot execution provider.

Mirrors the market-data abstraction (Step 3): a single ``ExecutionProvider``
interface with interchangeable implementations behind a global selector. The
agent, risk engine and API depend on this interface, never on a concrete
provider (TWAK or PancakeSwap).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from backend.app.execution.models import GasDecision, TransactionResult

# Canonical sentinel for the chain-native asset (BNB), matching the convention
# already used by the TWAK spot smoke test.
NATIVE_EVM_ASSET = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"


class ExecutionProviderName(StrEnum):
    """Supported spot execution providers."""

    TWAK = "twak"
    PANCAKESWAP = "pancakeswap"


class ExecutionProviderError(RuntimeError):
    """Raised when an execution request cannot be completed."""


class ExecutionProviderConfigurationError(ExecutionProviderError):
    """Raised when a selected provider is missing required configuration."""


class ExecutionCapabilityError(ExecutionProviderError):
    """Raised when a provider cannot satisfy a requested capability.

    Spot swaps are atomic and hold no persistent position at provider level,
    so ``get_position``/``close_position`` raise this on the spot providers.
    """


class ExecutionQuote(BaseModel):
    """Normalized swap quote, identical shape across providers."""

    from_asset: str
    to_asset: str
    amount_in_atomic: int
    amount_out_atomic: int
    min_amount_out_atomic: int
    slippage_pct: Decimal
    route_provider: str
    details: dict[str, Any] = Field(default_factory=dict)


class ExecutionPosition(BaseModel):
    """Normalized open-position view.

    Spot providers do not expose positions; this exists so the interface is
    forward-compatible with venues that do (kept minimal on purpose).
    """

    asset: str
    size_atomic: int
    entry_price: Decimal | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ExecutionProviderStatus(BaseModel):
    """Non-secret execution provider runtime diagnostics."""

    name: ExecutionProviderName
    configured: bool
    network: str
    router_address: str | None = None
    wallet_configured: bool = False
    autonomous_mode: bool | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ExecutionProvider(ABC):
    """Common interface consumed by the agent, risk engine and API.

    ``get_quote``/``execute_swap``/``status`` are the methods every spot
    provider must implement. ``get_position``/``close_position`` carry a
    fail-closed default so the atomic spot providers inherit a consistent
    "not applicable" behaviour without duplicating code.
    """

    name: ExecutionProviderName

    @abstractmethod
    async def get_quote(
        self,
        *,
        amount_in_atomic: int,
        from_asset: str,
        to_asset: str,
        wallet_address: str,
        slippage_pct: Decimal,
        from_domain: str | None = None,
        to_domain: str | None = None,
    ) -> ExecutionQuote:
        """Return a normalized quote for swapping ``from_asset`` to ``to_asset``."""

    @abstractmethod
    async def execute_swap(
        self,
        *,
        amount_in_atomic: int,
        from_asset: str,
        to_asset: str,
        wallet_address: str,
        slippage_pct: Decimal,
        gas_decision: GasDecision,
        from_domain: str | None = None,
        to_domain: str | None = None,
        allow_mainnet: bool = False,
    ) -> TransactionResult:
        """Execute (or prepare) a swap, honouring the shared guardrails."""

    @abstractmethod
    def status(self) -> ExecutionProviderStatus:
        """Return non-secret runtime diagnostics."""

    async def get_position(self, *, asset: str) -> ExecutionPosition:
        """Spot swaps are atomic: no persistent position exists at this layer."""

        raise ExecutionCapabilityError(
            f"{self.name} executes atomic spot swaps and exposes no persistent position"
        )

    async def close_position(
        self,
        *,
        asset: str,
        gas_decision: GasDecision,
        allow_mainnet: bool = False,
    ) -> TransactionResult:
        """Spot swaps are atomic: closing is a new swap decided by the agent."""

        raise ExecutionCapabilityError(
            f"{self.name} executes atomic spot swaps; closing is a new swap, not a provider op"
        )
