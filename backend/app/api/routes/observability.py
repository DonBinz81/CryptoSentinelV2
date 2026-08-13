"""Admin-only safe observability routes for the web dashboard."""

from __future__ import annotations

import json
import re
from collections import deque
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query

from backend.app.api.dependencies import AdminAccessDep, SettingsDep
from backend.app.schemas.observability import LogEntry, LogResponse

router = APIRouter(prefix="/api/v1/observability", tags=["observability"])

MAX_SCAN_LINES = 5000
MAX_RETURN_LINES = 500
SECRET_PATTERNS = [
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"(?i)(token\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"(?i)(secret\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"(?i)(password\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"(?i)(private[_-]?key\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"\b0x[a-fA-F0-9]{64}\b"),
]


@router.get("/logs", response_model=LogResponse)
async def dashboard_logs(
    settings: SettingsDep,
    _: AdminAccessDep,
    limit: int = Query(default=200, ge=1, le=MAX_RETURN_LINES),
    level: str | None = Query(default=None, min_length=1, max_length=20),
    search: str | None = Query(default=None, min_length=1, max_length=120),
) -> LogResponse:
    """Return a bounded, redacted tail of backend logs for the dashboard."""

    return tail_sanitized_logs(settings, limit=limit, level=level, search=search)


def tail_sanitized_logs(
    settings: Any,
    *,
    limit: int = 200,
    level: str | None = None,
    search: str | None = None,
) -> LogResponse:
    if not getattr(settings, "log_file_enabled", False):
        return LogResponse(available=False, source="disabled", entries=[])

    raw_path = str(getattr(settings, "log_file_path", "") or "")
    if not raw_path:
        return LogResponse(available=False, source="not_configured", entries=[])

    path = Path(raw_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists() or not path.is_file():
        return LogResponse(available=False, source="backend.log", entries=[])

    level_filter = level.lower() if level else None
    search_filter = search.lower() if search else None
    entries: list[LogEntry] = []
    scanned = _tail_lines(path, MAX_SCAN_LINES)

    for raw_line in scanned:
        entry = _parse_line(raw_line)
        if level_filter and (entry.level or "").lower() != level_filter:
            continue
        searchable = f"{entry.timestamp or ''} {entry.level or ''} {entry.logger or ''} {entry.message}".lower()
        if search_filter and search_filter not in searchable:
            continue
        entries.append(entry)

    truncated = len(entries) > limit
    return LogResponse(
        available=True,
        source="backend.log",
        entries=entries[-limit:],
        truncated=truncated,
    )


def _tail_lines(path: Path, max_lines: int) -> list[str]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return list(deque(handle, maxlen=max_lines))


def _parse_line(raw_line: str) -> LogEntry:
    line = _sanitize(raw_line.strip())
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return LogEntry(message=line)

    if not isinstance(payload, dict):
        return LogEntry(message=line)

    message = payload.get("message") or payload.get("event") or payload.get("msg") or line
    return LogEntry(
        timestamp=_string_or_none(payload.get("timestamp") or payload.get("time") or payload.get("asctime")),
        level=_string_or_none(payload.get("level") or payload.get("levelname") or payload.get("severity")),
        logger=_string_or_none(payload.get("logger") or payload.get("name") or payload.get("module")),
        message=_sanitize(str(message)),
    )


def _sanitize(value: str) -> str:
    sanitized = value
    for pattern in SECRET_PATTERNS:
        sanitized = pattern.sub(lambda match: f"{match.group(1)}[REDACTED]" if match.groups() else "[REDACTED]", sanitized)
    return sanitized


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
