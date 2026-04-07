#!/usr/bin/env python3
"""
Weekly screening script.
Run this script weekly to generate swing trade candidates.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.config import config
from app.store import Database
from app.screener import run_screener
from app.features import get_latest_snapshot_per_symbol
import pandas as pd
import logging
import json

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """Run weekly screening"""
    logger.info("Starting weekly swing screener...")

    # Initialize database
    db = Database(config.db_path)

    # Get latest data with indicators
    query = """
    SELECT e.symbol, e.trade_date, e.open, e.high, e.low, e.close,
           e.volume, e.turnover, e.prev_close,
           i.sma_20, i.sma_50, i.rsi_14, i.atr_14, i.vol_ma_20, i.hh_20, i.ll_20
    FROM eod e
    JOIN indicators i ON e.symbol = i.symbol AND e.trade_date = i.trade_date
    WHERE e.trade_date = (SELECT MAX(trade_date) FROM eod)
    """

    with db.get_connection() as conn:
        df = pd.read_sql_query(query, conn)

    if df.empty:
        logger.error("No data available. Please run data ingestion first.")
        return 1

    screening_date = df.iloc[0]["trade_date"]
    logger.info(f"Screening data from {screening_date}")

    # Get latest snapshot per symbol
    latest = get_latest_snapshot_per_symbol(df)

    # Run screener
    results = run_screener(latest, top_n=20, capital_per_trade=100000)

    if results.empty:
        logger.info("No candidates found matching criteria")
        print("\n" + "="*80)
        print("NO SWING TRADE CANDIDATES FOUND")
        print("="*80)
        return 0

    # Save to database
    db.save_screener_results(results, screening_date)

    # Display results
    print("\n" + "="*80)
    print(f"WEEKLY SWING TRADE CANDIDATES - {screening_date}")
    print("="*80)
    print()

    for idx, row in results.iterrows():
        metadata = json.loads(row["metadata"])

        print(f"#{idx + 1}. {row['symbol']}")
        print(f"   Score: {row['score']:.1f}/8")
        print(f"   Current Price: ₹{row['close_price']:.2f}")
        print(f"   Entry: ₹{row['entry_price']:.2f}")
        print(f"   Stop Loss: ₹{row['stop_loss']:.2f} (-{metadata['risk_pct']:.2f}%)")
        print(f"   Target: ₹{row['target_price']:.2f} (+{metadata['expected_gain_pct']:.2f}%)")
        print(f"   Risk:Reward = 1:{row['risk_reward']:.2f}")
        print(f"   Position Size: {row['position_size']} shares")
        print(f"   RSI: {metadata['rsi_14']:.1f} | ATR: {metadata['atr_pct']:.2f}%")
        print()

    print("="*80)
    print(f"Total candidates: {len(results)}")
    print("="*80)

    logger.info("Screening complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
