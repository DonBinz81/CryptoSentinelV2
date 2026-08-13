"""In-app support ticket routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from backend.app.api.dependencies import AdminAccessDep, ReadAccessDep, SessionDep
from backend.app.domain.common.models import DEFAULT_SINGLE_USER_ID
from backend.app.notifications.service import get_notification_service
from backend.app.persistence.repositories.device_profiles import DeviceProfileRepository
from backend.app.persistence.repositories.support import SupportRepository
from backend.app.schemas.support import (
    DeviceProfileRequest,
    DeviceProfileResponse,
    SupportMessageCreateRequest,
    SupportMessageResponse,
    SupportNotificationResponse,
    SupportReadAllResponse,
    SupportStatusUpdateRequest,
    SupportTicketCreateRequest,
    SupportTicketDetail,
    SupportTicketListResponse,
    SupportTicketSummary,
    TicketStatus,
)

router = APIRouter(prefix="/api/v1/support", tags=["support"])

ALLOWED_DIAGNOSTIC_KEYS = {
    "app_version",
    "build_number",
    "platform",
    "locale",
    "device_id",
    "backend_url",
    "market_data_provider",
    "request_id",
    "last_error",
    "timestamp",
}
CLOSED_STATUSES = {"closed", "archived"}


def _sanitize_diagnostics(payload: dict | None) -> dict | None:
    if not isinstance(payload, dict):
        return None
    sanitized = {}
    for key, value in payload.items():
        if key not in ALLOWED_DIAGNOSTIC_KEYS:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            sanitized[str(key)] = value
    return sanitized or None


def _display_name(value: str | None) -> str:
    name = (value or "").strip()
    return name if name else "Dispositivo senza nome"


def _message_response(message) -> SupportMessageResponse:
    return SupportMessageResponse(
        message_id=message.message_id,
        ticket_id=message.ticket_id,
        sender_type=message.sender_type,
        sender_id=message.sender_id,
        body=message.body,
        diagnostics=message.diagnostics_json,
        created_at=message.created_at,
    )


def _ticket_summary(ticket, *, viewer: str = "user") -> SupportTicketSummary:
    seen_at = ticket.admin_last_seen_at if viewer == "admin" else ticket.user_last_seen_at
    other_sender = "user" if viewer == "admin" else "admin"
    messages = getattr(ticket, "messages", []) or []
    has_unread = any(
        m.sender_type == other_sender and (seen_at is None or m.created_at > seen_at)
        for m in messages
    )
    return SupportTicketSummary(
        ticket_id=ticket.ticket_id,
        user_id=ticket.user_id,
        device_id=ticket.device_id,
        display_name=_display_name(ticket.display_name_snapshot),
        category=ticket.category,
        priority=ticket.priority,
        status=ticket.status,
        subject=ticket.subject,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        last_message_at=ticket.last_message_at,
        resolved_at=ticket.resolved_at,
        closed_at=ticket.closed_at,
        closed_by=ticket.closed_by,
        message_count=len(messages),
        has_unread=has_unread,
    )


def _ticket_detail(ticket, *, viewer: str = "user") -> SupportTicketDetail:
    summary = _ticket_summary(ticket, viewer=viewer)
    seen_at = ticket.admin_last_seen_at if viewer == "admin" else ticket.user_last_seen_at
    return SupportTicketDetail(
        **summary.model_dump(),
        messages=[_message_response(message) for message in ticket.messages],
        last_seen_at=seen_at,
    )


def _notification_response(count: int, latest_ticket, *, viewer: str = "user") -> SupportNotificationResponse:
    return SupportNotificationResponse(
        unread_count=count,
        latest_ticket=_ticket_summary(latest_ticket, viewer=viewer) if latest_ticket is not None else None,
    )


async def _notify_device(ticket, *, title: str, body: str) -> None:
    service = get_notification_service()
    tokens = service.store.tokens_for_device(ticket.user_id, ticket.device_id)
    if not tokens:
        return
    service.fcm.send(
        tokens=tokens,
        title=title,
        body=body,
        severity="info",
        data={
            "type": "support_ticket",
            "ticket_id": ticket.ticket_id,
            "status": ticket.status,
        },
    )


@router.post("/device-profile", response_model=DeviceProfileResponse)
async def upsert_device_profile(
    request: DeviceProfileRequest,
    session: SessionDep,
    _: ReadAccessDep,
) -> DeviceProfileResponse:
    record = await DeviceProfileRepository(session).upsert(
        user_id=request.user_id,
        device_id=request.device_id,
        display_name=request.display_name,
        platform=request.platform,
        app_version=request.app_version,
        build_number=request.build_number,
        locale=request.locale,
    )
    return DeviceProfileResponse(
        user_id=record.user_id,
        device_id=record.device_id,
        display_name=record.display_name,
        platform=record.platform,
        app_version=record.app_version,
        build_number=record.build_number,
        locale=record.locale,
        updated_at=record.updated_at,
        last_seen_at=record.last_seen_at,
    )


@router.post("/tickets", response_model=SupportTicketDetail, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    request: SupportTicketCreateRequest,
    session: SessionDep,
    _: ReadAccessDep,
) -> SupportTicketDetail:
    profile = await DeviceProfileRepository(session).upsert(
        user_id=request.user_id,
        device_id=request.device_id,
        display_name=request.display_name,
    )
    ticket = await SupportRepository(session).create_ticket(
        user_id=request.user_id,
        device_id=request.device_id,
        display_name_snapshot=profile.display_name or request.display_name,
        category=request.category,
        priority=request.priority,
        subject=request.subject,
        body=request.message,
        diagnostics=_sanitize_diagnostics(request.diagnostics),
    )
    return _ticket_detail(ticket)


@router.get("/tickets", response_model=SupportTicketListResponse)
async def list_user_tickets(
    session: SessionDep,
    _: ReadAccessDep,
    device_id: str = Query(min_length=1, max_length=128),
) -> SupportTicketListResponse:
    items = await SupportRepository(session).list_tickets(
        user_id=str(DEFAULT_SINGLE_USER_ID),
        device_id=device_id,
        admin=False,
    )
    summaries = [_ticket_summary(item) for item in items]
    return SupportTicketListResponse(items=summaries, total=len(summaries))


@router.get("/notifications", response_model=SupportNotificationResponse)
async def user_notifications(
    session: SessionDep,
    _: ReadAccessDep,
) -> SupportNotificationResponse:
    count, latest = await SupportRepository(session).unread_count(
        user_id=str(DEFAULT_SINGLE_USER_ID),
        viewer="user",
    )
    return _notification_response(count, latest)


@router.get("/tickets/{ticket_id}", response_model=SupportTicketDetail)
async def get_user_ticket(
    ticket_id: str,
    session: SessionDep,
    _: ReadAccessDep,
    device_id: str = Query(min_length=1, max_length=128),
) -> SupportTicketDetail:
    ticket = await SupportRepository(session).get_ticket(
        ticket_id,
        user_id=str(DEFAULT_SINGLE_USER_ID),
        device_id=device_id,
    )
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return _ticket_detail(ticket)


@router.post("/tickets/{ticket_id}/read", response_model=SupportTicketDetail)
async def mark_user_ticket_read(
    ticket_id: str,
    session: SessionDep,
    _: ReadAccessDep,
    device_id: str = Query(min_length=1, max_length=128),
) -> SupportTicketDetail:
    repo = SupportRepository(session)
    ticket = await repo.get_ticket(
        ticket_id,
        user_id=str(DEFAULT_SINGLE_USER_ID),
        device_id=device_id,
    )
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return _ticket_detail(await repo.mark_seen(ticket, viewer="user"))


@router.post("/tickets/read-all", response_model=SupportReadAllResponse)
async def mark_user_tickets_read(
    session: SessionDep,
    _: ReadAccessDep,
) -> SupportReadAllResponse:
    updated = await SupportRepository(session).mark_all_seen(
        user_id=str(DEFAULT_SINGLE_USER_ID),
        viewer="user",
    )
    return SupportReadAllResponse(updated=updated)


@router.post("/tickets/{ticket_id}/messages", response_model=SupportTicketDetail)
async def add_user_message(
    ticket_id: str,
    request: SupportMessageCreateRequest,
    session: SessionDep,
    _: ReadAccessDep,
) -> SupportTicketDetail:
    if not request.device_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="device_id is required")
    repo = SupportRepository(session)
    ticket = await repo.get_ticket(
        ticket_id,
        user_id=request.user_id,
        device_id=request.device_id,
    )
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    if ticket.status in CLOSED_STATUSES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ticket is closed")
    return _ticket_detail(
        await repo.add_message(
            ticket,
            sender_type="user",
            sender_id=request.device_id,
            body=request.message,
            diagnostics=_sanitize_diagnostics(request.diagnostics),
        )
    )


@router.post("/tickets/{ticket_id}/close", response_model=SupportTicketDetail)
async def close_user_ticket(
    ticket_id: str,
    request: SupportMessageCreateRequest,
    session: SessionDep,
    _: ReadAccessDep,
) -> SupportTicketDetail:
    if not request.device_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="device_id is required")
    repo = SupportRepository(session)
    ticket = await repo.get_ticket(ticket_id, user_id=request.user_id, device_id=request.device_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return _ticket_detail(await repo.set_status(ticket, status="closed", actor="user"))


@router.get("/admin/tickets", response_model=SupportTicketListResponse)
async def list_admin_tickets(
    session: SessionDep,
    _: AdminAccessDep,
    ticket_status: TicketStatus | None = None,
    include_archived: bool = False,
) -> SupportTicketListResponse:
    items = await SupportRepository(session).list_tickets(
        user_id=str(DEFAULT_SINGLE_USER_ID),
        admin=True,
        status=ticket_status,
        include_archived=include_archived,
    )
    summaries = [_ticket_summary(item, viewer="admin") for item in items]
    return SupportTicketListResponse(items=summaries, total=len(summaries))


@router.get("/admin/notifications", response_model=SupportNotificationResponse)
async def admin_notifications(
    session: SessionDep,
    _: AdminAccessDep,
) -> SupportNotificationResponse:
    count, latest = await SupportRepository(session).unread_count(
        user_id=str(DEFAULT_SINGLE_USER_ID),
        viewer="admin",
    )
    return _notification_response(count, latest, viewer="admin")


@router.get("/admin/tickets/{ticket_id}", response_model=SupportTicketDetail)
async def get_admin_ticket(
    ticket_id: str,
    session: SessionDep,
    _: AdminAccessDep,
) -> SupportTicketDetail:
    ticket = await SupportRepository(session).get_ticket(
        ticket_id,
        user_id=str(DEFAULT_SINGLE_USER_ID),
        admin=True,
    )
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return _ticket_detail(ticket, viewer="admin")


@router.post("/admin/tickets/{ticket_id}/read", response_model=SupportTicketDetail)
async def mark_admin_ticket_read(
    ticket_id: str,
    session: SessionDep,
    _: AdminAccessDep,
) -> SupportTicketDetail:
    repo = SupportRepository(session)
    ticket = await repo.get_ticket(
        ticket_id,
        user_id=str(DEFAULT_SINGLE_USER_ID),
        admin=True,
    )
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return _ticket_detail(await repo.mark_seen(ticket, viewer="admin"), viewer="admin")


@router.post("/admin/tickets/read-all", response_model=SupportReadAllResponse)
async def mark_admin_tickets_read(
    session: SessionDep,
    _: AdminAccessDep,
) -> SupportReadAllResponse:
    updated = await SupportRepository(session).mark_all_seen(
        user_id=str(DEFAULT_SINGLE_USER_ID),
        viewer="admin",
    )
    return SupportReadAllResponse(updated=updated)


@router.post("/admin/tickets/{ticket_id}/messages", response_model=SupportTicketDetail)
async def add_admin_message(
    ticket_id: str,
    request: SupportMessageCreateRequest,
    session: SessionDep,
    _: AdminAccessDep,
) -> SupportTicketDetail:
    repo = SupportRepository(session)
    ticket = await repo.get_ticket(ticket_id, user_id=str(DEFAULT_SINGLE_USER_ID), admin=True)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    if ticket.status in CLOSED_STATUSES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ticket is closed")
    updated = await repo.add_message(
        ticket,
        sender_type="admin",
        sender_id="admin",
        body=request.message,
    )
    await _notify_device(updated, title="Risposta supporto", body=updated.subject)
    return _ticket_detail(updated, viewer="admin")


@router.patch("/admin/tickets/{ticket_id}/status", response_model=SupportTicketDetail)
async def update_admin_ticket_status(
    ticket_id: str,
    request: SupportStatusUpdateRequest,
    session: SessionDep,
    _: AdminAccessDep,
) -> SupportTicketDetail:
    repo = SupportRepository(session)
    ticket = await repo.get_ticket(ticket_id, user_id=str(DEFAULT_SINGLE_USER_ID), admin=True)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    updated = await repo.set_status(ticket, status=request.status, actor="admin")
    if request.status in {"resolved", "closed"}:
        await _notify_device(updated, title="Ticket aggiornato", body=f"{updated.subject}: {updated.status}")
    return _ticket_detail(updated, viewer="admin")
