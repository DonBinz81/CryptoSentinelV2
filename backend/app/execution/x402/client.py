"""x402 service selection with bounded BSC-only fallback."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from threading import Lock
from typing import Any

from backend.app.core.config import Settings
from backend.app.execution.spot_twak.client import TwakClient, TwakError


class X402Client:
    def __init__(
        self,
        settings: Settings,
        twak: TwakClient | None = None,
        *,
        session_factory: Any | None = None,
        user_id: str | None = None,
    ) -> None:
        self._settings = settings
        self._twak = twak or TwakClient(settings)
        self._budget_date: date = datetime.now(UTC).date()
        self._spent_usd = Decimal("0")
        self._lock = Lock()
        # Optional DB persistence of the daily budget (Step 5).  When a session
        # factory is supplied the cumulative spend survives process restarts.
        self._session_factory = session_factory
        self._user_id = user_id or str(getattr(settings, "default_user_id", ""))
        self._budget_loaded = False

    @property
    def endpoints(self) -> list[str]:
        candidates = [self._settings.agentdata_base_url, *self._settings.x402_fallback_base_urls]
        return [url.rstrip("/") for url in candidates if url]

    async def request(
        self,
        path: str,
        *,
        max_payment_atomic: int,
        payment_usd: Decimal,
        wallet_password: str,
    ) -> dict[str, Any]:
        if self._settings.x402_network != "bsc":
            raise ValueError("x402 execution is restricted to BSC")
        await self._load_persisted_budget()
        self._reserve_budget(payment_usd)
        await self._persist_budget()
        errors: list[str] = []
        try:
            for base_url in self.endpoints:
                try:
                    return await self._twak.x402_request(
                        f"{base_url}/{path.lstrip('/')}",
                        max_payment_atomic=max_payment_atomic,
                        wallet_password=wallet_password,
                    )
                except TwakError as exc:
                    errors.append(type(exc).__name__)
            raise TwakError(f"No configured BSC x402 provider succeeded: {errors}")
        except BaseException:
            self._rollback_budget(payment_usd)
            await self._persist_budget()
            raise

    def _reserve_budget(self, payment_usd: Decimal) -> None:
        if payment_usd <= 0:
            raise ValueError("x402 payment must be positive")
        per_call = Decimal(str(self._settings.x402_max_payment_per_call_usd))
        daily = Decimal(str(self._settings.x402_daily_spend_limit_usd))
        if payment_usd > per_call:
            raise ValueError("x402 payment exceeds the per-call hard cap")
        with self._lock:
            today = datetime.now(UTC).date()
            if today != self._budget_date:
                self._budget_date = today
                self._spent_usd = Decimal("0")
            if self._spent_usd + payment_usd > daily:
                raise ValueError("x402 payment exceeds the daily hard cap")
            self._spent_usd += payment_usd

    def _rollback_budget(self, payment_usd: Decimal) -> None:
        with self._lock:
            self._spent_usd = max(Decimal("0"), self._spent_usd - payment_usd)

    async def _load_persisted_budget(self) -> None:
        if self._session_factory is None or self._budget_loaded:
            return
        from backend.app.persistence.repositories.x402_budget import X402BudgetRepository

        async with self._session_factory() as session:
            repo = X402BudgetRepository(session)
            persisted = await repo.load_today(self._user_id)
        with self._lock:
            self._budget_date = datetime.now(UTC).date()
            self._spent_usd = persisted
        self._budget_loaded = True

    async def _persist_budget(self) -> None:
        if self._session_factory is None:
            return
        from backend.app.persistence.repositories.x402_budget import X402BudgetRepository

        with self._lock:
            current = self._spent_usd
        async with self._session_factory() as session:
            repo = X402BudgetRepository(session)
            await repo.save(self._user_id, current)
