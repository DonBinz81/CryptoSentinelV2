"""Persist the active public execution wallet in RuntimeState.

This script stores only a public EVM address. It never reads or writes private
keys and never prints secret values.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.core.config import get_settings
from backend.app.execution.wallet_selection import add_wallet_address, set_active_wallet_address
from backend.app.persistence.sync_database import init_sync_db, reset_sync_db

DEFAULT_TWAK_WALLET = "0xDF27d02a536F1AaAF16a25D5E76DA50d716EAfeB"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", default=DEFAULT_TWAK_WALLET, help="Public EVM wallet address to select.")
    args = parser.parse_args()

    settings = get_settings()
    init_sync_db(settings.database_url, echo=settings.database_echo)
    try:
        try:
            selected = set_active_wallet_address(settings, args.address)
        except ValueError:
            selected = add_wallet_address(settings, args.address)
        print(f"Active execution wallet selected: {selected}")
        return 0
    finally:
        reset_sync_db()


if __name__ == "__main__":
    raise SystemExit(main())
