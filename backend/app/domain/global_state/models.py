"""Global portfolio state placeholders."""

from decimal import Decimal

from backend.app.domain.common.models import UserScopedModel


class GlobalPortfolioSnapshot(UserScopedModel):
    """Portfolio-level snapshot shared by spot and perpetual views."""

    total_value_usd: Decimal | None = None
    drawdown_pct: Decimal | None = None
    total_exposure_pct: Decimal | None = None
