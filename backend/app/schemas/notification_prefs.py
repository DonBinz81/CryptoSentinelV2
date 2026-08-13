"""Schemi API per preferenze notifiche agente."""

from pydantic import BaseModel


class NotificationPreferences(BaseModel):
    """Preferenze utente per i tipi di notifica push."""

    spot_trades: bool = True
    perp_trades: bool = True
    risk_alerts: bool = True
    daily_summary: bool = True
    critical: bool = True


class NotificationPreferencesResponse(BaseModel):
    """Risposta GET/PUT preferenze notifiche."""

    preferences: NotificationPreferences
    source: str  # "default" | "persisted"
