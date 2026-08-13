"""Non-disablable BNB gas reserve and cost-benefit guard."""

from decimal import Decimal, ROUND_UP

from backend.app.execution.models import GasDecision

WEI_PER_BNB = Decimal(10**18)


class GasGuard:
    def __init__(self, reserve_pct: Decimal, reserve_floor_bnb: Decimal) -> None:
        if reserve_pct < Decimal("15"):
            raise ValueError("Gas reserve cannot be lower than 15%")
        if reserve_floor_bnb <= 0:
            raise ValueError("Gas reserve floor must be positive")
        self._reserve_pct = reserve_pct
        self._reserve_floor_wei = int((reserve_floor_bnb * WEI_PER_BNB).to_integral_value())

    def evaluate(
        self,
        *,
        balance_wei: int,
        gas_limit: int,
        gas_price_wei: int,
        expected_profit_usd: Decimal,
        bnb_price_usd: Decimal,
    ) -> GasDecision:
        percentage_reserve = int(
            (Decimal(balance_wei) * self._reserve_pct / Decimal(100)).to_integral_value(
                rounding=ROUND_UP
            )
        )
        reserve = max(percentage_reserve, self._reserve_floor_wei)
        cost = gas_limit * gas_price_wei
        gas_cost_usd = Decimal(cost) / WEI_PER_BNB * bnb_price_usd
        after = balance_wei - cost - reserve
        reason = None
        if after < 0:
            reason = "insufficient_bnb_after_hard_gas_reserve"
        elif gas_cost_usd >= expected_profit_usd:
            reason = "estimated_gas_cost_not_below_expected_profit"
        return GasDecision(
            allowed=reason is None,
            balance_wei=balance_wei,
            reserve_wei=reserve,
            estimated_cost_wei=cost,
            spendable_after_gas_wei=max(0, after),
            expected_profit_usd=expected_profit_usd,
            estimated_gas_cost_usd=gas_cost_usd,
            reason=reason,
        )

