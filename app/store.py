"""Lightweight persistence for report history and quality trends.

Uses the Python standard-library ``sqlite3`` — no external database, no ORM.
The store records only **report summaries** (score, counts, timestamps); it
never persists patient rows or sample data, which keeps the PHI footprint at
zero even when history is enabled.

Enable by setting ``EHR_DB_PATH`` (or accept the default under ``var/``).
Disable entirely by setting ``EHR_HISTORY=off``.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, Optional

from . import config

# A single module-level lock serialises writes; reads are concurrent. SQLite in
# WAL mode handles concurrent readers fine, and our write volume is tiny.
_write_lock = threading.Lock()
_initialised = False


def history_enabled() -> bool:
    return os.getenv("EHR_HISTORY", "on").lower() not in {"off", "0", "false", "no"}


def _db_path() -> str:
    return os.getenv("EHR_DB_PATH", config.DEFAULT_DB_PATH)


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    path = _db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Create the schema if it does not exist (idempotent)."""
    global _initialised
    with _write_lock, _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS report_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at  TEXT    NOT NULL,
                dataset     TEXT    NOT NULL,
                source      TEXT    NOT NULL,   -- upload | sample | fhir | audit | cli
                variant     TEXT,
                row_count   INTEGER NOT NULL,
                score       REAL    NOT NULL,
                grade       TEXT    NOT NULL,
                errors      INTEGER NOT NULL,
                warnings    INTEGER NOT NULL,
                rules_failed INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_history_dataset_time "
            "ON report_history (dataset, created_at)"
        )
        conn.commit()
        # Flip the flag while still holding the lock so a concurrent
        # _ensure_init() can't observe a half-initialised database.
        _initialised = True


def _ensure_init() -> None:
    if not _initialised:
        init_db()


def save_report(report: dict, source: str) -> Optional[int]:
    """Persist a single report's summary. Returns the new row id, or None if
    history is disabled. Only aggregate fields are stored — never row data."""
    if not history_enabled():
        return None
    _ensure_init()
    s = report.get("summary", {})
    row = (
        datetime.now(timezone.utc).isoformat(timespec="seconds"),
        report.get("dataset", "unknown"),
        source,
        report.get("variant"),
        int(report.get("row_count", 0)),
        float(s.get("score", 0.0)),
        str(s.get("grade", "")),
        int(s.get("errors", 0)),
        int(s.get("warnings", 0)),
        int(s.get("rules_failed", 0)),
    )
    with _write_lock, _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO report_history
                (created_at, dataset, source, variant, row_count,
                 score, grade, errors, warnings, rules_failed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )
        conn.commit()
        return cur.lastrowid


def save_many(reports: list[dict], source: str) -> int:
    """Persist several reports (e.g. every table from an audit). Returns count."""
    if not history_enabled():
        return 0
    saved = 0
    for r in reports:
        if save_report(r, source) is not None:
            saved += 1
    return saved


def list_history(dataset: Optional[str] = None, limit: int = 50) -> list[dict]:
    """Most-recent-first history, optionally filtered to one dataset."""
    if not history_enabled():
        return []
    _ensure_init()
    limit = max(1, min(int(limit), 500))
    with _connect() as conn:
        if dataset:
            rows = conn.execute(
                "SELECT * FROM report_history WHERE dataset = ? "
                "ORDER BY id DESC LIMIT ?",
                (dataset, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM report_history ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def trends(dataset: str, limit: int = 30) -> dict:
    """Oldest-to-newest score/error series for one dataset, for charting."""
    if not history_enabled():
        return {"dataset": dataset, "points": [], "enabled": False}
    _ensure_init()
    limit = max(1, min(int(limit), 365))
    with _connect() as conn:
        rows = conn.execute(
            "SELECT created_at, score, errors, warnings, row_count "
            "FROM report_history WHERE dataset = ? ORDER BY id DESC LIMIT ?",
            (dataset, limit),
        ).fetchall()
    points = [dict(r) for r in reversed(rows)]  # chronological for the chart
    return {"dataset": dataset, "enabled": True, "count": len(points), "points": points}


def datasets_with_history() -> list[str]:
    if not history_enabled():
        return []
    _ensure_init()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT dataset FROM report_history ORDER BY dataset"
        ).fetchall()
    return [r["dataset"] for r in rows]


def clear() -> None:
    """Wipe history (used by tests)."""
    _ensure_init()
    with _write_lock, _connect() as conn:
        conn.execute("DELETE FROM report_history")
        conn.commit()
