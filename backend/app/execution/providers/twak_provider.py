"""TWAK execution provider: adapts the existing TwakClient to ExecutionProvider.

This is an adaptation refactor, not a rewrite: the HMAC signing, Amber REST and
CLI logic in ``TwakClient`` are reused unchanged. Provider used for the
hackathon, where on-chain execution via Trust Wallet Agent Kit is mandatory.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from backend.app.core.config import Settings
from backend.app.execution.base import (
    ExecutionProvider,
    ExecutionProviderName,
    ExecutionProviderStatus,
    ExecutionQuote,
)
from backend.app.execution.models import ExecutionStatus, GasDecision, TransactionResult
from backend.app.execution.spot_twak import TwakClient


def _find_first(payload: Any, names: set[str]) -> Any:
    """Best-effort recursive lookup of the first matching key in an Amber payload."""

    if isinstance(payload, dict):
        for key, value in payload.items():
            if key.lower() in names and not isinstance(value, (dict, list)):
                return value
            nested = _find_first(value, names)
            if nested is not None:
                return nested
    if isinstance(payload, list):
        for value in payload:
            nested = _find_first(value, names)
            if nested is not None:
                return nested
    return None


def _route_provider_name(route: dict[str, Any]) -> str:
    steps = route.get("steps") or []
    names = [str(step.get("provider", {}).get("name", "")) for step in steps]
    return " → ".join(name for name in names if name) or "unknown"


class TWAKProvider(ExecutionProvider):
    """Spot execution through Trust Wallet Agent Kit (Amber API + CLI signing)."""

    name = ExecutionProviderName.TWAK

    def __init__(self, settings: Settings, client: TwakClient | None = None) -> None:
        self._settings = settings
        self._client = client or TwakClient(settings)

    def _default_domain(self) -> str:
        return "smartchain-testnet" if self._settings.bsc_network == "testnet" else "smartchain"

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
        domain = from_domain or self._default_domain()
        payload = await self._client.quote(
            amount_atomic=amount_in_atomic,
            from_asset=from_asset,
            to_asset=to_asset,
            wallet_address=wallet_address,
            from_domain=domain,
            to_domain=to_domain or domain,
            slippage_pct=slippage_pct,
        )
        routes = payload.get("routes") or []
        route = routes[0] if routes else {}
        amount_out = _find_first(route, {"toamount", "amountout", "outcome", "toamountatomic"})
        amount_out_atomic = int(amount_out) if amount_out is not None else 0
        min_out = int(amount_out_atomic * (Decimal(1) - slippage_pct / Decimal(100)))
        return ExecutionQuote(
            from_asset=from_asset,
            to_asset=to_asset,
            amount_in_atomic=amount_in_atomic,
            amount_out_atomic=amount_out_atomic,
            min_amount_out_atomic=min_out,
            slippage_pct=slippage_pct,
            route_provider=_route_provider_name(route),
            details={"routes_returned": len(routes)},
        )

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
        domain = from_domain or self._default_domain()
        prepared = await self._client.execute_swap(
            amount_atomic=amount_in_atomic,
            from_asset=from_asset,
            to_asset=to_asset,
            wallet_address=wallet_address,
            from_domain=domain,
            to_domain=to_domain or domain,
            slippage_pct=slippage_pct,
            gas_decision=gas_decision,
        )
        # TWAK returns unsigned transaction data; the wallet signs out-of-band
        # (Trust Wallet autonomous mode). The normalized status is PREPARED.
        return TransactionResult(
            status=ExecutionStatus.PREPARED,
            reason="twak_route_prepared_requires_wallet_signature",
            details={
                "route": prepared.get("route"),
                "transactions": prepared.get("transactions"),
                "requires_wallet_signature": prepared.get("requires_wallet_signature", True),
                "route_provider": _route_provider_name(prepared.get("route") or {}),
            },
        )

    def status(self) -> ExecutionProviderStatus:
        chain = "bsc" if self._settings.bsc_network == "mainnet" else "bsctestnet"
        return ExecutionProviderStatus(
            name=self.name,
            configured=self._client.configured,
            network=self._settings.bsc_network,
            router_address=None,
            wallet_configured=bool(self._settings.twak_access_id and self._settings.twak_hmac_secret),
            autonomous_mode=self._settings.twak_autonomous_mode,
            details={
                "approval_policy": self._settings.twak_approval_policy,
                "allowed_spender_count": len(self._settings.twak_allowed_spenders),
                "chain": chain,
                "domain": self._default_domain(),
                "testnet_only_execution": self._settings.bsc_network == "testnet",
            },
        )
