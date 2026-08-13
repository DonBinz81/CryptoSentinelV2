"""Route registration."""

from fastapi import APIRouter

from backend.app.api.routes import (
    agent,
    admin,
    alerts,
    execution,
    health,
    market_data,
    mobile_agent,
    notification_prefs,
    notifications,
    observability,
    status,
    support,
    views,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(status.router)
api_router.include_router(admin.router)
api_router.include_router(agent.router)
api_router.include_router(notifications.router)
api_router.include_router(notification_prefs.router)
api_router.include_router(alerts.router)
api_router.include_router(market_data.router)
api_router.include_router(execution.router)
api_router.include_router(views.router)
api_router.include_router(mobile_agent.router)
api_router.include_router(observability.router)
api_router.include_router(support.router)
