#!/usr/bin/env python3
"""
Daily data ingestion script.
Run this script daily (or use cron) to download and process latest NSE data.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.config import config
from app.store import Database
from app.ingest import NSEDataIngester
from app.features import compute_indicators_for_all_symbols, extract_indicator_columns
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """Run daily data ingestion"""
    logger.info("Starting daily data ingestion...")

    # Initialize components
    db = Database(config.db_path)
    ingester = NSEDataIngester(config.cache_dir, config.raw_dir)

    # Get latest trading day
    trade_date = ingester.get_latest_trading_day()
    logger.info(f"Fetching data for {trade_date.strftime('%Y-%m-%d')}")

    # Download bhavcopy
    csv_path = ingester.download_bhavcopy(trade_date)

    if not csv_path:
        logger.error(f"Failed to download data for {trade_date}")
        return 1

    # Load and store EOD data
    df = ingester.load_bhavcopy_csv(csv_path)
    records = db.upsert_eod_data(df)
    logger.info(f"Stored {records} EOD records")

    # Compute and store indicators
    logger.info("Computing indicators...")
    import pandas as pd
    with db.get_connection() as conn:
        all_data = pd.read_sql_query("SELECT * FROM eod ORDER BY symbol, trade_date", conn)

    with_indicators = compute_indicators_for_all_symbols(all_data)
    indicators_df = extract_indicator_columns(with_indicators)
    db.upsert_indicators(indicators_df)

    logger.info("Daily ingestion complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
