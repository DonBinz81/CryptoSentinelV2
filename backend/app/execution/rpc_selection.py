"""Runtime BSC RPC endpoint selection.

Settings remain the source for the configured endpoint list. This helper only
persists an admin override that moves one configured endpoint to the front of
the failover order for newly-created RPC clients.
"""

from __future__ import annotations

from urllib.parse import urlparse

from backend.app.core.config import Settings
from backend.app.persistence.runtime_state import get_runtime_value, set_runtime_value

RPC_ENDPOINT_STATE_KEY = "execution_rpc_endpoint_index"


def rpc_endpoint_label(url: str) -> str:
    """Return a non-secret endpoint label for UI/logging."""

    parsed = urlparse(url)
    return parsed.hostname or f"endpoint-{abs(hash(url)) % 10000}"


def get_active_rpc_index(settings: Settings) -> int | None:
    """Return the persisted RPC index if it still points at a configured URL."""

    raw = get_runtime_value(str(settings.default_user_id), RPC_ENDPOINT_STATE_KEY)
    if raw is None:
        return None
    try:
        index = int(raw)
    except ValueError:
        return None
    if 0 <= index < len(settings.bsc_rpc_urls):
        return index
    return None


def set_active_rpc_index(settings: Settings, index: int) -> None:
    """Persist the preferred BSC RPC endpoint index for the current user."""

    if not 0 <= index < len(settings.bsc_rpc_urls):
        raise ValueError("RPC endpoint index is out of range")
    set_runtime_value(str(settings.default_user_id), RPC_ENDPOINT_STATE_KEY, str(index))


def ordered_bsc_rpc_urls(settings: Settings) -> list[str]:
    """Return BSC RPC URLs with the admin-selected endpoint first."""

    urls = list(settings.bsc_rpc_urls)
    active_index = get_active_rpc_index(settings)
    if active_index is None or active_index == 0:
        return urls
    selected = urls[active_index]
    return [selected, *urls[:active_index], *urls[active_index + 1 :]]
