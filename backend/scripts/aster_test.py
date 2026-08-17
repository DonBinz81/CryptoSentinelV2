"""CLI for the Aster connection test — same logic as App and Dashboard.

    backend/.venv/bin/python -m backend.scripts.aster_test

Read-only: it runs the shared diagnostics, which only performs informational GET
requests. It cannot place, modify or cancel orders, and never prints credentials.
"""

from __future__ import annotations

import asyncio
import sys

from backend.app.core.config import get_settings
from backend.app.execution.venues.aster.diagnostics import run_connection_test

_MARK = {"ok": "[ OK ]", "warning": "[ ATT ]", "error": "[ ERR ]", "critical": "[ CRIT ]"}


async def _main() -> int:
    report = await run_connection_test(get_settings())

    print()
    print("  TEST CONNESSIONE ASTER")
    print("  " + "-" * 62)
    for check in report.checks:
        print(f"  {_MARK.get(check.status, '[ ? ]'):8} {check.label}")
        print(f"           {check.detail}")
        if check.technical:
            print(f"           codice Aster: {check.technical}")
    print("  " + "-" * 62)
    print(f"  {report.summary}")
    account = f" · account {report.account}" if report.account else ""
    print(f"  durata {report.duration_ms} ms{account}")
    if report.blocked:
        print("  ATTENZIONE: operazioni Aster bloccate (identità non corrispondente).")
    print()

    return 0 if report.overall in ("ok", "warning") else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
