"""
Persistent EOD ingest run journal — idempotency + operator visibility.

Records provider, requested range, success/failure, row counts, freshness.
"""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.config import config

JOURNAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS ingest_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  trigger TEXT NOT NULL,
  status TEXT NOT NULL,
  provider TEXT,
  requested_from TEXT,
  requested_to TEXT,
  target_session TEXT,
  eod_rows INTEGER DEFAULT 0,
  nifty_rows INTEGER DEFAULT 0,
  indicator_rows INTEGER DEFAULT 0,
  dates_ingested_json TEXT,
  freshness_status TEXT,
  latest_eod TEXT,
  error TEXT,
  message TEXT,
  meta_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_ingest_runs_started ON ingest_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_ingest_runs_target ON ingest_runs(target_session, status);
"""


def _path(db_path: Path | None = None) -> Path:
    return Path(db_path or config.db_path)


def ensure_journal_schema(db_path: Path | None = None) -> None:
    with sqlite3.connect(str(_path(db_path))) as conn:
        conn.executescript(JOURNAL_SCHEMA)
        conn.commit()


def begin_run(
    *,
    trigger: str,
    target_session: str | None = None,
    requested_from: str | None = None,
    requested_to: str | None = None,
    provider: str | None = None,
    db_path: Path | None = None,
    meta: dict[str, Any] | None = None,
) -> int:
    ensure_journal_schema(db_path)
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(str(_path(db_path))) as conn:
        cur = conn.execute(
            """
            INSERT INTO ingest_runs(
              started_at, trigger, status, provider, requested_from, requested_to,
              target_session, meta_json
            ) VALUES (?, ?, 'running', ?, ?, ?, ?, ?)
            """,
            (
                now,
                trigger,
                provider,
                requested_from,
                requested_to,
                target_session,
                json.dumps(meta or {}, default=str),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def finish_run(
    run_id: int,
    *,
    status: str,
    provider: str | None = None,
    eod_rows: int = 0,
    nifty_rows: int = 0,
    indicator_rows: int = 0,
    dates_ingested: list | None = None,
    freshness: dict[str, Any] | None = None,
    error: str | None = None,
    message: str | None = None,
    db_path: Path | None = None,
) -> None:
    ensure_journal_schema(db_path)
    now = datetime.now(timezone.utc).isoformat()
    fr = freshness or {}
    with sqlite3.connect(str(_path(db_path))) as conn:
        conn.execute(
            """
            UPDATE ingest_runs SET
              finished_at=?, status=?, provider=COALESCE(?, provider),
              eod_rows=?, nifty_rows=?, indicator_rows=?,
              dates_ingested_json=?, freshness_status=?, latest_eod=?,
              error=?, message=?
            WHERE id=?
            """,
            (
                now,
                status,
                provider,
                int(eod_rows or 0),
                int(nifty_rows or 0),
                int(indicator_rows or 0),
                json.dumps(list(dates_ingested or []), default=str),
                fr.get("status"),
                fr.get("latest_date"),
                error,
                message,
                run_id,
            ),
        )
        conn.commit()


def last_successful_for_session(
    target_session: str,
    *,
    db_path: Path | None = None,
) -> Optional[dict[str, Any]]:
    ensure_journal_schema(db_path)
    with sqlite3.connect(str(_path(db_path))) as conn:
        row = conn.execute(
            """
            SELECT id, started_at, finished_at, trigger, status, provider,
                   target_session, eod_rows, latest_eod, message
            FROM ingest_runs
            WHERE target_session = ? AND status IN ('ok', 'skipped_already_fresh')
            ORDER BY id DESC LIMIT 1
            """,
            (target_session,),
        ).fetchone()
    if not row:
        return None
    cols = [
        "id",
        "started_at",
        "finished_at",
        "trigger",
        "status",
        "provider",
        "target_session",
        "eod_rows",
        "latest_eod",
        "message",
    ]
    return dict(zip(cols, row))


def recent_runs(*, limit: int = 20, db_path: Path | None = None) -> list[dict[str, Any]]:
    ensure_journal_schema(db_path)
    with sqlite3.connect(str(_path(db_path))) as conn:
        rows = conn.execute(
            """
            SELECT id, started_at, finished_at, trigger, status, provider,
                   requested_from, requested_to, target_session,
                   eod_rows, nifty_rows, indicator_rows, freshness_status,
                   latest_eod, error, message
            FROM ingest_runs
            ORDER BY id DESC LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    cols = [
        "id",
        "started_at",
        "finished_at",
        "trigger",
        "status",
        "provider",
        "requested_from",
        "requested_to",
        "target_session",
        "eod_rows",
        "nifty_rows",
        "indicator_rows",
        "freshness_status",
        "latest_eod",
        "error",
        "message",
    ]
    return [dict(zip(cols, r)) for r in rows]


def journal_summary(*, db_path: Path | None = None) -> dict[str, Any]:
    ensure_journal_schema(db_path)
    with sqlite3.connect(str(_path(db_path))) as conn:
        last_ok = conn.execute(
            """
            SELECT id, finished_at, provider, target_session, latest_eod, eod_rows, message
            FROM ingest_runs WHERE status IN ('ok', 'skipped_already_fresh')
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        last_any = conn.execute(
            """
            SELECT id, finished_at, status, provider, error, message, target_session
            FROM ingest_runs ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        fail_n = conn.execute(
            "SELECT COUNT(*) FROM ingest_runs WHERE status='error'"
        ).fetchone()[0]
    return {
        "last_success": (
            {
                "id": last_ok[0],
                "finished_at": last_ok[1],
                "provider": last_ok[2],
                "target_session": last_ok[3],
                "latest_eod": last_ok[4],
                "eod_rows": last_ok[5],
                "message": last_ok[6],
            }
            if last_ok
            else None
        ),
        "last_run": (
            {
                "id": last_any[0],
                "finished_at": last_any[1],
                "status": last_any[2],
                "provider": last_any[3],
                "error": last_any[4],
                "message": last_any[5],
                "target_session": last_any[6],
            }
            if last_any
            else None
        ),
        "error_count": int(fail_n or 0),
        "journal_ok": True,
    }
