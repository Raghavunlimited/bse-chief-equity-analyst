"""
Enhanced Stock Analysis with Pros/Cons and Detailed Scoring Explanation
"""
import pandas as pd
import numpy as np
from typing import List, Dict


def generate_pros_cons(row: pd.Series) -> Dict[str, List[str]]:
    """
    Generate detailed pros and cons for each stock based on technical indicators.
    This helps traders make informed decisions.
    """
    pros = []
    cons = []

    # === TREND ANALYSIS ===
    if row.get("close", 0) > row.get("sma_50", 0):
        pros.append("Trading above 50-day SMA - Bullish trend")
    else:
        cons.append("Trading below 50-day SMA - Weak trend")

    if row.get("sma_20", 0) > row.get("sma_50", 0):
        pros.append("SMA 20 above SMA 50 - Golden cross pattern")
    else:
        cons.append("SMA 20 below SMA 50 - Bearish structure")

    # === MOMENTUM ===
    rsi = row.get("rsi_14", 50)
    if 55 <= rsi <= 70:
        pros.append(f"RSI at {rsi:.1f} - Strong momentum without being overbought")
    elif rsi > 75:
        cons.append(f"RSI at {rsi:.1f} - Overbought, risk of pullback")
    elif rsi < 40:
        cons.append(f"RSI at {rsi:.1f} - Weak momentum")
    else:
        pros.append(f"RSI at {rsi:.1f} - Neutral, room for upside")

    # === TREND STRENGTH (ADX) ===
    adx = row.get("adx", 20)
    if adx > 30:
        pros.append(f"ADX at {adx:.1f} - Strong trending market")
    elif adx < 20:
        cons.append(f"ADX at {adx:.1f} - Weak trend, choppy price action")

    # === VOLUME ===
    vol_ratio = row.get("vol_ratio", 1)
    if vol_ratio >= 1.5:
        pros.append(f"Volume {vol_ratio:.1f}x average - Strong institutional interest")
    elif vol_ratio >= 1.0:
        pros.append("Volume above average - Confirms price movement")
    else:
        cons.append(f"Volume {vol_ratio:.1f}x average - Low conviction move")

    # === BREAKOUT ===
    dist_20d = row.get("dist_from_20d_high", 100)
    if dist_20d <= 2:
        pros.append("Near 20-day high - Breakout potential")
    elif dist_20d > 10:
        cons.append(f"{dist_20d:.1f}% below 20-day high - Not in breakout zone")

    dist_52w = row.get("dist_from_52w_high", 100)
    if dist_52w <= 5:
        pros.append("Near 52-week high - Leaders make new highs")
    elif dist_52w <= 15:
        pros.append("Within 15% of 52-week high - Strong relative performance")
    elif dist_52w > 30:
        cons.append(f"{dist_52w:.1f}% below 52-week high - Underperforming stock")

    # === VOLATILITY ===
    atr_pct = row.get("atr_pct", 3)
    if 2 <= atr_pct <= 5:
        pros.append(f"ATR {atr_pct:.1f}% - Optimal volatility for swing trading")
    elif atr_pct > 6:
        cons.append(f"ATR {atr_pct:.1f}% - High volatility, wider stops needed")
    elif atr_pct < 1.5:
        cons.append(f"ATR {atr_pct:.1f}% - Low volatility, limited upside")

    # === RISK/REWARD ===
    rr = row.get("risk_reward", 2)
    if rr >= 2.5:
        pros.append(f"Risk:Reward 1:{rr:.1f} - Excellent setup")
    elif rr >= 2:
        pros.append(f"Risk:Reward 1:{rr:.1f} - Good setup")
    elif rr < 1.5:
        cons.append(f"Risk:Reward 1:{rr:.1f} - Poor risk/reward")

    # === EXPECTED GAIN ===
    gain = row.get("expected_gain_pct", 0)
    if gain >= 7:
        pros.append(f"Target gain {gain:.1f}% - High profit potential")
    elif gain >= 5:
        pros.append(f"Target gain {gain:.1f}% - Good profit potential")
    elif gain < 4:
        cons.append(f"Target gain {gain:.1f}% - Limited upside")

    # === RELATIVE STRENGTH ===
    rs = row.get("relative_strength", 1)
    if rs > 1.1:
        pros.append("Outperforming NIFTY 50 - Relative strength leader")
    elif rs < 0.9:
        cons.append("Underperforming NIFTY 50 - Relative weakness")

    # === PRICE ACTION ===
    if row.get("higher_low", 0) == 1:
        pros.append("Making higher lows - Bullish price structure")

    # Ensure we have at least one pro and con
    if not pros:
        pros.append("Stock is on the screener list - Meets basic criteria")
    if not cons:
        cons.append("No major concerns identified")

    return {"pros": pros, "cons": cons}


def get_score_explanation() -> Dict:
    """
    Returns detailed explanation of how scores are calculated.
    """
    return {
        "total_points": 20,
        "categories": [
            {
                "name": "Trend Factors",
                "max_points": 6,
                "factors": [
                    {"name": "Trend Alignment", "points": 2, "condition": "Close > SMA20 > SMA50", "why": "Confirms bullish trend structure"},
                    {"name": "EMA Bullish", "points": 1, "condition": "EMA 9 > EMA 21", "why": "Short-term momentum is positive"},
                    {"name": "Strong Trend (ADX)", "points": 2, "condition": "ADX > 25", "why": "Trending market, not choppy"},
                    {"name": "SMA 50 Rising", "points": 1, "condition": "SMA 50 today > 5 days ago", "why": "Medium-term uptrend"}
                ]
            },
            {
                "name": "Momentum Factors",
                "max_points": 5,
                "factors": [
                    {"name": "RSI Bullish Zone", "points": 2, "condition": "RSI between 55-70", "why": "Strong but not overbought"},
                    {"name": "Positive ROC", "points": 1, "condition": "10-day Rate of Change > 0", "why": "Price is gaining"},
                    {"name": "Accelerating", "points": 1, "condition": "5-day ROC > 10-day ROC", "why": "Momentum increasing"},
                    {"name": "Not Overbought", "points": 1, "condition": "RSI < 75", "why": "Room to run higher"}
                ]
            },
            {
                "name": "Breakout Factors",
                "max_points": 4,
                "factors": [
                    {"name": "Near 20-day High", "points": 2, "condition": "Within 2% of 20-day high", "why": "Ready to break out"},
                    {"name": "Near 52-week High", "points": 1, "condition": "Within 10% of 52-week high", "why": "Leaders make new highs"},
                    {"name": "Bollinger Breakout", "points": 1, "condition": "Price near upper band + squeeze", "why": "Volatility expansion setup"}
                ]
            },
            {
                "name": "Volume Factors",
                "max_points": 3,
                "factors": [
                    {"name": "Volume Surge", "points": 2, "condition": "Volume >= 1.5x average", "why": "Institutional buying"},
                    {"name": "Above Avg Volume", "points": 1, "condition": "Volume >= average", "why": "Price move has conviction"}
                ]
            },
            {
                "name": "Volatility Factors",
                "max_points": 2,
                "factors": [
                    {"name": "ATR Sweet Spot", "points": 2, "condition": "ATR% between 2-6%", "why": "Enough movement for profit, not too risky"}
                ]
            }
        ],
        "interpretation": {
            "16-20": "STRONG - High probability setup, consider larger position",
            "12-15": "MODERATE - Good setup, standard position size",
            "8-11": "WEAK - Marginal setup, smaller position or skip",
            "0-7": "AVOID - Does not meet criteria"
        }
    }


def generate_recommendation(row: pd.Series) -> Dict:
    """
    Generate a trading recommendation based on all factors.
    """
    score = row.get("total_score", row.get("score", 0))
    rsi = row.get("rsi_14", 50)
    adx = row.get("adx", 20)
    vol_ratio = row.get("vol_ratio", 1)

    # Determine action
    if score >= 15 and rsi < 70 and vol_ratio >= 1.2:
        action = "STRONG BUY"
        confidence = "HIGH"
        reason = "Multiple bullish factors aligned with volume confirmation"
    elif score >= 12 and rsi < 75:
        action = "BUY"
        confidence = "MEDIUM"
        reason = "Good setup but watch for confirmation"
    elif score >= 8:
        action = "WATCHLIST"
        confidence = "LOW"
        reason = "Potential setup forming, wait for more confirmation"
    else:
        action = "AVOID"
        confidence = "N/A"
        reason = "Does not meet swing trading criteria"

    # Position sizing recommendation
    if confidence == "HIGH":
        position_pct = "Full position (100% of allocated capital)"
    elif confidence == "MEDIUM":
        position_pct = "Half position (50% of allocated capital)"
    else:
        position_pct = "Quarter position or skip"

    return {
        "action": action,
        "confidence": confidence,
        "reason": reason,
        "position_sizing": position_pct,
        "risk_management": {
            "stop_loss": "Exit immediately if stop is hit",
            "target": "Book profits at target, trail stop if momentum continues",
            "time_stop": "Exit after 10 days if neither hit"
        }
    }


def calculate_support_resistance(df: pd.DataFrame) -> Dict:
    """
    Calculate key support and resistance levels.
    """
    if df.empty:
        return {"support": [], "resistance": []}

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values

    # Recent highs and lows
    recent_high = high[-20:].max()
    recent_low = low[-20:].min()

    # 52-week high/low (if available)
    high_52w = high.max()
    low_52w = low.min()

    # Pivot points
    pivot = (high[-1] + low[-1] + close[-1]) / 3
    r1 = 2 * pivot - low[-1]
    r2 = pivot + (high[-1] - low[-1])
    s1 = 2 * pivot - high[-1]
    s2 = pivot - (high[-1] - low[-1])

    return {
        "current_price": float(close[-1]),
        "support_levels": [
            {"level": float(s1), "type": "Pivot S1"},
            {"level": float(s2), "type": "Pivot S2"},
            {"level": float(recent_low), "type": "20-day Low"},
            {"level": float(low_52w), "type": "52-week Low"}
        ],
        "resistance_levels": [
            {"level": float(r1), "type": "Pivot R1"},
            {"level": float(r2), "type": "Pivot R2"},
            {"level": float(recent_high), "type": "20-day High"},
            {"level": float(high_52w), "type": "52-week High"}
        ],
        "pivot_point": float(pivot)
    }
