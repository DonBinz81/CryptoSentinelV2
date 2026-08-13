"""Structured logging setup."""

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
import sys
from typing import Any

import structlog

from backend.app.core.config import PROJECT_ROOT, Settings


def configure_logging(settings: Settings) -> None:
    """Configure stdlib and structlog for JSON or console output."""

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if settings.log_file_enabled:
        log_path = Path(settings.log_file_path)
        if not log_path.is_absolute():
            log_path = PROJECT_ROOT / log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            TimedRotatingFileHandler(
                log_path,
                when="midnight",
                backupCount=settings.log_retention_days,
                encoding="utf-8",
                utc=True,
            )
        )

    logging.basicConfig(
        format="%(message)s",
        handlers=handlers,
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        force=True,
    )

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.CallsiteParameterAdder(
            {
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            }
        ),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.log_format == "console":
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a lazy structured logger with a component name."""

    return structlog.get_logger(name, component=name)
