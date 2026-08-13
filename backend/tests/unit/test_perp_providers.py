"""Tests for the abstract perpetual execution layer: interface, provider, selector."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from backend.app.execution.perp_base import (
    PerpCapabilityError,
    PerpExecutionProvider,
    PerpExecutionProviderName,
    PerpOrder,
    PerpProviderStatus,
)
from backend.app.execution.perp_providers import BnbSdkPerpProvider
from backend.app.execution.perp_registry import PerpExecutionRegistry


class FakeSettings(SimpleNamespace):
    def model_copy(self, *, update: dict[str, Any] | None = None) -> "FakeSettings":
        values = dict(self.__dict__)
        values.update(update or {})
        return FakeSettings(**values)


class FakeBridge:
    """Stand-in for BnbAgentSdkBridge (no bnbagent import, no network)."""

    def __init__(self) -> None:
        self.signed: tuple[Any, Any, Any] | None = None
        self.submitted: dict[str, Any] | None = None

    @property
    def status(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "installed": True,
            "wallet_bound": True,
            "network": "testnet",
            "identity": "erc8004",
            "commerce": "erc8183",
            "memory_module": "not_exposed_by_public_sdk",
            "venue_configured": False,
        }

    def sign_order(self, *, domain: Any, types: Any, message: Any) -> dict[str, Any]:
        self.signed = (domain, types, message)
        return {"signature": "0xsigned"}

    async def submit_order(self, signed: dict[str, Any]) -> dict[str, Any]:
        self.submitted = signed
        return {"status": "submitted", "order": signed}


def _provider() -> BnbSdkPerpProvider:
    return BnbSdkPerpProvider(SimpleNamespace(bsc_network="testnet"), bridge=FakeBridge())


def test_provider_implements_interface() -> None:
    provider = _provider()
    assert isinstance(provider, PerpExecutionProvider)
    assert provider.name is PerpExecutionProviderName.BNB_SDK
    status = provider.status()
    assert isinstance(status, PerpProviderStatus)
    assert status.name is PerpExecutionProviderName.BNB_SDK
    assert status.network == "testnet"
    assert status.venue_configured is False


@pytest.mark.asyncio
async def test_high_level_methods_are_gated_until_a_venue_exists() -> None:
    provider = _provider()
    with pytest.raises(PerpCapabilityError):
        await provider.open_position(
            PerpOrder(asset="BTC", direction="long", size=Decimal("1"), leverage=Decimal("2"))
        )
    with pytest.raises(PerpCapabilityError):
        await provider.close_position(asset="BTC")
    with pytest.raises(PerpCapabilityError):
        await provider.get_position(asset="BTC")


@pytest.mark.asyncio
async def test_sign_and_submit_order_delegates_to_bridge() -> None:
    bridge = FakeBridge()
    provider = BnbSdkPerpProvider(SimpleNamespace(bsc_network="testnet"), bridge=bridge)
    result = await provider.sign_and_submit_order(
        domain={"chainId": 97, "verifyingContract": "0x0"},
        types={"Order": [{"name": "size", "type": "uint256"}]},
        message={"size": 1},
    )
    assert bridge.signed is not None
    assert result["status"] == "submitted"
    assert result["order"] == {"signature": "0xsigned"}


class FakePerpProvider(PerpExecutionProvider):
    name = PerpExecutionProviderName.BNB_SDK

    def status(self) -> PerpProviderStatus:
        return PerpProviderStatus(name=self.name, configured=True, network="testnet")


def test_registry_default_and_selection() -> None:
    settings = FakeSettings(
        default_user_id="00000000-0000-0000-0000-000000000001",
        perp_execution_provider="bnb_sdk",
        bsc_network="testnet",
        wallet_address=None,
        wallet_addresses=[],
    )
    registry = PerpExecutionRegistry(
        settings,  # type: ignore[arg-type]
        providers={PerpExecutionProviderName.BNB_SDK: FakePerpProvider()},
    )
    assert registry.active_name is PerpExecutionProviderName.BNB_SDK
    assert isinstance(registry.active, FakePerpProvider)
    assert registry.select(PerpExecutionProviderName.BNB_SDK).name is PerpExecutionProviderName.BNB_SDK
    assert len(registry.statuses()) == 1
