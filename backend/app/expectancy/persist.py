"""SQLite persistence for regime-segmented expectancy metrics."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.expectancy.regimes import REGIME_LABELS

logger = logging.getLogger(__name__)

EXPECTANCY_SCHEMA = """
CREATE TABLE IF NOT EXISTS expectancy_metrics (
  rule_id TEXT NOT NULL,
  desk TEXT NOT NULL,
  regime TEXT NOT NULL,
  sample_size INTEGER NOT NULL,
  win_rate_pct REAL,
  avg_win_r REAL,
  avg_loss_r REAL,
  expectancy_r REAL,
  profit_factor REAL,
  max_drawdown_pct REAL,
  as_of TEXT,
  computed_at TEXT NOT NULL,
  meta_json TEXT,
  PRIMARY KEY(rule_id, regime)
);

CREATE INDEX IF NOT EXISTS idx_expectancy_desk ON expectancy_metrics(desk);
CREATE INDEX IF NOT EXISTS idx_expectancy_computed ON expectancy_metrics(computed_at);
"""


def ensure_expectancy_schema(db) -> None:
    with db.get_connection() as conn:
        conn.executescript(EXPECTANCY_SCHEMA)
        conn.commit()


def upsert_metrics_rows(
    db,
    *,
    rule_id: str,
    desk: str,
    by_regime: dict[str, dict[str, Any]],
    as_of: str | None = None,
    meta: dict[str, Any] | None = None,
) -> int:
    ensure_expectancy_schema(db)
    now = datetime.now(timezone.utc).isoformat()
    meta_json = json.dumps(meta or {}, default=str)
    rows = 0
    with db.get_connection() as conn:
        for regime, m in by_regime.items():
            if regime == "ALL":
                # Store ALL as well for dashboards
                pass
            conn.execute(
                """
                INSERT OR REPLACE INTO expectancy_metrics(
                    rule_id, desk, regime, sample_size, win_rate_pct,
                    avg_win_r, avg_loss_r, expectancy_r, profit_factor,
                    max_drawdown_pct, as_of, computed_at, meta_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rule_id,
                    desk,
                    regime,
                    int(m.get("sample_size") or 0),
                    m.get("win_rate_pct"),
                    m.get("avg_win_r"),
                    m.get("avg_loss_r"),
                    m.get("expectancy_r"),
                    m.get("profit_factor"),
                    m.get("max_drawdown_pct"),
                    as_of,
                    now,
                    meta_json,
                ),
            )
            rows += 1
        conn.commit()
    logger.info("Upserted %s expectancy rows for %s", rows, rule_id)
    return rows


def load_metrics(
    db,
    *,
    rule_id: str,
    regime: str | None = None,
) -> dict[str, Any] | None:
    ensure_expectancy_schema(db)
    with db.get_connection() as conn:
        if regime:
            row = conn.execute(
                """
                SELECT rule_id, desk, regime, sample_size, win_rate_pct,
                       avg_win_r, avg_loss_r, expectancy_r, profit_factor,
                       max_drawdown_pct, as_of, computed_at, meta_json
                FROM expectancy_metrics
                WHERE rule_id = ? AND regime = ?
                """,
                (rule_id, regime),
            ).fetchone()
            if not row:
                return None
            cols = [
                "rule_id",
                "desk",
                "regime",
                "sample_size",
                "win_rate_pct",
                "avg_win_r",
                "avg_loss_r",
                "expectancy_r",
                "profit_factor",
                "max_drawdown_pct",
                "as_of",
                "computed_at",
                "meta_json",
            ]
            d = dict(zip(cols, row))
            if d.get("meta_json"):
                try:
                    d["meta"] = json.loads(d["meta_json"])
                except json.JSONDecodeError:
                    d["meta"] = {}
            return d

        rows = conn.execute(
            """
            SELECT rule_id, desk, regime, sample_size, win_rate_pct,
                   avg_win_r, avg_loss_r, expectancy_r, profit_factor,
                   max_drawdown_pct, as_of, computed_at
            FROM expectancy_metrics WHERE rule_id = ?
            """,
            (rule_id,),
        ).fetchall()
        if not rows:
            return None
        by: dict[str, Any] = {"rule_id": rule_id, "regimes": {}}
        for r in rows:
            by["regimes"][r[2]] = {
                "rule_id": r[0],
                "desk": r[1],
                "regime": r[2],
                "sample_size": r[3],
                "win_rate_pct": r[4],
                "avg_win_r": r[5],
                "avg_loss_r": r[6],
                "expectancy_r": r[7],
                "profit_factor": r[8],
                "max_drawdown_pct": r[9],
                "as_of": r[10],
                "computed_at": r[11],
            }
            by["desk"] = r[1]
            by["as_of"] = r[10]
            by["computed_at"] = r[11]
        return by


def metrics_stale(db, *, rule_id: str, max_age_hours: float = 72.0) -> bool:
    """True if missing or older than max_age_hours."""
    ensure_expectancy_schema(db)
    with db.get_connection() as conn:
        row = conn.execute(
            """
            SELECT computed_at FROM expectancy_metrics
            WHERE rule_id = ? AND regime = 'ALL'
            ORDER BY computed_at DESC LIMIT 1
            """,
            (rule_id,),
        ).fetchone()
    if not row or not row[0]:
        return True
    try:
        ts = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0
        return age_h > max_age_hours
    except (TypeError, ValueError):
        return True


def list_all_metrics(db) -> list[dict[str, Any]]:
    ensure_expectancy_schema(db)
    with db.get_connection() as conn:
        rows = conn.execute(
            """
            SELECT rule_id, desk, regime, sample_size, win_rate_pct,
                   avg_win_r, avg_loss_r, expectancy_r, profit_factor,
                   max_drawdown_pct, as_of, computed_at
            FROM expectancy_metrics
            ORDER BY rule_id, regime
            """
        ).fetchall()
    cols = [
        "rule_id",
        "desk",
        "regime",
        "sample_size",
        "win_rate_pct",
        "avg_win_r",
        "avg_loss_r",
        "expectancy_r",
        "profit_factor",
        "max_drawdown_pct",
        "as_of",
        "computed_at",
    ]
    return [dict(zip(cols, r)) for r in rows]


def empty_regime_bundle(rule_id: str, desk: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for label in (*REGIME_LABELS, "ALL"):
        out[label] = {
            "rule_id": rule_id,
            "desk": desk,
            "regime": label,
            "sample_size": 0,
            "win_rate_pct": None,
            "avg_win_r": None,
            "avg_loss_r": None,
            "expectancy_r": None,
            "profit_factor": None,
            "max_drawdown_pct": None,
        }
    return out
