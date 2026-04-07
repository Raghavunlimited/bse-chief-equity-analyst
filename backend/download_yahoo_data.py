#!/usr/bin/env python3
"""
Download real NSE stock data from Yahoo Finance.
More reliable than direct NSE scraping.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
import logging
import time
from app.store import Database
from app.config import config
from app.features import compute_indicators_for_all_symbols, extract_indicator_columns

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# NIFTY 500 constituents - a good universe for swing trading
# This includes large, mid, and small cap stocks
NIFTY_500_SYMBOLS = [
    # NIFTY 50 (Large Cap - Most Liquid)
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "HINDUNILVR", "SBIN", "BHARTIARTL", "ITC", "KOTAKBANK",
    "LT", "HCLTECH", "AXISBANK", "ASIANPAINT", "MARUTI",
    "SUNPHARMA", "TITAN", "BAJFINANCE", "DMART", "NTPC",
    "TATAMOTORS", "M&M", "ULTRACEMCO", "ONGC", "NESTLEIND",
    "WIPRO", "JSWSTEEL", "POWERGRID", "ADANIENT", "ADANIPORTS",
    "COALINDIA", "TATASTEEL", "HINDALCO", "BAJAJFINSV", "TECHM",
    "HDFCLIFE", "GRASIM", "DIVISLAB", "DRREDDY", "APOLLOHOSP",
    "CIPLA", "EICHERMOT", "HEROMOTOCO", "INDUSINDBK", "SBILIFE",
    "BRITANNIA", "TATACONSUM", "BPCL", "BAJAJ-AUTO", "LTIM",

    # NIFTY NEXT 50 (Mid Cap - Good Momentum Potential)
    "ADANIGREEN", "VEDL", "TRENT", "ZOMATO", "SIEMENS",
    "GODREJCP", "DABUR", "HAVELLS", "JINDALSTEL", "ICICIPRULI",
    "IOC", "DLF", "PIDILITIND", "INDIGO", "ABB",
    "BANKBARODA", "PNB", "AMBUJACEM", "COLPAL", "GAIL",
    "MARICO", "BERGEPAINT", "ICICIGI", "MCDOWELL-N", "TORNTPHARM",
    "IDEA", "IRCTC", "TATAPOWER", "MUTHOOTFIN", "PFC",
    "RECLTD", "NAUKRI", "ACC", "PIIND", "CHOLAFIN",
    "BOSCHLTD", "AUBANK", "CANBK", "HINDPETRO", "SHREECEM",
    "CONCOR", "YESBANK", "IDFCFIRSTB", "SRF", "SBICARD",

    # Additional Mid/Small Caps with High Volatility (Good for Swing Trading)
    "POLYCAB", "VOLTAS", "TATAELXSI", "PERSISTENT", "COFORGE",
    "MPHASIS", "LTTS", "LAURUSLABS", "AUROPHARMA", "BIOCON",
    "CADILAHC", "METROPOLIS", "LALPATHLAB", "JUBLFOOD", "PAGEIND",
    "DELHIVERY", "ZEEL", "PVR", "BHARATFORG", "ESCORTS",
    "ASHOKLEY", "TVSMOTOR", "BALKRISIND", "MOTHERSON", "MRF",
    "DEEPAKNTR", "ATUL", "NAVINFLUOR", "COROMANDEL", "UBL",
    "MFSL", "LICHSGFIN", "MANAPPURAM", "L&TFH", "BANDHANBNK",
    "FEDERALBNK", "RBLBANK", "CUB", "KARURVYSYA", "IDFC",
    "OBEROIRLTY", "PRESTIGE", "SOBHA", "PHOENIXLTD", "GODREJPROP",
    "ASTRAL", "SUPREMEIND", "RELAXO", "BATAINDIA", "VBL",

    # High Beta Stocks (More Volatile - Higher Swing Potential)
    "ADANIWILMAR", "ADANIPOWER", "IRFC", "RVNL", "SJVN",
    "NHPC", "NLCINDIA", "SAIL", "NMDC", "NATIONALUM",
    "HINDZINC", "APOLLOTYRE", "CEAT", "JKcement", "RAMCOCEM",
    "STAR", "SUNTV", "TV18BRDCST", "NETWORK18", "NAZARA",
    "HAPPSTMNDS", "ROUTE", "LATENTVIEW", "TANLA", "KPITTECH"
]


def download_yahoo_data(symbols: list, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Download historical data from Yahoo Finance.
    Appends .NS suffix for NSE stocks.
    """
    all_data = []
    failed_symbols = []

    total = len(symbols)
    logger.info(f"Downloading data for {total} symbols...")

    for i, symbol in enumerate(symbols):
        yf_symbol = f"{symbol}.NS"

        try:
            # Download data
            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(start=start_date, end=end_date, interval="1d")

            if df.empty:
                failed_symbols.append(symbol)
                continue

            # Reset index to get date as column
            df = df.reset_index()

            # Rename columns to match our schema
            df = df.rename(columns={
                "Date": "trade_date",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume"
            })

            # Add symbol
            df["symbol"] = symbol

            # Calculate turnover (price * volume)
            df["turnover"] = df["close"] * df["volume"]

            # Add prev_close
            df["prev_close"] = df["close"].shift(1)
            df = df.dropna(subset=["prev_close"])

            # Format date
            df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")

            # Select columns
            df = df[["symbol", "trade_date", "open", "high", "low", "close",
                     "volume", "turnover", "prev_close"]]

            all_data.append(df)

            # Progress
            if (i + 1) % 20 == 0:
                logger.info(f"Progress: {i + 1}/{total} symbols downloaded")

            # Small delay to avoid rate limiting
            time.sleep(0.1)

        except Exception as e:
            failed_symbols.append(symbol)
            continue

    if all_data:
        combined = pd.concat(all_data, ignore_index=True)
        logger.info(f"Downloaded {len(combined)} total records")
        logger.info(f"Successful: {total - len(failed_symbols)}, Failed: {len(failed_symbols)}")
        return combined
    else:
        return pd.DataFrame()


def main():
    """Download real NSE data from Yahoo Finance"""
    logger.info("=" * 60)
    logger.info("YAHOO FINANCE DATA DOWNLOADER")
    logger.info("=" * 60)

    # Calculate date range (last 120 days for ~80 trading days)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=150)  # Extra buffer for weekends/holidays

    logger.info(f"Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    logger.info(f"Symbols to download: {len(NIFTY_500_SYMBOLS)}")
    print()

    # Initialize database
    db = Database(config.db_path)

    # Clear existing data
    with db.get_connection() as conn:
        conn.execute("DELETE FROM screener_results")
        conn.execute("DELETE FROM indicators")
        conn.execute("DELETE FROM eod")
        conn.commit()
    logger.info("Cleared existing data")

    # Download data
    df = download_yahoo_data(
        NIFTY_500_SYMBOLS,
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d")
    )

    if df.empty:
        logger.error("Failed to download any data")
        return 1

    # Store in database
    logger.info("Storing data in database...")
    db.upsert_eod_data(df)

    # Compute indicators
    logger.info("Computing technical indicators (this may take a minute)...")
    with_indicators = compute_indicators_for_all_symbols(df)
    indicators_df = extract_indicator_columns(with_indicators)
    db.upsert_indicators(indicators_df)

    # Summary
    min_date, max_date = db.get_date_range()
    symbols = db.get_all_symbols()
    trading_days = df["trade_date"].nunique()

    print()
    logger.info("=" * 60)
    logger.info("DOWNLOAD COMPLETE!")
    logger.info("=" * 60)
    logger.info(f"Date range: {min_date} to {max_date}")
    logger.info(f"Trading days: {trading_days}")
    logger.info(f"Total symbols: {len(symbols)}")
    logger.info(f"Total records: {len(df):,}")
    print()
    logger.info("Now run the screener: python run_weekly_screen.py")
    logger.info("Or view in web app: http://localhost:3000")

    return 0


if __name__ == "__main__":
    sys.exit(main())
