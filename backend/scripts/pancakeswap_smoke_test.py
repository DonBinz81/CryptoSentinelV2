"""Run one guarded PancakeSwap V2 spot swap directly via web3.py.

Quote-only by default. With --execute it builds, signs (encrypted keystore) and
broadcasts ONE real swap, reconciled on-chain. Testnet is the default and only
unguarded target; --allow-mainnet is the sole path that may submit on mainnet
and requires an extra explicit confirmation.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from decimal import Decimal, InvalidOperation

from web3 import Web3

from backend.app.core.config import get_settings
from backend.app.core.logging import configure_logging, get_logger
from backend.app.execution.base import NATIVE_EVM_ASSET
from backend.app.execution.gas import GasGuard
from backend.app.execution.models import ExecutionStatus
from backend.app.execution.providers import PancakeSwapProvider
from backend.app.execution.rpc import MultiRpcClient

logger = get_logger("scripts.pancakeswap_smoke_test")


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


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    configure_logging(settings)
    if not settings.bsc_rpc_urls:
        raise RuntimeError("No BSC RPC endpoints are configured")
    is_mainnet = settings.bsc_network != "testnet"
    if is_mainnet and not args.allow_mainnet:
        raise RuntimeError("Mainnet detected: pass --allow-mainnet to enable real mainnet execution")

    rpc = MultiRpcClient(
        settings.bsc_rpc_urls,
        settings.bsc_rpc_timeout_seconds,
        settings.tatum_rpc_api_key,
    )
    provider = PancakeSwapProvider(settings, rpc=rpc)
    amount_in_atomic = int(args.amount * Decimal(10**args.from_decimals))

    quote = await provider.get_quote(
        amount_in_atomic=amount_in_atomic,
        from_asset=args.from_asset,
        to_asset=args.to_asset,
        wallet_address=settings.wallet_address or NATIVE_EVM_ASSET,
        slippage_pct=args.slippage,
    )
    print(f"Router: {provider.router_address}")
    print(f"Path: {quote.details.get('path')}")
    print(f"Amount in (atomic): {quote.amount_in_atomic}")
    print(f"Amount out (atomic): {quote.amount_out_atomic}")
    print(f"Min out (atomic, slippage {args.slippage}%): {quote.min_amount_out_atomic}")
    logger.info(
        "pancakeswap_quote_ok",
        amount_out_atomic=quote.amount_out_atomic,
        min_out_atomic=quote.min_amount_out_atomic,
        network=settings.bsc_network,
    )

    if not args.execute:
        print("Quote-only run; nothing was broadcast. Pass --execute to swap.")
        return 0

    label = "MAINNET" if is_mainnet else "TESTNET"
    confirmation = input(f"Type {label} to submit ONE real swap: ").strip()
    if confirmation != label:
        print("Swap cancelled.")
        return 1
    if not settings.wallet_encrypted_private_key_path or not settings.wallet_key_passphrase_env:
        raise RuntimeError("Encrypted keystore path and passphrase env name must be configured")
    if not os.environ.get(settings.wallet_key_passphrase_env):
        raise RuntimeError(
            f"Keystore passphrase env var {settings.wallet_key_passphrase_env} is not set"
        )

    wallet_address = settings.wallet_address
    if not wallet_address or not Web3.is_address(wallet_address):
        raise RuntimeError("A valid wallet_address must be configured")
    balance_wei = int(await rpc.call("eth_getBalance", [wallet_address, "latest"]), 16)
    gas_price_wei = int(await rpc.call("eth_gasPrice"), 16)
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
    if not decision.allowed:
        raise RuntimeError(f"Gas guard rejected the swap: {decision.reason}")

    result = await provider.execute_swap(
        amount_in_atomic=amount_in_atomic,
        from_asset=args.from_asset,
        to_asset=args.to_asset,
        wallet_address=wallet_address,
        slippage_pct=args.slippage,
        gas_decision=decision,
        allow_mainnet=args.allow_mainnet,
    )
    print(f"Status: {result.status}")
    if result.transaction_hash:
        print(f"Tx hash: {result.transaction_hash}")
    if result.explorer_url:
        print(f"Explorer: {result.explorer_url}")
    return 0 if result.status in (ExecutionStatus.CONFIRMED, ExecutionStatus.SKIPPED) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("amount", type=_decimal)
    parser.add_argument("--from-asset", default=NATIVE_EVM_ASSET, help="Token address or native sentinel")
    parser.add_argument("--to-asset", required=True)
    parser.add_argument("--from-decimals", type=int, default=18)
    parser.add_argument("--slippage", type=_decimal, default=Decimal("0.5"))
    parser.add_argument("--gas-limit", type=_positive_int, default=350_000)
    parser.add_argument("--expected-profit-usd", type=_decimal, default=Decimal("1"))
    parser.add_argument("--bnb-price-usd", type=_decimal, default=Decimal("600"))
    parser.add_argument("--execute", action="store_true", help="Broadcast one real swap")
    parser.add_argument("--allow-mainnet", action="store_true", help="Permit mainnet submission")
    args = parser.parse_args()
    try:
        return asyncio.run(_run(args))
    except (RuntimeError, ValueError) as exc:
        print(f"PancakeSwap smoke test failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
