"""Wallet and RPC diagnostics for the Step 8 dashboard."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from backend.app.core.config import Settings
from backend.app.execution.rpc_selection import (
    get_active_rpc_index,
    ordered_bsc_rpc_urls,
    set_active_rpc_index,
)
from backend.app.execution.service import ExecutionService
from backend.app.execution.wallet_selection import TWAK_OPERATIONAL_WALLET_ADDRESS
from backend.app.persistence.sync_database import create_all_sync, init_sync_db, reset_sync_db

USER_ID = UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def sync_db(tmp_path: Path):
    reset_sync_db()
    init_sync_db(f"sqlite:///{tmp_path / 'execution_wallets.db'}")
    create_all_sync()
    yield
    reset_sync_db()


def settings(**overrides: Any) -> Settings:
    payload: dict[str, Any] = {
        "default_user_id": USER_ID,
        "eligible_tokens": [f"TOKEN_{index}" for index in range(120)],
        "bnb_gas_reserve_pct": 15,
        "bnb_gas_reserve_min": 0.000005,
        "bsc_network": "testnet",
        "bsc_chain_id": 97,
        "bsc_rpc_urls": ["https://rpc-a.example", "https://rpc-b.example"],
        "bsc_rpc_timeout_seconds": 1,
        "wallet_address": "0x0000000000000000000000000000000000000001",
        "wallet_addresses": [],
        "wallet_encrypted_private_key_path": "configured",
        "twak_access_id": "configured",
        "twak_hmac_secret": "configured",
        "execution_provider": "twak",
        "perp_execution_provider": "bnb_sdk",
        "bnb_ai_agent_sdk_enabled": True,
    }
    payload.update(overrides)
    return Settings.model_validate(payload)


def test_rpc_endpoint_override_reorders_configured_urls(sync_db) -> None:
    config = settings()

    assert get_active_rpc_index(config) is None
    assert ordered_bsc_rpc_urls(config) == ["https://rpc-a.example", "https://rpc-b.example"]

    set_active_rpc_index(config, 1)

    assert get_active_rpc_index(config) == 1
    assert ordered_bsc_rpc_urls(config) == ["https://rpc-b.example", "https://rpc-a.example"]


@pytest.mark.asyncio
async def test_execution_wallets_returns_balances_and_rpc_status(sync_db, monkeypatch) -> None:
    async def fake_call(self, method, params=None):
        del self, params
        if method == "eth_getBalance":
            return hex(1500000000000000000)
        if method == "eth_chainId":
            return hex(97)
        raise AssertionError(f"unexpected RPC method: {method}")

    monkeypatch.setattr("backend.app.execution.rpc.MultiRpcClient.call", fake_call)

    response = await ExecutionService(settings()).wallets()

    assert response.bsc_network == "testnet"
    assert response.chain_id == 97
    assert response.wallets[0].provider == "twak"
    assert response.wallets[0].active is True
    assert response.wallets[0].balance_bnb == "1.5"
    assert response.wallets[1].provider == "pancakeswap"
    assert response.wallets[2].provider == "bnb_sdk"
    assert [endpoint.reachable for endpoint in response.rpc_endpoints] == [True, True]
    assert response.rpc_endpoints[0].status == "reachable"


@pytest.mark.asyncio
async def test_execution_network_override_switches_chain_id(sync_db, monkeypatch) -> None:
    async def fake_call(self, method, params=None):
        del self, params
        if method == "eth_getBalance":
            return hex(1)
        if method == "eth_chainId":
            return hex(56)
        raise AssertionError(f"unexpected RPC method: {method}")

    monkeypatch.setattr("backend.app.execution.rpc.MultiRpcClient.call", fake_call)

    service = ExecutionService(settings())
    response = await service.select_network("mainnet")

    assert response.bsc_network == "mainnet"
    assert response.chain_id == 56
    assert response.network == "BSC mainnet"
    assert response.rpc_endpoints[0].status == "reachable"


def test_execution_status_uses_effective_mainnet_chain(sync_db) -> None:
    service = ExecutionService(settings(bsc_network="mainnet", bsc_chain_id=56))

    status = service.status()
    twak = next(provider for provider in status["spot"]["providers"] if provider["name"] == "twak")
    pancake = next(provider for provider in status["spot"]["providers"] if provider["name"] == "pancakeswap")

    assert status["network"] == "mainnet"
    assert status["chain"] == "bsc"
    assert status["chain_id"] == 56
    assert status["testnet_only"] is False
    assert twak["details"]["chain"] == "bsc"
    assert twak["details"]["domain"] == "smartchain"
    assert twak["details"]["testnet_only_execution"] is False
    assert pancake["details"]["chain"] == "bsc"
    assert pancake["details"]["testnet_only_execution"] is False


@pytest.mark.asyncio
async def test_execution_wallet_can_add_and_select_runtime_address(sync_db, monkeypatch) -> None:
    async def fake_call(self, method, params=None):
        del self
        if method == "eth_getBalance":
            address = params[0]
            return hex(2) if address.endswith("0002") else hex(1)
        if method == "eth_chainId":
            return hex(97)
        raise AssertionError(f"unexpected RPC method: {method}")

    monkeypatch.setattr("backend.app.execution.rpc.MultiRpcClient.call", fake_call)

    service = ExecutionService(settings())
    added = await service.add_wallet("0x0000000000000000000000000000000000000002")

    assert added.active_wallet_address == "0x0000000000000000000000000000000000000002"
    assert [wallet.address for wallet in added.available_wallets] == [
        "0x0000000000000000000000000000000000000001",
        "0x0000000000000000000000000000000000000002",
    ]

    selected = await service.select_wallet("0x0000000000000000000000000000000000000001")

    assert selected.active_wallet_address == "0x0000000000000000000000000000000000000001"
    assert selected.wallets[0].address == "0x0000000000000000000000000000000000000001"


@pytest.mark.asyncio
async def test_deprecated_twak_wallet_migrates_to_operational_wallet(sync_db, monkeypatch) -> None:
    old_wallet = "0x5354d789d065d7a6CaA4287674261bE517AF6104"

    async def fake_call(self, method, params=None):
        del self, params
        if method == "eth_getBalance":
            return hex(1)
        if method == "eth_chainId":
            return hex(56)
        raise AssertionError(f"unexpected RPC method: {method}")

    monkeypatch.setattr("backend.app.execution.rpc.MultiRpcClient.call", fake_call)

    response = await ExecutionService(
        settings(
            wallet_address=old_wallet,
            bsc_network="mainnet",
            bsc_chain_id=56,
        )
    ).wallets()

    assert response.active_wallet_address == TWAK_OPERATIONAL_WALLET_ADDRESS
    assert old_wallet not in [wallet.address for wallet in response.available_wallets]
    assert response.wallets[0].address == TWAK_OPERATIONAL_WALLET_ADDRESS
