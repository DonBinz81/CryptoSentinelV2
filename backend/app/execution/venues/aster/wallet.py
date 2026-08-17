"""Aster wallet view — read-only summary for the Wallet screen.

Shows the two addresses and the balance held on Aster. The sub-account address is
returned in full (funds are sent there), the API wallet abbreviated (it only signs).
The signing key is never returned, in any form.

Balances are cached briefly: both the dashboard and the app poll this view, and
Aster must not be hit on every refresh.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.app.core.logging import get_logger
from backend.app.execution.venues.aster.client import AsterClient, AsterError, short_address

logger = get_logger("execution.venue.aster.wallet")

_CACHE_TTL_SECONDS = 30.0
_cache: dict[str, Any] = {"at": 0.0, "value": None}


@dataclass
class AsterAssetBalance:
    asset: str
    balance: str
    available: str


@dataclass
class AsterWalletView:
    configured: bool
    subaccount_name: str | None = None
    #: Full address: this is where funds must be sent.
    subaccount_address: str | None = None
    #: Abbreviated: it only signs requests, nothing is ever sent to it.
    api_wallet_address_short: str | None = None
    balances: list[AsterAssetBalance] = field(default_factory=list)
    total_balance_usdt: str | None = None
    open_positions: int | None = None
    reachable: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["balances"] = [asdict(b) for b in self.balances]
        return data


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


async def get_wallet_view(settings, *, force_refresh: bool = False) -> AsterWalletView:
    """Addresses and balance held on Aster, or an explanation of what is missing."""
    account = getattr(settings, "aster_account_address", "")
    api_wallet = getattr(settings, "aster_api_wallet_address", "")
    key = getattr(settings, "aster_api_wallet_private_key", "")
    name = getattr(settings, "aster_subaccount_name", "") or None

    if not (account and api_wallet and key):
        return AsterWalletView(
            configured=False,
            subaccount_name=name,
            error="Credenziali Aster non configurate sul server.",
        )

    now = time.monotonic()
    cached = _cache.get("value")
    if cached is not None and not force_refresh and (now - _cache["at"]) < _CACHE_TTL_SECONDS:
        return cached

    view = AsterWalletView(
        configured=True,
        subaccount_name=name,
        subaccount_address=account,
        api_wallet_address_short=short_address(api_wallet),
    )

    client = AsterClient(
        base_url=getattr(settings, "aster_base_url", ""),
        account_address=account,
        api_wallet_address=api_wallet,
        api_wallet_private_key=key,
    )

    try:
        raw_balances = await client.balance()
        total = 0.0
        for item in raw_balances if isinstance(raw_balances, list) else []:
            amount = _as_float(item.get("balance"))
            if amount <= 0:
                continue
            view.balances.append(
                AsterAssetBalance(
                    asset=str(item.get("asset", "?")),
                    balance=str(item.get("balance", "0")),
                    available=str(item.get("availableBalance", item.get("balance", "0"))),
                )
            )
            if str(item.get("asset", "")).upper() in ("USDT", "USDC"):
                total += amount
        view.total_balance_usdt = f"{total:.2f}"
        view.reachable = True
    except AsterError as exc:
        # Never surface the raw request: it carries the signature.
        view.error = "Impossibile leggere il saldo da Aster in questo momento."
        logger.warning("aster_wallet_balance_failed", code=exc.code, status=exc.status)
        _cache.update(at=now, value=view)
        return view

    try:
        positions = await client.position_risk()
        view.open_positions = len(
            [p for p in (positions if isinstance(positions, list) else [])
             if _as_float(p.get("positionAmt")) != 0]
        )
    except AsterError as exc:
        logger.warning("aster_wallet_positions_failed", code=exc.code, status=exc.status)

    _cache.update(at=now, value=view)
    return view
