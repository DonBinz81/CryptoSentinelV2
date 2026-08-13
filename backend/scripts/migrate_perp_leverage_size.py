"""One-shot migration: corregge size e pnl_usd nelle tabelle perp.

Prima del fix in service.py, la size veniva salvata senza moltiplicare per
il leverage (size = capital / price invece di capital * leverage / price).
Questo script aggiorna i record esistenti moltiplicando per il leverage.

Esecuzione:
    cd backend
    python -m scripts.migrate_perp_leverage_size

Il backup viene creato automaticamente prima di qualsiasi modifica.
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "local.db"
BACKUP_DIR = Path(__file__).parent.parent / "storage" / "backups"


def _backup(db_path: Path) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dest = BACKUP_DIR / f"local_{ts}_pre_leverage_migration.db"
    shutil.copy2(db_path, dest)
    print(f"[backup] {dest}")
    return dest


def migrate(db_path: Path = DB_PATH) -> None:
    _backup(db_path)

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # ------------------------------------------------------------------ #
    # 1. perp_positions: size *= leverage, pnl_unrealized ricalcolato      #
    # ------------------------------------------------------------------ #
    positions = cur.execute(
        "SELECT id, side, size, entry_price, current_price, leverage, pnl_unrealized "
        "FROM perp_positions"
    ).fetchall()

    pos_updated = 0
    for row in positions:
        lev = row["leverage"] or 1
        if lev <= 1:
            continue  # niente da correggere
        new_size = row["size"] * lev
        if row["side"] == "long":
            new_pnl = (row["current_price"] - row["entry_price"]) * new_size
        else:
            new_pnl = (row["entry_price"] - row["current_price"]) * new_size
        cur.execute(
            "UPDATE perp_positions SET size = ?, pnl_unrealized = ? WHERE id = ?",
            (new_size, new_pnl, row["id"]),
        )
        pos_updated += 1

    print(f"[perp_positions] aggiornate {pos_updated} righe su {len(positions)}")

    # ------------------------------------------------------------------ #
    # 2. perp_trades: size *= leverage, pnl_usd *= leverage (solo close)   #
    # ------------------------------------------------------------------ #
    trades = cur.execute(
        "SELECT id, direction, size, leverage, pnl_usd FROM perp_trades"
    ).fetchall()

    trade_updated = 0
    for row in trades:
        lev = row["leverage"] or 1
        if lev <= 1:
            continue
        new_size = row["size"] * lev
        new_pnl = (row["pnl_usd"] * lev) if row["pnl_usd"] is not None else None
        if row["direction"] == "close":
            cur.execute(
                "UPDATE perp_trades SET size = ?, pnl_usd = ? WHERE id = ?",
                (new_size, new_pnl, row["id"]),
            )
        else:
            cur.execute(
                "UPDATE perp_trades SET size = ? WHERE id = ?",
                (new_size, row["id"]),
            )
        trade_updated += 1

    print(f"[perp_trades]     aggiornate {trade_updated} righe su {len(trades)}")

    con.commit()
    con.close()
    print("[done] migrazione completata.")


if __name__ == "__main__":
    migrate()
