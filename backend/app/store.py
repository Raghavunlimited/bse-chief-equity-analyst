"""SQLite storage for EOD prices and indicators."""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS eod (
  symbol TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  open REAL,
  high REAL,
  low REAL,
  close REAL,
  volume REAL,
  turnover REAL,
  prev_close REAL,
  PRIMARY KEY(symbol, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_eod_date ON eod(trade_date);
CREATE INDEX IF NOT EXISTS idx_eod_symbol ON eod(symbol);

CREATE TABLE IF NOT EXISTS indicators (
  symbol TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  sma_20 REAL,
  sma_50 REAL,
  rsi_14 REAL,
  atr_14 REAL,
  vol_ma_20 REAL,
  hh_20 REAL,
  ll_20 REAL,
  roc_3 REAL,
  roc_20 REAL,
  prev_volume REAL,
  PRIMARY KEY(symbol, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_indicators_date ON indicators(trade_date);

CREATE TABLE IF NOT EXISTS screener_results (
  symbol TEXT NOT NULL,
  screening_date TEXT NOT NULL,
  score REAL,
  close_price REAL,
  entry_price REAL,
  stop_loss REAL,
  target_price REAL,
  risk_reward REAL,
  position_size INT,
  metadata TEXT,
  PRIMARY KEY(symbol, screening_date)
);

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


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with self.get_connection() as conn:
            conn.executescript(DB_SCHEMA)
            # Migrate older DBs missing new indicator columns
            cols = {
                row[1]
                for row in conn.execute("PRAGMA table_info(indicators)").fetchall()
            }
            for col, typedef in [
                ("roc_3", "REAL"),
                ("roc_20", "REAL"),
                ("prev_volume", "REAL"),
            ]:
                if col not in cols:
                    conn.execute(f"ALTER TABLE indicators ADD COLUMN {col} {typedef}")
            conn.commit()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def upsert_eod_data(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        records = df.to_dict("records")
        with self.get_connection() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO eod(
                    symbol, trade_date, open, high, low, close,
                    volume, turnover, prev_close
                ) VALUES (
                    :symbol, :trade_date, :open, :high, :low, :close,
                    :volume, :turnover, :prev_close
                )
                """,
                records,
            )
            conn.commit()
        logger.info("Upserted %s EOD rows", len(records))
        return len(records)

    def purge_eod_after(self, max_trade_date: str) -> int:
        """Drop residual rows (e.g. synthetic demo) newer than live feed coverage."""
        with self.get_connection() as conn:
            cur = conn.execute("DELETE FROM eod WHERE trade_date > ?", (max_trade_date,))
            n1 = cur.rowcount
            cur = conn.execute(
                "DELETE FROM indicators WHERE trade_date > ?", (max_trade_date,)
            )
            n2 = cur.rowcount
            conn.commit()
        logger.info(
            "Purged %s EOD + %s indicator rows after %s", n1, n2, max_trade_date
        )
        return n1 + n2

    def upsert_indicators(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        needed = [
            "symbol",
            "trade_date",
            "sma_20",
            "sma_50",
            "rsi_14",
            "atr_14",
            "vol_ma_20",
            "hh_20",
            "ll_20",
            "roc_3",
            "roc_20",
            "prev_volume",
        ]
        for c in needed:
            if c not in df.columns:
                df[c] = None
        records = df[needed].to_dict("records")
        with self.get_connection() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO indicators(
                    symbol, trade_date, sma_20, sma_50, rsi_14, atr_14,
                    vol_ma_20, hh_20, ll_20, roc_3, roc_20, prev_volume
                ) VALUES (
                    :symbol, :trade_date, :sma_20, :sma_50, :rsi_14, :atr_14,
                    :vol_ma_20, :hh_20, :ll_20, :roc_3, :roc_20, :prev_volume
                )
                """,
                records,
            )
            conn.commit()
        return len(records)

    def get_eod_data(
        self,
        symbol: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        query = "SELECT * FROM eod WHERE 1=1"
        params: list = []
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        if start_date:
            query += " AND trade_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND trade_date <= ?"
            params.append(end_date)
        query += " ORDER BY trade_date ASC"
        if limit:
            query += f" LIMIT {int(limit)}"
        with self.get_connection() as conn:
            return pd.read_sql_query(query, conn, params=params)

    def get_all_symbols(self) -> list[str]:
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT symbol FROM eod WHERE symbol != 'NIFTY' ORDER BY symbol"
            ).fetchall()
            return [r[0] for r in rows]

    def get_date_range(self) -> tuple[str | None, str | None]:
        with self.get_connection() as conn:
            return conn.execute(
                "SELECT MIN(trade_date), MAX(trade_date) FROM eod WHERE symbol != 'NIFTY'"
            ).fetchone()

    def get_max_trade_date(self) -> str | None:
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT MAX(trade_date) FROM eod WHERE symbol != 'NIFTY'"
            ).fetchone()
            return row[0] if row else None

    def get_trading_dates(self, end_date: str | None = None) -> list[str]:
        query = "SELECT DISTINCT trade_date FROM eod WHERE symbol != 'NIFTY'"
        params: list = []
        if end_date:
            query += " AND trade_date <= ?"
            params.append(end_date)
        query += " ORDER BY trade_date"
        with self.get_connection() as conn:
            return [r[0] for r in conn.execute(query, params).fetchall()]

    def freshness(
        self,
        max_age_days: int = 3,
        *,
        now: datetime | None = None,
    ) -> dict:
        """
        EOD freshness vs expected trading session (holiday-aware).

        ``age_days`` is trading-day age vs ``expected_eod_as_of`` (not raw weekdays).
        """
        from app.nse_calendar import (
            calendar_public_status,
            expected_eod_as_of,
            load_holiday_dates,
            trading_days_between,
        )
        from zoneinfo import ZoneInfo

        IST = ZoneInfo("Asia/Kolkata")
        latest = self.get_max_trade_date()
        holidays, meta = load_holiday_dates()
        dt = now.astimezone(IST) if now is not None else datetime.now(IST)
        expected = expected_eod_as_of(dt, holidays=holidays)
        cal = calendar_public_status(now=dt)

        if not latest:
            return {
                "status": "EMPTY",
                "latest_date": None,
                "expected_as_of": expected.isoformat(),
                "age_days": None,
                "age_unit": "trading_days",
                "holiday_calendar_applied": meta.applied,
                "holiday_list_complete": meta.complete,
                "calendar": cal,
                "message": "No EOD data. Run Refresh / Force full or wait for scheduled ingest.",
            }

        latest_d = datetime.strptime(latest, "%Y-%m-%d").date()
        if latest_d >= expected:
            age = 0
        else:
            age = trading_days_between(latest_d, expected, holidays=holidays)

        if age <= 1:
            status = "FRESH"
        elif age <= max_age_days:
            status = "RECENT"
        else:
            status = "STALE"

        incomplete_note = ""
        if not meta.complete:
            incomplete_note = (
                " Holiday list incomplete/missing — weekday holidays may be wrong."
            )

        return {
            "status": status,
            "latest_date": latest,
            "expected_as_of": expected.isoformat(),
            "age_days": age,
            "age_unit": "trading_days",
            "holiday_calendar_applied": meta.applied,
            "holiday_list_complete": meta.complete,
            "calendar": cal,
            "message": (
                f"Latest EOD {latest}; expected {expected.isoformat()} "
                f"({age} trading day(s) behind) — {status}.{incomplete_note}"
            ),
        }

    def get_joined_snapshot(self, as_of: str) -> pd.DataFrame:
        """EOD + indicators for all symbols on as_of date (excl. NIFTY)."""
        query = """
        SELECT e.*, i.sma_20, i.sma_50, i.rsi_14, i.atr_14, i.vol_ma_20,
               i.hh_20, i.ll_20, i.roc_3, i.roc_20, i.prev_volume
        FROM eod e
        JOIN indicators i ON e.symbol = i.symbol AND e.trade_date = i.trade_date
        WHERE e.trade_date = ? AND e.symbol != 'NIFTY'
        """
        with self.get_connection() as conn:
            return pd.read_sql_query(query, conn, params=(as_of,))

    def get_nifty_series(self, end_date: str | None = None, lookback: int = 80) -> pd.DataFrame:
        query = "SELECT * FROM eod WHERE symbol = 'NIFTY'"
        params: list = []
        if end_date:
            query += " AND trade_date <= ?"
            params.append(end_date)
        query += " ORDER BY trade_date DESC LIMIT ?"
        params.append(lookback)
        with self.get_connection() as conn:
            df = pd.read_sql_query(query, conn, params=params)
        if df.empty:
            return df
        return df.sort_values("trade_date").reset_index(drop=True)

    def get_symbol_history(
        self, symbol: str, end_date: str | None = None, lookback: int = 80
    ) -> pd.DataFrame:
        query = "SELECT * FROM eod WHERE symbol = ?"
        params: list = [symbol]
        if end_date:
            query += " AND trade_date <= ?"
            params.append(end_date)
        query += " ORDER BY trade_date DESC LIMIT ?"
        params.append(lookback)
        with self.get_connection() as conn:
            df = pd.read_sql_query(query, conn, params=params)
        return df.sort_values("trade_date").reset_index(drop=True) if not df.empty else df

    def stats_overview(self) -> dict:
        with self.get_connection() as conn:
            symbols = conn.execute(
                "SELECT COUNT(DISTINCT symbol) FROM eod WHERE symbol != 'NIFTY'"
            ).fetchone()[0]
            rows = conn.execute("SELECT COUNT(*) FROM eod").fetchone()[0]
            mn, mx = conn.execute(
                "SELECT MIN(trade_date), MAX(trade_date) FROM eod WHERE symbol != 'NIFTY'"
            ).fetchone()
        try:
            from app.universe_nse import coverage_stats

            coverage = coverage_stats(self.get_all_symbols())
        except Exception:
            coverage = {
                "exchange": "NSE",
                "listed_eq_approx": None,
                "in_database": symbols,
                "note": "NSE liquid equities",
            }
        return {
            "symbol_count": symbols,
            "row_count": rows,
            "min_date": mn,
            "max_date": mx,
            "coverage": coverage,
            "ingest_cap": None,
        }
