"""Persist DB metadata (e.g. demo vs live source)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    conn.commit()
    return conn


def set_meta(db_path: Path, key: str, value: Any):
    with _conn(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            (key, json.dumps(value)),
        )
        conn.commit()


def get_meta(db_path: Path, key: str, default=None):
    with _conn(db_path) as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row[0])
    except json.JSONDecodeError:
        return row[0]


def data_provenance(db_path: Path) -> dict:
    """What kind of data is in the DB right now."""
    source = get_meta(db_path, "data_source", "unknown")
    note = get_meta(db_path, "data_note", "")
    return {
        "data_source": source,  # demo | nse | yahoo | mixed | unknown
        "data_note": note,
        "is_demo": source == "demo",
    }
