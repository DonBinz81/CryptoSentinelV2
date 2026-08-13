"""Tests for the abstract execution layer: interface, providers, selector."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from eth_abi import encode as abi_encode
from web3 import Web3

from backend.app.core.config import Settings
from backend.app.execution.base import (
    NATIVE_EVM_ASSET,
    ExecutionCapabilityError,
    ExecutionProvider,
    ExecutionProviderError,
    ExecutionProviderName,
)
from backend.app.execution.gas import GasGuard
from backend.app.execution.models import ExecutionStatus
from backend.app.execution.providers import PancakeSwapProvider, TWAKProvider
from backend.app.execution.providers.pancakeswap_provider import (
    SEL_SWAP_EXACT_ETH,
    SEL_SWAP_EXACT_TOKENS,
)
from backend.app.execution.registry import ExecutionProviderRegistry

ROUTER_TESTNET = "0xD99D1c33F9fC3444f8101754aBC46c52416550D1"
WBNB_TESTNET = "0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd"
TOKEN_A = "0x1111111111111111111111111111111111111111"
TOKEN_B = "0x2222222222222222222222222222222222222222"
OWNER = "0x0000000000000000000000000000000000000002"


def _settings(**overrides: Any) -> Settings:
    payload: dict[str, Any] = {
        "eligible_tokens": [f"TOKEN_{index}" for index in range(149)],
        "bnb_gas_reserve_pct": 15,
        "bnb_gas_reserve_min": 0.000005,
    }
    payload.update(overrides)
    return Settings.model_validate(payload)


def _allowed_gas_decision() -> Any:
    return GasGuard(Decimal("15"), Decimal("0.000005")).evaluate(
        balance_wei=10**18,
        gas_limit=21_000,
        gas_price_wei=1_000_000_000,
        expected_profit_usd=Decimal("2"),
        bnb_price_usd=Decimal("600"),
    )


def _rejected_gas_decision() -> Any:
    return GasGuard(Decimal("15"), Decimal("0.000005")).evaluate(
        balance_wei=10**18,
        gas_limit=100_000,
        gas_price_wei=10_000_000_000,
        expected_profit_usd=Decimal("0.50"),
        bnb_price_usd=Decimal("600"),
    )


class FakeRpc:
    """Records RPC calls and returns canned responses keyed by method."""

    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[str, Any]] = []

    async def call(self, method: str, params: list[Any] | None = None) -> Any:
        self.calls.append((method, params))
        if method not in self.responses:
            raise AssertionError(f"unexpected RPC call: {method}")
        value = self.responses[method]
        return value() if callable(value) else value


class FakeTwakClient:
    configured = True

    def __init__(self) -> None:
        self.quote_calls = 0
        self.swap_calls = 0

    async def quote(self, **kwargs: Any) -> dict[str, Any]:
        self.quote_calls += 1
        return {
            "routes": [
                {
                    "steps": [{"provider": {"name": "PancakeSwap V2"}}],
                    "toAmount": "123456",
                }
            ]
        }

    async def execute_swap(self, **kwargs: Any) -> dict[str, Any]:
        self.swap_calls += 1
        return {
            "status": "prepared",
            "route": {"steps": [{"provider": {"name": "PancakeSwap V2"}}]},
            "transactions": [{"type": "swap"}],
            "requires_wallet_signature": True,
        }


# ── Interface compliance ───────────────────────────────────────────────────────


def test_both_providers_implement_the_interface() -> None:
    settings = _settings()
    twak = TWAKProvider(settings, client=FakeTwakClient())
    pancake = PancakeSwapProvider(settings, rpc=FakeRpc())
    assert isinstance(twak, ExecutionProvider)
    assert isinstance(pancake, ExecutionProvider)
    assert twak.name is ExecutionProviderName.TWAK
    assert pancake.name is ExecutionProviderName.PANCAKESWAP
    # Status is non-secret and well-formed for both.
    assert twak.status().name is ExecutionProviderName.TWAK
    assert pancake.status().router_address == Web3.to_checksum_address(ROUTER_TESTNET)


@pytest.mark.asyncio
async def test_spot_providers_have_no_persistent_position() -> None:
    settings = _settings()
    for provider in (TWAKProvider(settings, client=FakeTwakClient()), PancakeSwapProvider(settings, rpc=FakeRpc())):
        with pytest.raises(ExecutionCapabilityError):
            await provider.get_position(asset=TOKEN_A)
        with pytest.raises(ExecutionCapabilityError):
            await provider.close_position(asset=TOKEN_A, gas_decision=_allowed_gas_decision())


# ── Selector / registry ────────────────────────────────────────────────────────


def test_registry_switches_active_provider() -> None:
    settings = _settings()
    registry = ExecutionProviderRegistry(settings)
    assert registry.active_name is ExecutionProviderName.TWAK
    assert isinstance(registry.active, TWAKProvider)

    registry.select(ExecutionProviderName.PANCAKESWAP)
    assert registry.active_name is ExecutionProviderName.PANCAKESWAP
    assert isinstance(registry.active, PancakeSwapProvider)

    registry.select(ExecutionProviderName.TWAK)
    assert isinstance(registry.active, TWAKProvider)


def test_registry_boot_default_follows_settings() -> None:
    registry = ExecutionProviderRegistry(_settings(execution_provider="pancakeswap"))
    assert registry.active_name is ExecutionProviderName.PANCAKESWAP


# ── PancakeSwap: quote via getAmountsOut ───────────────────────────────────────


@pytest.mark.asyncio
async def test_pancake_quote_decodes_get_amounts_out() -> None:
    amounts = [10**18, 5 * 10**17]
    encoded = "0x" + abi_encode(["uint256[]"], [amounts]).hex()
    rpc = FakeRpc({"eth_call": encoded})
    provider = PancakeSwapProvider(_settings(), rpc=rpc)

    quote = await provider.get_quote(
        amount_in_atomic=10**18,
        from_asset=NATIVE_EVM_ASSET,
        to_asset=TOKEN_B,
        wallet_address=OWNER,
        slippage_pct=Decimal("0.5"),
    )
    assert quote.amount_out_atomic == 5 * 10**17
    assert quote.min_amount_out_atomic == int(Decimal(5 * 10**17) * Decimal("0.995"))
    assert quote.route_provider == "pancakeswap_v2"
    # Native input path starts at WBNB.
    assert quote.details["path"][0] == Web3.to_checksum_address(WBNB_TESTNET)


# ── PancakeSwap: swap transaction construction (pure) ──────────────────────────


def test_build_swap_transaction_for_token_input() -> None:
    provider = PancakeSwapProvider(_settings(), rpc=FakeRpc())
    tx = provider.build_swap_transaction(
        from_asset=TOKEN_A,
        to_asset=TOKEN_B,
        amount_in_atomic=10**18,
        min_out_atomic=99,
        recipient=OWNER,
        nonce=7,
        gas_price_wei=1_000_000_000,
        chain_id=97,
        deadline=1_900_000_000,
    )
    assert tx["to"] == Web3.to_checksum_address(ROUTER_TESTNET)
    assert tx["value"] == 0
    assert tx["nonce"] == 7
    assert tx["chainId"] == 97
    assert bytes.fromhex(tx["data"][2:10]) == SEL_SWAP_EXACT_TOKENS


def test_build_swap_transaction_for_native_input() -> None:
    provider = PancakeSwapProvider(_settings(), rpc=FakeRpc())
    tx = provider.build_swap_transaction(
        from_asset=NATIVE_EVM_ASSET,
        to_asset=TOKEN_B,
        amount_in_atomic=2 * 10**17,
        min_out_atomic=1,
        recipient=OWNER,
        nonce=0,
        gas_price_wei=1_000_000_000,
        chain_id=97,
        deadline=1_900_000_000,
    )
    assert tx["value"] == 2 * 10**17
    assert bytes.fromhex(tx["data"][2:10]) == SEL_SWAP_EXACT_ETH


def test_build_path_routes_token_to_token_through_wbnb() -> None:
    provider = PancakeSwapProvider(_settings(), rpc=FakeRpc())
    path = provider.build_path(TOKEN_A, TOKEN_B)
    assert path == [
        Web3.to_checksum_address(TOKEN_A),
        Web3.to_checksum_address(WBNB_TESTNET),
        Web3.to_checksum_address(TOKEN_B),
    ]


# ── Guardrails apply to PancakeSwap (cannot be bypassed) ───────────────────────


@pytest.mark.asyncio
async def test_pancake_rejects_slippage_over_hard_limit() -> None:
    rpc = FakeRpc()
    provider = PancakeSwapProvider(_settings(), rpc=rpc)
    with pytest.raises(ExecutionProviderError, match="slippage"):
        await provider.execute_swap(
            amount_in_atomic=10**18,
            from_asset=TOKEN_A,
            to_asset=TOKEN_B,
            wallet_address=OWNER,
            slippage_pct=Decimal("2"),  # hard limit default is 1.0%
            gas_decision=_allowed_gas_decision(),
        )
    assert rpc.calls == []  # blocked before any I/O


@pytest.mark.asyncio
async def test_pancake_cannot_bypass_rejected_gas_guard() -> None:
    rpc = FakeRpc()
    provider = PancakeSwapProvider(_settings(), rpc=rpc)
    with pytest.raises(ExecutionProviderError, match="gas guard"):
        await provider.execute_swap(
            amount_in_atomic=10**18,
            from_asset=TOKEN_A,
            to_asset=TOKEN_B,
            wallet_address=OWNER,
            slippage_pct=Decimal("0.5"),
            gas_decision=_rejected_gas_decision(),
        )
    assert rpc.calls == []  # never reached the network


@pytest.mark.asyncio
async def test_pancake_mainnet_submission_is_gated() -> None:
    rpc = FakeRpc()
    provider = PancakeSwapProvider(_settings(bsc_network="mainnet"), rpc=rpc)
    result = await provider.execute_swap(
        amount_in_atomic=10**18,
        from_asset=TOKEN_A,
        to_asset=TOKEN_B,
        wallet_address=OWNER,
        slippage_pct=Decimal("0.5"),
        gas_decision=_allowed_gas_decision(),
        allow_mainnet=False,
    )
    assert result.status is ExecutionStatus.SKIPPED
    assert result.reason == "mainnet_execution_gated"
    assert rpc.calls == []  # no wallet, no broadcast


# ── TWAKProvider normalization ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_twak_provider_normalizes_quote_and_swap() -> None:
    client = FakeTwakClient()
    provider = TWAKProvider(_settings(), client=client)

    quote = await provider.get_quote(
        amount_in_atomic=10**18,
        from_asset=NATIVE_EVM_ASSET,
        to_asset=TOKEN_B,
        wallet_address=OWNER,
        slippage_pct=Decimal("0.5"),
    )
    assert quote.amount_out_atomic == 123456
    assert "PancakeSwap" in quote.route_provider
    assert client.quote_calls == 1

    result = await provider.execute_swap(
        amount_in_atomic=10**18,
        from_asset=NATIVE_EVM_ASSET,
        to_asset=TOKEN_B,
        wallet_address=OWNER,
        slippage_pct=Decimal("0.5"),
        gas_decision=_allowed_gas_decision(),
    )
    assert result.status is ExecutionStatus.PREPARED
    assert result.details["transactions"] == [{"type": "swap"}]
    assert result.details["requires_wallet_signature"] is True
    assert client.swap_calls == 1
