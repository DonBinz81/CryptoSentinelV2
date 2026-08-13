"""Repository for user-facing device profile metadata."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.persistence.models.device_profiles import DeviceProfile


class DeviceProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        *,
        user_id: str,
        device_id: str,
        display_name: str | None = None,
        platform: str | None = None,
        app_version: str | None = None,
        build_number: str | None = None,
        locale: str | None = None,
    ) -> DeviceProfile:
        now = datetime.now(UTC)
        result = await self._session.execute(
            select(DeviceProfile)
            .where(DeviceProfile.user_id == user_id)
            .where(DeviceProfile.device_id == device_id)
        )
        record = result.scalar_one_or_none()
        normalized_name = display_name.strip() if display_name else None
        if record is None:
            record = DeviceProfile(
                user_id=user_id,
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
            self._session.add(record)
        else:
            if normalized_name is not None:
                record.display_name = normalized_name or None
            record.platform = platform or record.platform
            record.app_version = app_version or record.app_version
            record.build_number = build_number or record.build_number
            record.locale = locale or record.locale
            record.updated_at = now
            record.last_seen_at = now
        await self._session.commit()
        await self._session.refresh(record)
        return record

    async def get(self, *, user_id: str, device_id: str) -> DeviceProfile | None:
        result = await self._session.execute(
            select(DeviceProfile)
            .where(DeviceProfile.user_id == user_id)
            .where(DeviceProfile.device_id == device_id)
        )
        return result.scalar_one_or_none()
