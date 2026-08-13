"""On-chain transaction reconciliation."""

from __future__ import annotations

from backend.app.execution.models import ExecutionStatus, TransactionResult
from backend.app.execution.rpc import MultiRpcClient


def _hex_int(value: str | None) -> int | None:
    return int(value, 16) if value else None


class TransactionReconciler:
    def __init__(
        self,
        rpc: MultiRpcClient,
        explorer_base_url: str | None,
        required_confirmations: int = 1,
    ) -> None:
        if required_confirmations < 1:
            raise ValueError("required_confirmations must be at least 1")
        self._rpc = rpc
        self._explorer = explorer_base_url.rstrip("/") if explorer_base_url else None
        self._required_confirmations = required_confirmations

    async def reconcile(
        self,
        transaction_hash: str,
        *,
        timeout_seconds: float,
        poll_seconds: float,
    ) -> TransactionResult:
        receipt = await self._rpc.wait_for_receipt(transaction_hash, timeout_seconds, poll_seconds)
        if receipt is None:
            transaction = await self._rpc.call("eth_getTransactionByHash", [transaction_hash])
            return TransactionResult(
                status=ExecutionStatus.UNKNOWN if transaction else ExecutionStatus.FAILED,
                transaction_hash=transaction_hash,
                reason="receipt_timeout_requires_on_chain_recheck",
                explorer_url=self._url(transaction_hash),
            )
        block_number = _hex_int(receipt.get("blockNumber"))
        if block_number is None:
            return TransactionResult(
                status=ExecutionStatus.UNKNOWN,
                transaction_hash=transaction_hash,
                reason="receipt_missing_block_number",
                explorer_url=self._url(transaction_hash),
            )
        if self._required_confirmations > 1:
            latest_block = _hex_int(await self._rpc.call("eth_blockNumber"))
            confirmations = (latest_block - block_number + 1) if latest_block is not None else 0
            if confirmations < self._required_confirmations:
                return TransactionResult(
                    status=ExecutionStatus.UNKNOWN,
                    transaction_hash=transaction_hash,
                    block_number=block_number,
                    reason="required_confirmations_not_reached",
                    explorer_url=self._url(transaction_hash),
                    details={
                        "confirmations": confirmations,
                        "required_confirmations": self._required_confirmations,
                    },
                )
        success = _hex_int(receipt.get("status")) == 1
        return TransactionResult(
            status=ExecutionStatus.CONFIRMED if success else ExecutionStatus.FAILED,
            transaction_hash=transaction_hash,
            block_number=block_number,
            gas_used=_hex_int(receipt.get("gasUsed")),
            effective_gas_price_wei=_hex_int(receipt.get("effectiveGasPrice")),
            explorer_url=self._url(transaction_hash),
            reason=None if success else "transaction_reverted_on_chain",
        )

    def _url(self, transaction_hash: str) -> str | None:
        return f"{self._explorer}/tx/{transaction_hash}" if self._explorer else None
