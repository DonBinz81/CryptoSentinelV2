"""Bounded submission and on-chain reconciliation."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from backend.app.execution.models import ExecutionStatus, TransactionResult
from backend.app.execution.reconciliation import TransactionReconciler

SubmitTransaction = Callable[[], Awaitable[str]]


class ExecutionCoordinator:
    def __init__(
        self,
        reconciler: TransactionReconciler,
        *,
        max_attempts: int,
        receipt_timeout_seconds: float,
        receipt_poll_seconds: float,
    ) -> None:
        if max_attempts < 1 or max_attempts > 3:
            raise ValueError("max_attempts must be between 1 and 3")
        self._reconciler = reconciler
        self._max_attempts = max_attempts
        self._timeout = receipt_timeout_seconds
        self._poll = receipt_poll_seconds

    async def submit(self, submit_transaction: SubmitTransaction) -> TransactionResult:
        last_reason = "submission_failed_before_hash"
        for attempt in range(1, self._max_attempts + 1):
            try:
                transaction_hash = await submit_transaction()
            except Exception as exc:
                last_reason = f"submission_error:{type(exc).__name__}"
                continue
            result = await self._reconciler.reconcile(
                transaction_hash,
                timeout_seconds=self._timeout,
                poll_seconds=self._poll,
            )
            result.details["attempt"] = attempt
            # A known hash is never re-submitted. UNKNOWN must be checked on-chain later.
            return result
        return TransactionResult(status=ExecutionStatus.FAILED, reason=last_reason)
