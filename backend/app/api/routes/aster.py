"""Aster connection diagnostics — read-only endpoint.

Admin-only, and deliberately limited: it runs the shared diagnostic sequence,
which performs GET requests on informational endpoints only. There is no code
path from here to placing, modifying or cancelling an order, or moving funds.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.api.dependencies import AdminAccessDep, SettingsDep
from backend.app.execution.venues.aster.diagnostics import run_connection_test

router = APIRouter(prefix="/api/v1/aster", tags=["aster"])


@router.post("/connection-test")
async def aster_connection_test(settings: SettingsDep, _: AdminAccessDep) -> dict:
    """Run the read-only Aster diagnostic and return the per-check outcome.

    The response never contains the private key, the full signer address or any
    signature: addresses are abbreviated by the diagnostics layer.
    """
    report = await run_connection_test(settings)
    return report.to_dict()
