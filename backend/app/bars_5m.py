"""
Persistent validated NSE cash 5-minute bars.

Contract:
  - Timestamps are bar *start* unix seconds (UTC epoch).
  - Only completed bars are used for strategy / expectancy (no forming candle).
  - Session filter: regular NSE hours 09:15–15:30 IST (weekday); holidays not
    applied until Phase 4 — weekends rejected.
  - Dedup key: (symbol, bar_start_unix). Corrections overwrite OHLCV when the
    incoming bar is completed and has equal/newer source priority.
  - Gaps: detectable via expected 5m grid within a session_date.
  - Retention: purge bars older than retention_days (default 45 calendar days).
  - Restart: SQLite WAL; upserts are idempotent.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

import pandas as pd

from app.config import config

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

INTERVAL_SEC = 300
SESSION_OPEN = time(9, 15)
SESSION_CLOSE = time(15, 30)  # last bar starts 15:25

# Source priority for corrections (higher wins on conflict)
SOURCE_PRIORITY = {
    "kotak_neo_ws": 30,
    "yahoo_chart": 20,
    "synthetic_test": 10,
    "unknown": 0,
}

BARS_5M_SCHEMA = """
CREATE TABLE IF NOT EXISTS bars_5m (
  symbol TEXT NOT NULL,
  bar_start_unix INTEGER NOT NULL,
  session_date TEXT NOT NULL,
  open REAL NOT NULL,
  high REAL NOT NULL,
  low REAL NOT NULL,
  close REAL NOT NULL,
  volume REAL NOT NULL DEFAULT 0,
  source TEXT NOT NULL DEFAULT 'unknown',
  completed INTEGER NOT NULL DEFAULT 1,
  ingested_at_unix REAL NOT NULL,
  PRIMARY KEY(symbol, bar_start_unix)
);

CREATE INDEX IF NOT EXISTS idx_bars_5m_symbol_session
  ON bars_5m(symbol, session_date);
CREATE INDEX IF NOT EXISTS idx_bars_5m_session
  ON bars_5m(session_date);
CREATE INDEX IF NOT EXISTS idx_bars_5m_symbol_unix
  ON bars_5m(symbol, bar_start_unix);
"""


@dataclass(frozen=True)
class Bar5m:
    symbol: str
    bar_start_unix: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    source: str = "unknown"
    completed: bool = True
    session_date: str = ""

    def validate(self) -> tuple[bool, str]:
        if not self.symbol:
            return False, "missing_symbol"
        if self.bar_start_unix <= 0:
            return False, "bad_ts"
        if self.bar_start_unix % INTERVAL_SEC != 0:
            return False, "unaligned_bucket"
        for name, v in (
            ("open", self.open),
            ("high", self.high),
            ("low", self.low),
            ("close", self.close),
        ):
            try:
                fv = float(v)
            except (TypeError, ValueError):
                return False, f"invalid_{name}"
            if fv <= 0:
                return False, f"non_positive_{name}"
        if float(self.high) < float(self.low):
            return False, "high_lt_low"
        if float(self.high) < max(float(self.open), float(self.close)):
            return False, "high_inconsistent"
        if float(self.low) > min(float(self.open), float(self.close)):
            return False, "low_inconsistent"
        if float(self.volume) < 0:
            return False, "negative_volume"
        if not in_regular_session(self.bar_start_unix):
            return False, "outside_session"
        return True, "ok"


def floor_bucket(ts_unix: float) -> int:
    return int(ts_unix) // INTERVAL_SEC * INTERVAL_SEC


def ist_dt(ts_unix: float) -> datetime:
    return datetime.fromtimestamp(float(ts_unix), tz=IST)


def session_date_for(ts_unix: float) -> str:
    return ist_dt(ts_unix).date().isoformat()


def in_regular_session(ts_unix: float) -> bool:
    """True if bar *start* is on a weekday inside NSE regular cash hours."""
    dt = ist_dt(ts_unix)
    if dt.weekday() >= 5:
        return False
    t = dt.time()
    # Last valid 5m start is 15:25 (covers 15:25–15:30)
    last_start = time(15, 25)
    return SESSION_OPEN <= t <= last_start


def expected_session_starts(session_date: str) -> list[int]:
    """All valid 5m bar starts for a calendar session_date (IST)."""
    d = date.fromisoformat(session_date)
    if d.weekday() >= 5:
        return []
    start = datetime.combine(d, SESSION_OPEN, tzinfo=IST)
    end = datetime.combine(d, time(15, 25), tzinfo=IST)
    out: list[int] = []
    cur = start
    while cur <= end:
        out.append(int(cur.timestamp()))
        cur += timedelta(seconds=INTERVAL_SEC)
    return out


def find_gaps(session_date: str, present_starts: Iterable[int]) -> list[int]:
    present = set(int(x) for x in present_starts)
    return [s for s in expected_session_starts(session_date) if s not in present]


def ensure_bars_5m_schema(db_path: Path | None = None) -> Path:
    path = Path(db_path or config.db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path)) as conn:
        conn.executescript(BARS_5M_SCHEMA)
        conn.commit()
    return path


def _conn(db_path: Path | None = None) -> sqlite3.Connection:
    path = ensure_bars_5m_schema(db_path)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def upsert_bars(
    bars: Iterable[Bar5m | dict[str, Any]],
    *,
    db_path: Path | None = None,
    now_unix: float | None = None,
) -> dict[str, int]:
    """
    Insert/replace completed bars. Incomplete bars are stored but never overwrite
    a completed bar. Higher SOURCE_PRIORITY wins on conflict.
    """
    import time as _time

    now = float(now_unix if now_unix is not None else _time.time())
    stats = {"accepted": 0, "rejected": 0, "skipped_incomplete_vs_complete": 0}
    rows: list[Bar5m] = []
    for raw in bars:
        if isinstance(raw, dict):
            b = Bar5m(
                symbol=str(raw["symbol"]).upper().strip(),
                bar_start_unix=int(raw["bar_start_unix"]),
                open=float(raw["open"]),
                high=float(raw["high"]),
                low=float(raw["low"]),
                close=float(raw["close"]),
                volume=float(raw.get("volume") or 0.0),
                source=str(raw.get("source") or "unknown"),
                completed=bool(raw.get("completed", True)),
                session_date=str(
                    raw.get("session_date") or session_date_for(int(raw["bar_start_unix"]))
                ),
            )
        else:
            b = raw
            if not b.session_date:
                b = Bar5m(
                    symbol=b.symbol,
                    bar_start_unix=b.bar_start_unix,
                    open=b.open,
                    high=b.high,
                    low=b.low,
                    close=b.close,
                    volume=b.volume,
                    source=b.source,
                    completed=b.completed,
                    session_date=session_date_for(b.bar_start_unix),
                )
        ok, reason = b.validate()
        if not ok:
            stats["rejected"] += 1
            logger.debug("bars_5m reject %s %s: %s", b.symbol, b.bar_start_unix, reason)
            continue
        rows.append(b)

    if not rows:
        return stats

    with _conn(db_path) as conn:
        for b in rows:
            existing = conn.execute(
                "SELECT completed, source FROM bars_5m WHERE symbol=? AND bar_start_unix=?",
                (b.symbol, b.bar_start_unix),
            ).fetchone()
            if existing:
                ex_completed, ex_source = bool(existing[0]), str(existing[1] or "unknown")
                if ex_completed and not b.completed:
                    stats["skipped_incomplete_vs_complete"] += 1
                    continue
                if (
                    SOURCE_PRIORITY.get(b.source, 0)
                    < SOURCE_PRIORITY.get(ex_source, 0)
                    and ex_completed
                    and b.completed
                ):
                    stats["rejected"] += 1
                    continue
            conn.execute(
                """
                INSERT OR REPLACE INTO bars_5m(
                  symbol, bar_start_unix, session_date, open, high, low, close,
                  volume, source, completed, ingested_at_unix
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    b.symbol,
                    b.bar_start_unix,
                    b.session_date,
                    float(b.open),
                    float(b.high),
                    float(b.low),
                    float(b.close),
                    float(b.volume),
                    b.source,
                    1 if b.completed else 0,
                    now,
                ),
            )
            stats["accepted"] += 1
        conn.commit()
    return stats


def load_bars(
    symbol: str,
    *,
    completed_only: bool = True,
    session_date: str | None = None,
    start_unix: int | None = None,
    end_unix: int | None = None,
    limit: int | None = None,
    db_path: Path | None = None,
) -> pd.DataFrame:
    sym = symbol.upper().strip()
    clauses = ["symbol = ?"]
    params: list[Any] = [sym]
    if completed_only:
        clauses.append("completed = 1")
    if session_date:
        clauses.append("session_date = ?")
        params.append(session_date)
    if start_unix is not None:
        clauses.append("bar_start_unix >= ?")
        params.append(int(start_unix))
    if end_unix is not None:
        clauses.append("bar_start_unix <= ?")
        params.append(int(end_unix))
    sql = (
        f"SELECT symbol, bar_start_unix, session_date, open, high, low, close, "
        f"volume, source, completed FROM bars_5m WHERE {' AND '.join(clauses)} "
        f"ORDER BY bar_start_unix ASC"
    )
    if limit:
        sql += f" LIMIT {int(limit)}"
    with _conn(db_path) as conn:
        df = pd.read_sql_query(sql, conn, params=params)
    return df


def closes_volumes_from_df(df: pd.DataFrame) -> tuple[list[float], list[float]]:
    if df is None or df.empty:
        return [], []
    closes = [float(x) for x in df["close"].tolist()]
    vols = [float(x) for x in df["volume"].tolist()]
    return closes, vols


def retention_purge(
    *,
    retention_days: int | None = None,
    db_path: Path | None = None,
    now: datetime | None = None,
) -> int:
    days = int(
        retention_days
        if retention_days is not None
        else getattr(config, "bars_5m_retention_days", 45)
    )
    now_ist = now or datetime.now(IST)
    cutoff = (now_ist.date() - timedelta(days=days)).isoformat()
    with _conn(db_path) as conn:
        cur = conn.execute("DELETE FROM bars_5m WHERE session_date < ?", (cutoff,))
        conn.commit()
        return int(cur.rowcount or 0)


def bar_counts(*, db_path: Path | None = None) -> dict[str, Any]:
    with _conn(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM bars_5m WHERE completed=1").fetchone()[0]
        syms = conn.execute(
            "SELECT COUNT(DISTINCT symbol) FROM bars_5m WHERE completed=1"
        ).fetchone()[0]
        oldest = conn.execute(
            "SELECT MIN(session_date) FROM bars_5m WHERE completed=1"
        ).fetchone()[0]
        newest = conn.execute(
            "SELECT MAX(session_date) FROM bars_5m WHERE completed=1"
        ).fetchone()[0]
    return {
        "completed_bars": int(total or 0),
        "symbols": int(syms or 0),
        "oldest_session": oldest,
        "newest_session": newest,
        "interval": "5m",
        "timezone": "Asia/Kolkata",
    }


def bars_from_yahoo_chart_payload(
    *,
    symbol: str,
    timestamps: list[int],
    opens: list,
    highs: list,
    lows: list,
    closes: list,
    volumes: list,
    source: str = "yahoo_chart",
    now_unix: float | None = None,
    drop_incomplete: bool = True,
) -> list[Bar5m]:
    """
    Convert Yahoo chart arrays into Bar5m rows.

    Yahoo timestamps are bar *start*. The last bar may still be forming —
    drop it when ``drop_incomplete`` and now is still inside that bucket.
    """
    import time as _time

    now = float(now_unix if now_unix is not None else _time.time())
    n = min(len(timestamps), len(closes))
    out: list[Bar5m] = []
    for i in range(n):
        c = closes[i]
        if c is None:
            continue
        ts = floor_bucket(int(timestamps[i]))
        o = opens[i] if i < len(opens) and opens[i] is not None else c
        h = highs[i] if i < len(highs) and highs[i] is not None else c
        l_ = lows[i] if i < len(lows) and lows[i] is not None else c
        v = volumes[i] if i < len(volumes) and volumes[i] is not None else 0.0
        completed = True
        if drop_incomplete and i == n - 1:
            # Forming if current time is still within [start, start+300)
            if now < ts + INTERVAL_SEC:
                completed = False
        bar = Bar5m(
            symbol=symbol.upper().strip(),
            bar_start_unix=ts,
            open=float(o),
            high=float(h),
            low=float(l_),
            close=float(c),
            volume=float(v),
            source=source,
            completed=completed,
            session_date=session_date_for(ts),
        )
        ok, _ = bar.validate()
        if ok and (completed or not drop_incomplete):
            if completed:
                out.append(bar)
            # incomplete intentionally omitted for strategy store
    return out


def ingest_yahoo_chart_symbol(
    yahoo_symbol: str,
    *,
    range_: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Fetch Yahoo 5m chart and persist completed session bars."""
    from app import live_quotes

    rng = range_ or getattr(config, "bars_5m_yahoo_range", "5d")
    data = live_quotes._fetch_chart(yahoo_symbol, "5m", rng)  # noqa: SLF001
    if not data:
        return {"ok": False, "error": "chart_fetch_failed", "accepted": 0}

    # Map yahoo → desk symbol
    sym = yahoo_symbol
    if yahoo_symbol.endswith(".NS"):
        sym = yahoo_symbol[:-3]
    elif yahoo_symbol.startswith("^"):
        sym = {"^NSEI": "NIFTY", "^NSEBANK": "BANKNIFTY"}.get(
            yahoo_symbol, yahoo_symbol.lstrip("^")
        )

    ts = list(data.get("timestamp") or [])
    indicators = (data.get("indicators") or {}).get("quote") or [{}]
    q = indicators[0] if indicators else {}
    bars = bars_from_yahoo_chart_payload(
        symbol=sym,
        timestamps=ts,
        opens=list(q.get("open") or []),
        highs=list(q.get("high") or []),
        lows=list(q.get("low") or []),
        closes=list(q.get("close") or []),
        volumes=list(q.get("volume") or []),
        source="yahoo_chart",
    )
    stats = upsert_bars(bars, db_path=db_path)
    retention_purge(db_path=db_path)
    return {"ok": True, "symbol": sym, "yahoo_symbol": yahoo_symbol, **stats, "range": rng}


def persist_kotak_closed_bar(
    *,
    symbol: str,
    bar_start_unix: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float,
    db_path: Path | None = None,
) -> dict[str, int]:
    bar = Bar5m(
        symbol=symbol.upper().strip(),
        bar_start_unix=floor_bucket(bar_start_unix),
        open=float(open_),
        high=float(high),
        low=float(low),
        close=float(close),
        volume=float(volume or 0.0),
        source="kotak_neo_ws",
        completed=True,
        session_date=session_date_for(bar_start_unix),
    )
    return upsert_bars([bar], db_path=db_path)
