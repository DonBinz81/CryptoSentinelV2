"""Schemas for safe observability endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class LogEntry(BaseModel):
    timestamp: str | None = None
    level: str | None = None
    logger: str | None = None
    message: str


class LogResponse(BaseModel):
    available: bool
    source: str
    entries: list[LogEntry]
    truncated: bool = False
