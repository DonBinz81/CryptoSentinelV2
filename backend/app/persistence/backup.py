"""SQLite backup utility.

Copies the DB file to a timestamped backup directory, verifies the copy, and
only then publishes it under its final name. Controlled by two config values
(interval and retention); called by the lifespan shutdown and optionally by a
periodic background task.
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import structlog

logger = structlog.get_logger("persistence.backup")

# A copy carries this suffix from the moment it is written until it has been
# verified. Nothing with this suffix is a backup, and nothing counts it as one.
_STAGING_SUFFIX = ".part"


class BackupVerificationError(RuntimeError):
    """The copy exists on disk but is not a usable database."""


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

    The copy is written under a staging name, verified, and renamed to its
    final name only once it is a readable database with a schema. A copy that
    fails or comes out truncated is removed rather than left behind under a
    name that looks like a backup: on 2026-09-25 a full disk produced eight
    consecutive zero-byte "backups" this way, and a retention pass keyed on
    recency would have kept them and discarded the intact ones.

    Pruning runs whether or not the copy succeeded. A full disk is exactly
    when retention has to keep working.

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
    staged = dest.with_name(dest.name + _STAGING_SUFFIX)

    try:
        shutil.copy2(src, staged)
        _verify_copy(staged)
        staged.replace(dest)
    except Exception:
        staged.unlink(missing_ok=True)
        logger.exception("db_backup_failed", path=str(dest))
        raise
    finally:
        _prune(dest_dir, src.stem, retention_days=retention_days)

    logger.info("db_backup_created", path=str(dest), bytes=dest.stat().st_size)
    return dest


def _verify_copy(staged: Path) -> None:
    """Raise unless *staged* is a complete, readable database.

    Three checks, cheapest first. The size check catches the common failure
    (ENOSPC leaves an empty file) without opening anything. quick_check walks
    the page tree and fails on a file cut short of its declared page count.
    The schema check is there because an empty file is, to SQLite, a valid
    database with no tables, and passes quick_check with "ok".

    The copy is opened through an immutable URI: no locks, and no -wal/-shm
    sidecars created next to the backup.
    """
    size = staged.stat().st_size
    if size == 0:
        raise BackupVerificationError("copy is empty")

    uri = f"file:{staged.as_posix()}?immutable=1"
    con = sqlite3.connect(uri, uri=True)
    try:
        check = con.execute("PRAGMA quick_check").fetchone()
        if check is None or check[0] != "ok":
            raise BackupVerificationError(f"quick_check: {check[0] if check else 'no result'}")
        tables = con.execute("SELECT count(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0]
        if tables == 0:
            raise BackupVerificationError("copy has no schema")
    except sqlite3.DatabaseError as exc:
        raise BackupVerificationError(f"not a readable database: {exc}") from exc
    finally:
        con.close()


def _prune(backup_dir: Path, stem: str, *, retention_days: int) -> None:
    """Remove backups older than *retention_days* days, and any leftover staging file."""
    cutoff = datetime.now(UTC).timestamp() - retention_days * 86_400
    for f in backup_dir.glob(f"{stem}_*.db"):
        if f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)
            logger.info("db_backup_pruned", path=str(f))
    # A staging file that survived means a previous run died between copy and
    # verification. It was never a backup, so it does not get to age out.
    for f in backup_dir.glob(f"{stem}_*.db{_STAGING_SUFFIX}"):
        f.unlink(missing_ok=True)
        logger.warning("db_backup_stale_staging_removed", path=str(f))
