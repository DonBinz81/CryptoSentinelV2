"""Minimal venue router: which venue executes what.

Two distinct moments, on purpose:

* **opening** — the venue is chosen from market and pair;
* **existing position** — the venue is *read* from the position, never chosen again.

The second rule is what prevents a position opened on one venue from being reduced
or closed on another. No hidden fallbacks: if no enabled venue can serve the
request the caller gets ``None`` and must skip with ``venue_unavailable``.

Multi-venue selection (cost comparison between DEXes) is deliberately absent: it
arrives with the second venue, not before.
"""

from __future__ import annotations

from backend.app.core.logging import get_logger
from backend.app.execution.venue_availability import UNAVAILABLE, get_venue_availability_service
from backend.app.execution.venues.base import PerpVenue
from backend.app.execution.venues.dry_run import DRY_RUN_VENUE, DryRunPerpVenue

logger = get_logger("execution.venue_router")

#: Decision reason when no enabled venue can serve a market/pair.
VENUE_UNAVAILABLE = "venue_unavailable"


class PerpVenueRouter:
    """Resolve the venue for a new position, or read it from an existing one."""

    def __init__(self, venues: dict[str, PerpVenue] | None = None) -> None:
        self._venues: dict[str, PerpVenue] = venues or {DRY_RUN_VENUE: DryRunPerpVenue()}

    def get(self, name: str | None) -> PerpVenue | None:
        return self._venues.get(name) if name else None

    async def _pair_is_unavailable(self, market: str, symbol: str) -> bool:
        """True only when the venue itself says it does not list the pair.

        ``unknown`` never blocks: it means *we* could not check — a rate limit,
        an RPC outage, a network we cannot probe — and a limit of ours must not
        stop trading a pair the venue may well support. Only a definite "not
        listed" is worth refusing an entry over.
        """
        try:
            table = await get_venue_availability_service().availability([symbol])
        except Exception as exc:
            logger.warning("availability_check_failed", symbol=symbol, error_type=type(exc).__name__)
            return False
        return table.get(symbol.upper(), {}).get(market, {}).get("status") == UNAVAILABLE

    async def resolve_entry_venue(self, market: str, symbol: str, *, execution_mode: str) -> PerpVenue | None:
        """Pick the venue for a NEW position. Only dry-run exists today.

        The availability check runs in dry-run too, on purpose: a simulation that
        opens positions the live venue would refuse produces results that cannot
        be trusted as a rehearsal.
        """
        if await self._pair_is_unavailable(market, symbol):
            logger.info(
                "venue_unavailable",
                market=market,
                symbol=symbol,
                execution_mode=execution_mode,
                reason="pair not listed on the configured venue",
            )
            return None
        if execution_mode == "dry_run":
            return self._venues.get(DRY_RUN_VENUE)
        # No live perp venue is implemented yet: fail loudly instead of silently
        # falling back to the simulator, which would fake real trading.
        logger.warning(
            "venue_unavailable",
            market=market,
            symbol=symbol,
            execution_mode=execution_mode,
            reason="no live perp venue configured",
        )
        return None

    def resolve_position_venue(self, position) -> PerpVenue | None:
        """Read the venue an existing position was opened on. Never re-resolve it.

        A position keeps its venue for its whole life: entry, TP1, TP2, stop,
        ratchet, Smart SL and close all go to the same place.
        """
        venue = self._venues.get(position.venue) if position.venue else None
        if venue is None:
            logger.error(
                "venue_unavailable",
                position_id=getattr(position, "position_id", None),
                venue=getattr(position, "venue", None),
                reason="position venue missing or not registered",
            )
        return venue


_router: PerpVenueRouter | None = None


def get_perp_venue_router() -> PerpVenueRouter:
    global _router
    if _router is None:
        _router = PerpVenueRouter()
    return _router
