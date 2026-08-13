"""Archive existing dry-run records and remove them from live analytics tables."""

from __future__ import annotations

import argparse
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.core.config import get_settings
from backend.app.persistence.archive import DEFAULT_ARCHIVE_LABEL, archive_dry_run_records
from backend.app.persistence.database import close_db, get_session_factory, init_db


async def _run(label: str, *, keep_live: bool) -> int:
    settings = get_settings()
    await init_db(settings.database_url, echo=settings.database_echo)
    try:
        async with get_session_factory()() as session:
            archive = await archive_dry_run_records(
                session,
                user_id=str(settings.default_user_id),
                archive_label=label,
                delete_live=not keep_live,
                reset_portfolio_capital_usd=None if keep_live else Decimal(str(settings.dry_run_capital_usd)),
            )
        print(f"Archived dry-run records: {archive.run_id} ({archive.archive_label})")
        return 0
    finally:
        await close_db()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default=DEFAULT_ARCHIVE_LABEL)
    parser.add_argument("--keep-live", action="store_true", help="Archive without deleting live rows.")
    args = parser.parse_args()
    return asyncio.run(_run(args.label, keep_live=args.keep_live))


if __name__ == "__main__":
    raise SystemExit(main())
