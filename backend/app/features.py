"""Technical indicators computed per symbol on time series."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def calculate_rsi(data: pd.Series, period: int = 14) -> pd.Series:
    delta = data.diff()
    gain = delta.clip(lower=0).rolling(window=period).mean()
    loss = (-delta.clip(upper=0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calculate_atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(window=period).mean()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    result = df.copy()
    result["sma_20"] = result["close"].rolling(20).mean()
    result["sma_50"] = result["close"].rolling(50).mean()
    result["rsi_14"] = calculate_rsi(result["close"], 14)
    result["atr_14"] = calculate_atr(
        result["high"], result["low"], result["close"], 14
    )
    result["vol_ma_20"] = result["volume"].rolling(20).mean()
    result["hh_20"] = result["high"].rolling(20).max()
    result["ll_20"] = result["low"].rolling(20).min()
    result["roc_3"] = result["close"].pct_change(3) * 100
    result["roc_20"] = result["close"].pct_change(20) * 100
    result["prev_volume"] = result["volume"].shift(1)
    return result


def compute_indicators_for_all_symbols(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    df = df.sort_values(["symbol", "trade_date"])
    parts = []
    for _, group in df.groupby("symbol"):
        parts.append(add_indicators(group.sort_values("trade_date")))
    result = pd.concat(parts, ignore_index=True)
    logger.info("Indicators for %s symbols", result["symbol"].nunique())
    return result


def extract_indicator_columns(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "symbol",
        "trade_date",
        "sma_20",
        "sma_50",
        "rsi_14",
        "atr_14",
        "vol_ma_20",
        "hh_20",
        "ll_20",
        "roc_3",
        "roc_20",
        "prev_volume",
    ]
    return df[cols].copy()


def recompute_and_store(db, lookback_days: int = 120) -> int:
    """Recompute indicators for recent window and upsert."""
    max_date = db.get_max_trade_date()
    if not max_date:
        return 0
    from datetime import datetime, timedelta

    start = (
        datetime.strptime(max_date, "%Y-%m-%d") - timedelta(days=lookback_days)
    ).strftime("%Y-%m-%d")
    eod = db.get_eod_data(start_date=start)
    # Also include NIFTY
    nifty = db.get_eod_data(symbol="NIFTY", start_date=start)
    if not nifty.empty:
        eod = pd.concat([eod, nifty], ignore_index=True)
    if eod.empty:
        return 0
    with_ind = compute_indicators_for_all_symbols(eod)
    return db.upsert_indicators(extract_indicator_columns(with_ind))
