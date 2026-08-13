"""Runtime BSC network selection for execution diagnostics and providers."""

from __future__ import annotations

from typing import Literal

from backend.app.core.config import Settings
from backend.app.execution.wallet_selection import effective_wallet_settings
from backend.app.persistence.runtime_state import get_runtime_value, set_runtime_value

BscExecutionNetwork = Literal["testnet", "mainnet"]
BSC_NETWORK_STATE_KEY = "execution_bsc_network"
BSC_CHAIN_IDS: dict[BscExecutionNetwork, int] = {"testnet": 97, "mainnet": 56}


def get_active_bsc_network(settings: Settings) -> BscExecutionNetwork:
    """Return the runtime-selected BSC network, falling back to Settings."""

    raw = get_runtime_value(str(settings.default_user_id), BSC_NETWORK_STATE_KEY)
    if raw in BSC_CHAIN_IDS:
        return raw  # type: ignore[return-value]
    if settings.bsc_network == "mainnet":
        return "mainnet"
    return "testnet"


def set_active_bsc_network(settings: Settings, network: BscExecutionNetwork) -> None:
    """Persist the preferred BSC network for the current user."""

    set_runtime_value(str(settings.default_user_id), BSC_NETWORK_STATE_KEY, network)


def effective_execution_settings(settings: Settings) -> Settings:
    """Return Settings with the runtime BSC network override applied."""

    settings = effective_wallet_settings(settings)
    network = get_active_bsc_network(settings)
    return settings.model_copy(
        update={
            "bsc_network": network,
            "bsc_chain_id": BSC_CHAIN_IDS[network],
            "twak_chain": "bsc" if network == "mainnet" else "bsctestnet",
        }
    )
