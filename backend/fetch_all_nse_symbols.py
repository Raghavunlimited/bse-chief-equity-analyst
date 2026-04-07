"""
Dynamically fetch ALL NSE equity symbols from various sources.
This ensures we always have the complete list of listed equities.
"""
import requests
import pandas as pd
import logging
from pathlib import Path
from datetime import datetime, timedelta
import time
import zipfile
import io

logger = logging.getLogger(__name__)

# Basic sector mapping for major stocks (will be extended dynamically)
from nse_stocks import SECTOR_MAP


def get_all_symbols_from_bhavcopy(days_back: int = 3) -> list:
    """
    Fetch ALL equity symbols from recent NSE bhavcopy.
    This is the most reliable method as it has ALL listed stocks.
    """
    BASE_URL = "https://nsearchives.nseindia.com"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "*/*",
    }

    # Try recent dates (skip weekends)
    today = datetime.now()
    symbols = set()

    for days in range(1, days_back + 7):
        trade_date = today - timedelta(days=days)

        # Skip weekends
        if trade_date.weekday() >= 5:
            continue

        date_str = trade_date.strftime("%d%b%Y").upper()
        filename = f"cm{date_str}bhav.csv.zip"

        year = trade_date.year
        month = trade_date.strftime("%b").upper()
        url = f"{BASE_URL}/content/historical/EQUITIES/{year}/{month}/{filename}"

        logger.info(f"Fetching symbols from: {url}")

        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            if response.status_code == 200:
                with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                    csv_filename = filename.replace(".zip", "")
                    csv_content = zf.read(csv_filename)

                    df = pd.read_csv(io.BytesIO(csv_content))

                    # Filter EQ series only
                    eq_df = df[df["SERIES"] == "EQ"]
                    symbols.update(eq_df["SYMBOL"].tolist())

                    logger.info(f"Found {len(eq_df)} EQ symbols from {date_str}")

                    if len(symbols) > 1500:  # We have enough
                        break

            time.sleep(0.5)

        except Exception as e:
            logger.warning(f"Failed to fetch from {date_str}: {e}")
            continue

    return sorted(list(symbols))


def get_symbols_from_nse_api() -> list:
    """
    Try to get symbols from NSE API endpoints.
    """
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
    }

    symbols = set()

    # Try equity list endpoint
    try:
        session = requests.Session()
        # First hit main page for cookies
        session.get("https://www.nseindia.com", headers=HEADERS, timeout=10)
        time.sleep(1)

        # Get all equity data
        response = session.get(
            "https://www.nseindia.com/api/equity-stockIndices?index=SECURITIES%20IN%20F%26O",
            headers=HEADERS,
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            for item in data.get("data", []):
                if "symbol" in item:
                    symbols.add(item["symbol"])

    except Exception as e:
        logger.warning(f"NSE API fetch failed: {e}")

    return sorted(list(symbols))


def get_all_nse_equity_symbols(cache_file: Path = None, max_age_hours: int = 24) -> list:
    """
    Get ALL NSE equity symbols with caching.

    Priority:
    1. Use cached file if fresh
    2. Fetch from bhavcopy (most complete)
    3. Fall back to static list
    """
    # Default cache file
    if cache_file is None:
        cache_file = Path(__file__).parent / "data" / "all_nse_symbols.txt"

    cache_file.parent.mkdir(parents=True, exist_ok=True)

    # Check cache
    if cache_file.exists():
        mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
        age = datetime.now() - mtime

        if age < timedelta(hours=max_age_hours):
            symbols = cache_file.read_text().strip().split("\n")
            logger.info(f"Using cached symbol list: {len(symbols)} symbols")
            return symbols

    # Fetch fresh list
    logger.info("Fetching fresh NSE equity symbol list...")

    symbols = get_all_symbols_from_bhavcopy()

    if len(symbols) < 1000:
        # Fallback to API
        api_symbols = get_symbols_from_nse_api()
        symbols = list(set(symbols) | set(api_symbols))

    if len(symbols) < 500:
        # Last resort: use SECTOR_MAP keys
        symbols = list(set(symbols) | set(SECTOR_MAP.keys()))

    # Remove problematic symbols
    exclude = {"SYMBOL", "", "NA", "NULL"}
    symbols = [s for s in symbols if s and s.upper() not in exclude]

    # Cache the list
    if symbols:
        cache_file.write_text("\n".join(sorted(symbols)))
        logger.info(f"Cached {len(symbols)} symbols to {cache_file}")

    return sorted(symbols)


def get_symbol_sector(symbol: str) -> str:
    """Get sector for a symbol, returns 'Unknown' if not mapped."""
    return SECTOR_MAP.get(symbol, "Unknown")


def assign_sectors_to_symbols(symbols: list) -> list:
    """
    Assign sectors to a list of symbols.
    Returns list of dicts with symbol and sector.
    """
    return [
        {"symbol": s, "sector": get_symbol_sector(s)}
        for s in symbols
    ]


# Quick test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    symbols = get_all_nse_equity_symbols()
    print(f"\nTotal NSE equity symbols: {len(symbols)}")

    # Show sector distribution
    sector_counts = {}
    for s in symbols:
        sector = get_symbol_sector(s)
        sector_counts[sector] = sector_counts.get(sector, 0) + 1

    print("\nSector distribution:")
    for sector, count in sorted(sector_counts.items(), key=lambda x: -x[1])[:15]:
        print(f"  {sector}: {count}")

    unknown_count = sector_counts.get("Unknown", 0)
    mapped_count = len(symbols) - unknown_count
    print(f"\nMapped stocks: {mapped_count}")
    print(f"Unknown sector: {unknown_count}")
