"""Admin-only operational routes."""

from typing import Any

from fastapi import APIRouter

from backend.app.agent.heartbeat import heartbeat
from backend.app.api.dependencies import AdminAccessDep

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.post("/heartbeat")
async def trigger_heartbeat(_: AdminAccessDep) -> dict[str, Any]:
    """Manually record an admin heartbeat tick."""

    heartbeat.beat("admin_manual_tick")
    return {"status": "ok", "heartbeat": heartbeat.as_dict()}
