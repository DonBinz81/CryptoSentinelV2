"""Repository for FCM device token records."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.persistence.models.device_tokens import DeviceToken


class DeviceTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        token_id: str,
        token: str,
        user_id: str,
        platform: str = "android",
        device_id: str | None = None,
        app_version: str | None = None,
        locale: str | None = None,
    ) -> DeviceToken:
        now = datetime.now(UTC)
        result = await self._session.execute(
            select(DeviceToken).where(DeviceToken.token_id == token_id)
        )
        record = result.scalar_one_or_none()
        if record is None:
            record = DeviceToken(
                token_id=token_id,
                token=token,
                user_id=user_id,
                platform=platform,
                device_id=device_id,
                app_version=app_version,
                locale=locale,
                created_at=now,
                updated_at=now,
            )
            self._session.add(record)
        else:
            record.token = token
            record.user_id = user_id
            record.platform = platform
            record.device_id = device_id
            record.app_version = app_version
            record.locale = locale
            record.updated_at = now
        await self._session.commit()
        await self._session.refresh(record)
        return record

    async def remove(self, token_id: str, user_id: str) -> bool:
        result = await self._session.execute(
            delete(DeviceToken)
            .where(DeviceToken.token_id == token_id)
            .where(DeviceToken.user_id == user_id)
        )
        await self._session.commit()
        return result.rowcount > 0

    async def tokens_for_user(self, user_id: str) -> list[str]:
        result = await self._session.execute(
            select(DeviceToken.token).where(DeviceToken.user_id == user_id)
        )
        return list(result.scalars().all())

    async def count(self) -> int:
        result = await self._session.execute(select(DeviceToken))
        return len(result.scalars().all())

    async def all_records(self) -> list[DeviceToken]:
        result = await self._session.execute(select(DeviceToken))
        return list(result.scalars().all())
