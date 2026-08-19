"""Async SQLAlchemy engine, session factory and DB health helpers."""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.persistence.models import Base

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None

logger = structlog.get_logger("persistence.database")


async def init_db(database_url: str, *, echo: bool = False) -> None:
    """Create tables and initialise the session factory.

    Safe to call multiple times — subsequent calls are no-ops if the engine is
    already set up.
    """
    global _engine, _session_factory
    if _engine is not None:
        return

    _engine = create_async_engine(database_url, echo=echo, future=True)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)

    async with _engine.begin() as conn:
        # WAL mode: allows concurrent reads alongside writes, prevents "database is locked"
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA busy_timeout=5000"))
        await conn.run_sync(Base.metadata.create_all)
        await _apply_column_migrations(conn)

    logger.info("database_initialised", url=_redact_url(database_url))


async def _apply_column_migrations(conn) -> None:
    """ADD COLUMN migrations for existing tables — idempotent (errors silently ignored)."""
    new_columns = [
        ("spot_trades", "pnl_usd", "NUMERIC(20,8)"),
        ("perp_trades", "pnl_usd", "NUMERIC(20,8)"),
        ("spot_positions", "tp1_reached", "BOOLEAN NOT NULL DEFAULT 0"),
        ("perp_positions", "ratchet_state", "TEXT"),
        ("support_tickets", "user_last_seen_at", "DATETIME"),
        ("support_tickets", "admin_last_seen_at", "DATETIME"),
        ("perp_trades", "position_id", "VARCHAR(64)"),
        ("portfolio_state", "daily_counter_since", "DATETIME"),
        ("portfolio_state", "daily_counter_reset_at", "DATETIME"),
        ("portfolio_state", "daily_counter_resets_today", "INTEGER NOT NULL DEFAULT 0"),
    ]
    for table, column, col_type in new_columns:
        try:
            await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
        except Exception:
            pass  # column already exists

    await _backfill_perp_trade_position_id(conn)


async def _backfill_perp_trade_position_id(conn) -> None:
    """Fill position_id on historical perp trades from the trade_id prefix.

    Historical rows encode the link only inside the id, as
    ``<prefix>_<position_id>_<hex8>`` with a 4-char prefix (cls_/add_/ssl_).
    substr strips both ends; opening trades carry no position id and stay NULL.

    Idempotent: only touches rows where position_id is still NULL.
    """
    try:
        result = await conn.execute(
            text(
                """
                UPDATE perp_trades
                   SET position_id = substr(trade_id, 5, length(trade_id) - 13)
                 WHERE position_id IS NULL
                   AND length(trade_id) > 13
                   AND (trade_id LIKE 'cls\\_%' ESCAPE '\\'
                     OR trade_id LIKE 'add\\_%' ESCAPE '\\'
                     OR trade_id LIKE 'ssl\\_%' ESCAPE '\\')
                """
            )
        )
        if result.rowcount:
            logger.info("perp_trades_position_id_backfilled", rows=result.rowcount)
    except Exception as exc:  # pragma: no cover - never block startup on a backfill
        logger.warning("perp_trades_position_id_backfill_failed", error=str(exc))


async def close_db() -> None:
    """Dispose the engine on shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async DB session."""
    if _session_factory is None:
        raise RuntimeError("Database not initialised — call init_db() first")
    async with _session_factory() as session:
        yield session


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Database not initialised — call init_db() first")
    return _session_factory


async def check_db() -> dict[str, Any]:
    """Probe DB connectivity with SELECT 1.  Returns a status dict."""
    if _session_factory is None:
        return {"connected": False, "error": "not_initialised"}
    start = time.monotonic()
    try:
        async with _session_factory() as session:
            await session.execute(text("SELECT 1"))
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        return {"connected": True, "latency_ms": latency_ms}
    except Exception as exc:
        return {"connected": False, "error": str(exc)}


def _redact_url(url: str) -> str:
    """Remove credentials from a DB URL for safe logging."""
    try:
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(url)
        if parsed.password:
            netloc = parsed.hostname or ""
            if parsed.port:
                netloc = f"{netloc}:{parsed.port}"
            parsed = parsed._replace(netloc=netloc)
        return urlunparse(parsed)
    except Exception:
        return "[redacted]"
