"""ORM model for agent decision log."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AgentDecision(Base):
    """Records every LLM meta-controller decision for auditability and replay."""

    __tablename__ = "agent_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    decision_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    asset: Mapped[str | None] = mapped_column(String(32), nullable=True)
    market: Mapped[str] = mapped_column(String(8), nullable=False, default="spot")  # spot / perp
    signal_quality: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    action: Mapped[str] = mapped_column(String(16), nullable=False)  # enter / skip / reduce / block
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_result: Mapped[str | None] = mapped_column(String(16), nullable=True)
    trade_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
