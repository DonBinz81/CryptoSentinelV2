"""Firebase Cloud Messaging client."""

from pathlib import Path
from threading import Lock
from typing import Any

import firebase_admin
from firebase_admin import App
from firebase_admin import credentials, messaging

from backend.app.core.config import Settings
from backend.app.core.logging import get_logger
from backend.app.schemas.notifications import NotificationSendResponse, NotificationSeverity

logger = get_logger("notifications.fcm")


class FcmClient:
    """Thin wrapper around Firebase Admin SDK."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = Lock()
        self._initialized = False

    @property
    def configured(self) -> bool:
        """Return whether FCM can be initialized with current settings."""

        return bool(
            self.settings.fcm_enabled
            and self.settings.fcm_project_id
            and self.settings.fcm_credentials_path
            and Path(self.settings.fcm_credentials_path).exists()
        )

    def initialize(self) -> bool:
        """Initialize Firebase Admin SDK once."""

        if self._initialized:
            return True
        if not self.configured:
            return False
        with self._lock:
            if self._initialized:
                return True
            app_name = "cryptosentinel-agent"
            try:
                firebase_admin.get_app(app_name)
            except ValueError:
                cred = credentials.Certificate(self.settings.fcm_credentials_path)
                firebase_admin.initialize_app(
                    cred,
                    {"projectId": self.settings.fcm_project_id},
                    name=app_name,
                )
            self._initialized = True
            return True

    def send(
        self,
        tokens: list[str],
        title: str,
        body: str,
        severity: NotificationSeverity,
        data: dict[str, str],
        dry_run: bool = False,
    ) -> NotificationSendResponse:
        """Send a notification to all provided tokens."""

        if not tokens:
            return NotificationSendResponse(
                status="skipped",
                severity=severity,
                requested_tokens=0,
                success_count=0,
                failure_count=0,
                skipped_reason="no_registered_tokens",
            )
        if not self.initialize():
            return NotificationSendResponse(
                status="skipped",
                severity=severity,
                requested_tokens=len(tokens),
                success_count=0,
                failure_count=0,
                skipped_reason="fcm_not_configured",
            )

        message_ids: list[str] = []
        failure_count = 0
        payload_data = self._stringify_data({**data, "severity": severity})

        topic = data.get("topic", "")
        trade_topics = {self.settings.fcm_spot_topic, self.settings.fcm_perp_topic}
        channel_id = "trade_alerts" if topic in trade_topics else "price_alerts"

        # Tag deterministico: Android sostituisce la notifica precedente con lo stesso tag
        # invece di accumularle. Evita di superare il limite di 50 notifiche per app.
        notif_type = data.get("type", "")
        asset = data.get("asset", "")
        market = data.get("market", "")
        if notif_type == "price_alert":
            notif_tag = f"price_{data.get('coin_id', '')}_{data.get('cross_direction', '')}"
        elif notif_type == "range_alert":
            notif_tag = f"range_{data.get('coin_id', '')}"
        elif notif_type == "fav_alert":
            notif_tag = f"fav_{data.get('coin_id', '')}_{data.get('direction', '')}"
        elif "pnl_usd" in data:
            notif_tag = f"close_{topic}_{asset}_{market}"
        elif "alert_type" in data:
            notif_tag = f"risk_{data.get('alert_type', topic)}"
        elif asset:
            notif_tag = f"open_{topic}_{asset}_{market}"
        else:
            notif_tag = topic or "cs"

        for token in tokens:
            message = messaging.Message(
                token=token,
                notification=messaging.Notification(title=title, body=body),
                data=payload_data,
                android=messaging.AndroidConfig(
                    priority="high" if severity == "critical" else "normal",
                    notification=messaging.AndroidNotification(
                        channel_id=channel_id,
                        sound="default",
                        priority="max" if severity == "critical" else "default",
                        visibility="public",
                        tag=notif_tag,
                    ),
                ),
            )
            try:
                message_ids.append(messaging.send(message, dry_run=dry_run, app=self._app()))
            except Exception as exc:  # Firebase SDK exposes multiple concrete error types.
                failure_count += 1
                logger.warning("fcm_send_failed", error=str(exc), severity=severity)

        success_count = len(message_ids)
        status = "sent" if failure_count == 0 else "partial" if success_count > 0 else "failed"
        return NotificationSendResponse(
            status=status,
            severity=severity,
            requested_tokens=len(tokens),
            success_count=success_count,
            failure_count=failure_count,
            message_ids=message_ids,
        )

    @staticmethod
    def _app() -> App:
        """Return the named Firebase app used by the backend."""

        return firebase_admin.get_app("cryptosentinel-agent")

    @staticmethod
    def _stringify_data(data: dict[str, Any]) -> dict[str, str]:
        """FCM data payload values must be strings."""

        return {str(key): str(value) for key, value in data.items()}
