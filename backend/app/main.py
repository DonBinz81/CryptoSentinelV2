"""FastAPI application entrypoint."""

import asyncio
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from time import perf_counter
from typing import Any
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from backend.app.agent.heartbeat import heartbeat
from backend.app.agent.loops import fast_loop as agent_fast_loop
from backend.app.agent.loops import slow_loop as agent_slow_loop
from backend.app.agent.ohlcv_warmup import warmup_selected_watchlist
from backend.app.agent.watchlist import seed_perp_watchlist_if_empty
from backend.app.api.routes import api_router
from backend.app.api.routes.mobile_agent import apply_mobile_settings_to_config, _settings_from_runtime
from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import configure_logging, get_logger
from backend.app.core.security.headers import add_security_headers
from backend.app.notifications.price_checker import price_checker_loop
from backend.app.persistence.backup import backup_db
from backend.app.persistence.database import close_db, get_session_factory, init_db
from backend.app.persistence.migration import migrate_json_to_db, upgrade_schema
from backend.app.persistence.repositories.pnl import PnlRepository
from backend.app.persistence.sync_database import init_sync_db, reset_sync_db

settings = get_settings()
configure_logging(settings)
logger = get_logger("api")


def _dashboard_cors_origin_regex(port: int) -> str:
    """Allow local and Tailscale dashboard dev origins without wildcard CORS."""
    escaped_port = re.escape(str(port))
    return (
        r"^https?://("
        r"localhost|"
        r"127\.0\.0\.1|"
        r"100(?:\.\d{1,3}){3}"
        rf"):{escaped_port}$"
    )


async def _heartbeat_loop(settings: Settings) -> None:
    """Keep an internal heartbeat active for health checks."""

    while True:
        heartbeat.beat("internal_tick")
        await asyncio.sleep(settings.heartbeat_interval_seconds)


async def _backup_loop(settings: Settings) -> None:
    """Periodically snapshot the SQLite DB to the configured backup directory."""

    interval = max(1, settings.db_backup_interval_hours) * 3600
    while True:
        await asyncio.sleep(interval)
        try:
            backup_db(
                settings.database_url,
                settings.db_backup_dir,
                retention_days=settings.db_backup_retention_days,
            )
        except Exception:
            logger.exception("db_backup_periodic_failed")


async def _startup_ohlcv_warmup(settings: Settings) -> None:
    """Warm OHLCV caches after the API has started accepting requests."""

    try:
        warmup = await warmup_selected_watchlist(settings)
        logger.info(
            "agent_startup_ohlcv_warmup_finished",
            status=warmup.get("status"),
            reason=warmup.get("reason"),
            requested_assets=warmup.get("requested_assets", 0),
            loaded=warmup.get("loaded", 0),
            ready=warmup.get("ready", 0),
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("agent_startup_ohlcv_warmup_failed", error=str(exc))


async def _ensure_base_portfolio(settings: Settings) -> None:
    """Create the dry-run base portfolio when reset/startup leaves no state row."""

    async with get_session_factory()() as session:
        repo = PnlRepository(session)
        user_id = str(settings.default_user_id)
        if await repo.get_portfolio(user_id) is not None:
            return
        capital = Decimal(str(settings.dry_run_capital_usd))
        await repo.upsert_portfolio(
            user_id,
            total_equity_usd=capital,
            initial_equity_usd=capital,
            peak_equity_usd=capital,
            agent_status="idle",
        )
        logger.info("base_portfolio_created", total_equity_usd=str(capital))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start and stop backend runtime tasks."""

    heartbeat.beat("startup")

    await init_db(settings.database_url, echo=settings.database_echo)
    init_sync_db(settings.database_url, echo=settings.database_echo)
    async with get_session_factory()() as session:
        await upgrade_schema(session)
        await migrate_json_to_db(
            session,
            fcm_tokens_path=settings.fcm_token_store_path,
        )
    await _ensure_base_portfolio(settings)
    seed_perp_watchlist_if_empty(settings)
    # Ripristina i parametri di rischio/strategia salvati dall'utente nel DB.
    mobile_settings, _, persisted = _settings_from_runtime(settings)
    if persisted:
        apply_mobile_settings_to_config(mobile_settings, settings)
        logger.info("mobile_settings_restored_from_runtime", capital_per_trade_pct=mobile_settings.capital_per_trade_pct)
    warmup_task = asyncio.create_task(_startup_ohlcv_warmup(settings))
    heartbeat_task = asyncio.create_task(_heartbeat_loop(settings))
    price_checker_task = asyncio.create_task(price_checker_loop())
    agent_fast_task = asyncio.create_task(agent_fast_loop(settings))
    agent_slow_task = asyncio.create_task(agent_slow_loop(settings))
    background_tasks = [warmup_task, heartbeat_task, price_checker_task, agent_fast_task, agent_slow_task]
    if settings.db_backup_enabled:
        background_tasks.append(asyncio.create_task(_backup_loop(settings)))
    logger.info(
        "backend_started",
        environment=settings.app_env,
        execution_mode=settings.execution_mode,
        markets_enabled=settings.markets_enabled,
        eligible_token_count=len(settings.eligible_tokens),
        auth_configured=settings.auth_configured,
    )
    try:
        yield
    finally:
        for t in background_tasks:
            t.cancel()
        for t in background_tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass
        if settings.db_backup_enabled:
            try:
                backup_db(
                    settings.database_url,
                    settings.db_backup_dir,
                    retention_days=settings.db_backup_retention_days,
                )
            except Exception:
                logger.exception("db_backup_on_shutdown_failed")
        await close_db()
        reset_sync_db()
        logger.info("backend_stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="CryptoSentinel autonomous trading agent backend foundations.",
        lifespan=lifespan,
    )

    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=_dashboard_cors_origin_regex(settings.dashboard_port),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Token", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next: Any) -> Response:
        return await add_security_headers(request, call_next, settings)

    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next: Any) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = perf_counter()
        logger.info(
            "request_started",
            method=request.method,
            path=request.url.path,
            client=request.client.host if request.client else None,
        )
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                elapsed_ms=round((perf_counter() - started) * 1000, 2),
            )
            return response
        except Exception:
            logger.exception(
                "request_failed",
                method=request.method,
                path=request.url.path,
                elapsed_ms=round((perf_counter() - started) * 1000, 2),
            )
            raise
        finally:
            structlog.contextvars.clear_contextvars()

    app.include_router(api_router)
    return app


app = create_app()
