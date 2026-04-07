from __future__ import annotations
import pandas as pd
import numpy as np
import json
import logging
from typing import Optional
from app.config import config

logger = logging.getLogger(__name__)


def filter_universe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply universe filters:
    - Minimum traded value
    - Minimum price
    - Valid data (no NaN in critical fields)
    """
    filtered = df.copy()

    # Remove rows with missing critical data
    filtered = filtered.dropna(subset=["close", "volume", "turnover", "sma_20", "sma_50"])

    # Minimum price filter
    filtered = filtered[filtered["close"] >= config.min_price]

    # Calculate average traded value (use last 20 days if available)
    # For now, use current day turnover as proxy
    filtered = filtered[filtered["turnover"] >= config.min_traded_value]

    logger.info(f"Universe filtered: {len(filtered)} stocks from {len(df)} stocks")

    return filtered


def calculate_scores(df: pd.DataFrame) -> pd.DataFrame:
    """
    Score stocks based on swing trading criteria:
    1. Trend strength (close > SMA50, SMA50 rising)
    2. Momentum (RSI in constructive zone)
    3. Breakout potential (close near 20-day high)
    4. Volume confirmation (volume > average)
    """
    scored = df.copy()

    # 1. Trend filter (2 points)
    scored["trend_ok"] = (
        (scored["close"] > scored["sma_50"]) &
        (scored["sma_50"] > scored["sma_50"].shift(5))  # SMA50 rising
    ).astype(int) * 2

    # 2. RSI in constructive zone (2 points)
    scored["momentum_ok"] = (
        (scored["rsi_14"] >= config.rsi_min) &
        (scored["rsi_14"] <= config.rsi_max)
    ).astype(int) * 2

    # 3. Breakout setup (close near 20-day high) (2 points)
    scored["breakout_ok"] = (
        scored["close"] >= (config.breakout_threshold * scored["hh_20"])
    ).astype(int) * 2

    # 4. Volume confirmation (1 point)
    scored["volume_ok"] = (
        scored["volume"] >= (config.volume_multiplier * scored["vol_ma_20"])
    ).astype(int)

    # 5. Above short-term MA (1 point)
    scored["above_sma20"] = (scored["close"] > scored["sma_20"]).astype(int)

    # Total score (max 8 points)
    scored["score"] = (
        scored["trend_ok"] +
        scored["momentum_ok"] +
        scored["breakout_ok"] +
        scored["volume_ok"] +
        scored["above_sma20"]
    )

    return scored


def calculate_trade_plan(df: pd.DataFrame, capital_per_trade: float = 100000) -> pd.DataFrame:
    """
    Calculate entry, stop loss, target, and position size for each stock.
    Uses ATR-based risk management.
    """
    result = df.copy()

    # Entry price: current close
    result["entry_price"] = result["close"]

    # ATR percentage
    result["atr_pct"] = (result["atr_14"] / result["close"]) * 100

    # Stop loss: Entry - (1 * ATR)
    result["stop_loss"] = result["entry_price"] - (config.stop_loss_atr_multiple * result["atr_14"])

    # Target: Entry + (2 * ATR)
    result["target_price"] = result["entry_price"] + (config.target_atr_multiple * result["atr_14"])

    # Risk per share
    result["risk_per_share"] = result["entry_price"] - result["stop_loss"]

    # Risk-reward ratio
    result["risk_reward"] = (
        (result["target_price"] - result["entry_price"]) /
        result["risk_per_share"]
    )

    # Position size based on 2% risk
    risk_amount = capital_per_trade * config.risk_per_trade
    result["position_size"] = (risk_amount / result["risk_per_share"]).fillna(0).astype(int)

    # Expected gain (in %)
    result["expected_gain_pct"] = (
        ((result["target_price"] - result["entry_price"]) / result["entry_price"]) * 100
    )

    # Risk (in %)
    result["risk_pct"] = (
        ((result["entry_price"] - result["stop_loss"]) / result["entry_price"]) * 100
    )

    return result


def create_metadata(row: pd.Series) -> str:
    """Create JSON metadata for screener result"""
    metadata = {
        "sma_20": float(row.get("sma_20", 0)),
        "sma_50": float(row.get("sma_50", 0)),
        "rsi_14": float(row.get("rsi_14", 0)),
        "atr_14": float(row.get("atr_14", 0)),
        "atr_pct": float(row.get("atr_pct", 0)),
        "volume": int(row.get("volume", 0)),
        "vol_ma_20": float(row.get("vol_ma_20", 0)),
        "hh_20": float(row.get("hh_20", 0)),
        "expected_gain_pct": float(row.get("expected_gain_pct", 0)),
        "risk_pct": float(row.get("risk_pct", 0)),
        "trend_ok": int(row.get("trend_ok", 0)),
        "momentum_ok": int(row.get("momentum_ok", 0)),
        "breakout_ok": int(row.get("breakout_ok", 0)),
        "volume_ok": int(row.get("volume_ok", 0)),
    }
    return json.dumps(metadata)


def run_screener(df: pd.DataFrame, top_n: int = 20, capital_per_trade: float = 100000) -> pd.DataFrame:
    """
    Main screener pipeline:
    1. Filter universe
    2. Calculate scores
    3. Calculate trade plans
    4. Return top N candidates
    """
    logger.info(f"Starting screener with {len(df)} stocks")

    # Step 1: Filter universe
    filtered = filter_universe(df)
    if filtered.empty:
        logger.warning("No stocks passed universe filter")
        return pd.DataFrame()

    # Step 2: Calculate scores
    scored = calculate_scores(filtered)

    # Step 3: Calculate trade plans
    with_trades = calculate_trade_plan(scored, capital_per_trade)

    # Step 4: Sort by score and filter valid setups
    # Only include setups with score >= 4 and positive risk-reward
    valid = with_trades[
        (with_trades["score"] >= 4) &
        (with_trades["risk_reward"] > 0) &
        (with_trades["position_size"] > 0)
    ].copy()

    # Sort by score (descending) and take top N
    top_candidates = valid.sort_values("score", ascending=False).head(top_n)

    # Return empty DataFrame if no valid candidates
    if top_candidates.empty:
        logger.warning("No valid candidates found")
        return pd.DataFrame()

    # Create metadata (must check empty first - pandas apply returns DataFrame on empty df)
    top_candidates["metadata"] = top_candidates.apply(create_metadata, axis=1)

    # Rename close to close_price for consistency
    top_candidates = top_candidates.rename(columns={"close": "close_price"})

    # Select final columns for output
    output_columns = [
        "symbol", "score", "close_price", "entry_price", "stop_loss",
        "target_price", "risk_reward", "position_size", "metadata"
    ]

    result = top_candidates[output_columns].copy()

    logger.info(f"Screener completed: {len(result)} candidates selected")

    return result
