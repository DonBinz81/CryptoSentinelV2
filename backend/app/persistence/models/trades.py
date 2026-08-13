"""ORM models for spot and perpetual trade records."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

PRICE_NUMERIC = Numeric(30, 18)


class SpotTrade(Base):
    """One completed or attempted spot swap execution."""

    __tablename__ = "spot_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    asset: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)  # buy / sell
    amount: Mapped[Decimal] = mapped_column(Numeric(30, 18), nullable=False)
    price: Mapped[Decimal] = mapped_column(PRICE_NUMERIC, nullable=False)
    amount_quote: Mapped[Decimal] = mapped_column(Numeric(30, 8), nullable=False)
    tx_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="prepared")
    gas_cost_wei: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gas_cost_bnb: Mapped[Decimal | None] = mapped_column(Numeric(30, 18), nullable=True)
    slippage_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    fees_quote: Mapped[Decimal | None] = mapped_column(Numeric(30, 8), nullable=True)
    fee_mode: Mapped[str | None] = mapped_column(String(8), nullable=True)           # all|none
    swap_fee_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    slippage_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    block_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    block_timestamp_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signal_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    pnl_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)


class PerpTrade(Base):
    """One perpetual trade execution (open or close leg)."""

    __tablename__ = "perp_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    asset: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)  # long / short
    direction: Mapped[str] = mapped_column(String(8), nullable=False)  # open / close
    size: Mapped[Decimal] = mapped_column(Numeric(30, 18), nullable=False)
    price: Mapped[Decimal] = mapped_column(PRICE_NUMERIC, nullable=False)
    leverage: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    tx_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="prepared")
    gas_cost_wei: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gas_cost_bnb: Mapped[Decimal | None] = mapped_column(Numeric(30, 18), nullable=True)
    slippage_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    fees_quote: Mapped[Decimal | None] = mapped_column(Numeric(30, 8), nullable=True)
    fee_mode: Mapped[str | None] = mapped_column(String(8), nullable=True)           # taker|maker|none
    taker_fee_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    maker_fee_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    slippage_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    funding_rate_8h: Mapped[Decimal | None] = mapped_column(Numeric(20, 10), nullable=True)
    block_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    block_timestamp_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    venue: Mapped[str | None] = mapped_column(String(64), nullable=True)
    signal_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    pnl_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
