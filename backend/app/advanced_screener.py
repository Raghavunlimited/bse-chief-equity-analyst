#!/usr/bin/env python3
"""
Advanced Swing Trading Screener with Multiple Factors
Designed to find stocks with 5-7% weekly potential

FACTORS CONSIDERED:
1. Trend Strength (SMA alignment, ADX)
2. Momentum (RSI, Rate of Change)
3. Relative Strength vs NIFTY (outperformers)
4. Breakout Detection (52-week high proximity, range breakouts)
5. Volume Analysis (volume surge, accumulation)
6. Volatility Sweet Spot (ATR % in optimal range)
7. Sector Momentum (hot sectors)
8. Price Action Quality (higher lows, consolidation)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import numpy as np
import json
import logging
from typing import Optional
from app.config import config

logger = logging.getLogger(__name__)


def calculate_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Average Directional Index for trend strength"""
    plus_dm = high.diff()
    minus_dm = low.diff().abs() * -1

    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm > 0] = 0
    minus_dm = minus_dm.abs()

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.rolling(period).mean()
    plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = dx.rolling(period).mean()

    return adx


def calculate_roc(close: pd.Series, period: int = 10) -> pd.Series:
    """Rate of Change - momentum indicator"""
    return ((close - close.shift(period)) / close.shift(period)) * 100


def calculate_bollinger_bands(close: pd.Series, period: int = 20, std_dev: float = 2.0):
    """Calculate Bollinger Bands for volatility squeeze detection"""
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    bandwidth = ((upper - lower) / sma) * 100
    return sma, upper, lower, bandwidth


def calculate_relative_strength(stock_returns: pd.Series, benchmark_returns: pd.Series, period: int = 20) -> pd.Series:
    """Calculate relative strength vs benchmark (NIFTY)"""
    rs = (stock_returns.rolling(period).mean() / benchmark_returns.rolling(period).mean())
    return rs


def add_advanced_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add advanced technical indicators for screening"""
    result = df.copy()

    # Basic short-term indicators
    result["sma_10"] = result["close"].rolling(10).mean()
    result["sma_20"] = result["close"].rolling(20).mean()
    result["sma_50"] = result["close"].rolling(50).mean()
    result["ema_9"] = result["close"].ewm(span=9).mean()
    result["ema_21"] = result["close"].ewm(span=21).mean()

    # Long-term indicators (benefits from 10-year data)
    result["sma_200"] = result["close"].rolling(200).mean()
    result["ema_50"] = result["close"].ewm(span=50).mean()

    # RSI
    delta = result["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    result["rsi_14"] = 100 - (100 / (1 + rs))

    # ATR and ATR %
    tr1 = result["high"] - result["low"]
    tr2 = (result["high"] - result["close"].shift()).abs()
    tr3 = (result["low"] - result["close"].shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    result["atr_14"] = tr.rolling(14).mean()
    result["atr_pct"] = (result["atr_14"] / result["close"]) * 100

    # ADX - Trend Strength
    result["adx"] = calculate_adx(result["high"], result["low"], result["close"])

    # Rate of Change (momentum) - multiple periods
    result["roc_5"] = calculate_roc(result["close"], 5)
    result["roc_10"] = calculate_roc(result["close"], 10)
    result["roc_20"] = calculate_roc(result["close"], 20)  # Monthly momentum
    result["roc_60"] = calculate_roc(result["close"], 60)  # Quarterly momentum

    # Volume indicators
    result["vol_ma_20"] = result["volume"].rolling(20).mean()
    result["vol_ma_50"] = result["volume"].rolling(50).mean()
    result["vol_ratio"] = result["volume"] / result["vol_ma_20"]

    # Price position - short and long term
    result["hh_20"] = result["high"].rolling(20).max()
    result["ll_20"] = result["low"].rolling(20).min()
    result["hh_52w"] = result["high"].rolling(250).max()  # 52 weeks
    result["ll_52w"] = result["low"].rolling(250).min()   # 52 weeks
    result["hh_2y"] = result["high"].rolling(500).max()   # 2 years
    result["hh_5y"] = result["high"].rolling(1250).max()  # 5 years (all-time proxy)

    # Proximity to highs/lows (%)
    result["dist_from_20d_high"] = ((result["hh_20"] - result["close"]) / result["hh_20"]) * 100
    result["dist_from_52w_high"] = ((result["hh_52w"] - result["close"]) / result["hh_52w"]) * 100
    result["dist_from_52w_low"] = ((result["close"] - result["ll_52w"]) / result["ll_52w"]) * 100
    result["dist_from_5y_high"] = ((result["hh_5y"] - result["close"]) / result["hh_5y"]) * 100

    # Long-term trend indicators
    result["above_200sma"] = (result["close"] > result["sma_200"]).astype(int)
    result["sma_50_above_200"] = (result["sma_50"] > result["sma_200"]).astype(int)  # Golden cross
    result["price_vs_200sma_pct"] = ((result["close"] - result["sma_200"]) / result["sma_200"]) * 100

    # Bollinger Bands
    _, upper, lower, bandwidth = calculate_bollinger_bands(result["close"])
    result["bb_upper"] = upper
    result["bb_lower"] = lower
    result["bb_bandwidth"] = bandwidth

    # Price relative to bands
    result["bb_position"] = (result["close"] - lower) / (upper - lower)

    # Daily returns
    result["daily_return"] = result["close"].pct_change() * 100

    # Consecutive up/down days
    result["up_day"] = (result["close"] > result["close"].shift(1)).astype(int)

    # Higher lows pattern (bullish)
    result["higher_low"] = (result["low"] > result["low"].shift(1)).astype(int)

    # Gap analysis
    result["gap_pct"] = ((result["open"] - result["close"].shift(1)) / result["close"].shift(1)) * 100

    # Long-term performance metrics (yearly returns for 10 years)
    result["return_1y"] = calculate_roc(result["close"], 250)
    result["return_3y"] = calculate_roc(result["close"], 750)
    result["return_5y"] = calculate_roc(result["close"], 1250)

    return result


def score_for_swing_trade(df: pd.DataFrame) -> pd.DataFrame:
    """
    Advanced scoring system for swing trading
    Maximum score: 25 points (expanded with long-term factors)
    """
    scored = df.copy()

    # === TREND FACTORS (8 points max) ===

    # 1. Price above key SMAs (2 points)
    scored["trend_alignment"] = (
        (scored["close"] > scored["sma_20"]) &
        (scored["close"] > scored["sma_50"]) &
        (scored["sma_20"] > scored["sma_50"])
    ).astype(int) * 2

    # 2. EMA crossover bullish (1 point)
    scored["ema_bullish"] = (scored["ema_9"] > scored["ema_21"]).astype(int)

    # 3. Strong trend (ADX > 25) (2 points)
    scored["strong_trend"] = (scored["adx"] > 25).astype(int) * 2

    # 4. SMA 50 rising (1 point)
    scored["sma_rising"] = (scored["sma_50"] > scored["sma_50"].shift(5)).astype(int)

    # 5. Above 200 SMA - long-term uptrend (1 point)
    scored["long_term_bullish"] = scored["above_200sma"]

    # 6. Golden cross - 50 SMA above 200 SMA (1 point)
    scored["golden_cross"] = scored["sma_50_above_200"]

    # === MOMENTUM FACTORS (5 points max) ===

    # 7. RSI in bullish zone (55-70) (2 points)
    scored["rsi_bullish"] = (
        (scored["rsi_14"] >= 55) & (scored["rsi_14"] <= 70)
    ).astype(int) * 2

    # 8. Positive momentum (ROC > 0) (1 point)
    scored["positive_momentum"] = (scored["roc_10"] > 0).astype(int)

    # 9. Accelerating momentum (5-day ROC > 10-day ROC) (1 point)
    scored["accelerating"] = (scored["roc_5"] > scored["roc_10"]).astype(int)

    # 10. Not overbought (RSI < 75) (1 point)
    scored["not_overbought"] = (scored["rsi_14"] < 75).astype(int)

    # === BREAKOUT FACTORS (5 points max) ===

    # 11. Near 20-day high (within 2%) (2 points)
    scored["near_breakout"] = (scored["dist_from_20d_high"] <= 2).astype(int) * 2

    # 12. Near 52-week high (within 10%) - stocks making new highs tend to continue (1 point)
    scored["near_52w_high"] = (scored["dist_from_52w_high"] <= 10).astype(int)

    # 13. Breaking out of Bollinger squeeze (1 point)
    scored["bb_breakout"] = (
        (scored["bb_position"] > 0.8) &
        (scored["bb_bandwidth"] < scored["bb_bandwidth"].rolling(20).mean())
    ).astype(int)

    # 14. Near all-time high (within 15% of 5-year high) (1 point)
    scored["near_ath"] = (scored["dist_from_5y_high"] <= 15).astype(int)

    # === VOLUME FACTORS (3 points max) ===

    # 15. Volume surge (> 1.5x average) (2 points)
    scored["volume_surge"] = (scored["vol_ratio"] >= 1.5).astype(int) * 2

    # 16. Above average volume (1 point)
    scored["above_avg_volume"] = (scored["vol_ratio"] >= 1.0).astype(int)

    # === VOLATILITY FACTORS (2 points max) ===

    # 17. ATR in sweet spot (2-5%) - enough movement but not too risky (2 points)
    scored["atr_optimal"] = (
        (scored["atr_pct"] >= 2) & (scored["atr_pct"] <= 6)
    ).astype(int) * 2

    # === LONG-TERM VALUE FACTORS (2 points max) ===

    # 18. Bounced from 52-week low (at least 20% above) (1 point)
    scored["recovery_play"] = (scored["dist_from_52w_low"] >= 20).astype(int)

    # 19. Positive 1-year return (1 point)
    scored["yearly_positive"] = (scored["return_1y"] > 0).astype(int)

    # === CALCULATE TOTAL SCORE ===
    score_columns = [
        "trend_alignment", "ema_bullish", "strong_trend", "sma_rising",
        "long_term_bullish", "golden_cross",
        "rsi_bullish", "positive_momentum", "accelerating", "not_overbought",
        "near_breakout", "near_52w_high", "bb_breakout", "near_ath",
        "volume_surge", "above_avg_volume", "atr_optimal",
        "recovery_play", "yearly_positive"
    ]

    scored["total_score"] = sum(scored[col] for col in score_columns)

    return scored


def calculate_trade_plan(df: pd.DataFrame, capital_per_trade: float = 100000,
                         risk_pct: float = 0.02) -> pd.DataFrame:
    """Calculate entry, stop loss, target with dynamic R:R based on ATR"""
    result = df.copy()

    result["entry_price"] = result["close"]

    # Dynamic stop loss based on ATR (1.5x ATR for tighter stops on high-quality setups)
    result["stop_loss"] = result["entry_price"] - (1.5 * result["atr_14"])

    # Dynamic target based on score (higher score = more aggressive target)
    # Base: 2x ATR, High score (15+): 3x ATR
    target_multiplier = np.where(result["total_score"] >= 15, 3.0, 2.5)
    result["target_price"] = result["entry_price"] + (target_multiplier * result["atr_14"])

    result["risk_per_share"] = result["entry_price"] - result["stop_loss"]
    result["reward_per_share"] = result["target_price"] - result["entry_price"]
    result["risk_reward"] = result["reward_per_share"] / result["risk_per_share"]

    # Position sizing based on risk
    risk_amount = capital_per_trade * risk_pct
    result["position_size"] = (risk_amount / result["risk_per_share"]).fillna(0).astype(int)

    # Expected gain %
    result["expected_gain_pct"] = ((result["target_price"] - result["entry_price"]) / result["entry_price"]) * 100
    result["risk_pct"] = ((result["entry_price"] - result["stop_loss"]) / result["entry_price"]) * 100

    return result


def create_analysis_report(row: pd.Series) -> dict:
    """Create detailed analysis report for each stock"""
    report = {
        # Price data
        "close": float(row.get("close", 0)),
        "sma_20": float(row.get("sma_20", 0)),
        "sma_50": float(row.get("sma_50", 0)),
        "sma_200": float(row.get("sma_200", 0)),

        # Momentum
        "rsi_14": float(row.get("rsi_14", 0)),
        "roc_10": float(row.get("roc_10", 0)),
        "roc_60": float(row.get("roc_60", 0)),
        "adx": float(row.get("adx", 0)),

        # Volatility
        "atr_14": float(row.get("atr_14", 0)),
        "atr_pct": float(row.get("atr_pct", 0)),
        "bb_bandwidth": float(row.get("bb_bandwidth", 0)),

        # Volume
        "volume": int(row.get("volume", 0)),
        "vol_ratio": float(row.get("vol_ratio", 0)),

        # Breakout
        "dist_from_20d_high": float(row.get("dist_from_20d_high", 0)),
        "dist_from_52w_high": float(row.get("dist_from_52w_high", 0)),
        "dist_from_52w_low": float(row.get("dist_from_52w_low", 0)),
        "dist_from_5y_high": float(row.get("dist_from_5y_high", 0)),

        # Long-term performance
        "return_1y": float(row.get("return_1y", 0)),
        "return_3y": float(row.get("return_3y", 0)),
        "return_5y": float(row.get("return_5y", 0)),
        "above_200sma": int(row.get("above_200sma", 0)),
        "golden_cross": int(row.get("sma_50_above_200", 0)),

        # Trade plan
        "expected_gain_pct": float(row.get("expected_gain_pct", 0)),
        "risk_pct": float(row.get("risk_pct", 0)),

        # Score breakdown
        "trend_score": int(row.get("trend_alignment", 0)) + int(row.get("ema_bullish", 0)) +
                       int(row.get("strong_trend", 0)) + int(row.get("sma_rising", 0)) +
                       int(row.get("long_term_bullish", 0)) + int(row.get("golden_cross", 0)),
        "momentum_score": int(row.get("rsi_bullish", 0)) + int(row.get("positive_momentum", 0)) +
                          int(row.get("accelerating", 0)) + int(row.get("not_overbought", 0)),
        "breakout_score": int(row.get("near_breakout", 0)) + int(row.get("near_52w_high", 0)) +
                          int(row.get("bb_breakout", 0)) + int(row.get("near_ath", 0)),
        "volume_score": int(row.get("volume_surge", 0)) + int(row.get("above_avg_volume", 0)),
        "value_score": int(row.get("recovery_play", 0)) + int(row.get("yearly_positive", 0)),

        # Analysis summary
        "strength": "STRONG" if row.get("total_score", 0) >= 18 else
                    "MODERATE" if row.get("total_score", 0) >= 12 else "WEAK",

        "trade_type": "BREAKOUT" if row.get("near_breakout", 0) > 0 else
                      "MOMENTUM" if row.get("rsi_bullish", 0) > 0 else "TREND"
    }

    return report


def run_advanced_screener(df: pd.DataFrame, top_n: int = 20,
                          capital_per_trade: float = 100000,
                          min_score: int = 12) -> pd.DataFrame:
    """
    Run advanced swing trading screener

    Args:
        df: DataFrame with OHLCV data (latest snapshot per symbol)
        top_n: Number of top candidates to return
        capital_per_trade: Capital allocated per trade
        min_score: Minimum score to qualify (out of 25)

    Returns:
        DataFrame with top swing trade candidates
    """
    logger.info(f"Starting advanced screener with {len(df)} stocks")

    # Filter universe (liquidity)
    filtered = df.dropna(subset=["close", "volume", "turnover", "sma_20", "sma_50"])
    filtered = filtered[filtered["close"] >= 50]  # Min price
    filtered = filtered[filtered["turnover"] >= 5_00_00_000]  # Min ₹5 Cr turnover

    logger.info(f"Universe filtered: {len(filtered)} stocks passed liquidity filter")

    if filtered.empty:
        return pd.DataFrame()

    # Score stocks
    scored = score_for_swing_trade(filtered)

    # Calculate trade plans
    with_trades = calculate_trade_plan(scored, capital_per_trade)

    # Filter by minimum score and valid setups
    valid = with_trades[
        (with_trades["total_score"] >= min_score) &
        (with_trades["risk_reward"] > 1.5) &
        (with_trades["position_size"] > 0) &
        (with_trades["expected_gain_pct"] >= 4)  # At least 4% target
    ].copy()

    # Sort by score (descending) and take top N
    top_candidates = valid.sort_values("total_score", ascending=False).head(top_n)

    # Create metadata
    top_candidates["metadata"] = top_candidates.apply(
        lambda row: json.dumps(create_analysis_report(row)), axis=1
    )

    # Rename for consistency
    top_candidates = top_candidates.rename(columns={
        "close": "close_price",
        "total_score": "score"
    })

    # Select output columns
    output_columns = [
        "symbol", "score", "close_price", "entry_price", "stop_loss",
        "target_price", "risk_reward", "position_size", "metadata"
    ]

    result = top_candidates[output_columns].copy()

    logger.info(f"Advanced screener completed: {len(result)} candidates selected")

    return result
