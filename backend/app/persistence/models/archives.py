"""Archived dry-run data snapshots."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ArchivedRun(Base):
    """JSON snapshot of dry-run records removed from live views."""

    __tablename__ = "archived_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    archive_label: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    archived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
