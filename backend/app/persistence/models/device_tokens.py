"""ORM model for FCM device token registry."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DeviceToken(Base):
    __tablename__ = "device_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(512), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, default="android")
    device_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    locale: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
