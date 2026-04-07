from __future__ import annotations
import sqlite3
from pathlib import Path
import pandas as pd
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

DB_SCHEMA = """
-- EOD price data
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

-- Computed indicators
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
  PRIMARY KEY(symbol, trade_date),
  FOREIGN KEY(symbol, trade_date) REFERENCES eod(symbol, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_indicators_date ON indicators(trade_date);

-- Screener results
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

CREATE INDEX IF NOT EXISTS idx_screener_date ON screener_results(screening_date);
CREATE INDEX IF NOT EXISTS idx_screener_score ON screener_results(score DESC);
"""


class Database:
    """SQLite database manager for NSE swing trader"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database schema"""
        with self.get_connection() as conn:
            conn.executescript(DB_SCHEMA)
            logger.info(f"Database initialized at {self.db_path}")

    def get_connection(self) -> sqlite3.Connection:
        """Get database connection with WAL mode enabled"""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def upsert_eod_data(self, df: pd.DataFrame) -> int:
        """
        Insert or replace EOD data.
        Returns number of rows inserted.
        """
        if df.empty:
            return 0

        records = df.to_dict("records")

        with self.get_connection() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO eod(
                    symbol, trade_date, open, high, low, close,
                    volume, turnover, prev_close
                )
                VALUES (
                    :symbol, :trade_date, :open, :high, :low, :close,
                    :volume, :turnover, :prev_close
                )
                """,
                records
            )
            conn.commit()

        logger.info(f"Upserted {len(records)} EOD records")
        return len(records)

    def upsert_indicators(self, df: pd.DataFrame) -> int:
        """Insert or replace computed indicators"""
        if df.empty:
            return 0

        records = df.to_dict("records")

        with self.get_connection() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO indicators(
                    symbol, trade_date, sma_20, sma_50, rsi_14, atr_14,
                    vol_ma_20, hh_20, ll_20
                )
                VALUES (
                    :symbol, :trade_date, :sma_20, :sma_50, :rsi_14, :atr_14,
                    :vol_ma_20, :hh_20, :ll_20
                )
                """,
                records
            )
            conn.commit()

        logger.info(f"Upserted {len(records)} indicator records")
        return len(records)

    def save_screener_results(self, df: pd.DataFrame, screening_date: str) -> int:
        """Save screener results for a specific date"""
        if df.empty:
            return 0

        df = df.copy()
        df["screening_date"] = screening_date
        records = df.to_dict("records")

        with self.get_connection() as conn:
            # Delete old results for this date
            conn.execute(
                "DELETE FROM screener_results WHERE screening_date = ?",
                (screening_date,)
            )

            # Insert new results
            conn.executemany(
                """
                INSERT INTO screener_results(
                    symbol, screening_date, score, close_price, entry_price,
                    stop_loss, target_price, risk_reward, position_size, metadata
                )
                VALUES (
                    :symbol, :screening_date, :score, :close_price, :entry_price,
                    :stop_loss, :target_price, :risk_reward, :position_size, :metadata
                )
                """,
                records
            )
            conn.commit()

        logger.info(f"Saved {len(records)} screener results for {screening_date}")
        return len(records)

    def get_eod_data(self, symbol: str = None, start_date: str = None,
                     end_date: str = None, limit: int = None) -> pd.DataFrame:
        """Fetch EOD data with optional filters"""
        query = "SELECT * FROM eod WHERE 1=1"
        params = []

        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        if start_date:
            query += " AND trade_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND trade_date <= ?"
            params.append(end_date)

        query += " ORDER BY trade_date DESC"

        if limit:
            query += f" LIMIT {limit}"

        with self.get_connection() as conn:
            return pd.read_sql_query(query, conn, params=params)

    def get_latest_screener_results(self, limit: int = 20) -> pd.DataFrame:
        """Get latest screener results"""
        query = """
        SELECT * FROM screener_results
        WHERE screening_date = (SELECT MAX(screening_date) FROM screener_results)
        ORDER BY score DESC
        LIMIT ?
        """

        with self.get_connection() as conn:
            return pd.read_sql_query(query, conn, params=(limit,))

    def get_all_symbols(self) -> list[str]:
        """Get list of all symbols in database"""
        query = "SELECT DISTINCT symbol FROM eod ORDER BY symbol"

        with self.get_connection() as conn:
            cursor = conn.execute(query)
            return [row[0] for row in cursor.fetchall()]

    def get_date_range(self) -> tuple[str | None, str | None]:
        """Get min and max dates available in database"""
        query = "SELECT MIN(trade_date), MAX(trade_date) FROM eod"

        with self.get_connection() as conn:
            cursor = conn.execute(query)
            return cursor.fetchone()
