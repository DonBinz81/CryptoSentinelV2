"""Global market-cap ranking for the coins shown in the setup screen.

Display only. The ranking never reorders the stored watchlists: the engine scans
them in order, and with a cap on open positions the first symbol evaluated is the
one that takes the slot — so reordering what is persisted would quietly change
which coins get traded, not just how they are listed.

The figure is CoinMarketCap's global rank (BTC is #1), taken from the market-data
provider already configured for the application. Refreshed once a day: market caps
move slowly enough, and a fixed daily cost of about one credit keeps the API
budget untouched.

When the provider cannot be reached the last known ranking is kept, so the setup
list does not reshuffle itself because of a transient outage.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import get_logger
from backend.app.data.market_data.cache import TTLCache
from backend.app.data.market_data.registry import get_market_data_registry

logger = get_logger("market_data.ranking")

#: Market caps move slowly; once a day is what the user asked for and what the
#: credit budget comfortably absorbs.
DEFAULT_TTL_SECONDS = 24 * 3600.0

#: After a failure, retry sooner than a full day — but not so often that a broken
#: provider is hammered on every screen refresh.
FAILURE_TTL_SECONDS = 900.0

#: How deep into the global ranking we look. Coins below this simply have no
#: rank and sort last: going deeper costs credits for names nobody trades.
RANKING_DEPTH = 1000

_RANKING_KEY = "market_cap_ranking"


@dataclass(frozen=True, slots=True)
class SymbolRanking:
    """Where one coin sits in the global market-cap ranking."""

    rank: int | None
    market_cap: float | None

    def as_dict(self) -> dict[str, float | int | None]:
        return {"rank": self.rank, "market_cap": self.market_cap}


class MarketRankingService:
    """Resolve, cache and serve the global market-cap rank per symbol."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        cache: TTLCache | None = None,
        registry=None,
    ) -> None:
        self._settings = settings or get_settings()
        self._cache = cache if cache is not None else TTLCache(DEFAULT_TTL_SECONDS)
        self._registry = registry
        # Survives cache expiry on purpose: a failed refresh must not blank the
        # ranking and reshuffle the whole setup list.
        self._last_good: dict[str, SymbolRanking] = {}

    def _provider(self):
        return (self._registry or get_market_data_registry()).active

    async def _fetch_ranking(self) -> dict[str, SymbolRanking] | None:
        """Read the global market-cap ranking. ``None`` when the provider fails.

        The whole ranking is requested, not one symbol at a time: ``asset_ids``
        takes provider-specific identifiers, not tickers, so asking for "UNI"
        matches whatever obscure token happens to own that id. Reading the
        ranking top-down instead means a repeated ticker resolves to the most
        capitalised coin carrying it, which is the one a trader means.
        """

        try:
            assets = await self._provider().get_market_list(currency="usd", limit=RANKING_DEPTH)
        except Exception as exc:  # provider down, quota exhausted, timeout
            logger.warning("ranking_fetch_failed", error_type=type(exc).__name__)
            return None
        ranking: dict[str, SymbolRanking] = {}
        for asset in assets:
            symbol = (asset.symbol or "").upper()
            # First occurrence wins: the list is ordered by market cap.
            if symbol and symbol not in ranking:
                ranking[symbol] = SymbolRanking(asset.market_cap_rank, asset.market_cap)
        return ranking

    async def ranking(self, symbols: list[str]) -> dict[str, dict[str, float | int | None]]:
        """Ranking for the given symbols, keyed by symbol.

        Symbols outside the covered depth get a null rank and sort last, rather
        than being given a number that does not belong to them.
        """

        table: dict[str, SymbolRanking] | None = self._cache.get(_RANKING_KEY)
        if table is None:
            table = await self._fetch_ranking()
            if table is None:
                # Keep serving the last good ranking; retry before a full day.
                table = self._last_good
                self._cache.set(_RANKING_KEY, table, FAILURE_TTL_SECONDS)
            else:
                self._last_good = table
                self._cache.set(_RANKING_KEY, table)
                logger.info("ranking_refreshed", symbols=len(table), depth=RANKING_DEPTH)

        empty = SymbolRanking(None, None)
        return {
            symbol.upper(): table.get(symbol.upper(), empty).as_dict() for symbol in symbols
        }


_service: MarketRankingService | None = None


def get_market_ranking_service() -> MarketRankingService:
    global _service
    if _service is None:
        _service = MarketRankingService()
    return _service
