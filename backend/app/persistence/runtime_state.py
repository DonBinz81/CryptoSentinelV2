"""Synchronous helpers to read/write persisted runtime state.

Used by the market-data registry to persist the globally selected provider so
the choice survives a restart while Settings remain the boot default.  All
operations degrade silently if the sync DB is not initialised (e.g. in tests
that do not need persistence).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from backend.app.persistence.models.runtime_state import RuntimeState
from backend.app.persistence.sync_database import get_sync_session


def get_runtime_value(user_id: str, key: str) -> str | None:
    try:
        with get_sync_session() as session:
            row = session.execute(
                select(RuntimeState)
                .where(RuntimeState.user_id == user_id)
                .where(RuntimeState.key == key)
            ).scalar_one_or_none()
            return row.value if row else None
    except Exception:
        return None


def set_runtime_value(user_id: str, key: str, value: str) -> None:
    try:
        now = datetime.now(UTC)
        with get_sync_session() as session:
            row = session.execute(
                select(RuntimeState)
                .where(RuntimeState.user_id == user_id)
                .where(RuntimeState.key == key)
            ).scalar_one_or_none()
            if row is None:
                row = RuntimeState(user_id=user_id, key=key, value=value, updated_at=now)
                session.add(row)
            else:
                row.value = value
                row.updated_at = now
            session.commit()
    except Exception:
        pass
