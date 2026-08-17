"""Where each symbol can actually be traded, asked to the venues themselves.

The setup screen must never offer a pair the engine could not open. This module
answers one question per (symbol, market): can the configured venue execute it?

Three states, deliberately:

* ``available``   — the venue publishes that market;
* ``unavailable`` — the venue answered, and does not list it;
* ``unknown``     — we could not verify it. Our limit, not the venue's.

``unknown`` is never collapsed into ``unavailable``: a rate limit or an RPC
outage must not look like a missing market.

Perp reads Aster ``exchangeInfo``: one public, unauthenticated request covers
every symbol at once. The supported pairs are therefore never hard-coded — the
day Aster lists a new one, it shows up without a code change or a new APK.

Spot is an AMM, so "available" means "the pools the router would hop through
exist". It is resolved **only** for symbols whose BSC address comes from the
curated ``SPOT_TOKEN_MAP``. Resolving an address from the ticker through the
market-data provider is not used here: one ticker matches many tokens (the
symbol "BTC" resolves to an unrelated BEP20 token), and confirming a pool for
the wrong contract would be worse than admitting we do not know.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import get_logger
from backend.app.data.market_data.cache import TTLCache
from backend.app.execution.network_selection import effective_execution_settings
from backend.app.execution.providers import PancakeSwapProvider
from backend.app.execution.venues.aster import AsterClient

logger = get_logger("execution.venue_availability")

AVAILABLE = "available"
UNAVAILABLE = "unavailable"
UNKNOWN = "unknown"

SPOT_VENUE = "pancakeswap"
PERP_VENUE = "aster"

#: Venue metadata changes rarely; one hour keeps the setup screen responsive
#: without querying the venue on every render.
DEFAULT_TTL_SECONDS = 3600.0

#: A failed lookup is cached far more briefly: a transient outage must not
#: freeze every symbol as "unknown" for a whole hour.
FAILURE_TTL_SECONDS = 60.0

_PERP_MARKETS_KEY = "aster:perp_markets"
_BNB_PRICE_KEY = "pancakeswap:bnb_price_usd"
_ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


@dataclass(frozen=True, slots=True)
class MarketAvailability:
    """Availability of one symbol on one market, plus why when it is not."""

    venue: str
    status: str
    reason: str | None = None

    def as_dict(self) -> dict[str, str]:
        payload = {"venue": self.venue, "status": self.status}
        if self.reason:
            payload["reason"] = self.reason
        return payload


class VenueAvailabilityService:
    """Resolve, and cache, which venue can execute which symbol.

    Read-only by construction: it never places, changes or cancels anything, and
    the Aster call it makes is the public unauthenticated one.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        cache: TTLCache | None = None,
        aster_client: AsterClient | None = None,
        spot_provider: PancakeSwapProvider | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._cache = cache if cache is not None else TTLCache(DEFAULT_TTL_SECONDS)
        self._aster_client = aster_client
        self._spot_provider = spot_provider
        self._spot_provider_injected = spot_provider is not None
        self._spot_provider_network: str | None = None

    def _execution_settings(self) -> Settings:
        """Settings as the execution layer sees them, runtime override included.

        The BSC network can be switched at runtime by an admin, not only through
        the environment. Reading the raw Settings here would let the setup screen
        claim one network while the engine trades on another — the second source
        of truth this module exists to avoid.
        """
        try:
            return effective_execution_settings(self._settings)
        except Exception as exc:  # runtime state unavailable: fall back to config
            logger.warning("effective_settings_unavailable", error_type=type(exc).__name__)
            return self._settings

    # ── Venue clients ─────────────────────────────────────────────────────────

    def _aster(self) -> AsterClient:
        if self._aster_client is None:
            # exchangeInfo is public: the credentials stay empty on purpose, so
            # availability keeps working on an instance with no Aster account.
            self._aster_client = AsterClient(
                base_url=self._settings.aster_base_url,
                account_address="",
                api_wallet_address="",
                api_wallet_private_key="",
            )
        return self._aster_client

    def _spot(self, settings: Settings) -> PancakeSwapProvider:
        if self._spot_provider_injected:
            return self._spot_provider  # type: ignore[return-value]
        # Rebuilt when the network changes: router, factory and WBNB differ, and
        # a stale provider would probe the wrong chain.
        if self._spot_provider is None or self._spot_provider_network != settings.bsc_network:
            self._spot_provider = PancakeSwapProvider(settings)
            self._spot_provider_network = settings.bsc_network
        return self._spot_provider

    # ── Perp (Aster) ──────────────────────────────────────────────────────────

    async def _perp_markets(self) -> frozenset[str] | None:
        """Base assets Aster lists as tradable perpetuals; ``None`` if unknown."""

        cached = self._cache.get(_PERP_MARKETS_KEY)
        if cached is not None:
            ok, markets = cached
            return markets if ok else None
        try:
            payload = await self._aster().public_exchange_info()
            symbols = payload.get("symbols", []) if isinstance(payload, dict) else []
            tradable = [
                entry
                for entry in symbols
                if entry.get("contractType") == "PERPETUAL" and entry.get("status") == "TRADING"
            ]
            markets = frozenset(str(entry.get("baseAsset", "")).upper() for entry in tradable)
        except Exception as exc:  # network, timeout, malformed payload
            logger.warning("perp_markets_unavailable", error_type=type(exc).__name__)
            self._cache.set(_PERP_MARKETS_KEY, (False, frozenset()), FAILURE_TTL_SECONDS)
            return None
        self._cache.set(_PERP_MARKETS_KEY, (True, markets))
        # Base assets, not markets: one asset can have several quote pairs
        # (BTCUSDT and BTCUSDC are one tradable coin for the setup screen).
        logger.info("perp_markets_loaded", base_assets=len(markets), markets=len(tradable))
        return markets

    # ── Spot (PancakeSwap) ────────────────────────────────────────────────────

    def _mapped_address(self, symbol: str) -> str | None:
        """BSC address from the curated map only — never resolved by ticker."""

        entry = self._settings.spot_token_map.get(symbol.upper())
        if not entry:
            return None
        address, _, _decimals = entry.partition(":")
        return address or None

    async def _spot_status(self, symbol: str, settings: Settings) -> MarketAvailability:
        # The network is part of the key: switching chain must not serve answers
        # computed against the other one.
        cache_key = f"pancakeswap:spot:{settings.bsc_network}:{symbol.upper()}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        token = self._mapped_address(symbol)
        if token is None:
            # Not a venue answer: we simply have no trustworthy address for it.
            return MarketAvailability(
                SPOT_VENUE, UNKNOWN, "indirizzo BSC non verificato per questo simbolo"
            )
        quote = settings.spot_quote_token_address
        if not quote:
            return MarketAvailability(SPOT_VENUE, UNKNOWN, "token di quotazione spot non configurato")
        if settings.bsc_network == "testnet":
            # Curated addresses are mainnet ones: probing the testnet factory
            # would report "no pool" for coins that trade perfectly well on
            # mainnet, and that answer would block them in the setup screen.
            return MarketAvailability(SPOT_VENUE, UNKNOWN, "rete BSC di test: verifica spot non significativa")

        provider = self._spot(settings)
        try:
            # Same path the engine would swap through, so the answer matches
            # what execution would really attempt: every hop needs its pool.
            path = provider.build_path(quote, token)
            for first, second in zip(path, path[1:]):
                pair = await provider.pair_address(first, second)
                if pair == _ZERO_ADDRESS:
                    result = MarketAvailability(
                        SPOT_VENUE, UNAVAILABLE, "nessuna pool PancakeSwap per questo pair"
                    )
                    self._cache.set(cache_key, result)
                    return result
        except Exception as exc:  # RPC unreachable, bad address, decode failure
            logger.warning("spot_status_unavailable", symbol=symbol, error_type=type(exc).__name__)
            result = MarketAvailability(SPOT_VENUE, UNKNOWN, "verifica on-chain non riuscita")
            self._cache.set(cache_key, result, FAILURE_TTL_SECONDS)
            return result

        result = MarketAvailability(SPOT_VENUE, AVAILABLE)
        self._cache.set(cache_key, result)
        return result

    # ── Spot pool depth ───────────────────────────────────────────────────────

    async def _bnb_price_usd(self, settings: Settings, provider) -> Decimal | None:
        """BNB price read from the quote/WBNB pool itself, no external feed."""

        cached = self._cache.get(_BNB_PRICE_KEY)
        if cached is not None:
            return cached
        quote = settings.spot_quote_token_address
        if not quote:
            return None
        try:
            pair = await provider.pair_address(quote, provider.wbnb_address)
            if pair == _ZERO_ADDRESS:
                return None
            token0, reserve0, reserve1 = await provider.pair_reserves(pair)
            quote_reserve, wbnb_reserve = (
                (reserve0, reserve1) if token0.lower() == quote.lower() else (reserve1, reserve0)
            )
            if wbnb_reserve == 0:
                return None
            price = Decimal(quote_reserve) / Decimal(wbnb_reserve)
        except Exception as exc:
            logger.warning("bnb_price_unavailable", error_type=type(exc).__name__)
            return None
        self._cache.set(_BNB_PRICE_KEY, price, FAILURE_TTL_SECONDS * 5)
        return price

    async def spot_pool_liquidity_usd(self, symbol: str) -> Decimal | None:
        """Depth, in USD, of the pool the router would actually swap through.

        The last hop is what matters: ``build_path`` always routes through WBNB,
        so a deep direct pair the router would never touch is not liquidity we
        can use. ``None`` means "not measurable" — an unmapped symbol, a test
        network, an RPC failure — and the caller must treat it as unknown rather
        than as zero, or a lookup failure would silently block every trade.
        """

        settings = self._execution_settings()
        if settings.bsc_network == "testnet":
            return None
        token = self._mapped_address(symbol)
        quote = settings.spot_quote_token_address
        if not token or not quote:
            return None

        cache_key = f"pancakeswap:depth:{settings.bsc_network}:{symbol.upper()}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        provider = self._spot(settings)
        try:
            path = provider.build_path(quote, token)
            counterpart, target = path[-2], path[-1]
            pair = await provider.pair_address(counterpart, target)
            if pair == _ZERO_ADDRESS:
                depth = Decimal(0)
            else:
                token0, reserve0, reserve1 = await provider.pair_reserves(pair)
                side = (
                    reserve0 if token0.lower() == counterpart.lower() else reserve1
                )
                units = Decimal(side) / Decimal(10**18)
                if counterpart.lower() == provider.wbnb_address.lower():
                    price = await self._bnb_price_usd(settings, provider)
                    if price is None:
                        return None
                    depth = units * price
                else:
                    depth = units
        except Exception as exc:
            logger.warning("pool_depth_unavailable", symbol=symbol, error_type=type(exc).__name__)
            return None

        self._cache.set(cache_key, depth)
        return depth

    # ── Public API ────────────────────────────────────────────────────────────

    async def availability(self, symbols: list[str]) -> dict[str, dict[str, dict[str, str]]]:
        """Availability of every given symbol on both markets, keyed by symbol."""

        settings = self._execution_settings()
        perp_markets = await self._perp_markets()
        result: dict[str, dict[str, dict[str, str]]] = {}
        for symbol in symbols:
            key = symbol.upper()
            if perp_markets is None:
                perp = MarketAvailability(PERP_VENUE, UNKNOWN, "venue non raggiungibile")
            elif key in perp_markets:
                perp = MarketAvailability(PERP_VENUE, AVAILABLE)
            else:
                perp = MarketAvailability(PERP_VENUE, UNAVAILABLE, "non quotata su Aster")
            spot = await self._spot_status(key, settings)
            result[key] = {"spot": spot.as_dict(), "perp": perp.as_dict()}
        return result


_service: VenueAvailabilityService | None = None


def get_venue_availability_service() -> VenueAvailabilityService:
    global _service
    if _service is None:
        _service = VenueAvailabilityService()
    return _service
