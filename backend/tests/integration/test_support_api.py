from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.dependencies import require_admin_access, require_read_access
from backend.app.api.routes import support
from backend.app.api.routes.support import router
from backend.app.persistence.database import close_db, get_session, init_db


@pytest_asyncio.fixture
async def support_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    await close_db()
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'support.db'}")

    async def _session_override():
        from backend.app.persistence.database import get_session_factory

        async with get_session_factory()() as session:
            yield session

    monkeypatch.setattr(
        support,
        "get_notification_service",
        lambda: SimpleNamespace(
            store=SimpleNamespace(tokens_for_device=lambda user_id, device_id: []),
            fcm=SimpleNamespace(send=lambda **kwargs: None),
        ),
    )

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[require_read_access] = lambda: None
    app.dependency_overrides[require_admin_access] = lambda: None
    yield app
    await close_db()


def test_support_ticket_thread_and_admin_status_flow(support_app: FastAPI) -> None:
    client = TestClient(support_app)

    created = client.post(
        "/api/v1/support/tickets",
        json={
            "device_id": "device-a",
            "display_name": "Marco S23",
            "category": "bug",
            "priority": "high",
            "subject": "Alert non arriva",
            "message": "Non ricevo push sugli alert.",
            "diagnostics": {
                "app_version": "1.0.0",
                "request_id": "req-1",
                "forbidden": "must-not-pass",
            },
        },
    )
    assert created.status_code == 201
    ticket = created.json()
    ticket_id = ticket["ticket_id"]
    assert ticket["display_name"] == "Marco S23"
    assert ticket["messages"][0]["diagnostics"] == {"app_version": "1.0.0", "request_id": "req-1"}

    admin_notice = client.get("/api/v1/support/admin/notifications")
    assert admin_notice.status_code == 200
    assert admin_notice.json()["unread_count"] == 1

    marked_admin = client.post(f"/api/v1/support/admin/tickets/{ticket_id}/read")
    assert marked_admin.status_code == 200

    admin_notice_after_read = client.get("/api/v1/support/admin/notifications")
    assert admin_notice_after_read.status_code == 200
    assert admin_notice_after_read.json()["unread_count"] == 0

    listed = client.get("/api/v1/support/tickets", params={"device_id": "device-a"})
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    user_reply = client.post(
        f"/api/v1/support/tickets/{ticket_id}/messages",
        json={"device_id": "device-a", "message": "Aggiungo dettaglio."},
    )
    assert user_reply.status_code == 200
    assert len(user_reply.json()["messages"]) == 2

    admin_reply = client.post(
        f"/api/v1/support/admin/tickets/{ticket_id}/messages",
        json={"message": "Controllo i log."},
    )
    assert admin_reply.status_code == 200
    assert admin_reply.json()["status"] == "in_progress"
    assert len(admin_reply.json()["messages"]) == 3

    user_notice = client.get("/api/v1/support/notifications")
    assert user_notice.status_code == 200
    assert user_notice.json()["unread_count"] == 1
    assert user_notice.json()["latest_ticket"]["ticket_id"] == ticket_id

    marked_user = client.post(f"/api/v1/support/tickets/{ticket_id}/read", params={"device_id": "device-a"})
    assert marked_user.status_code == 200

    user_notice_after_read = client.get("/api/v1/support/notifications")
    assert user_notice_after_read.status_code == 200
    assert user_notice_after_read.json()["unread_count"] == 0

    second_admin_reply = client.post(
        f"/api/v1/support/admin/tickets/{ticket_id}/messages",
        json={"message": "Seconda risposta."},
    )
    assert second_admin_reply.status_code == 200
    assert client.get("/api/v1/support/notifications").json()["unread_count"] == 1

    marked_user_all = client.post("/api/v1/support/tickets/read-all")
    assert marked_user_all.status_code == 200
    assert marked_user_all.json()["updated"] == 1
    assert client.get("/api/v1/support/notifications").json()["unread_count"] == 0

    still_visible_to_user = client.get("/api/v1/support/tickets", params={"device_id": "device-b"})
    assert still_visible_to_user.status_code == 200
    assert still_visible_to_user.json()["total"] == 1

    visible_detail = client.get(f"/api/v1/support/tickets/{ticket_id}", params={"device_id": "device-b"})
    assert visible_detail.status_code == 200
    assert len(visible_detail.json()["messages"]) == 4

    user_reply_from_current_device = client.post(
        f"/api/v1/support/tickets/{ticket_id}/messages",
        json={"device_id": "device-b", "message": "Ora lo vedo di nuovo."},
    )
    assert user_reply_from_current_device.status_code == 200
    assert len(user_reply_from_current_device.json()["messages"]) == 5
    assert client.get("/api/v1/support/admin/notifications").json()["unread_count"] == 2

    marked_admin_all = client.post("/api/v1/support/admin/tickets/read-all")
    assert marked_admin_all.status_code == 200
    assert marked_admin_all.json()["updated"] == 1
    assert client.get("/api/v1/support/admin/notifications").json()["unread_count"] == 0

    resolved = client.patch(
        f"/api/v1/support/admin/tickets/{ticket_id}/status",
        json={"status": "resolved"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"

    closed = client.post(
        f"/api/v1/support/tickets/{ticket_id}/close",
        json={"device_id": "device-b", "message": "Chiuso"},
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert closed.json()["closed_by"] == "user"

    blocked = client.post(
        f"/api/v1/support/tickets/{ticket_id}/messages",
        json={"device_id": "device-b", "message": "Non dovrebbe passare."},
    )
    assert blocked.status_code == 409

    archived = client.patch(
        f"/api/v1/support/admin/tickets/{ticket_id}/status",
        json={"status": "archived"},
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    hidden_from_user = client.get("/api/v1/support/tickets", params={"device_id": "device-b"})
    assert hidden_from_user.status_code == 200
    assert hidden_from_user.json()["total"] == 0

    hidden_from_default_admin = client.get("/api/v1/support/admin/tickets")
    assert hidden_from_default_admin.status_code == 200
    assert hidden_from_default_admin.json()["total"] == 0

    visible_in_archive = client.get("/api/v1/support/admin/tickets", params={"ticket_status": "archived"})
    assert visible_in_archive.status_code == 200
    assert visible_in_archive.json()["total"] == 1
