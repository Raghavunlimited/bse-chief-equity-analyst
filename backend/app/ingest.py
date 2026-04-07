from __future__ import annotations
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import requests
import time
import zipfile
import io
import logging

logger = logging.getLogger(__name__)

class NSEDataIngester:
    """
    Downloads NSE Bhavcopy data without relying on external libraries.
    Uses NSE's official archive endpoints.
    """

    BASE_URL = "https://nsearchives.nseindia.com"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.nseindia.com/",
        "Connection": "keep-alive",
    }

    def __init__(self, cache_dir: Path, raw_dir: Path):
        self.cache_dir = cache_dir
        self.raw_dir = raw_dir
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self._session_initialized = False

        # Create directories
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
    
    def _init_session(self):
        """Initialize session by visiting NSE to get cookies"""
        if self._session_initialized:
            return
        try:
            logger.info("Initializing NSE session...")
            self.session.get("https://www.nseindia.com", timeout=10)
            time.sleep(2)
            self.session.get("https://www.nseindia.com/market-data/live-equity-market", timeout=10)
            time.sleep(1)
            self._session_initialized = True
            logger.info("NSE session initialized with cookies")
        except Exception as e:
            logger.warning(f"Could not initialize NSE session: {e}")

    def download_bhavcopy(self, trade_date: datetime) -> Path | None:
        """
        Downloads NSE Equity Bhavcopy for the given date.
        Format: cm{DD}{MMM}{YYYY}bhav.csv.zip
        Example: cm03FEB2026bhav.csv.zip
        """
        self._init_session()  # Ensure session is initialized with cookies
        
        date_str = trade_date.strftime("%d%b%Y").upper()
        filename = f"cm{date_str}bhav.csv.zip"

        # NSE archive URL structure
        year = trade_date.year
        month = trade_date.strftime("%b").upper()
        url = f"{self.BASE_URL}/content/historical/EQUITIES/{year}/{month}/{filename}"

        logger.info(f"Downloading bhavcopy from: {url}")

        try:
            # Add delay to respect rate limits
            time.sleep(1)

            response = self.session.get(url, timeout=30)
            
            # Check if we got HTML error page instead of ZIP
            if response.status_code == 200 and response.content[:4] != b'PK\x03\x04':
                logger.error(f"Got HTML page instead of ZIP for {trade_date}")
                return None
            
            response.raise_for_status()

            # Save zip file
            zip_path = self.cache_dir / filename
            zip_path.write_bytes(response.content)

            # Extract CSV
            with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                csv_filename = filename.replace(".zip", "")
                csv_content = zf.read(csv_filename)

                csv_path = self.raw_dir / csv_filename
                csv_path.write_bytes(csv_content)

                logger.info(f"Saved bhavcopy to: {csv_path}")
                return csv_path

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download bhavcopy for {trade_date}: {e}")
            return None

    def load_bhavcopy_csv(self, path: Path) -> pd.DataFrame:
        """Load and standardize bhavcopy CSV"""
        df = pd.read_csv(path)

        # Standardize column names
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
            "SERIES": "series",
            "TOTALTRADES": "trades"
        })

        # Filter only EQ series (equity)
        df = df[df["series"] == "EQ"].copy()

        # Convert trade_date to standard format
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")

        # Select relevant columns
        columns = ["symbol", "trade_date", "open", "high", "low", "close",
                   "volume", "turnover", "prev_close"]
        return df[columns]

    def get_latest_trading_day(self) -> datetime:
        """
        Get the latest trading day (handles weekends).
        Goes back from today to find the most recent weekday.
        """
        # Start from yesterday (since today's data may not be available yet)
        candidate = datetime.now() - timedelta(days=1)

        # Keep going back until we find a weekday (Mon=0 to Fri=4)
        while candidate.weekday() >= 5:  # 5=Saturday, 6=Sunday
            candidate -= timedelta(days=1)

        return candidate

    def download_historical_range(self, start_date: datetime, end_date: datetime) -> list[Path]:
        """Download bhavcopy for a date range"""
        paths = []
        current = start_date

        while current <= end_date:
            # Skip weekends
            if current.weekday() < 5:
                path = self.download_bhavcopy(current)
                if path:
                    paths.append(path)
                # Rate limiting: 1 request per second
                time.sleep(1)

            current += timedelta(days=1)

        return paths
