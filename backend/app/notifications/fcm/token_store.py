"""DB-backed FCM device token registry.

Source of truth is the ``device_tokens`` table.  The legacy JSON file is
migrated into the DB at startup and is no longer read in normal operation.
The public interface is unchanged so callers (NotificationService, price
checker) are unaffected.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from uuid import UUID

from sqlalchemy import delete, select

from backend.app.domain.common.models import DEFAULT_SINGLE_USER_ID
from backend.app.persistence.models.device_profiles import DeviceProfile
from backend.app.persistence.models.device_tokens import DeviceToken
from backend.app.persistence.sync_database import get_sync_session


@dataclass
class DeviceTokenRecord:
    """Stored FCM device token record (returned to callers)."""

    token_id: str
    token: str
    user_id: str
    platform: str
    device_id: str | None
    app_version: str | None
    locale: str | None
    display_name: str | None
    created_at: str
    updated_at: str


def _profile_for(session, *, user_id: str, device_id: str | None) -> DeviceProfile | None:
    if not device_id:
        return None
    return session.execute(
        select(DeviceProfile)
        .where(DeviceProfile.user_id == user_id)
        .where(DeviceProfile.device_id == device_id)
    ).scalar_one_or_none()


def _to_record(row: DeviceToken, profile: DeviceProfile | None = None) -> DeviceTokenRecord:
    return DeviceTokenRecord(
        token_id=row.token_id,
        token=row.token,
        user_id=row.user_id,
        platform=row.platform,
        device_id=row.device_id,
        app_version=row.app_version,
        locale=row.locale,
        display_name=profile.display_name if profile else None,
        created_at=row.created_at.isoformat() if row.created_at else "",
        updated_at=row.updated_at.isoformat() if row.updated_at else "",
    )


class DeviceTokenStore:
    """Database-backed token registry.

    The ``path`` argument is accepted for backward compatibility but is no
    longer used as a data source; the DB is authoritative.
    """

    def __init__(self, path: str | None = None) -> None:
        self.path = path
        self._lock = Lock()

    @staticmethod
    def token_id_for(token: str) -> str:
        """Return a stable non-secret identifier for a token."""

        return hashlib.sha256(token.encode("utf-8")).hexdigest()[:24]

    def register(
        self,
        token: str,
        user_id: UUID = DEFAULT_SINGLE_USER_ID,
        platform: str = "android",
        device_id: str | None = None,
        app_version: str | None = None,
        build_number: str | None = None,
        locale: str | None = None,
        display_name: str | None = None,
    ) -> DeviceTokenRecord:
        """Add or update a device token."""

        now = datetime.now(UTC)
        token_id = self.token_id_for(token)
        with self._lock, get_sync_session() as session:
            row = session.execute(
                select(DeviceToken).where(DeviceToken.token_id == token_id)
            ).scalar_one_or_none()
            if row is None:
                row = DeviceToken(
                    token_id=token_id,
                    token=token,
                    user_id=str(user_id),
                    platform=platform,
                    device_id=device_id,
                    app_version=app_version,
                    locale=locale,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.token = token
                row.user_id = str(user_id)
                row.platform = platform
                row.device_id = device_id
                row.app_version = app_version
                row.locale = locale
                row.updated_at = now
            profile = None
            if device_id:
                profile = _profile_for(session, user_id=str(user_id), device_id=device_id)
                normalized_name = display_name.strip() if display_name else None
                if profile is None:
                    profile = DeviceProfile(
                        user_id=str(user_id),
                        device_id=device_id,
                        display_name=normalized_name or None,
                        platform=platform,
                        app_version=app_version,
                        build_number=build_number,
                        locale=locale,
                        created_at=now,
                        updated_at=now,
                        last_seen_at=now,
                    )
                    session.add(profile)
                else:
                    if normalized_name is not None:
                        profile.display_name = normalized_name or None
                    profile.platform = platform or profile.platform
                    profile.app_version = app_version or profile.app_version
                    profile.build_number = build_number or profile.build_number
                    profile.locale = locale or profile.locale
                    profile.updated_at = now
                    profile.last_seen_at = now
            session.commit()
            session.refresh(row)
            if profile is not None:
                session.refresh(profile)
            return _to_record(row, profile)

    def remove(self, token: str, user_id: UUID = DEFAULT_SINGLE_USER_ID) -> str:
        """Remove a device token and return its token id."""

        token_id = self.token_id_for(token)
        with self._lock, get_sync_session() as session:
            session.execute(
                delete(DeviceToken)
                .where(DeviceToken.token_id == token_id)
                .where(DeviceToken.user_id == str(user_id))
            )
            session.commit()
            return token_id

    def tokens_for_user(self, user_id: UUID, token_ids: list[str] | None = None) -> list[str]:
        """Return raw FCM tokens for a user, optionally filtered by token id."""

        allowed = set(token_ids) if token_ids else None
        with get_sync_session() as session:
            stmt = select(DeviceToken).where(DeviceToken.user_id == str(user_id))
            rows = session.execute(stmt).scalars().all()
            return [
                row.token
                for row in rows
                if allowed is None or row.token_id in allowed
            ]

    def tokens_with_device(
        self, user_id: UUID = DEFAULT_SINGLE_USER_ID
    ) -> list[tuple[str, str | None]]:
        """Return ``(raw_token, device_id)`` pairs for a user.

        Used by the price checker to deliver each device only its own alerts.
        The raw token stays inside the backend and is never exposed via API.
        """

        with get_sync_session() as session:
            rows = session.execute(
                select(DeviceToken).where(DeviceToken.user_id == str(user_id))
            ).scalars().all()
            return [(row.token, row.device_id) for row in rows]

    def tokens_for_device(self, user_id: str, device_id: str | None) -> list[str]:
        """Return raw tokens for one user device id."""

        if not device_id:
            return []
        with get_sync_session() as session:
            rows = session.execute(
                select(DeviceToken)
                .where(DeviceToken.user_id == str(user_id))
                .where(DeviceToken.device_id == device_id)
            ).scalars().all()
            return [row.token for row in rows]

    def count(self) -> int:
        """Return registered token count."""

        with get_sync_session() as session:
            return len(session.execute(select(DeviceToken.id)).scalars().all())

    def list_all(self, user_id: UUID = DEFAULT_SINGLE_USER_ID) -> list[DeviceTokenRecord]:
        """Return all registered device records for a user."""

        with get_sync_session() as session:
            rows = session.execute(
                select(DeviceToken).where(DeviceToken.user_id == str(user_id))
            ).scalars().all()
            return [
                _to_record(row, _profile_for(session, user_id=row.user_id, device_id=row.device_id))
                for row in rows
            ]
