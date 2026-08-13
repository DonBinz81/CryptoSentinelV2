"""Perpetual trading domain placeholders."""

from decimal import Decimal
from typing import Literal

from backend.app.domain.common.models import UserScopedModel


class PerpPosition(UserScopedModel):
    """Open or closed perpetual position owned by a user."""

    market: Literal["perp"] = "perp"
    token_symbol: str
    side: Literal["long", "short"] | None = None
    leverage: Decimal | None = None
    liquidation_price: Decimal | None = None
