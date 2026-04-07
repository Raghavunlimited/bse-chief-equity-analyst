#!/usr/bin/env python3
"""
Download real NSE historical data for swing trading analysis.
Uses multiple data sources and methods to ensure data availability.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from datetime import datetime, timedelta
import pandas as pd
import requests
import time
import io
import zipfile
import logging
from app.store import Database
from app.config import config
from app.features import compute_indicators_for_all_symbols, extract_indicator_columns

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class NSEDataFetcher:
    """
    Fetches real NSE data using multiple methods.
    """

    # NSE Archive URLs
    ARCHIVE_URL = "https://nsearchives.nseindia.com/content/historical/EQUITIES/{year}/{month}/cm{date}bhav.csv.zip"

    # Alternative: NSE India API for live quotes
    NSE_API_BASE = "https://www.nseindia.com"

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def _init_nse_session(self):
        """Initialize NSE session with cookies"""
        try:
            # First visit NSE homepage to get cookies
            self.session.get(self.NSE_API_BASE, timeout=10)
            time.sleep(1)
        except Exception as e:
            logger.warning(f"Could not initialize NSE session: {e}")

    def download_bhavcopy(self, trade_date: datetime) -> pd.DataFrame | None:
        """
        Download NSE Bhavcopy for a specific date.
        Returns DataFrame or None if download fails.
        """
        date_str = trade_date.strftime("%d%b%Y").upper()
        year = trade_date.year
        month = trade_date.strftime("%b").upper()

        url = self.ARCHIVE_URL.format(year=year, month=month, date=date_str)

        logger.info(f"Downloading: {url}")

        try:
            response = self.session.get(url, timeout=30)

            if response.status_code == 200:
                # Extract CSV from zip
                with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                    csv_name = zf.namelist()[0]
                    with zf.open(csv_name) as f:
                        df = pd.read_csv(f)

                # Standardize columns
                df = df.rename(columns={
                    "SYMBOL": "symbol",
                    "OPEN": "open",
                    "HIGH": "high",
                    "LOW": "low",
                    "CLOSE": "close",
                    "LAST": "last",
                    "PREVCLOSE": "prev_close",
                    "TOTTRDQTY": "volume",
                    "TOTTRDVAL": "turnover",
                    "TIMESTAMP": "trade_date",
                    "SERIES": "series"
                })

                # Filter only EQ series
                df = df[df["series"] == "EQ"].copy()

                # Format date
                df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")

                # Select columns
                cols = ["symbol", "trade_date", "open", "high", "low", "close",
                        "volume", "turnover", "prev_close"]
                df = df[cols]

                logger.info(f"Downloaded {len(df)} stocks for {trade_date.strftime('%Y-%m-%d')}")
                return df

            elif response.status_code == 404:
                logger.warning(f"No data available for {trade_date.strftime('%Y-%m-%d')} (holiday or weekend)")
                return None
            else:
                logger.warning(f"HTTP {response.status_code} for {trade_date.strftime('%Y-%m-%d')}")
                return None

        except Exception as e:
            logger.error(f"Error downloading {trade_date.strftime('%Y-%m-%d')}: {e}")
            return None

    def download_historical_range(self, start_date: datetime, end_date: datetime) -> list[pd.DataFrame]:
        """Download data for a date range, skipping weekends and holidays."""
        all_data = []
        current = start_date

        # Initialize session
        self._init_nse_session()

        failed_count = 0
        max_failures = 5  # Stop if too many consecutive failures

        while current <= end_date:
            # Skip weekends
            if current.weekday() < 5:  # Monday=0, Friday=4
                df = self.download_bhavcopy(current)

                if df is not None and not df.empty:
                    all_data.append(df)
                    failed_count = 0
                else:
                    failed_count += 1
                    if failed_count >= max_failures:
                        logger.warning(f"Too many consecutive failures, stopping at {current.strftime('%Y-%m-%d')}")
                        break

                # Rate limiting: 2 seconds between requests
                time.sleep(2)

            current += timedelta(days=1)

        return all_data


def main():
    """Download real NSE data for the past 3-4 months"""
    logger.info("=" * 60)
    logger.info("NSE HISTORICAL DATA DOWNLOADER")
    logger.info("=" * 60)

    # Calculate date range (last 100 days to ensure ~70 trading days)
    end_date = datetime.now() - timedelta(days=1)  # Yesterday
    start_date = end_date - timedelta(days=120)  # ~4 months back

    logger.info(f"Downloading data from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    logger.info("This may take 5-10 minutes due to rate limiting...")
    print()

    # Initialize fetcher and database
    fetcher = NSEDataFetcher()
    db = Database(config.db_path)

    # Clear existing data for fresh start
    with db.get_connection() as conn:
        conn.execute("DELETE FROM screener_results")
        conn.execute("DELETE FROM indicators")
        conn.execute("DELETE FROM eod")
        conn.commit()
    logger.info("Cleared existing data")

    # Download historical data
    all_dfs = fetcher.download_historical_range(start_date, end_date)

    if not all_dfs:
        logger.error("No data downloaded! NSE servers may be blocking or unavailable.")
        logger.info("Trying alternative approach with known working dates...")

        # Try specific known dates from 2024
        test_dates = [
            datetime(2024, 12, 2),
            datetime(2024, 12, 3),
            datetime(2024, 12, 4),
            datetime(2024, 12, 5),
            datetime(2024, 12, 6),
        ]

        for test_date in test_dates:
            df = fetcher.download_bhavcopy(test_date)
            if df is not None:
                all_dfs.append(df)
                time.sleep(2)

    if not all_dfs:
        logger.error("Could not download any data from NSE.")
        logger.info("\nPossible reasons:")
        logger.info("1. NSE servers are blocking automated requests")
        logger.info("2. Network/firewall issues")
        logger.info("3. NSE archive URLs have changed")
        logger.info("\nAlternative: You can manually download Bhavcopy from:")
        logger.info("https://www.nseindia.com/all-reports-derivatives#702")
        return 1

    # Combine all data
    combined_df = pd.concat(all_dfs, ignore_index=True)
    logger.info(f"Total records: {len(combined_df)}")
    logger.info(f"Total trading days: {combined_df['trade_date'].nunique()}")
    logger.info(f"Total symbols: {combined_df['symbol'].nunique()}")

    # Store in database
    db.upsert_eod_data(combined_df)
    logger.info("Stored EOD data in database")

    # Compute indicators
    logger.info("Computing technical indicators...")
    with_indicators = compute_indicators_for_all_symbols(combined_df)
    indicators_df = extract_indicator_columns(with_indicators)
    db.upsert_indicators(indicators_df)
    logger.info("Indicators computed and stored")

    # Summary
    min_date, max_date = db.get_date_range()
    symbols = db.get_all_symbols()

    print()
    logger.info("=" * 60)
    logger.info("DOWNLOAD COMPLETE!")
    logger.info("=" * 60)
    logger.info(f"Date range: {min_date} to {max_date}")
    logger.info(f"Total symbols: {len(symbols)}")
    logger.info(f"Total records: {len(combined_df)}")
    print()
    logger.info("You can now run the screener: python run_weekly_screen.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
