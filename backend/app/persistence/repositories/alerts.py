"""Repository for alert configuration and checker state."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.persistence.models.alerts import AlertConfig


class AlertConfigRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(
        self,
        user_id: str,
        config: dict | None,
        state: dict,
    ) -> AlertConfig:
        result = await self._session.execute(
            select(AlertConfig).where(AlertConfig.user_id == user_id)
        )
        record = result.scalar_one_or_none()
        now = datetime.now(UTC)
        if record is None:
            record = AlertConfig(
                user_id=user_id,
                config_json=json.dumps(config) if config is not None else None,
                state_json=json.dumps(state),
                updated_at=now,
            )
            self._session.add(record)
        else:
            record.config_json = json.dumps(config) if config is not None else None
            record.state_json = json.dumps(state)
            record.updated_at = now
        await self._session.commit()
        await self._session.refresh(record)
        return record

    async def load(self, user_id: str) -> tuple[dict | None, dict]:
        """Return (config_dict | None, state_dict)."""
        result = await self._session.execute(
            select(AlertConfig).where(AlertConfig.user_id == user_id)
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None, {}
        config = json.loads(record.config_json) if record.config_json else None
        state = json.loads(record.state_json) if record.state_json else {}
        return config, state
