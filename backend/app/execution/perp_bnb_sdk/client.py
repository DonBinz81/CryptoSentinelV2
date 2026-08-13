"""BNB Agent SDK and EIP-712 boundary for perpetual execution."""

from __future__ import annotations

from typing import Any, Protocol

import httpx
from web3 import Web3

from backend.app.core.config import Settings


class TypedDataWallet(Protocol):
    @property
    def address(self) -> str: ...

    def sign_typed_data(
        self,
        domain: dict[str, Any],
        types: dict[str, list[dict[str, str]]],
        message: dict[str, Any],
    ) -> dict[str, Any]: ...


class PerpExecutionError(RuntimeError):
    """Raised when a perp order violates the signing or venue policy."""


class BnbAgentSdkBridge:
    def __init__(self, settings: Settings, wallet: TypedDataWallet | None = None) -> None:
        self._settings = settings
        self._wallet = wallet
        self._allowed_contracts = {
            Web3.to_checksum_address(address)
            for address in settings.perp_allowed_verifying_contracts
        }

    @property
    def status(self) -> dict[str, Any]:
        try:
            import bnbagent  # noqa: F401

            installed = True
        except ImportError:
            installed = False
        return {
            "enabled": self._settings.bnb_ai_agent_sdk_enabled,
            "installed": installed,
            "wallet_bound": self._wallet is not None,
            "network": self._settings.bsc_network,
            "identity": "erc8004",
            "commerce": "erc8183",
            "memory_module": "not_exposed_by_public_sdk",
            "venue_configured": bool(self._settings.perp_order_submit_url),
        }

    def sign_order(
        self,
        *,
        domain: dict[str, Any],
        types: dict[str, list[dict[str, str]]],
        message: dict[str, Any],
    ) -> dict[str, Any]:
        if self._settings.bsc_network != "testnet":
            raise PerpExecutionError("Step 4 perp signing is restricted to BSC testnet")
        if self._wallet is None:
            raise PerpExecutionError("No BNB SDK WalletProvider is bound")
        if int(domain.get("chainId", -1)) != self._settings.bsc_chain_id:
            raise PerpExecutionError("EIP-712 domain chainId does not match configured BSC chain")
        contract = Web3.to_checksum_address(str(domain.get("verifyingContract", "")))
        if contract not in self._allowed_contracts:
            raise PerpExecutionError("EIP-712 verifying contract is not allowlisted")
        return self._wallet.sign_typed_data(domain, types, message)

    async def submit_order(self, signed_order: dict[str, Any]) -> dict[str, Any]:
        if not self._settings.perp_order_submit_url:
            raise PerpExecutionError("No official perpetual venue endpoint is configured")
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(self._settings.perp_order_submit_url, json=signed_order)
            response.raise_for_status()
            return response.json()

    def create_identity_client(self) -> Any:
        if self._wallet is None:
            raise PerpExecutionError("No BNB SDK WalletProvider is bound")
        from bnbagent import ERC8004Agent

        return ERC8004Agent(wallet_provider=self._wallet, network="bsc-testnet")

    def create_commerce_client(self) -> Any:
        if self._wallet is None:
            raise PerpExecutionError("No BNB SDK WalletProvider is bound")
        from bnbagent.erc8183 import ERC8183Client

        return ERC8183Client(self._wallet, network="bsc-testnet")

