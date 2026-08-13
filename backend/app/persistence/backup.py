"""SQLite backup utility.

Copies the DB file to a timestamped backup directory. Controlled by two
config values (interval and retention); called by the lifespan shutdown and
optionally by a periodic background task.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import structlog

logger = structlog.get_logger("persistence.backup")


def _db_path(database_url: str) -> Path | None:
    """Extract the filesystem path from a sqlite+aiosqlite:// URL."""
    prefix = "sqlite"
    if not database_url.lower().startswith(prefix):
        return None
    # sqlite+aiosqlite:///./backend/local.db  → ./backend/local.db
    # sqlite+aiosqlite:////abs/path.db        → /abs/path.db
    raw = database_url.split("///", 1)[-1]
    return Path(raw)


def backup_db(database_url: str, backup_dir: str | Path, *, retention_days: int = 7) -> Path | None:
    """Copy the SQLite database to *backup_dir* with a UTC timestamp suffix.

    Returns the path of the new backup file, or None when the DB file does not
    exist or the URL is not a SQLite URL.
    """
    src = _db_path(database_url)
    if src is None or not src.exists():
        return None

    dest_dir = Path(backup_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dest = dest_dir / f"{src.stem}_{stamp}{src.suffix}"
    shutil.copy2(src, dest)
    logger.info("db_backup_created", path=str(dest))

    _prune(dest_dir, src.stem, retention_days=retention_days)
    return dest


def _prune(backup_dir: Path, stem: str, *, retention_days: int) -> None:
    """Remove backups older than *retention_days* days."""
    cutoff = datetime.now(UTC).timestamp() - retention_days * 86_400
    for f in backup_dir.glob(f"{stem}_*.db"):
        if f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)
            logger.info("db_backup_pruned", path=str(f))
