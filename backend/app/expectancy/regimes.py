"""
Expectancy market regimes (Phase 5).

Four mutually exclusive labels used to segment edge metrics:
  BULL_TREND | BEAR_TREND | HIGH_VOL_CHOP | LOW_VOL_RANGE

Classifier uses only bars ≤ as_of (no lookahead). Volatility is
annualized 20d close-to-close σ; trend uses SMA20/SMA50 stack.
"""
from __future__ import annotations

from typing import Any, Literal

import numpy as np
import pandas as pd

ExpectancyRegime = Literal[
    "BULL_TREND",
    "BEAR_TREND",
    "HIGH_VOL_CHOP",
    "LOW_VOL_RANGE",
    "UNKNOWN",
]

REGIME_LABELS: tuple[str, ...] = (
    "BULL_TREND",
    "BEAR_TREND",
    "HIGH_VOL_CHOP",
    "LOW_VOL_RANGE",
)

# Realized vol vs its own trailing median — above this → high-vol bucket
_HIGH_VOL_MULT = 1.25
# Absolute annualized vol floor that always counts as high-vol (India equity ~12–18% calm)
_HIGH_VOL_ABS = 0.22


def _atr_pct(df: pd.DataFrame, period: int = 14) -> float | None:
    if df is None or len(df) < period + 1:
        return None
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev).abs(), (low - prev).abs()],
        axis=1,
    ).max(axis=1)
    atr = float(tr.tail(period).mean())
    px = float(close.iloc[-1])
    if px <= 0:
        return None
    return atr / px


def classify_regime(ohlcv: pd.DataFrame) -> dict[str, Any]:
    """
    Classify the *last* bar of ``ohlcv`` into an expectancy regime.

    Requires ≥50 bars. Returns UNKNOWN when insufficient.
    """
    if ohlcv is None or ohlcv.empty or len(ohlcv) < 50:
        return {
            "regime": "UNKNOWN",
            "reason": "Need ≥50 bars for expectancy regime",
            "vol_ann": None,
            "vol_median": None,
            "atr_pct": None,
            "trend": None,
        }

    close = ohlcv["close"].astype(float)
    price = float(close.iloc[-1])
    sma20 = float(close.rolling(20).mean().iloc[-1])
    sma50 = float(close.rolling(50).mean().iloc[-1])

    rets = close.pct_change()
    vol_series = rets.rolling(20).std() * np.sqrt(252)
    vol_ann = float(vol_series.iloc[-1]) if pd.notna(vol_series.iloc[-1]) else None
    # Trailing median of vol (excludes current to reduce self-bias slightly)
    vol_hist = vol_series.iloc[-61:-1].dropna()
    vol_median = float(vol_hist.median()) if len(vol_hist) >= 20 else None

    atr_pct = _atr_pct(ohlcv)

    above_20 = price > sma20
    above_50 = price > sma50
    stack_bull = sma20 > sma50
    stack_bear = sma20 < sma50

    if above_20 and above_50 and stack_bull:
        trend = "up"
    elif (not above_20) and (not above_50) and stack_bear:
        trend = "down"
    else:
        trend = "flat"

    high_vol = False
    if vol_ann is not None:
        if vol_ann >= _HIGH_VOL_ABS:
            high_vol = True
        elif vol_median is not None and vol_ann >= vol_median * _HIGH_VOL_MULT:
            high_vol = True
    if atr_pct is not None and atr_pct >= 0.025:
        high_vol = True

    if high_vol and trend == "flat":
        regime: ExpectancyRegime = "HIGH_VOL_CHOP"
        reason = "Elevated realized vol without clear SMA stack"
    elif trend == "up" and not high_vol:
        regime = "BULL_TREND"
        reason = "Price > SMA20 > SMA50 with contained vol"
    elif trend == "up" and high_vol:
        # Trending but noisy — still bull for edge segmentation
        regime = "BULL_TREND"
        reason = "Bullish SMA stack (elevated vol)"
    elif trend == "down":
        regime = "BEAR_TREND"
        reason = "Price < SMA20 < SMA50"
    elif not high_vol:
        regime = "LOW_VOL_RANGE"
        reason = "Contained vol, mixed / range SMA structure"
    else:
        regime = "HIGH_VOL_CHOP"
        reason = "High vol residual chop"

    return {
        "regime": regime,
        "reason": reason,
        "vol_ann": round(vol_ann, 4) if vol_ann is not None else None,
        "vol_median": round(vol_median, 4) if vol_median is not None else None,
        "atr_pct": round(atr_pct, 5) if atr_pct is not None else None,
        "trend": trend,
        "sma20": round(sma20, 2),
        "sma50": round(sma50, 2),
        "price": round(price, 2),
    }


def regime_at(
    ohlcv: pd.DataFrame,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Classify regime using only bars with trade_date ≤ as_of."""
    if ohlcv is None or ohlcv.empty:
        return classify_regime(ohlcv)
    df = ohlcv
    if as_of and "trade_date" in df.columns:
        df = df[df["trade_date"] <= as_of]
    return classify_regime(df)


def regime_series(ohlcv: pd.DataFrame) -> pd.Series:
    """
    Point-in-time regime label for every bar that has ≥50 prior bars.
    Walk-forward safe: each index i uses only rows[: i+1].
    """
    if ohlcv is None or ohlcv.empty:
        return pd.Series(dtype=object)
    labels: list[str] = []
    idx = list(ohlcv.index)
    for i in range(len(ohlcv)):
        if i < 49:
            labels.append("UNKNOWN")
            continue
        window = ohlcv.iloc[: i + 1]
        labels.append(str(classify_regime(window)["regime"]))
    return pd.Series(labels, index=idx, name="expectancy_regime")
