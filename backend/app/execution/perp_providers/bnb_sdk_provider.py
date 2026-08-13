"""BNB AI Agent SDK / EIP-712 perpetual execution provider.

Adapts the existing BnbAgentSdkBridge to the PerpExecutionProvider interface.
This is an adaptation refactor, not a rewrite: the EIP-712 signing, venue
submission and ERC-8004/8183 identity/commerce logic in the bridge are reused
unchanged. First provider behind the perp interface; further perp DEX providers
plug in the same way.
"""

from __future__ import annotations

from typing import Any

from backend.app.core.config import Settings
from backend.app.execution.perp_base import (
    PerpExecutionProvider,
    PerpExecutionProviderName,
    PerpProviderStatus,
)
from backend.app.execution.perp_bnb_sdk import BnbAgentSdkBridge


class BnbSdkPerpProvider(PerpExecutionProvider):
    """Perpetual execution through the BNB AI Agent SDK (EIP-712 + venue submit)."""

    name = PerpExecutionProviderName.BNB_SDK

    def __init__(self, settings: Settings, bridge: BnbAgentSdkBridge | None = None) -> None:
        self._settings = settings
        self._bridge = bridge or BnbAgentSdkBridge(settings)

    @property
    def bridge(self) -> BnbAgentSdkBridge:
        """Expose the underlying EIP-712 boundary for provider-specific use."""

        return self._bridge

    def status(self) -> PerpProviderStatus:
        raw = self._bridge.status
        return PerpProviderStatus(
            name=self.name,
            configured=bool(raw.get("enabled") and raw.get("installed")),
            network=str(raw.get("network", self._settings.bsc_network)),
            venue_configured=bool(raw.get("venue_configured")),
            details={
                "wallet_bound": raw.get("wallet_bound"),
                "identity": raw.get("identity"),
                "commerce": raw.get("commerce"),
                "memory_module": raw.get("memory_module"),
            },
        )

    async def sign_and_submit_order(
        self,
        *,
        domain: dict[str, Any],
        types: dict[str, list[dict[str, str]]],
        message: dict[str, Any],
    ) -> dict[str, Any]:
        """Provider-specific EIP-712 path: sign the typed order and submit it.

        Not part of the common interface (other perp DEXes may not use EIP-712);
        callers that target BNB SDK use this directly via ``registry.active``.
        """

        signed = self._bridge.sign_order(domain=domain, types=types, message=message)
        return await self._bridge.submit_order(signed)
