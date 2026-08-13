"""Schemas for in-app support tickets."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from backend.app.domain.common.models import DEFAULT_SINGLE_USER_ID

TicketCategory = Literal["bug", "alert", "market", "agent", "wallet", "other"]
TicketPriority = Literal["low", "medium", "high", "critical"]
TicketStatus = Literal["open", "in_progress", "waiting_user", "resolved", "closed", "archived"]
SenderType = Literal["user", "admin"]


class DeviceProfileRequest(BaseModel):
    user_id: str = str(DEFAULT_SINGLE_USER_ID)
    device_id: str = Field(min_length=1, max_length=128)
    display_name: str | None = Field(default=None, max_length=120)
    platform: str | None = Field(default=None, max_length=32)
    app_version: str | None = Field(default=None, max_length=32)
    build_number: str | None = Field(default=None, max_length=32)
    locale: str | None = Field(default=None, max_length=16)


class DeviceProfileResponse(BaseModel):
    user_id: str
    device_id: str
    display_name: str | None
    platform: str | None
    app_version: str | None
    build_number: str | None
    locale: str | None
    updated_at: datetime
    last_seen_at: datetime


class SupportTicketCreateRequest(BaseModel):
    user_id: str = str(DEFAULT_SINGLE_USER_ID)
    device_id: str = Field(min_length=1, max_length=128)
    display_name: str | None = Field(default=None, max_length=120)
    category: TicketCategory = "other"
    priority: TicketPriority = "medium"
    subject: str = Field(min_length=1, max_length=160)
    message: str = Field(min_length=1, max_length=4000)
    diagnostics: dict | None = None


class SupportMessageCreateRequest(BaseModel):
    user_id: str = str(DEFAULT_SINGLE_USER_ID)
    device_id: str | None = Field(default=None, max_length=128)
    message: str = Field(min_length=1, max_length=4000)
    diagnostics: dict | None = None


class SupportStatusUpdateRequest(BaseModel):
    status: TicketStatus


class SupportMessageResponse(BaseModel):
    message_id: str
    ticket_id: str
    sender_type: SenderType
    sender_id: str | None
    body: str
    diagnostics: dict | None
    created_at: datetime


class SupportTicketSummary(BaseModel):
    ticket_id: str
    user_id: str
    device_id: str | None
    display_name: str
    category: TicketCategory
    priority: TicketPriority
    status: TicketStatus
    subject: str
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime
    resolved_at: datetime | None
    closed_at: datetime | None
    closed_by: str | None
    message_count: int = 0
    has_unread: bool = False


class SupportTicketDetail(SupportTicketSummary):
    messages: list[SupportMessageResponse]
    last_seen_at: datetime | None = None


class SupportTicketListResponse(BaseModel):
    items: list[SupportTicketSummary]
    total: int


class SupportNotificationResponse(BaseModel):
    unread_count: int
    latest_ticket: SupportTicketSummary | None = None


class SupportReadAllResponse(BaseModel):
    updated: int
