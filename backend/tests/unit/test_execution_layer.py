import base64
from decimal import Decimal
import hashlib
import hmac
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from backend.app.core.config import Settings
from backend.app.execution.approvals import ApprovalPolicyError, ExactApprovalPolicy
from backend.app.execution.coordinator import ExecutionCoordinator
from backend.app.execution.gas import GasGuard
from backend.app.execution.models import ExecutionStatus, TransactionResult
from backend.app.execution.perp_bnb_sdk import BnbAgentSdkBridge, PerpExecutionError
from backend.app.execution.reconciliation import TransactionReconciler
from backend.app.execution.rpc import MultiRpcClient
from backend.app.execution.spot_twak.client import (
    TwakClient,
    TwakCommandResult,
    TwakError,
    _resolve_cli_path,
    _safe_error_detail,
    _sign_amber_request,
)
from backend.app.execution.x402 import X402Client

ROUTER = "0xD99D1c33F9fC3444f8101754aBC46c52416550D1"
PERP_CONTRACT = "0x0000000000000000000000000000000000000097"


def _valid_settings_payload() -> dict[str, Any]:
    return {
        "eligible_tokens": [f"TOKEN_{index}" for index in range(149)],
        "bnb_gas_reserve_pct": 15,
        "bnb_gas_reserve_min": 0.000005,
    }


def test_execution_guardrails_cannot_be_relaxed() -> None:
    with pytest.raises(ValueError, match="15%"):
        Settings.model_validate({**_valid_settings_payload(), "bnb_gas_reserve_pct": 14})
    with pytest.raises(ValueError, match="testnet"):
        Settings.model_validate(
            {
                **_valid_settings_payload(),
                "execution_mode": "live",
                "bsc_network": "mainnet",
            }
        )
    with pytest.raises(ValueError, match="official competition contract"):
        Settings.model_validate(
            {
                **_valid_settings_payload(),
                "competition_contract_address": "0x0000000000000000000000000000000000000001",
            }
        )
    with pytest.raises(ValueError, match="only be enabled on BSC"):
        Settings.model_validate(
            {
                **_valid_settings_payload(),
                "x402_enabled": True,
                "x402_network": "base",
            }
        )


def test_twak_rest_configuration_status_uses_exact_settings_names() -> None:
    settings = Settings.model_validate(
        {
            **_valid_settings_payload(),
            "TWAK_ACCESS_ID": "access-id",
            "TWAK_HMAC_SECRET": "secret",
        }
    )
    assert settings.twak_rest_configured


def test_exact_approval_policy_rejects_unknown_and_excess_allowance() -> None:
    policy = ExactApprovalPolicy([ROUTER])
    assert policy.validate(ROUTER, 100, 100)
    with pytest.raises(ApprovalPolicyError):
        policy.validate("0x0000000000000000000000000000000000000001", 100, 100)
    with pytest.raises(ApprovalPolicyError):
        policy.validate(ROUTER, 101, 100)


def test_gas_guard_preserves_percentage_and_floor_and_requires_profit() -> None:
    guard = GasGuard(Decimal("15"), Decimal("0.000005"))
    allowed = guard.evaluate(
        balance_wei=10**18,
        gas_limit=21_000,
        gas_price_wei=1_000_000_000,
        expected_profit_usd=Decimal("2"),
        bnb_price_usd=Decimal("600"),
    )
    assert allowed.allowed
    assert allowed.reserve_wei == 150_000_000_000_000_000

    rejected = guard.evaluate(
        balance_wei=10**18,
        gas_limit=100_000,
        gas_price_wei=10_000_000_000,
        expected_profit_usd=Decimal("0.50"),
        bnb_price_usd=Decimal("600"),
    )
    assert not rejected.allowed
    assert rejected.reason == "estimated_gas_cost_not_below_expected_profit"


@pytest.mark.asyncio
async def test_rpc_falls_back_to_second_endpoint() -> None:
    called: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        called.append(request.url.host or "")
        if request.url.host == "primary.invalid":
            return httpx.Response(503)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 2, "result": "0x61"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rpc = MultiRpcClient(
            ["https://primary.invalid", "https://secondary.invalid"],
            client=client,
        )
        result = await rpc.call("eth_chainId")

    assert result == "0x61"
    assert called == ["primary.invalid", "secondary.invalid"]


@pytest.mark.asyncio
async def test_rpc_adds_api_key_only_for_tatum_hosts() -> None:
    headers: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        headers[request.url.host or ""] = request.headers.get("x-api-key")
        if request.url.host == "bsc-testnet.gateway.tatum.io":
            return httpx.Response(503)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 2, "result": "0x61"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rpc = MultiRpcClient(
            [
                "https://bsc-testnet.gateway.tatum.io",
                "https://bsc-testnet-rpc.publicnode.com",
            ],
            rpc_api_key="configured-secret",
            client=client,
        )
        result = await rpc.call("eth_chainId")

    assert result == "0x61"
    assert headers["bsc-testnet.gateway.tatum.io"] == "configured-secret"
    assert headers["bsc-testnet-rpc.publicnode.com"] is None


class FakeWallet:
    address = "0x0000000000000000000000000000000000000002"

    def sign_typed_data(
        self,
        domain: dict[str, Any],
        types: dict[str, list[dict[str, str]]],
        message: dict[str, Any],
    ) -> dict[str, Any]:
        return {"signature": "0xsigned", "domain": domain, "message": message}


def _perp_settings(**overrides: Any) -> SimpleNamespace:
    values = {
        "bsc_network": "testnet",
        "bsc_chain_id": 97,
        "perp_allowed_verifying_contracts": [PERP_CONTRACT],
        "perp_order_submit_url": None,
        "bnb_ai_agent_sdk_enabled": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_perp_eip712_signing_is_chain_and_contract_bound() -> None:
    bridge = BnbAgentSdkBridge(_perp_settings(), FakeWallet())
    signed = bridge.sign_order(
        domain={"chainId": 97, "verifyingContract": PERP_CONTRACT},
        types={"Order": [{"name": "size", "type": "uint256"}]},
        message={"size": 1},
    )
    assert signed["signature"] == "0xsigned"

    with pytest.raises(PerpExecutionError):
        bridge.sign_order(
            domain={"chainId": 56, "verifyingContract": PERP_CONTRACT},
            types={"Order": []},
            message={},
        )
    with pytest.raises(PerpExecutionError):
        bridge.sign_order(
            domain={
                "chainId": 97,
                "verifyingContract": "0x0000000000000000000000000000000000000001",
            },
            types={"Order": []},
            message={},
        )


class StubTwakClient(TwakClient):
    def __init__(self, settings: Any, provider: str) -> None:
        super().__init__(settings)
        self.provider = provider
        self.calls: list[list[str]] = []

    async def _run(
        self,
        arguments: list[str],
        *,
        wallet_password: str | None = None,
    ) -> TwakCommandResult:
        self.calls.append(arguments)
        if "--quote-only" in arguments:
            return TwakCommandResult(payload={"provider": self.provider}, return_code=0)
        return TwakCommandResult(payload={"hash": "0xtx"}, return_code=0)

    async def quote(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "routes": [
                {
                    "id": "route-1",
                    "steps": [
                        {
                            "id": "step-1",
                            "provider": {"name": self.provider},
                        }
                    ],
                }
            ]
        }

    async def route_step(self, step_id: str) -> dict[str, Any]:
        return {"stepId": step_id, "transaction": {"type": "swap"}}


def _twak_settings(**overrides: Any) -> SimpleNamespace:
    values = {
        "twak_cli_path": "twak",
        "twak_access_id": "configured",
        "twak_hmac_secret": "configured",
        "twak_api_base_url": "https://tws.trustwallet.com",
        "twak_chain": "bsctestnet",
        "bsc_network": "testnet",
        "risk_max_slippage_pct": 1.0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _allowed_gas_decision() -> Any:
    return GasGuard(Decimal("15"), Decimal("0.000005")).evaluate(
        balance_wei=10**18,
        gas_limit=21_000,
        gas_price_wei=1_000_000_000,
        expected_profit_usd=Decimal("2"),
        bnb_price_usd=Decimal("600"),
    )


def test_twak_error_detail_redacts_sensitive_patterns() -> None:
    detail = _safe_error_detail(
        (
            b"RPC https://example.invalid/path failed "
            b"password=secret token=secret "
            b"0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        ),
        b"",
    )
    assert "example.invalid" not in detail
    assert "secret" not in detail
    assert "aaaaaaaa" not in detail
    assert "[redacted-url]" in detail


def test_twak_hmac_matches_current_sdk_wire_format() -> None:
    headers = _sign_amber_request(
        "GET",
        "/amber-api/v1/domains",
        "",
        "access-id",
        "secret",
        nonce="fixed-nonce",
        request_date="Sun, 15 Jun 2026 12:00:00 GMT",
    )
    plaintext = (
        "GET;/amber-api/v1/domains;;access-id;fixed-nonce;"
        "Sun, 15 Jun 2026 12:00:00 GMT"
    )
    expected = base64.b64encode(
        hmac.new(b"secret", plaintext.encode(), hashlib.sha256).digest()
    ).decode()
    assert headers["Authorization"] == f"HMAC-SHA256 Signature={expected}"
    assert headers["X-TW-CREDENTIAL"] == "access-id"
    assert headers["X-TW-NONCE"] == "fixed-nonce"
    assert headers["X-TW-DATE"] == "Sun, 15 Jun 2026 12:00:00 GMT"


def test_twak_hmac_sorts_query_params() -> None:
    headers = _sign_amber_request(
        "GET",
        "/amber-api/v1/route",
        "z=last&a=first",
        "access-id",
        "secret",
        nonce="fixed-nonce",
        request_date="Sun, 15 Jun 2026 12:00:00 GMT",
    )
    plaintext = (
        "GET;/amber-api/v1/route;a=first&z=last;access-id;fixed-nonce;"
        "Sun, 15 Jun 2026 12:00:00 GMT"
    )
    expected = base64.b64encode(
        hmac.new(b"secret", plaintext.encode(), hashlib.sha256).digest()
    ).decode()
    assert headers["Authorization"] == f"HMAC-SHA256 Signature={expected}"


def test_twak_cli_resolution_uses_available_windows_launcher(tmp_path) -> None:
    launcher = tmp_path / "twak.cmd"
    launcher.write_text("@echo off\n", encoding="ascii")
    resolved = _resolve_cli_path("twak", {"PATH": str(tmp_path), "PATHEXT": ".CMD"})
    if resolved == "twak":
        pytest.skip("shutil.which PATHEXT behavior is platform-specific")
    assert resolved.lower().endswith("twak.cmd")


@pytest.mark.asyncio
async def test_twak_swap_requires_testnet_slippage_and_pancake_route() -> None:
    client = StubTwakClient(_twak_settings(), "PancakeSwap V2")
    result = await client.execute_swap(
        amount_atomic=10**18,
        from_asset="0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
        to_asset=ROUTER,
        wallet_address="0x0000000000000000000000000000000000000002",
        from_domain="smartchain-testnet",
        to_domain="smartchain-testnet",
        slippage_pct=Decimal("0.5"),
        gas_decision=_allowed_gas_decision(),
    )
    assert result["status"] == "prepared"

    bad_route = StubTwakClient(_twak_settings(), "Unknown Router")
    with pytest.raises(TwakError):
        await bad_route.execute_swap(
            amount_atomic=10**18,
            from_asset="0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
            to_asset=ROUTER,
            wallet_address="0x0000000000000000000000000000000000000002",
            from_domain="smartchain-testnet",
            to_domain="smartchain-testnet",
            slippage_pct=Decimal("0.5"),
            gas_decision=_allowed_gas_decision(),
        )

    mainnet = StubTwakClient(_twak_settings(bsc_network="mainnet"), "PancakeSwap V2")
    with pytest.raises(TwakError):
        await mainnet.execute_swap(
            amount_atomic=10**18,
            from_asset="0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
            to_asset=ROUTER,
            wallet_address="0x0000000000000000000000000000000000000002",
            from_domain="smartchain-testnet",
            to_domain="smartchain-testnet",
            slippage_pct=Decimal("0.5"),
            gas_decision=_allowed_gas_decision(),
        )


@pytest.mark.asyncio
async def test_twak_swap_cannot_bypass_rejected_gas_guard() -> None:
    client = StubTwakClient(_twak_settings(), "PancakeSwap V2")
    rejected = GasGuard(Decimal("15"), Decimal("0.000005")).evaluate(
        balance_wei=10**18,
        gas_limit=100_000,
        gas_price_wei=10_000_000_000,
        expected_profit_usd=Decimal("0.50"),
        bnb_price_usd=Decimal("600"),
    )
    with pytest.raises(TwakError, match="gas guard"):
        await client.execute_swap(
            amount_atomic=10**18,
            from_asset="0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
            to_asset=ROUTER,
            wallet_address="0x0000000000000000000000000000000000000002",
            from_domain="smartchain-testnet",
            to_domain="smartchain-testnet",
            slippage_pct=Decimal("0.5"),
            gas_decision=rejected,
        )
    assert client.calls == []


class StubReceiptRpc:
    async def wait_for_receipt(
        self,
        transaction_hash: str,
        timeout_seconds: float,
        poll_seconds: float,
    ) -> dict[str, str]:
        return {
            "status": "0x1",
            "blockNumber": "0x64",
            "gasUsed": "0x5208",
            "effectiveGasPrice": "0x3b9aca00",
        }

    async def call(self, method: str, params: list[Any] | None = None) -> str:
        assert method == "eth_blockNumber"
        return "0x64"


@pytest.mark.asyncio
async def test_reconciler_requires_configured_confirmations() -> None:
    reconciler = TransactionReconciler(
        StubReceiptRpc(),  # type: ignore[arg-type]
        "https://testnet.bscscan.com",
        required_confirmations=2,
    )
    result = await reconciler.reconcile(
        "0xknown",
        timeout_seconds=1,
        poll_seconds=0.01,
    )
    assert result.status is ExecutionStatus.UNKNOWN
    assert result.reason == "required_confirmations_not_reached"
    assert result.details["confirmations"] == 1


class StubReconciler:
    def __init__(self, status: ExecutionStatus) -> None:
        self.status = status
        self.hashes: list[str] = []

    async def reconcile(
        self,
        transaction_hash: str,
        *,
        timeout_seconds: float,
        poll_seconds: float,
    ) -> TransactionResult:
        self.hashes.append(transaction_hash)
        return TransactionResult(status=self.status, transaction_hash=transaction_hash)


@pytest.mark.asyncio
async def test_coordinator_retries_only_before_a_hash_exists() -> None:
    reconciler = StubReconciler(ExecutionStatus.UNKNOWN)
    coordinator = ExecutionCoordinator(
        reconciler,  # type: ignore[arg-type]
        max_attempts=2,
        receipt_timeout_seconds=1,
        receipt_poll_seconds=0.01,
    )
    calls = 0

    async def submit() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary")
        return "0xknown"

    result = await coordinator.submit(submit)
    assert result.status is ExecutionStatus.UNKNOWN
    assert calls == 2
    assert reconciler.hashes == ["0xknown"]


class StubX402Twak:
    def __init__(self) -> None:
        self.calls = 0

    async def x402_request(
        self,
        url: str,
        *,
        max_payment_atomic: int,
        wallet_password: str,
    ) -> dict[str, Any]:
        self.calls += 1
        return {"url": url, "paid": max_payment_atomic}


@pytest.mark.asyncio
async def test_x402_enforces_per_call_and_daily_budgets() -> None:
    settings = SimpleNamespace(
        x402_network="bsc",
        x402_max_payment_per_call_usd=0.25,
        x402_daily_spend_limit_usd=0.40,
        agentdata_base_url="https://agentdata.test",
        x402_fallback_base_urls=[],
    )
    twak = StubX402Twak()
    client = X402Client(settings, twak)  # type: ignore[arg-type]
    await client.request(
        "/data",
        max_payment_atomic=200_000,
        payment_usd=Decimal("0.20"),
        wallet_password="not-logged",
    )
    with pytest.raises(ValueError, match="daily"):
        await client.request(
            "/data",
            max_payment_atomic=250_000,
            payment_usd=Decimal("0.25"),
            wallet_password="not-logged",
        )
    with pytest.raises(ValueError, match="per-call"):
        await client.request(
            "/data",
            max_payment_atomic=300_000,
            payment_usd=Decimal("0.30"),
            wallet_password="not-logged",
        )
