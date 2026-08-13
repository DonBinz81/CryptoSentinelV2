"""ORM model for alert configuration and checker state."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AlertConfig(Base):
    """Stores the latest alert configuration synced from the app per user.

    config_json and state_json store the full Pydantic-serialized payloads so
    the schema can evolve without migration.
    """

    __tablename__ = "alert_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    state_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
