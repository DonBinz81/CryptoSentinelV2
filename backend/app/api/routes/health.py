"""Health and readiness routes."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

from backend.app.agent.heartbeat import heartbeat
from backend.app.api.dependencies import ReadAccessDep, SettingsDep
from backend.app.notifications.service import get_notification_service
from backend.app.persistence.database import check_db

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live(settings: SettingsDep) -> dict[str, Any]:
    """Public liveness endpoint for process supervision."""

    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "timestamp_utc": datetime.now(UTC).isoformat(),
    }


@router.get("/ready")
async def ready(settings: SettingsDep, _: ReadAccessDep) -> dict[str, Any]:
    """Authenticated readiness endpoint for internal clients."""

    notification_status = get_notification_service().status()
    db_health = await check_db()
    db_ok = db_health.get("connected") is True
    return {
        "status": "ready" if (settings.auth_configured and db_ok) else "degraded",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
        "auth_configured": settings.auth_configured,
        "database": {
            "configured": bool(settings.database_url),
            "connected": db_ok,
            "latency_ms": db_health.get("latency_ms"),
            "error": db_health.get("error"),
        },
        "external_services": {
            "cmc": "not_checked",
            "claude": "not_checked",
            "twak": "not_checked",
            "bnb_rpc": "not_checked",
            "fcm": "configured" if notification_status.configured else "not_configured",
        },
        "notifications": notification_status.model_dump(mode="json"),
        "heartbeat": heartbeat.as_dict(),
    }


@router.get("/heartbeat")
async def heartbeat_status(_: ReadAccessDep) -> dict[str, Any]:
    """Authenticated heartbeat status endpoint."""

    return {"status": "ok", "heartbeat": heartbeat.as_dict()}
