"""Local CMC credit budget accounting."""

from dataclasses import dataclass
from typing import Literal

CreditLevel = Literal["ok", "warning", "critical", "exhausted"]


@dataclass(slots=True)
class CreditBudget:
    """Track locally observed CMC credits and threshold state."""

    monthly_limit: int
    warning_threshold_pct: int
    critical_threshold_pct: int
    used: int = 0

    def consume(self, amount: int) -> None:
        self.used = min(self.monthly_limit, self.used + max(0, amount))

    @property
    def remaining(self) -> int:
        return max(0, self.monthly_limit - self.used)

    @property
    def remaining_pct(self) -> float:
        if self.monthly_limit <= 0:
            return 0.0
        return self.remaining / self.monthly_limit * 100.0

    @property
    def level(self) -> CreditLevel:
        if self.remaining == 0:
            return "exhausted"
        if self.remaining_pct <= self.critical_threshold_pct:
            return "critical"
        if self.remaining_pct <= self.warning_threshold_pct:
            return "warning"
        return "ok"
