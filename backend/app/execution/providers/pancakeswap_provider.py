"""Direct PancakeSwap V2 execution provider (web3.py).

Executes swaps straight against the official PancakeSwap V2 Router, with no
dependency on Trust Wallet (no 403, no TWAK fee). Reuses every shared guardrail
from the common layer — gas reserve, exact ERC-20 approval whitelist, bounded
submission and on-chain reconciliation — so it can never bypass them.

Router/WBNB addresses are verified against the official BscScan deployments and
configurable via Settings. Real mainnet submission stays gated: only the opt-in
smoke test may pass ``allow_mainnet`` explicitly.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from web3 import Web3

from backend.app.core.config import Settings
from backend.app.core.logging import get_logger
from backend.app.execution.base import (
    NATIVE_EVM_ASSET,
    ExecutionProvider,
    ExecutionProviderConfigurationError,
    ExecutionProviderError,
    ExecutionProviderName,
    ExecutionProviderStatus,
    ExecutionQuote,
)
from backend.app.execution.approvals import ExactApprovalPolicy
from backend.app.execution.coordinator import ExecutionCoordinator
from backend.app.execution.models import ExecutionStatus, GasDecision, TransactionResult
from backend.app.execution.reconciliation import TransactionReconciler
from backend.app.execution.rpc import MultiRpcClient
from backend.app.execution.rpc_selection import ordered_bsc_rpc_urls

logger = get_logger("execution.pancakeswap")

DEFAULT_SWAP_GAS_LIMIT = 350_000
DEFAULT_APPROVE_GAS_LIMIT = 80_000
DEFAULT_DEADLINE_SECONDS = 1_200


def _selector(signature: str) -> bytes:
    return Web3.keccak(text=signature)[:4]


# 4-byte selectors (computed, never hard-coded blindly).
SEL_GET_AMOUNTS_OUT = _selector("getAmountsOut(uint256,address[])")
SEL_ALLOWANCE = _selector("allowance(address,address)")
SEL_APPROVE = _selector("approve(address,uint256)")
SEL_SWAP_EXACT_TOKENS = _selector(
    "swapExactTokensForTokens(uint256,uint256,address[],address,uint256)"
)
SEL_SWAP_EXACT_ETH = _selector("swapExactETHForTokens(uint256,address[],address,uint256)")


class PancakeSwapProvider(ExecutionProvider):
    """Spot execution directly on the PancakeSwap V2 Router via web3.py."""

    name = ExecutionProviderName.PANCAKESWAP

    def __init__(
        self,
        settings: Settings,
        *,
        rpc: MultiRpcClient | None = None,
        wallet: Any | None = None,
    ) -> None:
        self._settings = settings
        self._rpc = rpc
        self._wallet = wallet
        self._approval_policy = ExactApprovalPolicy([self.router_address])

    # ── Addresses (per network, verified BscScan deployments) ──────────────────

    @property
    def router_address(self) -> str:
        if self._settings.bsc_network == "testnet":
            return Web3.to_checksum_address(self._settings.pancakeswap_router_address_testnet)
        return Web3.to_checksum_address(self._settings.pancakeswap_router_address_mainnet)

    @property
    def wbnb_address(self) -> str:
        if self._settings.bsc_network == "testnet":
            return Web3.to_checksum_address(self._settings.pancakeswap_wbnb_address_testnet)
        return Web3.to_checksum_address(self._settings.pancakeswap_wbnb_address_mainnet)

    # ── Pure helpers (no I/O, fully unit-testable) ─────────────────────────────

    def build_path(self, from_asset: str, to_asset: str) -> list[str]:
        wbnb = self.wbnb_address
        src = wbnb if from_asset == NATIVE_EVM_ASSET else Web3.to_checksum_address(from_asset)
        dst = wbnb if to_asset == NATIVE_EVM_ASSET else Web3.to_checksum_address(to_asset)
        if src.lower() == wbnb.lower() or dst.lower() == wbnb.lower():
            path = [src, dst]
        else:
            path = [src, wbnb, dst]
        return [Web3.to_checksum_address(address) for address in path]

    def encode_get_amounts_out(self, amount_in_atomic: int, path: list[str]) -> str:
        data = SEL_GET_AMOUNTS_OUT + abi_encode(
            ["uint256", "address[]"], [amount_in_atomic, path]
        )
        return "0x" + data.hex()

    @staticmethod
    def decode_amounts(result_hex: str) -> list[int]:
        raw = bytes.fromhex(result_hex.removeprefix("0x"))
        (amounts,) = abi_decode(["uint256[]"], raw)
        return list(amounts)

    def min_out_atomic(self, amount_out_atomic: int, slippage_pct: Decimal) -> int:
        factor = Decimal(1) - slippage_pct / Decimal(100)
        return int(Decimal(amount_out_atomic) * factor)

    def build_swap_transaction(
        self,
        *,
        from_asset: str,
        to_asset: str,
        amount_in_atomic: int,
        min_out_atomic: int,
        recipient: str,
        nonce: int,
        gas_price_wei: int,
        chain_id: int,
        gas_limit: int = DEFAULT_SWAP_GAS_LIMIT,
        deadline: int | None = None,
    ) -> dict[str, Any]:
        path = self.build_path(from_asset, to_asset)
        to_addr = Web3.to_checksum_address(recipient)
        deadline = deadline or (int(time.time()) + DEFAULT_DEADLINE_SECONDS)
        is_native_input = from_asset == NATIVE_EVM_ASSET
        if is_native_input:
            data = SEL_SWAP_EXACT_ETH + abi_encode(
                ["uint256", "address[]", "address", "uint256"],
                [min_out_atomic, path, to_addr, deadline],
            )
            value = amount_in_atomic
        else:
            data = SEL_SWAP_EXACT_TOKENS + abi_encode(
                ["uint256", "uint256", "address[]", "address", "uint256"],
                [amount_in_atomic, min_out_atomic, path, to_addr, deadline],
            )
            value = 0
        return {
            "from": to_addr,
            "to": self.router_address,
            "value": value,
            "data": "0x" + data.hex(),
            "nonce": nonce,
            "gas": gas_limit,
            "gasPrice": gas_price_wei,
            "chainId": chain_id,
        }

    def build_approve_transaction(
        self,
        *,
        token: str,
        amount_atomic: int,
        owner: str,
        nonce: int,
        gas_price_wei: int,
        chain_id: int,
        gas_limit: int = DEFAULT_APPROVE_GAS_LIMIT,
    ) -> dict[str, Any]:
        # Fail-closed: the spender must be the whitelisted router and the
        # allowance exactly the immediate need (reuses the shared policy).
        spender = self._approval_policy.validate(self.router_address, amount_atomic, amount_atomic)
        data = SEL_APPROVE + abi_encode(["address", "uint256"], [spender, amount_atomic])
        return {
            "from": Web3.to_checksum_address(owner),
            "to": Web3.to_checksum_address(token),
            "value": 0,
            "data": "0x" + data.hex(),
            "nonce": nonce,
            "gas": gas_limit,
            "gasPrice": gas_price_wei,
            "chainId": chain_id,
        }

    # ── Interface implementation ───────────────────────────────────────────────

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
        if amount_in_atomic <= 0:
            raise ExecutionProviderError("Quote amount must be positive")
        path = self.build_path(from_asset, to_asset)
        result_hex = await self._rpc_client().call(
            "eth_call",
            [
                {"to": self.router_address, "data": self.encode_get_amounts_out(amount_in_atomic, path)},
                "latest",
            ],
        )
        amounts = self.decode_amounts(result_hex)
        amount_out = amounts[-1] if amounts else 0
        return ExecutionQuote(
            from_asset=from_asset,
            to_asset=to_asset,
            amount_in_atomic=amount_in_atomic,
            amount_out_atomic=amount_out,
            min_amount_out_atomic=self.min_out_atomic(amount_out, slippage_pct),
            slippage_pct=slippage_pct,
            route_provider="pancakeswap_v2",
            details={"path": path, "amounts": amounts},
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
        # 1) Slippage hard limit (same guard the TWAK path enforces).
        if slippage_pct > Decimal(str(self._settings.risk_max_slippage_pct)):
            raise ExecutionProviderError("Requested slippage exceeds the configured hard limit")
        # 2) Gas reserve / cost-benefit guard — cannot be bypassed.
        if not gas_decision.allowed:
            raise ExecutionProviderError(
                f"Spot execution blocked by gas guard: {gas_decision.reason}"
            )
        # 3) Testnet-only gate: mainnet submission stays blocked unless an
        #    explicit opt-in (smoke test) requests it.
        if self._settings.bsc_network != "testnet" and not allow_mainnet:
            logger.info("pancakeswap_mainnet_execution_gated", network=self._settings.bsc_network)
            return TransactionResult(
                status=ExecutionStatus.SKIPPED,
                reason="mainnet_execution_gated",
                details={"network": self._settings.bsc_network},
            )

        wallet = self._require_wallet()
        owner = Web3.to_checksum_address(wallet.address)
        quote = await self.get_quote(
            amount_in_atomic=amount_in_atomic,
            from_asset=from_asset,
            to_asset=to_asset,
            wallet_address=owner,
            slippage_pct=slippage_pct,
        )
        chain_id = self._settings.bsc_chain_id
        rpc = self._rpc_client()
        gas_price_wei = int(await rpc.call("eth_gasPrice"), 16)

        # 4) Exact ERC-20 approval when swapping a token (native BNB needs none).
        if from_asset != NATIVE_EVM_ASSET:
            await self._ensure_allowance(
                token=from_asset,
                owner=owner,
                amount_atomic=amount_in_atomic,
                gas_price_wei=gas_price_wei,
                chain_id=chain_id,
                wallet=wallet,
            )

        # 5) Build + sign + submit the swap, reconciled on-chain.
        nonce = int(await rpc.call("eth_getTransactionCount", [owner, "pending"]), 16)
        swap_tx = self.build_swap_transaction(
            from_asset=from_asset,
            to_asset=to_asset,
            amount_in_atomic=amount_in_atomic,
            min_out_atomic=quote.min_amount_out_atomic,
            recipient=owner,
            nonce=nonce,
            gas_price_wei=gas_price_wei,
            chain_id=chain_id,
        )
        result = await self._submit_signed(swap_tx, wallet)
        result.details["route_provider"] = quote.route_provider
        result.details["min_amount_out_atomic"] = quote.min_amount_out_atomic
        return result

    def status(self) -> ExecutionProviderStatus:
        return ExecutionProviderStatus(
            name=self.name,
            configured=bool(self._settings.bsc_rpc_urls)
            and bool(self._settings.wallet_encrypted_private_key_path),
            network=self._settings.bsc_network,
            router_address=self.router_address,
            wallet_configured=bool(self._settings.wallet_encrypted_private_key_path),
            autonomous_mode=None,
            details={
                "wbnb_address": self.wbnb_address,
                "rpc_endpoint_count": len(self._settings.bsc_rpc_urls),
                "chain": "bsc" if self._settings.bsc_network == "mainnet" else "bsctestnet",
                "testnet_only_execution": self._settings.bsc_network == "testnet",
            },
        )

    # ── Private I/O helpers ────────────────────────────────────────────────────

    def _rpc_client(self) -> MultiRpcClient:
        if self._rpc is not None:
            return self._rpc
        return MultiRpcClient(
            ordered_bsc_rpc_urls(self._settings),
            self._settings.bsc_rpc_timeout_seconds,
            self._settings.tatum_rpc_api_key,
        )

    def _require_wallet(self) -> Any:
        if self._wallet is not None:
            return self._wallet
        path = self._settings.wallet_encrypted_private_key_path
        passphrase_env = self._settings.wallet_key_passphrase_env
        if not path or not passphrase_env:
            raise ExecutionProviderConfigurationError(
                "PancakeSwap execution requires an encrypted keystore and passphrase env name"
            )
        import os

        from backend.app.core.security.wallet_custody import EncryptedKeystoreWallet

        passphrase = os.environ.get(passphrase_env)
        if not passphrase:
            raise ExecutionProviderConfigurationError(
                "Keystore passphrase environment variable is not set"
            )
        # Spot swaps never sign EIP-712, so a no-op typed-data policy is fine.
        self._wallet = EncryptedKeystoreWallet(path, passphrase, signing_policy=object())
        return self._wallet

    async def _ensure_allowance(
        self,
        *,
        token: str,
        owner: str,
        amount_atomic: int,
        gas_price_wei: int,
        chain_id: int,
        wallet: Any,
    ) -> None:
        allowance_data = "0x" + (
            SEL_ALLOWANCE
            + abi_encode(["address", "address"], [owner, self.router_address])
        ).hex()
        rpc = self._rpc_client()
        current_hex = await rpc.call(
            "eth_call",
            [{"to": Web3.to_checksum_address(token), "data": allowance_data}, "latest"],
        )
        current = int(current_hex, 16) if current_hex and current_hex != "0x" else 0
        if current >= amount_atomic:
            return
        nonce = int(await rpc.call("eth_getTransactionCount", [owner, "pending"]), 16)
        approve_tx = self.build_approve_transaction(
            token=token,
            amount_atomic=amount_atomic,
            owner=owner,
            nonce=nonce,
            gas_price_wei=gas_price_wei,
            chain_id=chain_id,
        )
        approve_result = await self._submit_signed(approve_tx, wallet)
        if approve_result.status not in (ExecutionStatus.CONFIRMED, ExecutionStatus.UNKNOWN):
            raise ExecutionProviderError(
                f"ERC-20 approval did not confirm: {approve_result.reason}"
            )

    async def _submit_signed(self, transaction: dict[str, Any], wallet: Any) -> TransactionResult:
        reconciler = TransactionReconciler(
            self._rpc_client(),
            self._settings.bsc_explorer_base_url,
            self._settings.bsc_required_confirmations,
        )
        coordinator = ExecutionCoordinator(
            reconciler,
            max_attempts=self._settings.bsc_max_transaction_attempts,
            receipt_timeout_seconds=self._settings.bsc_receipt_timeout_seconds,
            receipt_poll_seconds=self._settings.bsc_receipt_poll_seconds,
        )

        async def _submit() -> str:
            signed = wallet.sign_transaction(transaction)
            raw = signed["rawTransaction"]
            raw_hex = raw if isinstance(raw, str) else "0x" + bytes(raw).hex()
            return await self._rpc_client().call("eth_sendRawTransaction", [raw_hex])

        return await coordinator.submit(_submit)
