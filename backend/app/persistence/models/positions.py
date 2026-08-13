"""ORM models for open spot and perpetual positions."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

PRICE_NUMERIC = Numeric(30, 18)


class SpotPosition(Base):
    """Active spot holding with live stop/TP levels."""

    __tablename__ = "spot_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    position_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    asset: Mapped[str] = mapped_column(String(32), nullable=False)
    size: Mapped[Decimal] = mapped_column(Numeric(30, 18), nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(PRICE_NUMERIC, nullable=False)
    current_price: Mapped[Decimal] = mapped_column(PRICE_NUMERIC, nullable=False)
    pnl_unrealized: Mapped[Decimal] = mapped_column(Numeric(30, 8), nullable=False, default=Decimal("0"))
    stop_loss: Mapped[Decimal | None] = mapped_column(PRICE_NUMERIC, nullable=True)
    initial_stop_loss: Mapped[Decimal | None] = mapped_column(PRICE_NUMERIC, nullable=True)  # SL originale, mai sovrascritto
    take_profit_1: Mapped[Decimal | None] = mapped_column(PRICE_NUMERIC, nullable=True)
    take_profit_2: Mapped[Decimal | None] = mapped_column(PRICE_NUMERIC, nullable=True)
    trailing_stop: Mapped[Decimal | None] = mapped_column(PRICE_NUMERIC, nullable=True)
    # ── Gestione uscite v3 (ATR-based) ────────────────────────────────────────
    entry_atr: Mapped[Decimal | None] = mapped_column(PRICE_NUMERIC, nullable=True)   # ATR congelato all'ingresso
    stop_reference_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stop_reference_price: Mapped[Decimal | None] = mapped_column(PRICE_NUMERIC, nullable=True)
    stop_reference_field: Mapped[str | None] = mapped_column(String(8), nullable=True)
    max_price: Mapped[Decimal | None] = mapped_column(PRICE_NUMERIC, nullable=True)   # massimo dall'ingresso (per trailing)
    scale_in_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)    # n. aggiunte a favore (E)
    # ── Costi posizione (fee + slippage, solo dry-run) ────────────────────────
    fee_mode: Mapped[str | None] = mapped_column(String(8), nullable=True)          # all|none
    swap_fee_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    slippage_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    tp1_reached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")  # open / closed
    open_trade_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PerpPosition(Base):
    """Active perpetual position with leverage, liquidation price and TP schema."""

    __tablename__ = "perp_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    position_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    asset: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)  # long / short
    size: Mapped[Decimal] = mapped_column(Numeric(30, 18), nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(PRICE_NUMERIC, nullable=False)
    current_price: Mapped[Decimal] = mapped_column(PRICE_NUMERIC, nullable=False)
    leverage: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    pnl_unrealized: Mapped[Decimal] = mapped_column(Numeric(30, 8), nullable=False, default=Decimal("0"))
    stop_loss: Mapped[Decimal | None] = mapped_column(PRICE_NUMERIC, nullable=True)
    initial_stop_loss: Mapped[Decimal | None] = mapped_column(PRICE_NUMERIC, nullable=True)  # SL originale, mai sovrascritto
    take_profit_1: Mapped[Decimal | None] = mapped_column(PRICE_NUMERIC, nullable=True)  # bordo value area (50%)
    take_profit_2: Mapped[Decimal | None] = mapped_column(PRICE_NUMERIC, nullable=True)  # POC (25%)
    trailing_stop: Mapped[Decimal | None] = mapped_column(PRICE_NUMERIC, nullable=True)  # null finché non attivo
    # ── Protezione posizione (breakeven + trailing dinamico ATR) ──────────────
    entry_atr: Mapped[Decimal | None] = mapped_column(PRICE_NUMERIC, nullable=True)   # ATR congelato all'ingresso
    stop_reference_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stop_reference_price: Mapped[Decimal | None] = mapped_column(PRICE_NUMERIC, nullable=True)
    stop_reference_field: Mapped[str | None] = mapped_column(String(8), nullable=True)
    max_price: Mapped[Decimal | None] = mapped_column(PRICE_NUMERIC, nullable=True)   # estremo favorevole dall'ingresso
    liquidation_price: Mapped[Decimal | None] = mapped_column(PRICE_NUMERIC, nullable=True)
    funding_rate: Mapped[Decimal | None] = mapped_column(Numeric(20, 10), nullable=True)
    # ── Costi posizione (fee + slippage + funding) ────────────────────────────
    fee_mode: Mapped[str | None] = mapped_column(String(8), nullable=True)          # taker|maker|none
    margin_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    opening_fee_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)   # costo effettivo applicato
    taker_fee_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)     # sempre calcolato (confronto)
    maker_fee_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)     # sempre calcolato (confronto)
    slippage_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)      # solo taker
    funding_accrued_usd: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False, default=Decimal("0"))
    smart_sl_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    tp1_reached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")  # open / closed
    venue: Mapped[str | None] = mapped_column(String(64), nullable=True)
    open_trade_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
