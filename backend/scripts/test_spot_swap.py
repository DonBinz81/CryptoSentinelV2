"""Run one guarded TWAK spot swap on BSC testnet."""

from __future__ import annotations

import argparse
import asyncio
import getpass
from decimal import Decimal, InvalidOperation
from typing import Any

from web3 import Web3

from backend.app.core.config import get_settings
from backend.app.core.logging import configure_logging, get_logger
from backend.app.execution.gas import GasGuard
from backend.app.execution.rpc import MultiRpcClient
from backend.app.execution.spot_twak import TwakClient

logger = get_logger("scripts.test_spot_swap")
NATIVE_EVM_ASSET = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"


def _decimal(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError("must be a decimal number") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _find_value(payload: Any, names: set[str]) -> str | None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key.lower() in names and isinstance(value, str):
                return value
            nested = _find_value(value, names)
            if nested:
                return nested
    if isinstance(payload, list):
        for value in payload:
            nested = _find_value(value, names)
            if nested:
                return nested
    return None


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    configure_logging(settings)
    if settings.bsc_network != "testnet" or settings.bsc_chain_id != 97:
        raise RuntimeError("Spot smoke test requires BSC testnet chain ID 97")
    if not settings.bsc_rpc_urls:
        raise RuntimeError("No BSC testnet RPC endpoints are configured")
    domain = args.domain or ("smartchain" if settings.bsc_network == "mainnet" else "smartchain-testnet")

    password = getpass.getpass("TWAK wallet password: ")
    if not password:
        raise RuntimeError("TWAK wallet password is required")
    confirmation = input("Type TESTNET to submit one real testnet swap: ").strip()
    if confirmation != "TESTNET":
        print("Swap cancelled.")
        return 1

    twak = TwakClient(settings)
    logger.info(
        "spot_smoke_test_started",
        chain=settings.twak_chain,
        configured_rpc_count=len(settings.bsc_rpc_urls),
        twak_rpc_source="twak_internal",
    )
    address_payload = await twak.wallet_address(wallet_password=password)
    address = _find_value(address_payload, {"address"})
    if not address or not Web3.is_address(address):
        raise RuntimeError("TWAK did not return a valid BSC testnet wallet address")

    rpc = MultiRpcClient(
        settings.bsc_rpc_urls,
        settings.bsc_rpc_timeout_seconds,
        settings.tatum_rpc_api_key,
    )
    try:
        balance_wei = int(await rpc.call("eth_getBalance", [address, "latest"]), 16)
        gas_price_wei = int(await rpc.call("eth_gasPrice"), 16)
    except Exception as exc:
        logger.error(
            "spot_rpc_preflight_failed",
            error_type=type(exc).__name__,
            configured_rpc_count=len(settings.bsc_rpc_urls),
        )
        raise RuntimeError(
            f"RPC preflight failed ({type(exc).__name__}); inspect rpc_endpoint_failed logs"
        ) from exc
    guard = GasGuard(
        Decimal(str(settings.bnb_gas_reserve_pct)),
        Decimal(str(settings.bnb_gas_reserve_min)),
    )
    decision = guard.evaluate(
        balance_wei=balance_wei,
        gas_limit=args.gas_limit,
        gas_price_wei=gas_price_wei,
        expected_profit_usd=args.expected_profit_usd,
        bnb_price_usd=args.bnb_price_usd,
    )
    logger.info(
        "spot_gas_guard_evaluated",
        allowed=decision.allowed,
        reason=decision.reason,
        estimation_mode="conservative_gas_limit_times_rpc_gas_price",
        gas_limit=args.gas_limit,
        estimated_cost_wei=decision.estimated_cost_wei,
        reserve_wei=decision.reserve_wei,
    )
    if not decision.allowed:
        raise RuntimeError(f"Gas guard rejected the swap: {decision.reason}")

    try:
        result = await twak.execute_swap(
            amount_atomic=int(args.amount * Decimal(10**args.from_decimals)),
            from_asset=args.from_asset or NATIVE_EVM_ASSET,
            to_asset=args.to_asset,
            wallet_address=address,
            from_domain=domain,
            to_domain=domain,
            slippage_pct=args.slippage,
            gas_decision=decision,
        )
    except Exception as exc:
        logger.error(
            "spot_twak_swap_failed",
            error_type=type(exc).__name__,
            error_detail=str(exc),
            chain=settings.twak_chain,
        )
        raise
    logger.info(
        "spot_rest_route_prepared",
        status=result["status"],
        transaction_count=len(result["transactions"]),
    )
    print("Status: prepared")
    print(f"Route steps: {len(result['transactions'])}")
    print("The REST API returned unsigned transaction data; nothing was broadcast.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("amount", type=_decimal)
    parser.add_argument("from_token")
    parser.add_argument("to_token")
    parser.add_argument("--domain", default=None)
    parser.add_argument("--from-asset")
    parser.add_argument("--to-asset", required=True)
    parser.add_argument("--from-decimals", type=int, default=18)
    parser.add_argument("--slippage", type=_decimal, default=Decimal("0.5"))
    parser.add_argument("--gas-limit", type=_positive_int, default=350_000)
    parser.add_argument("--expected-profit-usd", type=_decimal, required=True)
    parser.add_argument("--bnb-price-usd", type=_decimal, required=True)
    args = parser.parse_args()
    try:
        return asyncio.run(_run(args))
    except (RuntimeError, ValueError) as exc:
        print(f"Spot swap failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
