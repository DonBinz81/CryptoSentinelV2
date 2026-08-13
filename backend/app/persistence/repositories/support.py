"""Repository for support tickets and message threads."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.persistence.models.support import SupportMessage, SupportTicket


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:20]}"


class SupportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_ticket(
        self,
        *,
        user_id: str,
        device_id: str,
        display_name_snapshot: str | None,
        category: str,
        priority: str,
        subject: str,
        body: str,
        diagnostics: dict | None = None,
    ) -> SupportTicket:
        now = datetime.now(UTC)
        ticket = SupportTicket(
            ticket_id=_id("st"),
            user_id=user_id,
            device_id=device_id,
            display_name_snapshot=display_name_snapshot,
            category=category,
            priority=priority,
            status="open",
            subject=subject,
            created_at=now,
            updated_at=now,
            last_message_at=now,
            user_last_seen_at=now,
            admin_last_seen_at=None,
        )
        message = SupportMessage(
            message_id=_id("sm"),
            ticket_id=ticket.ticket_id,
            user_id=user_id,
            device_id=device_id,
            sender_type="user",
            sender_id=device_id,
            body=body,
            diagnostics_json=diagnostics,
            created_at=now,
        )
        self._session.add(ticket)
        self._session.add(message)
        await self._session.commit()
        return await self.get_ticket(ticket.ticket_id, user_id=user_id, device_id=device_id, admin=True)  # type: ignore[return-value]

    async def list_tickets(
        self,
        *,
        user_id: str,
        device_id: str | None = None,
        admin: bool = False,
        status: str | None = None,
        include_archived: bool = False,
    ) -> list[SupportTicket]:
        stmt = (
            select(SupportTicket)
            .options(selectinload(SupportTicket.messages))
            .order_by(SupportTicket.last_message_at.desc())
        )
        if not admin:
            stmt = stmt.where(SupportTicket.user_id == user_id)
            stmt = stmt.where(SupportTicket.status != "archived")
        elif status:
            stmt = stmt.where(SupportTicket.status == status)
        elif not include_archived:
            stmt = stmt.where(SupportTicket.status != "archived")
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_ticket(
        self,
        ticket_id: str,
        *,
        user_id: str,
        device_id: str | None = None,
        admin: bool = False,
    ) -> SupportTicket | None:
        stmt = (
            select(SupportTicket)
            .options(selectinload(SupportTicket.messages))
            .where(SupportTicket.ticket_id == ticket_id)
        )
        if not admin:
            stmt = stmt.where(SupportTicket.user_id == user_id)
            stmt = stmt.where(SupportTicket.status != "archived")
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_message(
        self,
        ticket: SupportTicket,
        *,
        sender_type: str,
        sender_id: str | None,
        body: str,
        diagnostics: dict | None = None,
    ) -> SupportTicket:
        now = datetime.now(UTC)
        message = SupportMessage(
            message_id=_id("sm"),
            ticket_id=ticket.ticket_id,
            user_id=ticket.user_id,
            device_id=ticket.device_id,
            sender_type=sender_type,
            sender_id=sender_id,
            body=body,
            diagnostics_json=diagnostics,
            created_at=now,
        )
        ticket.last_message_at = now
        ticket.updated_at = now
        if sender_type == "admin" and ticket.status == "open":
            ticket.status = "in_progress"
        elif sender_type == "user" and ticket.status in {"resolved", "waiting_user"}:
            ticket.status = "open"
            ticket.resolved_at = None
            ticket.closed_at = None
            ticket.closed_by = None
        self._session.add(ticket)
        self._session.add(message)
        await self._session.commit()
        self._session.expire(ticket, ["messages"])
        return await self.get_ticket(ticket.ticket_id, user_id=ticket.user_id, device_id=ticket.device_id, admin=True)  # type: ignore[return-value]

    async def mark_seen(
        self,
        ticket: SupportTicket,
        *,
        viewer: str,
    ) -> SupportTicket:
        now = datetime.now(UTC)
        if viewer == "admin":
            ticket.admin_last_seen_at = now
        else:
            ticket.user_last_seen_at = now
        self._session.add(ticket)
        await self._session.commit()
        return await self.get_ticket(ticket.ticket_id, user_id=ticket.user_id, device_id=ticket.device_id, admin=True)  # type: ignore[return-value]

    async def mark_all_seen(
        self,
        *,
        user_id: str,
        viewer: str,
    ) -> int:
        now = datetime.now(UTC)
        tickets = await self.list_tickets(user_id=user_id, admin=(viewer == "admin"))
        for ticket in tickets:
            if viewer == "admin":
                ticket.admin_last_seen_at = now
            else:
                ticket.user_last_seen_at = now
            self._session.add(ticket)
        await self._session.commit()
        return len(tickets)

    async def unread_count(
        self,
        *,
        user_id: str,
        viewer: str,
    ) -> tuple[int, SupportTicket | None]:
        seen_col = SupportTicket.admin_last_seen_at if viewer == "admin" else SupportTicket.user_last_seen_at
        sender = "user" if viewer == "admin" else "admin"
        stmt = (
            select(func.count(SupportMessage.id))
            .join(SupportTicket, SupportTicket.ticket_id == SupportMessage.ticket_id)
            .where(SupportTicket.user_id == user_id)
            .where(SupportTicket.status != "archived")
            .where(SupportMessage.sender_type == sender)
            .where(or_(seen_col.is_(None), SupportMessage.created_at > seen_col))
        )
        count = int((await self._session.execute(stmt)).scalar_one() or 0)
        if count <= 0:
            return 0, None
        latest_stmt = (
            select(SupportTicket)
            .options(selectinload(SupportTicket.messages))
            .join(SupportMessage, SupportTicket.ticket_id == SupportMessage.ticket_id)
            .where(SupportTicket.user_id == user_id)
            .where(SupportTicket.status != "archived")
            .where(SupportMessage.sender_type == sender)
            .where(or_(seen_col.is_(None), SupportMessage.created_at > seen_col))
            .order_by(SupportMessage.created_at.desc())
            .limit(1)
        )
        latest = (await self._session.execute(latest_stmt)).scalar_one_or_none()
        return count, latest

    async def set_status(
        self,
        ticket: SupportTicket,
        *,
        status: str,
        actor: str,
    ) -> SupportTicket:
        now = datetime.now(UTC)
        ticket.status = status
        ticket.updated_at = now
        if status == "resolved":
            ticket.resolved_at = now
            ticket.closed_at = None
            ticket.closed_by = None
        elif status in {"closed", "archived"}:
            ticket.closed_at = now
            ticket.closed_by = actor
        elif status in {"open", "in_progress", "waiting_user"}:
            ticket.closed_at = None
            ticket.closed_by = None
            if status != "resolved":
                ticket.resolved_at = None
        self._session.add(ticket)
        await self._session.commit()
        return await self.get_ticket(ticket.ticket_id, user_id=ticket.user_id, device_id=ticket.device_id, admin=True)  # type: ignore[return-value]
