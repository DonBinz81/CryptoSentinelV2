"""Notification routes."""

from fastapi import APIRouter, Depends

from backend.app.api.dependencies import AdminAccessDep, DeviceAccessDep, ReadAccessDep
from backend.app.notifications.service import NotificationService, get_notification_service
from backend.app.schemas.notifications import (
    DeviceListResponse,
    DeviceRecord,
    DeviceRegistrationRequest,
    DeviceRegistrationResponse,
    DeviceUnregisterRequest,
    NotificationRequest,
    NotificationSendResponse,
    NotificationStatusResponse,
)

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("/status")
async def notification_status(
    _: ReadAccessDep,
    service: NotificationService = Depends(get_notification_service),
) -> NotificationStatusResponse:
    """Return FCM subsystem status."""

    return service.status()


@router.get("/devices")
async def list_devices(
    _: AdminAccessDep,
    service: NotificationService = Depends(get_notification_service),
) -> DeviceListResponse:
    """List all registered device tokens (no raw FCM token exposed)."""

    records = service.list_devices()
    return DeviceListResponse(
        devices=[
            DeviceRecord(
                token_id=r.token_id,
                platform=r.platform,
                device_id=r.device_id,
                app_version=r.app_version,
                display_name=r.display_name,
                locale=r.locale,
                registered_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in records
        ],
        total=len(records),
    )


@router.post("/devices", status_code=201)
async def register_device(
    request: DeviceRegistrationRequest,
    _: DeviceAccessDep,
    service: NotificationService = Depends(get_notification_service),
) -> DeviceRegistrationResponse:
    """Register a device token for server-side notifications."""

    return service.register_device(request)


@router.post("/devices/unregister")
async def unregister_device(
    request: DeviceUnregisterRequest,
    _: DeviceAccessDep,
    service: NotificationService = Depends(get_notification_service),
) -> DeviceRegistrationResponse:
    """Remove a device token from the registry."""

    return service.unregister_device(request)


@router.post("/send")
async def send_notification(
    request: NotificationRequest,
    _: AdminAccessDep,
    service: NotificationService = Depends(get_notification_service),
) -> NotificationSendResponse:
    """Send a server-side notification via FCM."""

    return service.send(request)
