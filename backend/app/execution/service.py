"""Execution-layer coordination and non-sensitive status."""

from __future__ import annotations

import asyncio
import time
from decimal import Decimal
from typing import Any

from web3 import Web3

from backend.app.core.config import Settings, get_settings
from backend.app.execution.network_selection import (
    BscExecutionNetwork,
    effective_execution_settings,
    set_active_bsc_network,
)
from backend.app.execution.perp_registry import PerpExecutionRegistry
from backend.app.execution.registry import ExecutionProviderRegistry
from backend.app.execution.rpc import MultiRpcClient
from backend.app.execution.rpc_selection import (
    get_active_rpc_index,
    ordered_bsc_rpc_urls,
    rpc_endpoint_label,
    set_active_rpc_index,
)
from backend.app.execution.spot_twak import TwakClient
from backend.app.execution.wallet_selection import (
    add_wallet_address,
    configured_wallet_addresses,
    set_active_wallet_address,
)
from backend.app.execution.x402 import X402Client
from backend.app.persistence.database import get_session_factory
from backend.app.schemas.execution import (
    ExecutionWalletProviderView,
    ExecutionWalletAddressView,
    ExecutionWalletsResponse,
    RpcEndpointView,
)

WEI_PER_BNB = Decimal(10) ** 18


class ExecutionService:
    def __init__(self, settings: Settings) -> None:
        self.base_settings = settings
        self.settings = effective_execution_settings(settings)
        self.rpc = MultiRpcClient(
            ordered_bsc_rpc_urls(settings),
            settings.bsc_rpc_timeout_seconds,
            settings.tatum_rpc_api_key,
        )
        self.competition_rpc = MultiRpcClient(
            settings.competition_rpc_urls,
            settings.bsc_rpc_timeout_seconds,
            settings.tatum_rpc_api_key,
        )
        self.twak = TwakClient(self.settings)
        self.spot_registry = ExecutionProviderRegistry(self.settings)
        self.perp_registry = PerpExecutionRegistry(self.settings)
        self.x402 = X402Client(
            self.settings,
            self.twak,
            session_factory=lambda: get_session_factory()(),
            user_id=str(self.settings.default_user_id),
        )

    def status(self) -> dict[str, Any]:
        testnet_only = self.settings.bsc_network == "testnet"
        return {
            "network": self.settings.bsc_network,
            "chain": "bsc" if self.settings.bsc_network == "mainnet" else "bsctestnet",
            "chain_id": self.settings.bsc_chain_id,
            "testnet_only": testnet_only,
            "rpc_endpoint_count": len(self.settings.bsc_rpc_urls),
            "rpc_failover_configured": len(self.settings.bsc_rpc_urls) >= 2,
            "active_rpc_endpoint_index": get_active_rpc_index(self.settings),
            "gas_reserve_pct": self.settings.bnb_gas_reserve_pct,
            "gas_reserve_floor_bnb": self.settings.bnb_gas_reserve_min,
            "transaction_attempt_limit": self.settings.bsc_max_transaction_attempts,
            "spot": {
                "active_provider": self.spot_registry.active_name.value,
                "providers": [status.model_dump() for status in self.spot_registry.statuses()],
            },
            "perp": {
                "active_provider": self.perp_registry.active_name.value,
                "providers": [status.model_dump() for status in self.perp_registry.statuses()],
            },
            "x402": {
                "enabled": self.settings.x402_enabled,
                "network": self.settings.x402_network,
                "provider_count": len(self.x402.endpoints),
            },
            "competition": {
                "contract": self.settings.competition_contract_address,
                "chain_id": self.settings.competition_chain_id,
                "rpc_endpoint_count": len(self.settings.competition_rpc_urls),
                "wallet_configured": bool(self.settings.wallet_address),
            },
        }

    async def wallets(self) -> ExecutionWalletsResponse:
        """Return non-sensitive wallet and RPC execution diagnostics."""

        balance_bnb, balance_status = await self._wallet_bnb_balance(self.settings.wallet_address)
        available_wallets = await self._available_wallet_views()
        spot_active = self.spot_registry.active_name.value
        perp_active = self.perp_registry.active_name.value
        wallets = [
            ExecutionWalletProviderView(
                provider="twak",
                market="spot",
                address=self.settings.wallet_address,
                network=f"BSC {self.settings.bsc_network}",
                configured=bool(
                    self.settings.wallet_address
                    and self.settings.twak_access_id
                    and self.settings.twak_hmac_secret
                ),
                active=spot_active == "twak",
                balance_bnb=balance_bnb,
                balance_status=balance_status,
            ),
            ExecutionWalletProviderView(
                provider="pancakeswap",
                market="spot",
                address=self.settings.wallet_address,
                network=f"BSC {self.settings.bsc_network}",
                configured=bool(
                    self.settings.wallet_address
                    and self.settings.bsc_rpc_urls
                    and self.settings.wallet_encrypted_private_key_path
                ),
                active=spot_active == "pancakeswap",
                balance_bnb=balance_bnb,
                balance_status=balance_status,
            ),
            ExecutionWalletProviderView(
                provider="bnb_sdk",
                market="perp",
                address=self.settings.wallet_address,
                network=f"BSC {self.settings.bsc_network}",
                configured=bool(self.settings.wallet_address and self.settings.bnb_ai_agent_sdk_enabled),
                active=perp_active == "bnb_sdk",
                balance_bnb=balance_bnb,
                balance_status=balance_status,
            ),
        ]
        rpc_endpoints = await self._rpc_endpoint_views()
        active_index = get_active_rpc_index(self.settings)
        return ExecutionWalletsResponse(
            network=f"BSC {self.settings.bsc_network}",
            bsc_network="mainnet" if self.settings.bsc_network == "mainnet" else "testnet",
            chain_id=self.settings.bsc_chain_id,
            spot_active_provider=spot_active,
            perp_active_provider=perp_active,
            active_rpc_endpoint_index=active_index,
            active_wallet_address=self.settings.wallet_address,
            available_wallets=available_wallets,
            wallets=wallets,
            rpc_endpoints=rpc_endpoints,
        )

    async def select_rpc_endpoint(self, index: int) -> ExecutionWalletsResponse:
        """Persist an admin-selected BSC RPC endpoint and return fresh diagnostics."""

        set_active_rpc_index(self.settings, index)
        return await self.wallets()

    async def add_wallet(self, address: str) -> ExecutionWalletsResponse:
        """Persist an additional public wallet address and select it."""

        add_wallet_address(self.base_settings, address)
        self.settings = effective_execution_settings(self.base_settings)
        self.spot_registry = ExecutionProviderRegistry(self.settings)
        self.perp_registry = PerpExecutionRegistry(self.settings)
        return await self.wallets()

    async def send_token(
        self,
        *,
        to_address: str,
        amount: str,
        token: str,
        wallet_password: str,
    ) -> dict:
        """Invia token/BNB a un indirizzo via TWAK CLI. Richiede CLI configurata."""
        from web3 import Web3
        if not Web3.is_checksum_address(to_address) and not Web3.is_address(to_address):
            return {"status": "error", "error": "Indirizzo destinazione non valido"}
        try:
            amount_decimal = float(amount)
            if amount_decimal <= 0:
                return {"status": "error", "error": "L'importo deve essere maggiore di zero"}
        except ValueError:
            return {"status": "error", "error": "Importo non valido"}
        if not self.twak.configured:
            return {"status": "error", "error": "TWAK CLI non configurata — imposta twak_cli_path nelle Settings"}
        try:
            result = await self.twak.send_token(
                to_address=Web3.to_checksum_address(to_address),
                amount=amount,
                token=token,
                wallet_password=wallet_password,
            )
            tx_hash = result.get("txHash") or result.get("tx_hash") or result.get("hash")
            return {"status": "success", "tx_hash": tx_hash, "detail": result}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    async def select_wallet(self, address: str) -> ExecutionWalletsResponse:
        """Persist the active public wallet address."""

        set_active_wallet_address(self.base_settings, address)
        self.settings = effective_execution_settings(self.base_settings)
        self.spot_registry = ExecutionProviderRegistry(self.settings)
        self.perp_registry = PerpExecutionRegistry(self.settings)
        return await self.wallets()

    async def select_network(self, network: BscExecutionNetwork) -> ExecutionWalletsResponse:
        """Persist an admin-selected BSC network and return fresh diagnostics."""

        set_active_bsc_network(self.base_settings, network)
        self.settings = effective_execution_settings(self.base_settings)
        self.rpc = MultiRpcClient(
            ordered_bsc_rpc_urls(self.settings),
            self.settings.bsc_rpc_timeout_seconds,
            self.settings.tatum_rpc_api_key,
        )
        self.spot_registry = ExecutionProviderRegistry(self.settings)
        self.perp_registry = PerpExecutionRegistry(self.settings)
        return await self.wallets()

    async def _wallet_bnb_balance(self, address: str | None) -> tuple[str | None, str]:
        if not address:
            return None, "not_configured"
        if not self.settings.bsc_rpc_urls:
            return None, "rpc_not_configured"
        try:
            raw_balance = await asyncio.wait_for(
                self.rpc.call("eth_getBalance", [address, "latest"]),
                timeout=4.0,
            )
            balance_wei = int(str(raw_balance), 16)
        except Exception:
            return None, "unavailable"
        if balance_wei <= 0:
            return "0", "empty"
        balance = Decimal(balance_wei) / WEI_PER_BNB
        return f"{balance:.8f}".rstrip("0").rstrip("."), "ok"

    async def _available_wallet_views(self) -> list[ExecutionWalletAddressView]:
        views: list[ExecutionWalletAddressView] = []
        for address in configured_wallet_addresses(self.base_settings):
            balance_bnb, balance_status = await self._wallet_bnb_balance(address)
            views.append(
                ExecutionWalletAddressView(
                    address=address,
                    active=address == self.settings.wallet_address,
                    network=f"BSC {self.settings.bsc_network}",
                    balance_bnb=balance_bnb,
                    balance_status=balance_status,
                )
            )
        return views

    async def _rpc_endpoint_views(self) -> list[RpcEndpointView]:
        active_index = get_active_rpc_index(self.settings)
        displayed_active = active_index if active_index is not None else (0 if self.settings.bsc_rpc_urls else None)
        views: list[RpcEndpointView] = []
        for index, url in enumerate(self.settings.bsc_rpc_urls):
            started = time.perf_counter()
            reachable = False
            latency_ms: int | None = None
            chain_id: int | None = None
            status = "unreachable"
            client = MultiRpcClient(
                [url],
                self.settings.bsc_rpc_timeout_seconds,
                self.settings.tatum_rpc_api_key,
            )
            try:
                raw_chain_id = await client.call("eth_chainId")
                latency_ms = round((time.perf_counter() - started) * 1000)
                chain_id = int(str(raw_chain_id), 16)
                reachable = True
                status = "reachable" if chain_id == self.settings.bsc_chain_id else "chain_mismatch"
            except Exception:
                latency_ms = round((time.perf_counter() - started) * 1000)
            views.append(
                RpcEndpointView(
                    index=index,
                    label=rpc_endpoint_label(url),
                    active=index == displayed_active,
                    reachable=reachable,
                    latency_ms=latency_ms,
                    chain_id=chain_id,
                    status=status,
                )
            )
        return views

    async def competition_registration_status(self) -> dict[str, Any]:
        if not self.settings.wallet_address:
            return {"configured": False, "registered": False, "reason": "wallet_address_missing"}
        if not self.settings.competition_contract_address:
            return {"configured": False, "registered": False, "reason": "contract_address_missing"}
        chain_id = int(await self.competition_rpc.call("eth_chainId"), 16)
        if chain_id != self.settings.competition_chain_id:
            raise RuntimeError(
                "Competition RPC chain mismatch: "
                f"expected {self.settings.competition_chain_id}, got {chain_id}"
            )
        selector = Web3.keccak(text="isRegistered(address)")[:4].hex()
        address_word = self.settings.wallet_address.lower().removeprefix("0x").rjust(64, "0")
        result = await self.competition_rpc.call(
            "eth_call",
            [
                {
                    "to": Web3.to_checksum_address(self.settings.competition_contract_address),
                    "data": f"0x{selector}{address_word}",
                },
                "latest",
            ],
        )
        return {
            "configured": True,
            "registered": int(result, 16) != 0,
            "wallet": Web3.to_checksum_address(self.settings.wallet_address),
            "contract": Web3.to_checksum_address(self.settings.competition_contract_address),
            "chain_id": chain_id,
        }


def get_execution_service() -> ExecutionService:
    return ExecutionService(get_settings())
