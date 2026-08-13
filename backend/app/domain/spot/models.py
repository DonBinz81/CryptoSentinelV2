"""Spot trading domain placeholders."""

from decimal import Decimal
from typing import Literal

from backend.app.domain.common.models import UserScopedModel


class SpotPosition(UserScopedModel):
    """Open or closed spot position owned by a user."""

    market: Literal["spot"] = "spot"
    token_symbol: str
    entry_price: Decimal | None = None
    size_usd: Decimal | None = None
