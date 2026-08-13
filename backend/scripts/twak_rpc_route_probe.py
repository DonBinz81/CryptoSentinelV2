"""Probe authenticated TWAK route calls while rotating configured BSC RPC endpoints.

The script is quote-only: it does not sign transactions and does not broadcast.
It loads credentials through Settings without printing secret values.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse

from web3 import Web3

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import configure_logging, get_logger
from backend.app.execution.rpc import MultiRpcClient
from backend.app.execution.spot_twak import TwakClient, TwakError

logger = get_logger("scripts.twak_rpc_route_probe")
NATIVE_EVM_ASSET = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"


def _decimal(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError("must be a decimal number") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _safe_endpoint_label(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if parsed.hostname:
        return parsed.hostname
    return "configured_endpoint"


def _settings_for_single_rpc(settings: Settings, endpoint: str) -> Settings:
    return settings.model_copy(update={"bsc_rpc_urls": [endpoint]})


def _default_domain(settings: Settings) -> str:
    return "smartchain" if settings.bsc_network == "mainnet" else "smartchain-testnet"


async def _probe_endpoint(settings: Settings, args: argparse.Namespace, *, index: int, endpoint: str) -> bool:
    endpoint_label = _safe_endpoint_label(endpoint)
    single_rpc_settings = _settings_for_single_rpc(settings, endpoint)
    rpc = MultiRpcClient(
        single_rpc_settings.bsc_rpc_urls,
        single_rpc_settings.bsc_rpc_timeout_seconds,
        single_rpc_settings.tatum_rpc_api_key,
    )
    try:
        chain_id = int(await rpc.call("eth_chainId"), 16)
        gas_price = int(await rpc.call("eth_gasPrice"), 16)
    except Exception as exc:
        logger.warning(
            "twak_rpc_probe_preflight_failed",
            rpc_index=index,
            rpc_endpoint=endpoint_label,
            error_type=type(exc).__name__,
        )
        return False

    logger.info(
        "twak_rpc_probe_preflight_ok",
        rpc_index=index,
        rpc_endpoint=endpoint_label,
        chain_id=chain_id,
        gas_price_wei=gas_price,
    )
    twak = TwakClient(single_rpc_settings)
    try:
        payload = await twak.quote(
            amount_atomic=int(args.amount * Decimal(10**args.from_decimals)),
            from_asset=args.from_asset,
            to_asset=args.to_asset,
            wallet_address=args.wallet_address,
            from_domain=args.domain,
            to_domain=args.domain,
            slippage_pct=args.slippage,
        )
    except TwakError as exc:
        logger.warning(
            "twak_rpc_probe_route_failed",
            rpc_index=index,
            rpc_endpoint=endpoint_label,
            twak_operation=exc.operation,
            status_code=exc.return_code,
            detail=exc.detail,
        )
        return False

    routes = payload.get("routes") or []
    logger.info(
        "twak_rpc_probe_route_ok",
        rpc_index=index,
        rpc_endpoint=endpoint_label,
        route_count=len(routes),
    )
    print(f"TWAK route OK with RPC index {index} ({endpoint_label}); routes={len(routes)}")
    return True


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    configure_logging(settings)
    if not settings.twak_rest_configured:
        raise RuntimeError("TWAK REST credentials are not configured")
    if not settings.bsc_rpc_urls:
        raise RuntimeError("No BSC RPC endpoints are configured")
    if not Web3.is_address(args.wallet_address):
        raise RuntimeError("wallet_address must be a valid EVM address")
    if not Web3.is_address(args.from_asset) and args.from_asset != NATIVE_EVM_ASSET:
        raise RuntimeError("from_asset must be a valid EVM address or native EVM sentinel")
    if not Web3.is_address(args.to_asset):
        raise RuntimeError("to_asset must be a valid EVM address")

    logger.info(
        "twak_rpc_probe_started",
        configured_rpc_count=len(settings.bsc_rpc_urls),
        domain=args.domain or _default_domain(settings),
        amount_atomic=int(args.amount * Decimal(10**args.from_decimals)),
    )
    any_success = False
    for index, endpoint in enumerate(settings.bsc_rpc_urls):
        if args.domain is None:
            args.domain = _default_domain(settings)
        success = await _probe_endpoint(settings, args, index=index, endpoint=endpoint)
        any_success = any_success or success
        if success and args.stop_on_success:
            break
    if not any_success:
        print("No RPC endpoint produced a successful authenticated TWAK route.")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wallet-address", required=True)
    parser.add_argument("--amount", type=_decimal, required=True)
    parser.add_argument("--from-asset", default=NATIVE_EVM_ASSET)
    parser.add_argument("--to-asset", required=True)
    parser.add_argument("--from-decimals", type=int, default=18)
    parser.add_argument("--slippage", type=_decimal, default=Decimal("0.5"))
    parser.add_argument("--domain", default=None)
    parser.add_argument("--stop-on-success", action="store_true")
    args = parser.parse_args()
    try:
        return asyncio.run(_run(args))
    except (RuntimeError, ValueError) as exc:
        print(f"TWAK RPC route probe failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
