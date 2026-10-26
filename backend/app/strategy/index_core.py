"""
Shared index MTF/VWAP scoring — live desk + 5m expectancy harness.

Rule id: ``index_mtf_vwap_v1``. Uses daily regime (as-of prior EOD) + completed 5m.
"""
from __future__ import annotations

from typing import Any

STRATEGY_ID = "index_mtf_vwap_v1"
STRATEGY_VERSION = "1.0.0-5m"
STRATEGY_TIMEFRAME = "5m"
DATA_INTERVAL = "5m"

BUY_SCORE = 62.0
SELL_SCORE = 38.0


def ema(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    k = 2.0 / (period + 1)
    e = sum(closes[:period]) / period
    for c in closes[period:]:
        e = c * k + e * (1 - k)
    return float(e)


def rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(-period, 0):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag = sum(gains) / period
    al = sum(losses) / period
    if al == 0:
        return 100.0
    return round(100.0 - (100.0 / (1.0 + ag / al)), 2)


def slope_pct(closes: list[float], bars: int = 6) -> float | None:
    if len(closes) < bars + 1:
        return None
    a, b = closes[-(bars + 1)], closes[-1]
    if not a:
        return None
    return (b / a - 1.0) * 100.0


def score_index_mtf(
    *,
    symbol: str,
    price: float,
    closes_5m: list[float],
    daily_regime: str | None,
    vwap: float | None = None,
    change_pct: float | None = None,
    session_high: float | None = None,
    session_low: float | None = None,
    rel_spread: float | None = None,
) -> dict[str, Any]:
    """Pure index bias score. ``daily_regime`` must be known as-of prior day (no look-ahead)."""
    closes = [float(c) for c in closes_5m]
    ema9 = ema(closes, 9) if closes else None
    ema21 = ema(closes, 21) if closes else None
    rsi_v = rsi(closes) if closes else None
    slope = slope_pct(closes, 6) if closes else None

    score = 50.0
    tags: list[str] = []
    bits: list[str] = []
    regime = daily_regime

    if regime in ("STRONG_BULL", "BULL"):
        score += 12
        tags.append("DAILY_BULL")
        bits.append("daily bull regime")
    elif regime == "BEAR":
        score -= 14
        tags.append("DAILY_BEAR")
        bits.append("daily bear regime")
    elif regime == "NEUTRAL":
        score -= 4
        tags.append("DAILY_MIXED")

    if ema9 is not None and ema21 is not None:
        if ema9 > ema21 and price >= ema9:
            score += 14
            tags.append("EMA_BULL")
            bits.append("5m EMA9>EMA21")
        elif ema9 < ema21 and price <= ema9:
            score -= 14
            tags.append("EMA_BEAR")
            bits.append("5m EMA9<EMA21")
        else:
            tags.append("EMA_MIXED")

    if vwap:
        if price >= float(vwap) * 1.0005:
            score += 10
            tags.append("ABOVE_VWAP")
            bits.append("above VWAP")
        elif price <= float(vwap) * 0.9995:
            score -= 10
            tags.append("BELOW_VWAP")
            bits.append("below VWAP")

    if slope is not None:
        if slope > 0.15:
            score += 6
            tags.append("MOM_UP")
        elif slope < -0.15:
            score -= 6
            tags.append("MOM_DOWN")

    if change_pct is not None:
        if change_pct > 0.35:
            score += 5
        elif change_pct < -0.35:
            score -= 5

    if rsi_v is not None:
        if rsi_v >= 72:
            score -= 8
            tags.append("RSI_HOT")
            bits.append(f"RSI {rsi_v:.0f} hot")
        elif rsi_v <= 28:
            score += 8
            tags.append("RSI_WASHED")
            bits.append(f"RSI {rsi_v:.0f} washed")
        elif 45 <= rsi_v <= 60:
            score += 3

    if symbol == "BANKNIFTY" and rel_spread is not None:
        if rel_spread > 0.25:
            score += 6
            tags.append("BN_OUTPERFORM")
            bits.append(f"BN vs Nifty +{rel_spread:.2f}%")
        elif rel_spread < -0.25:
            score -= 6
            tags.append("BN_UNDERPERFORM")
            bits.append(f"BN vs Nifty {rel_spread:.2f}%")

    sess_hi, sess_lo = session_high, session_low
    if sess_hi and sess_lo and price:
        rng = float(sess_hi) - float(sess_lo)
        if rng > 0:
            pos = (price - float(sess_lo)) / rng
            if pos > 0.92 and "EMA_BULL" not in tags:
                score -= 4
                tags.append("NEAR_DAY_HIGH")
            elif pos < 0.08 and "EMA_BEAR" not in tags:
                score += 4
                tags.append("NEAR_DAY_LOW")

    score = max(0.0, min(100.0, score))
    if score >= BUY_SCORE:
        side = "BUY"
    elif score <= SELL_SCORE:
        side = "SELL"
    else:
        side = "HOLD"

    if regime == "BEAR" and side == "BUY" and score < 72:
        side = "HOLD"
        tags.append("REGIME_CLAMP")
        bits.append("BUY clamped by daily BEAR")

    atr_proxy = None
    if sess_hi is not None and sess_lo is not None:
        atr_proxy = max(float(sess_hi) - float(sess_lo), float(price) * 0.002)
    stop = target = None
    if atr_proxy and side == "BUY":
        stop = round(float(price) - 0.55 * atr_proxy, 2)
        target = round(float(price) + 0.9 * atr_proxy, 2)
    elif atr_proxy and side == "SELL":
        stop = round(float(price) + 0.55 * atr_proxy, 2)
        target = round(float(price) - 0.9 * atr_proxy, 2)

    conf = round(abs(score - 50.0) * 1.6 + 40.0, 1)
    conf = max(20.0, min(88.0, conf))
    if side == "HOLD":
        conf = min(conf, 58.0)

    return {
        "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "timeframe": STRATEGY_TIMEFRAME,
        "data_interval": DATA_INTERVAL,
        "side": side,
        "score": round(score, 1),
        "confidence": conf,
        "tags": tags,
        "bits": bits,
        "price": float(price),
        "rsi_5m": rsi_v,
        "ema9": ema9,
        "ema21": ema21,
        "slope_pct": slope,
        "vwap": float(vwap) if vwap is not None else None,
        "stop": stop,
        "target": target,
        "daily_regime": regime,
    }
