#!/usr/bin/env python3
"""
Download LIVE NSE data and generate comprehensive weekly swing trade analysis.
Includes relative strength vs NIFTY, sector analysis, and advanced screening.

Now dynamically fetches ALL NSE equity symbols (~1000+ stocks).
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
from app.advanced_screener import add_advanced_indicators, run_advanced_screener

# Import sector mapping for classification
from nse_stocks import SECTOR_MAP

# Import dynamic symbol fetcher for ALL NSE stocks
from fetch_all_nse_symbols import get_all_nse_equity_symbols, get_symbol_sector

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def download_with_retry(yf_symbol: str, period: str = "10y", max_retries: int = 3) -> pd.DataFrame:
    """Download data for a single symbol with retry logic."""
    for attempt in range(max_retries):
        try:
            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(period=period, interval="1d")
            if not df.empty:
                return df
            if attempt < max_retries - 1:
                time.sleep(0.5 * (attempt + 1))
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(0.5 * (attempt + 1))
            else:
                raise e
    return pd.DataFrame()


def download_live_data(symbols: list, years: int = 10) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Download historical data for stocks and NIFTY 50 index.
    Uses yfinance period parameter for reliable 10-year data.
    Returns: (stock_data, nifty_data)
    """
    period = f"{years}y"

    all_data = []
    failed = []
    success_count = 0
    total_records = 0

    logger.info(f"Downloading {len(symbols)} stocks with {years} years of historical data")
    logger.info("This will take some time for 1000+ stocks...")
    print()

    # Download NIFTY 50 index first
    logger.info("Downloading NIFTY 50 index (10 years)...")
    try:
        nifty = yf.Ticker("^NSEI")
        nifty_df = nifty.history(period=period, interval="1d")
        nifty_df = nifty_df.reset_index()
        nifty_df["symbol"] = "NIFTY50"
        nifty_df = nifty_df.rename(columns={
            "Date": "trade_date", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume"
        })
        nifty_df["trade_date"] = pd.to_datetime(nifty_df["trade_date"]).dt.strftime("%Y-%m-%d")
        nifty_df["turnover"] = nifty_df["close"] * nifty_df["volume"]
        nifty_df["prev_close"] = nifty_df["close"].shift(1)
        logger.info(f"NIFTY 50: {len(nifty_df)} trading days downloaded (10 years)")
    except Exception as e:
        logger.error(f"Failed to download NIFTY 50: {e}")
        nifty_df = pd.DataFrame()

    # Download stock data with progress tracking
    batch_size = 50
    start_time = time.time()

    for i, symbol in enumerate(symbols):
        yf_symbol = f"{symbol}.NS"
        try:
            df = download_with_retry(yf_symbol, period=period)

            if df.empty:
                failed.append(symbol)
                continue

            df = df.reset_index()
            df["symbol"] = symbol
            df["sector"] = SECTOR_MAP.get(symbol, "Unknown")

            df = df.rename(columns={
                "Date": "trade_date", "Open": "open", "High": "high",
                "Low": "low", "Close": "close", "Volume": "volume"
            })

            df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
            df["turnover"] = df["close"] * df["volume"]
            df["prev_close"] = df["close"].shift(1)
            df = df.dropna(subset=["prev_close"])

            all_data.append(df)
            success_count += 1
            total_records += len(df)

            # Progress update every batch_size stocks
            if (i + 1) % batch_size == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed
                remaining = (len(symbols) - i - 1) / rate if rate > 0 else 0
                logger.info(f"Progress: {i + 1}/{len(symbols)} ({success_count} success, {len(failed)} failed) | "
                           f"Records: {total_records:,} | ETA: {remaining/60:.1f} min")

            time.sleep(0.05)  # Small delay to avoid rate limiting

        except Exception as e:
            failed.append(symbol)

    # Final summary
    elapsed_total = time.time() - start_time
    logger.info(f"Download completed in {elapsed_total/60:.1f} minutes")

    if all_data:
        combined = pd.concat(all_data, ignore_index=True)
        logger.info(f"Total: {len(combined):,} records for {success_count} symbols ({years} years)")
        if failed:
            logger.info(f"Failed symbols: {len(failed)}")
        return combined, nifty_df
    else:
        return pd.DataFrame(), nifty_df


def compute_relative_strength(stock_df: pd.DataFrame, nifty_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate relative strength of each stock vs NIFTY"""
    if nifty_df.empty:
        stock_df["relative_strength"] = 1.0
        return stock_df

    # Get NIFTY returns
    nifty_returns = nifty_df.set_index("trade_date")["close"].pct_change()

    result_dfs = []
    for symbol, group in stock_df.groupby("symbol"):
        group = group.sort_values("trade_date").copy()
        stock_returns = group.set_index("trade_date")["close"].pct_change()

        # Calculate 20-day cumulative returns
        stock_cum = (1 + stock_returns).rolling(20).apply(lambda x: x.prod() - 1)
        nifty_cum = (1 + nifty_returns).rolling(20).apply(lambda x: x.prod() - 1)

        # Relative strength
        rs = stock_cum / nifty_cum.reindex(stock_cum.index)
        rs = rs.fillna(1.0)

        group = group.reset_index(drop=True)
        group["relative_strength"] = rs.values[-len(group):]

        result_dfs.append(group)

    return pd.concat(result_dfs, ignore_index=True)


def analyze_sectors(df: pd.DataFrame) -> dict:
    """Analyze sector performance"""
    latest = df[df["trade_date"] == df["trade_date"].max()].copy()

    sector_stats = []
    for sector in latest["sector"].unique():
        sector_stocks = latest[latest["sector"] == sector]
        if len(sector_stocks) < 2:
            continue

        avg_rsi = sector_stocks["rsi_14"].mean() if "rsi_14" in sector_stocks else 50
        avg_roc = sector_stocks["roc_10"].mean() if "roc_10" in sector_stocks else 0
        stock_count = len(sector_stocks)

        sector_stats.append({
            "sector": sector,
            "avg_rsi": avg_rsi,
            "avg_momentum": avg_roc,
            "stock_count": stock_count,
            "strength": "STRONG" if avg_rsi > 55 and avg_roc > 2 else "MODERATE" if avg_rsi > 50 else "WEAK"
        })

    return sorted(sector_stats, key=lambda x: x["avg_momentum"], reverse=True)


def main():
    """Run complete live data update and analysis"""
    logger.info("=" * 70)
    logger.info("LIVE NSE DATA UPDATE & ADVANCED SWING TRADE ANALYSIS")
    logger.info("=" * 70)
    print()

    # Initialize database
    db = Database(config.db_path)

    # Clear existing data
    with db.get_connection() as conn:
        conn.execute("DELETE FROM screener_results")
        conn.execute("DELETE FROM indicators")
        conn.execute("DELETE FROM eod")
        conn.commit()
    logger.info("Cleared existing data for fresh analysis")

    # Get ALL NSE equity symbols dynamically
    logger.info("Fetching complete list of NSE equity symbols...")
    all_symbols = get_all_nse_equity_symbols()
    logger.info(f"Total symbols to download: {len(all_symbols)}")

    # Download 10 years of historical data for ALL symbols
    stock_df, nifty_df = download_live_data(all_symbols, years=10)

    if stock_df.empty:
        logger.error("No data downloaded. Check internet connection.")
        return 1

    # Store raw EOD data
    cols = ["symbol", "trade_date", "open", "high", "low", "close", "volume", "turnover", "prev_close"]
    db.upsert_eod_data(stock_df[cols])

    # Compute advanced indicators per symbol
    logger.info("Computing advanced technical indicators...")
    all_with_indicators = []

    for symbol, group in stock_df.groupby("symbol"):
        group = group.sort_values("trade_date").copy()
        with_ind = add_advanced_indicators(group)
        all_with_indicators.append(with_ind)

    full_df = pd.concat(all_with_indicators, ignore_index=True)

    # Calculate relative strength vs NIFTY
    logger.info("Calculating relative strength vs NIFTY...")
    full_df = compute_relative_strength(full_df, nifty_df)

    # Store indicators
    indicator_cols = ["symbol", "trade_date", "sma_20", "sma_50", "rsi_14", "atr_14", "vol_ma_20", "hh_20", "ll_20"]
    indicators_df = full_df[indicator_cols].dropna()
    db.upsert_indicators(indicators_df)

    # Get latest snapshot for screening
    latest_date = full_df["trade_date"].max()
    latest = full_df[full_df["trade_date"] == latest_date].copy()

    logger.info(f"Screening {len(latest)} stocks from {latest_date}")

    # Run advanced screener
    results = run_advanced_screener(latest, top_n=25, capital_per_trade=100000, min_score=12)

    if not results.empty:
        # Save to database
        db.save_screener_results(results, latest_date)

    # Sector analysis
    sector_analysis = analyze_sectors(full_df)

    # Display results
    print()
    print("=" * 70)
    print(f"WEEKLY SWING TRADE ANALYSIS - {latest_date}")
    print("=" * 70)
    print()

    # Sector Momentum
    print("📊 SECTOR MOMENTUM (Top 5 Hot Sectors):")
    print("-" * 50)
    for i, sector in enumerate(sector_analysis[:5], 1):
        print(f"  {i}. {sector['sector']:20} | RSI: {sector['avg_rsi']:.1f} | Momentum: {sector['avg_momentum']:+.1f}% | {sector['strength']}")
    print()

    # Top Picks
    if not results.empty:
        print(f"🎯 TOP {len(results)} SWING TRADE CANDIDATES:")
        print("=" * 70)
        print()

        for idx, row in results.reset_index(drop=True).iterrows():
            import json
            meta = json.loads(row["metadata"])

            print(f"#{idx + 1}. {row['symbol']}")
            print(f"    Score: {row['score']}/25 | Strength: {meta['strength']} | Type: {meta['trade_type']}")
            print(f"    Entry: ₹{row['entry_price']:.2f} | Stop: ₹{row['stop_loss']:.2f} (-{meta['risk_pct']:.1f}%)")
            print(f"    Target: ₹{row['target_price']:.2f} (+{meta['expected_gain_pct']:.1f}%)")
            print(f"    R:R = 1:{row['risk_reward']:.2f} | Position: {row['position_size']} shares")
            print(f"    RSI: {meta['rsi_14']:.1f} | ADX: {meta['adx']:.1f} | Vol Ratio: {meta['vol_ratio']:.1f}x")
            print(f"    Dist from 52W High: {meta['dist_from_52w_high']:.1f}%")
            print()

    print("=" * 70)
    print(f"Total candidates: {len(results)}")
    print("=" * 70)
    print()
    print("📱 View in dashboard: http://localhost:3000")
    print("📚 API docs: http://localhost:8000/docs")

    return 0


if __name__ == "__main__":
    sys.exit(main())
