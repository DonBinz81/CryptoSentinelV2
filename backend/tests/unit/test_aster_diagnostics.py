"""Aster read-only diagnostics: outcomes, safety and secret hygiene."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.execution.venues.aster.client import AsterClient, short_address
from backend.app.execution.venues.aster.diagnostics import run_connection_test

# Throwaway key used only to check address/key coherence. It signs nothing real.
TEST_KEY = "0x" + "11" * 32
TEST_SIGNER = "0x19E7E376E7C213B7E7e7e46cc70A5dD086DAff2A"  # address of that key


def _settings(**overrides):
    base = dict(
        aster_enabled=True,
        aster_base_url="https://fapi3.asterdex.com",
        aster_account_address="0x1111111111111111111111111111111111111111",
        aster_api_wallet_address=TEST_SIGNER,
        aster_api_wallet_private_key=TEST_KEY,
        aster_subaccount_name="CryptosentinelV2",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_missing_configuration_fails_before_any_network_call() -> None:
    """Without credentials the test must stop immediately, saying what is missing."""
    report = await run_connection_test(_settings(aster_api_wallet_private_key=""))

    assert report.overall == "error"
    assert report.checks[0].key == "config"
    assert "chiave di firma" in report.checks[0].detail
    # Stopped at the first check: nothing was attempted over the network.
    assert len(report.checks) == 1


@pytest.mark.asyncio
async def test_key_not_matching_wallet_is_caught_before_signing() -> None:
    """Address and key from different wallets: the most likely setup mistake."""
    report = await run_connection_test(
        _settings(aster_api_wallet_address="0x2222222222222222222222222222222222222222")
    )

    assert report.overall == "error"
    signer_check = next(c for c in report.checks if c.key == "signer")
    assert signer_check.status == "error"
    assert "non corrisponde" in signer_check.detail


@pytest.mark.asyncio
async def test_report_never_leaks_credentials() -> None:
    """No private key, no full signer address anywhere in the payload."""
    report = await run_connection_test(_settings())
    blob = str(report.to_dict())

    assert TEST_KEY not in blob
    assert TEST_KEY[2:] not in blob
    assert TEST_SIGNER not in blob          # only the abbreviated form may appear
    assert report.account == "0x1111...1111"


def test_short_address_abbreviates() -> None:
    assert short_address("0x1234567890abcdef1234567890abcdef12345678") == "0x1234...5678"
    assert short_address(None) == "-"
    assert short_address("0x12") == "-"


def test_client_detects_matching_key_and_address() -> None:
    ok = AsterClient(
        base_url="https://example.invalid",
        account_address="0x1111111111111111111111111111111111111111",
        api_wallet_address=TEST_SIGNER,
        api_wallet_private_key=TEST_KEY,
    )
    assert ok.signer_matches_key() is True

    wrong = AsterClient(
        base_url="https://example.invalid",
        account_address="0x1111111111111111111111111111111111111111",
        api_wallet_address="0x2222222222222222222222222222222222222222",
        api_wallet_private_key=TEST_KEY,
    )
    assert wrong.signer_matches_key() is False


def test_client_exposes_no_trading_methods() -> None:
    """Structural guarantee: this client physically cannot trade."""
    forbidden = ("order", "cancel", "close", "open_position", "transfer", "withdraw")
    methods = [m for m in dir(AsterClient) if not m.startswith("_")]
    offending = [m for m in methods if any(word in m.lower() for word in forbidden)]
    assert offending == [], f"metodi non consentiti in questa fase: {offending}"


def test_signature_is_deterministic_and_hex() -> None:
    """The EIP-712 signature must be reproducible for identical parameters."""
    client = AsterClient(
        base_url="https://example.invalid",
        account_address="0x1111111111111111111111111111111111111111",
        api_wallet_address=TEST_SIGNER,
        api_wallet_private_key=TEST_KEY,
    )
    params = {"symbol": "BTCUSDT", "nonce": "1748310859508867", "signer": TEST_SIGNER}
    first = client._sign(dict(params))
    second = client._sign(dict(params))

    assert first == second
    assert int(first.replace("0x", ""), 16) > 0
    assert len(first.replace("0x", "")) == 130  # 65 bytes: r + s + v


# ── Vista wallet: cosa può essere mostrato e cosa no ─────────────────────────


@pytest.mark.asyncio
async def test_wallet_view_without_credentials_says_so() -> None:
    from backend.app.execution.venues.aster.wallet import get_wallet_view

    view = await get_wallet_view(_settings(aster_api_wallet_private_key=""))

    assert view.configured is False
    assert view.subaccount_address is None
    assert "non configurate" in (view.error or "")


@pytest.mark.asyncio
async def test_wallet_view_shows_subaccount_in_full_and_api_wallet_abbreviated() -> None:
    """Decisione di David: sub-account per intero (ci si versano i fondi), API abbreviato."""
    from backend.app.execution.venues.aster import wallet as wallet_module

    wallet_module._cache.update(at=0.0, value=None)  # niente cache fra i test
    view = await wallet_module.get_wallet_view(_settings(), force_refresh=True)
    payload = str(view.to_dict())

    assert view.subaccount_address == "0x1111111111111111111111111111111111111111"
    assert view.api_wallet_address_short == "0x19E7...ff2A"
    # L'indirizzo completo del wallet API non deve comparire, e la chiave mai.
    assert TEST_SIGNER not in payload
    assert TEST_KEY not in payload
    assert TEST_KEY[2:] not in payload
