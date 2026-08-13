"""Runtime-selected agent watchlist helpers."""

from __future__ import annotations

import json

from backend.app.core.config import Settings
from backend.app.persistence.runtime_state import get_runtime_value, set_runtime_value

WATCHLIST_STATE_KEY = "agent_watchlist_symbols"
WATCHLIST_SPOT_KEY = "agent_watchlist_spot"
WATCHLIST_PERP_KEY = "agent_watchlist_perp"

# Coin di default per il perp: alta liquidità su Binance Futures, Volume Profile affidabile.
DEFAULT_PERP_SYMBOLS = [
    "BTC", "ETH", "BNB", "SOL", "XRP", "DOGE", "ADA", "AVAX", "DOT", "LINK",
    "LTC", "BCH", "ETC", "ATOM", "UNI", "NEAR", "FIL", "APT", "ARB", "OP",
    "TRX", "MATIC", "ICP", "SUI", "TON", "INJ", "TIA", "SEI", "WLD", "JUP",
    "PENDLE", "AAVE", "MKR", "SNX", "CRV", "COMP", "YFI", "BAL", "SUSHI",
]


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def _load_symbols(user_id: str, key: str, eligible: set[str]) -> list[str]:
    """Load and validate a symbol list from runtime state."""
    raw = get_runtime_value(user_id, key)
    if not raw:
        return []
    try:
        values = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(values, list):
        return []
    selected: list[str] = []
    seen: set[str] = set()
    for value in values:
        symbol = normalize_symbol(str(value))
        if symbol in eligible and symbol not in seen:
            selected.append(symbol)
            seen.add(symbol)
    return selected


def selected_watchlist(settings: Settings) -> list[str]:
    """Return the master watchlist (all markets). Used for backward compat and status."""
    eligible = {normalize_symbol(t) for t in settings.eligible_tokens}
    return _load_symbols(str(settings.default_user_id), WATCHLIST_STATE_KEY, eligible)


def selected_spot_watchlist(settings: Settings) -> list[str]:
    """Return the spot-specific watchlist. Falls back to master if not set."""
    user_id = str(settings.default_user_id)
    eligible = {normalize_symbol(t) for t in settings.eligible_tokens}
    spot = _load_symbols(user_id, WATCHLIST_SPOT_KEY, eligible)
    if spot:
        return spot
    # Fallback: usa la master watchlist
    return _load_symbols(user_id, WATCHLIST_STATE_KEY, eligible)


def selected_perp_watchlist(settings: Settings) -> list[str]:
    """Return the perp-specific watchlist. Falls back to master if not set."""
    user_id = str(settings.default_user_id)
    eligible = {normalize_symbol(t) for t in settings.eligible_tokens}
    perp = _load_symbols(user_id, WATCHLIST_PERP_KEY, eligible)
    if perp:
        return perp
    # Fallback: usa la master watchlist
    return _load_symbols(user_id, WATCHLIST_STATE_KEY, eligible)


def set_selected_watchlist(settings: Settings, symbols: list[str]) -> list[str]:
    """Persist the master watchlist after validating against Settings."""
    eligible = {normalize_symbol(t) for t in settings.eligible_tokens}
    selected: list[str] = []
    seen: set[str] = set()
    for value in symbols:
        symbol = normalize_symbol(value)
        if symbol not in eligible:
            raise ValueError(f"Asset is not in the eligible universe: {value}")
        if symbol not in seen:
            selected.append(symbol)
            seen.add(symbol)
    set_runtime_value(str(settings.default_user_id), WATCHLIST_STATE_KEY, json.dumps(selected))
    return selected


def set_market_watchlist(settings: Settings, market: str, symbols: list[str]) -> list[str]:
    """Persist a market-specific (spot|perp) watchlist. Symbols must be in master."""
    master = set(selected_watchlist(settings))
    if not master:
        raise ValueError("Master watchlist is empty — set the master watchlist first")
    selected: list[str] = []
    seen: set[str] = set()
    for value in symbols:
        symbol = normalize_symbol(value)
        if symbol not in master:
            raise ValueError(f"Asset is not in the master watchlist: {value}")
        if symbol not in seen:
            selected.append(symbol)
            seen.add(symbol)
    key = WATCHLIST_SPOT_KEY if market == "spot" else WATCHLIST_PERP_KEY
    set_runtime_value(str(settings.default_user_id), key, json.dumps(selected))
    return selected


def seed_perp_watchlist_if_empty(settings: Settings) -> None:
    """Al primo avvio popola la perp watchlist con le coin di default se non già impostata."""
    user_id = str(settings.default_user_id)
    existing = get_runtime_value(user_id, WATCHLIST_PERP_KEY)
    if existing:
        return
    eligible = {normalize_symbol(t) for t in settings.eligible_tokens}
    master = set(_load_symbols(user_id, WATCHLIST_STATE_KEY, eligible))
    if not master:
        return
    # Intersezione tra default perp e master (solo coin che l'utente ha già in watchlist)
    valid = [s for s in DEFAULT_PERP_SYMBOLS if s in master]
    if not valid:
        # Se la master non ha nessuna delle default, usa tutta la master
        valid = list(master)
    set_runtime_value(user_id, WATCHLIST_PERP_KEY, json.dumps(valid))
