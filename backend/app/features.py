from __future__ import annotations
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


def calculate_rsi(data: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Relative Strength Index"""
    delta = data.diff()

    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Average True Range"""
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = abs(high - prev_close)
    tr3 = abs(low - prev_close)

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()

    return atr


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add technical indicators to price data.
    Expects df to be sorted by date and contain: open, high, low, close, volume
    """
    if df.empty:
        return df

    result = df.copy()

    # Moving averages
    result["sma_20"] = result["close"].rolling(20).mean()
    result["sma_50"] = result["close"].rolling(50).mean()

    # RSI
    result["rsi_14"] = calculate_rsi(result["close"], 14)

    # ATR
    result["atr_14"] = calculate_atr(result["high"], result["low"], result["close"], 14)

    # Volume moving average
    result["vol_ma_20"] = result["volume"].rolling(20).mean()

    # High/Low ranges
    result["hh_20"] = result["high"].rolling(20).max()
    result["ll_20"] = result["low"].rolling(20).min()

    return result


def compute_indicators_for_all_symbols(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute indicators for all symbols in the dataframe.
    Assumes df has columns: symbol, trade_date, open, high, low, close, volume
    """
    if df.empty:
        return pd.DataFrame()

    # Sort by symbol and date
    df = df.sort_values(["symbol", "trade_date"])

    # Group by symbol and compute indicators
    result_dfs = []

    for symbol, group_df in df.groupby("symbol"):
        group_df = group_df.sort_values("trade_date")
        with_indicators = add_indicators(group_df)
        result_dfs.append(with_indicators)

    result = pd.concat(result_dfs, ignore_index=True)

    logger.info(f"Computed indicators for {len(result['symbol'].unique())} symbols")

    return result


def extract_indicator_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Extract only indicator columns for storage"""
    indicator_cols = ["symbol", "trade_date", "sma_20", "sma_50", "rsi_14",
                      "atr_14", "vol_ma_20", "hh_20", "ll_20"]

    return df[indicator_cols].copy()


def get_latest_snapshot_per_symbol(df: pd.DataFrame) -> pd.DataFrame:
    """
    Get the latest row for each symbol.
    Useful for screening based on latest data.
    """
    if df.empty:
        return df

    # Sort and get last row per symbol
    df = df.sort_values(["symbol", "trade_date"])
    latest = df.groupby("symbol").tail(1).reset_index(drop=True)

    logger.info(f"Latest snapshot contains {len(latest)} symbols")

    return latest
