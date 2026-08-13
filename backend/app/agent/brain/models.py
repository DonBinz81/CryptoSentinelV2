"""Brain and meta-controller models."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

BrainAction = Literal["approve", "reduce", "block", "skip"]


@dataclass(frozen=True)
class BrainDecision:
    """Decision returned by the LLM meta-controller."""

    action: BrainAction
    confidence: Decimal
    reasoning: str
    size_multiplier: Decimal = Decimal("1")

    @property
    def allows_execution(self) -> bool:
        return self.action in {"approve", "reduce"}


@dataclass(frozen=True)
class BrainUsage:
    """Token usage from a single Claude API call."""

    model: str
    input_tokens: int
    output_tokens: int
