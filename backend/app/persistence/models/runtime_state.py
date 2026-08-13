"""ORM model for persisted runtime state (e.g. active market-data provider)."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class RuntimeState(Base):
    """Per-user key/value store for runtime selections that must survive restart.

    Settings remain the boot default; a row here overrides the default once the
    user makes an explicit runtime selection (e.g. the global market-data
    provider).
    """

    __tablename__ = "runtime_state"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_runtime_user_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str] = mapped_column(String(256), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
