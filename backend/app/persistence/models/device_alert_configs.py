"""ORM model for per-device alert configuration and checker state.

Separates alert configuration by device so each phone receives only the alerts
it configured. Logical key is ``(user_id, device_id)``. The legacy single-row
``AlertConfig`` table is kept for backward compatibility (tokens without a
device_id), so this is an additive change with no destructive migration.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DeviceAlertConfig(Base):
    """Latest alert configuration synced from one device, with checker state.

    config_json and state_json store the full Pydantic-serialized payloads so
    the schema can evolve without migration.
    """

    __tablename__ = "device_alert_configs"
    __table_args__ = (
        UniqueConstraint("user_id", "device_id", name="uq_device_alert_user_device"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    state_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
