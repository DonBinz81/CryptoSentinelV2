"""Shared execution-layer models."""

from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ExecutionStatus(StrEnum):
    PREPARED = "prepared"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    UNKNOWN = "unknown"
    SKIPPED = "skipped"


class TransactionResult(BaseModel):
    status: ExecutionStatus
    transaction_hash: str | None = None
    block_number: int | None = None
    gas_used: int | None = None
    effective_gas_price_wei: int | None = None
    explorer_url: str | None = None
    reason: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class GasDecision(BaseModel):
    allowed: bool
    balance_wei: int
    reserve_wei: int
    estimated_cost_wei: int
    spendable_after_gas_wei: int
    expected_profit_usd: Decimal
    estimated_gas_cost_usd: Decimal
    reason: str | None = None

