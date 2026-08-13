"""Explicit TWAK competition registration helper.

This script never runs automatically. It asks for the TWAK wallet password via
hidden input and delegates registration to the existing TWAK client.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.core.config import get_settings  # noqa: E402
from backend.app.execution.spot_twak.client import TwakClient  # noqa: E402


async def _register(*, confirm: bool) -> dict[str, Any]:
    if not confirm:
        raise SystemExit("Pass --confirm to run competition registration.")
    settings = get_settings()
    password = getpass.getpass("TWAK wallet password: ")
    if not password:
        raise SystemExit("Wallet password is required.")
    client = TwakClient(settings)
    return await client.competition_register(wallet_password=password)


def main() -> None:
    parser = argparse.ArgumentParser(description="Register the configured wallet for the BNB competition via TWAK.")
    parser.add_argument("--confirm", action="store_true", help="Actually run `twak compete register --json`.")
    args = parser.parse_args()
    result = asyncio.run(_register(confirm=args.confirm))
    print(result)


if __name__ == "__main__":
    main()
