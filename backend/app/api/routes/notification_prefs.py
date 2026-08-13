"""Route per le preferenze notifiche agente."""

from fastapi import APIRouter

from backend.app.api.dependencies import AdminAccessDep, ReadAccessDep, SettingsDep
from backend.app.notifications.agent_notifier import AgentNotifier, get_agent_notifier
from backend.app.persistence.runtime_state import get_runtime_value
from backend.app.schemas.notification_prefs import (
    NotificationPreferences,
    NotificationPreferencesResponse,
)

router = APIRouter(prefix="/api/v1/notifications/preferences", tags=["notifications"])


@router.get("", response_model=NotificationPreferencesResponse)
async def get_preferences(
    settings: SettingsDep,
    _: ReadAccessDep,
) -> NotificationPreferencesResponse:
    """Restituisce le preferenze notifiche correnti dell'utente."""
    notifier = get_agent_notifier()
    user_id = str(settings.default_user_id)
    prefs = notifier.get_preferences(user_id)
    raw = get_runtime_value(user_id, AgentNotifier.PREFS_KEY)
    return NotificationPreferencesResponse(
        preferences=prefs,
        source="persisted" if raw else "default",
    )


@router.put("", response_model=NotificationPreferencesResponse)
async def update_preferences(
    request: NotificationPreferences,
    settings: SettingsDep,
    _: AdminAccessDep,
) -> NotificationPreferencesResponse:
    """Aggiorna e persiste le preferenze notifiche dell'utente."""
    notifier = get_agent_notifier()
    notifier.set_preferences(str(settings.default_user_id), request)
    return NotificationPreferencesResponse(preferences=request, source="persisted")
