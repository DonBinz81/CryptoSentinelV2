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


def _load_symbols(
    user_id: str,
    key: str,
    eligible: set[str],
    restrict_to: set[str] | None = None,
) -> list[str]:
    """Load and validate a symbol list from runtime state.

    `restrict_to` applica un secondo filtro (la master watchlist per le liste di
    mercato). Senza di esso lettura e scrittura divergevano: la lettura ammetteva
    ogni simbolo `eligible`, mentre `set_market_watchlist` pretende che stia nella
    master. Bastava restringere la master perche' la lista persistita contenesse
    simboli non piu' validi: il client la rileggeva, la rispediva intera al primo
    toggle e il backend rispondeva 400 su QUALSIASI coin.
    """
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
        if symbol not in eligible or symbol in seen:
            continue
        if restrict_to is not None and symbol not in restrict_to:
            continue
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
    master = _load_symbols(user_id, WATCHLIST_STATE_KEY, eligible)
    spot = _load_symbols(user_id, WATCHLIST_SPOT_KEY, eligible, restrict_to=set(master))
    if spot:
        return spot
    # Fallback: usa la master watchlist
    return master


def selected_perp_watchlist(settings: Settings) -> list[str]:
    """Return the perp-specific watchlist. Falls back to master if not set."""
    user_id = str(settings.default_user_id)
    eligible = {normalize_symbol(t) for t in settings.eligible_tokens}
    master = _load_symbols(user_id, WATCHLIST_STATE_KEY, eligible)
    perp = _load_symbols(user_id, WATCHLIST_PERP_KEY, eligible, restrict_to=set(master))
    if perp:
        return perp
    # Fallback: usa la master watchlist
    return master


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
    user_id = str(settings.default_user_id)
    set_runtime_value(user_id, WATCHLIST_STATE_KEY, json.dumps(selected))
    _prune_market_watchlists(user_id, eligible, set(selected))
    return selected


def _prune_market_watchlists(user_id: str, eligible: set[str], master: set[str]) -> None:
    """Rimuove da spot e perp i simboli non piu' presenti nella master.

    Senza questa potatura restringere la master lasciava nelle liste di mercato
    simboli orfani, che il backend poi rifiutava in scrittura: la watchlist
    diventava non salvabile finche' non si riscriveva il DB a mano.
    """
    for key in (WATCHLIST_SPOT_KEY, WATCHLIST_PERP_KEY):
        current = _load_symbols(user_id, key, eligible)
        if not current:
            continue
        pruned = [symbol for symbol in current if symbol in master]
        if pruned != current:
            set_runtime_value(user_id, key, json.dumps(pruned))


def set_market_watchlist(settings: Settings, market: str, symbols: list[str]) -> list[str]:
    """Persist a market-specific (spot|perp) watchlist. Symbols must be in master."""
    master = set(selected_watchlist(settings))
    if not master:
        raise ValueError("Master watchlist is empty — set the master watchlist first")
    selected: list[str] = []
    seen: set[str] = set()
    invalid: list[str] = []
    for value in symbols:
        symbol = normalize_symbol(value)
        if symbol not in master:
            # Elenca TUTTI i simboli fuori master, non solo il primo: con un solo
            # nome per volta la diagnosi dal client richiedeva un tentativo a coin.
            if symbol not in invalid:
                invalid.append(symbol)
            continue
        if symbol not in seen:
            selected.append(symbol)
            seen.add(symbol)
    if invalid:
        raise ValueError(
            "Assets not in the master watchlist: " + ", ".join(invalid)
        )
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
