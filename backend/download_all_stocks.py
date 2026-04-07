#!/usr/bin/env python3
"""
Download complete NSE stock list and refresh data for all stocks.
This script downloads all NSE-listed stocks and then fetches their data.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.store import Database
from app.config import config
from app.advanced_screener import add_advanced_indicators, run_advanced_screener
from nse_stocks import SECTOR_MAP

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_nse_stock_list():
    """
    Get list of all NSE stocks from various sources.
    Returns list of stock symbols.
    """
    all_symbols = set()

    # Method 1: NIFTY 500 constituents (from Yahoo Finance)
    nifty500_symbols = [
        # NIFTY 50
        "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "BHARTIARTL", "INFY", "SBIN",
        "ITC", "HINDUNILVR", "LT", "KOTAKBANK", "AXISBANK", "BAJFINANCE", "MARUTI",
        "ASIANPAINT", "HCLTECH", "SUNPHARMA", "TITAN", "NTPC", "ONGC",
        "TATAMOTORS", "POWERGRID", "M&M", "ULTRACEMCO", "ADANIENT", "ADANIPORTS",
        "BAJAJFINSV", "WIPRO", "JSWSTEEL", "TATASTEEL", "COALINDIA", "NESTLEIND",
        "GRASIM", "BRITANNIA", "HINDALCO", "TECHM", "DIVISLAB", "DRREDDY",
        "CIPLA", "EICHERMOT", "BPCL", "TATACONSUM", "APOLLOHOSP", "INDUSINDBK",
        "SBILIFE", "HDFCLIFE", "BAJAJ-AUTO", "HEROMOTOCO", "VEDL", "ADANIGREEN",

        # NIFTY NEXT 50
        "GODREJCP", "DABUR", "MARICO", "PIDILITIND", "BERGEPAINT", "HAVELLS",
        "SIEMENS", "ABB", "CUMMINSIND", "VOLTAS", "CROMPTON", "POLYCAB",
        "DLF", "GODREJPROP", "OBEROIRLTY", "PRESTIGE", "SOBHA", "PHOENIXLTD",
        "TORNTPHARM", "AUROPHARMA", "BIOCON", "LAURUSLABS", "ALKEM", "LUPIN",
        "ZYDUSLIFE", "MANKIND", "NAUKRI", "DMART", "TRENT", "ABFRL",
        "COLPAL", "PAGEIND", "JUBLFOOD", "MCDOWELL-N", "UBL", "VBL",
        "NHPC", "SJVN", "TATAPOWER", "RECLTD", "PFC", "IRFC",
        "INDIGO", "IRCTC", "CONCOR", "ADANIPORTS", "BHARATFORG", "MOTHERSON",

        # NIFTY MIDCAP 100 additions
        "PERSISTENT", "COFORGE", "MPHASIS", "LTIM", "LTTS", "KPITTECH",
        "TATAELXSI", "HAPPSTMNDS", "LATENTVIEW", "TANLA", "ROUTE",
        "CHOLAFIN", "MUTHOOTFIN", "MANAPPURAM", "LICHSGFIN", "SHRIRAMFIN",
        "AUBANK", "IDFCFIRSTB", "FEDERALBNK", "BANDHANBNK", "RBLBANK",
        "PNB", "CANBK", "BANKBARODA", "UNIONBANK", "INDIANB", "IOB",
        "RAMCOCEM", "DALMIACEM", "JKCEMENT", "BIRLACORPN", "INDIACEM",
        "ACC", "AMBUJACEM", "SHREECEM", "NUVOCO",
        "JINDALSTEL", "NMDC", "SAIL", "NATIONALUM", "HINDZINC", "MOIL",
        "PETRONET", "IGL", "MGL", "GAIL", "OIL", "MRPL",
        "SRF", "PIIND", "ATUL", "NAVINFLUOR", "DEEPAKNTR", "TATACHEM",
        "COROMANDEL", "UPL", "RALLIS", "GNFC", "GSFC", "CHAMBALFERT",
        "EXIDEIND", "AMARAJABAT", "BOSCHLTD", "MRF", "BALKRISIND", "APOLLOTYRE",
        "CEATLTD", "SUNDRMFAST", "SCHAEFFLER", "TIMKEN", "SKFINDIA",
        "ESCORTS", "ASHOKLEY", "TVSMOTOR", "FORCEMOT",
        "KAJARIACER", "SOMANYCERA", "CENTURYPLY", "GREENPANEL",
        "ASTRAL", "SUPREMEIND", "KEI", "POLYCAB", "FINOLEX",
        "HAL", "BEL", "BDL", "BEML", "COCHINSHIP", "GRSE", "MDL",
        "RVNL", "IRCON", "RITES", "ENGINERSIN", "NBCC", "NCC",
        "KNRCON", "ASHOKA", "PNCINFRA", "HGINFRA", "IRB",
        "BRIGADE", "MAHLIFE", "LODHA", "SUNTECK", "ANANTRAJ",
        "MCX", "BSE", "CDSL", "CAMS", "KFINTECH", "ANGELONE",
        "ZOMATO", "PAYTM", "NYKAA", "POLICYBZR",
        "LICI", "GICRE", "NIACL", "STAR", "ICICIGI", "ICICIPRULI",
        "MAXHEALTH", "FORTIS", "MEDANTA", "KIMS", "ASTER",
        "LALPATHLAB", "METROPOLIS", "THYROCARE", "KRSNAA",
        "DIXON", "AMBER", "KALYANKJIL", "SENCO",
        "RAYMOND", "ARVIND", "WELSPUNIND", "TRIDENT", "KPR",
        "BLUEDART", "DELHIVERY", "ALLCARGO", "TCI", "GESHIP",
        "SUNTV", "ZEEL", "PVR", "SAREGAMA", "TIPS", "NAZARA",
        "BHARTIARTL", "IDEA", "TATACOMM", "INDUSTOWER",
        "DEVYANI", "WESTLIFE", "SAPPHIRE",

        # NIFTY SMALLCAP 250 additions
        "GRINDWELL", "CARBORUNIV", "HEG", "GRAPHITE", "AIAENG",
        "JKPAPER", "TNPL", "UFLEX", "HUHTAMAKI",
        "WELCORP", "RATNAMANI", "APLAPOLLO", "JINDALSAW",
        "DCBBANK", "KARURVYSYA", "CITYUNIONB", "SOUTHBANK", "JKBANK",
        "EQUITASBNK", "UJJIVANSFB", "CREDITACC", "APTUS", "AAVAS", "HOMEFIRST",
        "NATCOPHARMA", "GRANULES", "GLENMARK", "IPCA", "ABBOTINDIA",
        "PFIZER", "GLAXO", "SANOFI", "JBPHARMA", "AJANTPHARM", "ERIS",
        "NIITLTD", "CYIENT", "SONATSOFTW", "NEWGEN", "INTELLECT", "MASTEK",
        "ECLERX", "ZENSAR", "BIRLASOFT", "RATEGAIN", "FSL", "DATAPATTNS",
        "ENDURANCE", "SUPRAJIT", "GABRIEL", "LUMAXTECH", "UNOMINDA",
        "ELGIEQUIP", "TRIVENI", "THERMAX", "KALPATPOWR", "KEC",
        "ORIENTELEC", "BAJAJELEC", "SYMPHONY", "BLUESTARCO", "WHIRLPOOL",
        "RADICO", "BAJAJCON", "EMAMILTD", "JYOTHYLABS",
        "HATSUN", "PARAG", "BIKAJI", "GODFRYPHLP",
        "RELAXO", "BATAINDIA", "BATA", "VMART", "SHOPERSTOP",
        "SUZLON", "INOXWIND", "GIPCL", "SJVN",
        "MAPMYINDIA", "AFFLE", "INDIAMART", "JUSTDIAL",
        "MOTILALOFS", "EDELWEISS", "GEOJITFSL", "IIFL",
        "HUDCO", "ABSLAMC", "NSDL", "CRISIL",
        "IDEAFORGE", "PARAS", "DATAPATTNS", "TATATECH",
        "RAINBOW", "YATHARTH", "SHALBY", "VIJAYA",
        "JSWENERGY", "CESC", "TORNTPOWER", "NLCINDIA",
        "FACT", "RCF", "NFL", "GUJALKALI",
        "CLEAN", "FINEORG", "VINATIORGA", "GALAXYSURF", "AARTI",
        "ALKYLAMINE", "NEOGEN", "NOCIL", "PHILIPCARB", "SUDARSCHEM",
        "DHANUKA", "SUMICHEM", "BAYERCROP", "INSECTICID",
        "KOLTEPATIL", "RUSTOMJEE", "IBREALEST",
        "OLECTRA", "GREAVES", "VSTTILLERS",
        "TCPLPACK", "EPACK",
        "NETWORK18", "TV18BRDCST", "DELTACORP",
        "SPICEJET", "GMRAIRPORT",
        "GODREJIND", "MAHINDCIE", "VGUARD",
        "MIDHANI",
    ]

    all_symbols.update(nifty500_symbols)

    # Add symbols from our comprehensive sector map
    all_symbols.update(SECTOR_MAP.keys())

    # Clean up symbols
    all_symbols = {s.strip().upper() for s in all_symbols if s and len(s) > 0}

    return sorted(list(all_symbols))


def download_stock_data(symbol, start_date, end_date):
    """Download data for a single stock."""
    try:
        yf_symbol = f"{symbol}.NS"
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(start=start_date, end=end_date, interval="1d")

        if df.empty:
            return None, symbol

        df = df.reset_index()
        df["symbol"] = symbol
        df["sector"] = SECTOR_MAP.get(symbol, "Other")

        df = df.rename(columns={
            "Date": "trade_date", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume"
        })

        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
        df["turnover"] = df["close"] * df["volume"]
        df["prev_close"] = df["close"].shift(1)
        df = df.dropna(subset=["prev_close"])

        return df, None

    except Exception as e:
        return None, symbol


def download_all_stocks(symbols, days=150, max_workers=10):
    """
    Download data for all stocks using parallel execution.
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    logger.info(f"Downloading {len(symbols)} stocks from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

    all_data = []
    failed = []

    # Download NIFTY 50 index first
    logger.info("Downloading NIFTY 50 index...")
    try:
        nifty = yf.Ticker("^NSEI")
        nifty_df = nifty.history(start=start_date, end=end_date, interval="1d")
        nifty_df = nifty_df.reset_index()
        nifty_df["symbol"] = "NIFTY50"
        nifty_df = nifty_df.rename(columns={
            "Date": "trade_date", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume"
        })
        nifty_df["trade_date"] = pd.to_datetime(nifty_df["trade_date"]).dt.strftime("%Y-%m-%d")
        nifty_df["turnover"] = nifty_df["close"] * nifty_df["volume"]
        nifty_df["prev_close"] = nifty_df["close"].shift(1)
        logger.info(f"NIFTY 50: {len(nifty_df)} days downloaded")
    except Exception as e:
        logger.error(f"Failed to download NIFTY 50: {e}")
        nifty_df = pd.DataFrame()

    # Download stocks in parallel
    logger.info(f"Starting parallel download with {max_workers} workers...")

    completed = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(download_stock_data, symbol, start_date, end_date): symbol
            for symbol in symbols
        }

        for future in as_completed(futures):
            symbol = futures[future]
            completed += 1

            try:
                df, error = future.result()
                if df is not None and not df.empty:
                    all_data.append(df)
                if error:
                    failed.append(error)
            except Exception as e:
                failed.append(symbol)

            if completed % 50 == 0:
                logger.info(f"Progress: {completed}/{len(symbols)} ({len(all_data)} successful, {len(failed)} failed)")

    if all_data:
        combined = pd.concat(all_data, ignore_index=True)
        logger.info(f"Downloaded {len(combined)} records for {len(all_data)} symbols")
        logger.info(f"Failed symbols: {len(failed)}")
        return combined, nifty_df, failed
    else:
        return pd.DataFrame(), nifty_df, failed


def compute_relative_strength(stock_df, nifty_df):
    """Calculate relative strength of each stock vs NIFTY"""
    if nifty_df.empty:
        stock_df["relative_strength"] = 1.0
        return stock_df

    nifty_returns = nifty_df.set_index("trade_date")["close"].pct_change()

    result_dfs = []
    for symbol, group in stock_df.groupby("symbol"):
        group = group.sort_values("trade_date").copy()
        stock_returns = group.set_index("trade_date")["close"].pct_change()

        stock_cum = (1 + stock_returns).rolling(20).apply(lambda x: x.prod() - 1)
        nifty_cum = (1 + nifty_returns).rolling(20).apply(lambda x: x.prod() - 1)

        rs = stock_cum / nifty_cum.reindex(stock_cum.index)
        rs = rs.fillna(1.0)

        group = group.reset_index(drop=True)
        group["relative_strength"] = rs.values[-len(group):]

        result_dfs.append(group)

    return pd.concat(result_dfs, ignore_index=True)


def main():
    """Main entry point for downloading all NSE stocks."""
    logger.info("=" * 70)
    logger.info("COMPREHENSIVE NSE DATA DOWNLOAD")
    logger.info("=" * 70)

    # Get stock list
    symbols = get_nse_stock_list()
    logger.info(f"Total symbols to download: {len(symbols)}")

    # Initialize database
    db = Database(config.db_path)

    # Clear existing data
    logger.info("Clearing existing data for fresh download...")
    with db.get_connection() as conn:
        conn.execute("DELETE FROM screener_results")
        conn.execute("DELETE FROM indicators")
        conn.execute("DELETE FROM eod")
        conn.commit()

    # Download all stocks
    stock_df, nifty_df, failed = download_all_stocks(symbols, days=150, max_workers=10)

    if stock_df.empty:
        logger.error("No data downloaded. Check internet connection.")
        return 1

    # Store raw EOD data
    logger.info("Storing EOD data in database...")
    cols = ["symbol", "trade_date", "open", "high", "low", "close", "volume", "turnover", "prev_close"]
    db.upsert_eod_data(stock_df[cols])

    # Compute indicators
    logger.info("Computing technical indicators...")
    all_with_indicators = []

    for symbol, group in stock_df.groupby("symbol"):
        group = group.sort_values("trade_date").copy()
        with_ind = add_advanced_indicators(group)
        all_with_indicators.append(with_ind)

    full_df = pd.concat(all_with_indicators, ignore_index=True)

    # Calculate relative strength
    logger.info("Calculating relative strength vs NIFTY...")
    full_df = compute_relative_strength(full_df, nifty_df)

    # Store indicators
    logger.info("Storing indicators in database...")
    indicator_cols = ["symbol", "trade_date", "sma_20", "sma_50", "rsi_14", "atr_14", "vol_ma_20", "hh_20", "ll_20"]
    indicators_df = full_df[indicator_cols].dropna()
    db.upsert_indicators(indicators_df)

    # Run screener
    latest_date = full_df["trade_date"].max()
    latest = full_df[full_df["trade_date"] == latest_date].copy()

    logger.info(f"Running screener on {len(latest)} stocks from {latest_date}")
    results = run_advanced_screener(latest, top_n=25, capital_per_trade=100000, min_score=8)

    if not results.empty:
        db.save_screener_results(results, latest_date)

    # Summary
    print()
    print("=" * 70)
    print(f"DOWNLOAD COMPLETE")
    print("=" * 70)
    print(f"Symbols attempted: {len(symbols)}")
    print(f"Symbols successful: {len(stock_df['symbol'].unique())}")
    print(f"Symbols failed: {len(failed)}")
    print(f"Total records: {len(stock_df)}")
    print(f"Date range: {stock_df['trade_date'].min()} to {stock_df['trade_date'].max()}")
    print(f"Sectors found: {len(stock_df['sector'].unique())}")
    print(f"Screener candidates: {len(results)}")
    print("=" * 70)
    print()
    print("View in dashboard: http://localhost:3000")
    print("API docs: http://localhost:8000/docs")

    return 0


if __name__ == "__main__":
    sys.exit(main())
