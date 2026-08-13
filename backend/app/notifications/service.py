"""Notification application service."""

from functools import lru_cache

from backend.app.core.config import get_settings
from backend.app.notifications.fcm.client import FcmClient
from backend.app.notifications.fcm.token_store import DeviceTokenStore
from backend.app.schemas.notifications import (
    DeviceRegistrationRequest,
    DeviceRegistrationResponse,
    DeviceUnregisterRequest,
    NotificationRequest,
    NotificationSendResponse,
    NotificationStatusResponse,
)


class NotificationService:
    """Coordinate device registry and FCM delivery."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.store = DeviceTokenStore(self.settings.fcm_token_store_path)
        self.fcm = FcmClient(self.settings)

    def register_device(self, request: DeviceRegistrationRequest) -> DeviceRegistrationResponse:
        """Register a device token."""

        record = self.store.register(
            token=request.token,
            user_id=request.user_id,
            platform=request.platform,
            device_id=request.device_id,
            app_version=request.app_version,
            build_number=request.build_number,
            locale=request.locale,
            display_name=request.display_name,
        )
        return DeviceRegistrationResponse(status="registered", token_id=record.token_id, user_id=request.user_id)

    def unregister_device(self, request: DeviceUnregisterRequest) -> DeviceRegistrationResponse:
        """Remove a device token."""

        token_id = self.store.remove(request.token, request.user_id)
        return DeviceRegistrationResponse(status="removed", token_id=token_id, user_id=request.user_id)

    def send(self, request: NotificationRequest) -> NotificationSendResponse:
        """Send a notification to registered user devices."""

        tokens = self.store.tokens_for_user(request.user_id, request.token_ids)
        return self.fcm.send(
            tokens=tokens,
            title=request.title,
            body=request.body,
            severity=request.severity,
            data=request.data,
            dry_run=request.dry_run,
        )

    def list_devices(self) -> list:
        """Return all registered device records for the default user."""

        return self.store.list_all(self.settings.default_user_id)

    def status(self) -> NotificationStatusResponse:
        """Return notification subsystem status."""

        return NotificationStatusResponse(
            enabled=self.settings.fcm_enabled,
            configured=self.fcm.configured,
            token_count=self.store.count(),
            critical_topic=self.settings.fcm_critical_topic,
            token_store_path=self.settings.fcm_token_store_path,
        )


@lru_cache
def get_notification_service() -> NotificationService:
    """Return singleton notification service."""

    return NotificationService()
