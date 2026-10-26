"""
Shared intraday bias scoring — used by live desk and 5m expectancy harness.

Rule id: ``intraday_bias_v1``. Timeframe: 5-minute completed bars only.
Strategy version bump if score thresholds / inputs change.
"""
from __future__ import annotations

from typing import Any

STRATEGY_ID = "intraday_bias_v1"
STRATEGY_VERSION = "1.0.0-5m"
STRATEGY_TIMEFRAME = "5m"
DATA_INTERVAL = "5m"

# Live desk thresholds (must stay in sync with harness)
LONG_SCORE = 62.0
SHORT_SCORE = 38.0


def session_vwap(closes: list[float], volumes: list[float]) -> float | None:
    n = min(len(closes), len(volumes))
    if n == 0:
        return None
    pv = vv = 0.0
    for i in range(n):
        v = volumes[i]
        if v is None or v <= 0:
            continue
        pv += float(closes[i]) * float(v)
        vv += float(v)
    if vv <= 0:
        return None
    return pv / vv


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


def score_intraday_bias(
    *,
    price: float,
    closes_5m: list[float],
    volumes_5m: list[float] | None = None,
    change_pct: float | None = None,
    session_open: float | None = None,
    session_high: float | None = None,
    session_low: float | None = None,
) -> dict[str, Any]:
    """
    Pure scoring on completed 5m history ending at ``price`` (= last close).

    Returns side LONG/SHORT/FLAT, score, tags, stop/target, rsi, vwap.
    Does not consult market clocks or feeds — caller supplies validated inputs.
    """
    closes = [float(c) for c in closes_5m]
    volumes = [float(v) for v in (volumes_5m or [])]
    score = 50.0
    tags: list[str] = []

    if change_pct is not None:
        score += max(-15.0, min(15.0, float(change_pct) * 3.0))
        if change_pct >= 0.8:
            tags.append("STRONG_UP")
        elif change_pct <= -0.8:
            tags.append("STRONG_DOWN")

    if session_open and price:
        day_pct = (price / float(session_open) - 1.0) * 100.0
        score += max(-10.0, min(10.0, day_pct * 2.5))
        tags.append("ABOVE_OPEN" if day_pct > 0 else "BELOW_OPEN")

    high, low = session_high, session_low
    if high and low and high > low and price:
        loc = (price - float(low)) / (float(high) - float(low))
        if loc >= 0.75:
            score += 6
            tags.append("NEAR_HIGH")
        elif loc <= 0.25:
            score -= 6
            tags.append("NEAR_LOW")

    if len(closes) >= 12:
        a = sum(closes[-6:]) / 6
        b = sum(closes[-12:-6]) / 6
        if b:
            mom = (a / b - 1.0) * 100.0
            score += max(-12.0, min(12.0, mom * 8.0))
            tags.append("MOM_UP" if mom > 0 else "MOM_DOWN")

    rsi_v = rsi(closes) if closes else None
    if rsi_v is not None:
        if rsi_v >= 65:
            score += 4
            tags.append("RSI_HOT")
        elif rsi_v <= 35:
            score -= 4
            tags.append("RSI_COLD")

    vwap = session_vwap(closes, volumes) if closes else None
    if vwap is not None and price:
        if price >= vwap:
            score += 5
            tags.append("VWAP_ABOVE")
        else:
            score -= 5
            tags.append("VWAP_BELOW")
    elif closes:
        tags.append("VWAP_PROXY")

    if len(closes) >= 18:
        orb_high = max(closes[:12])
        orb_low = min(closes[:12])
        if price > orb_high * 1.001:
            score += 8
            tags.append("ORB_BREAK_UP")
        elif price < orb_low * 0.999:
            score -= 8
            tags.append("ORB_BREAK_DOWN")

    score = round(max(0.0, min(100.0, score)), 1)
    if score >= LONG_SCORE:
        side = "LONG"
    elif score <= SHORT_SCORE:
        side = "SHORT"
    else:
        side = "FLAT"

    stop = target = None
    if side == "LONG" and price and low:
        stop = round(min(float(low), price * 0.992), 2)
        target = round(price * 1.006, 2)
    elif side == "SHORT" and price and high:
        stop = round(max(float(high), price * 1.008), 2)
        target = round(price * 0.994, 2)

    return {
        "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "timeframe": STRATEGY_TIMEFRAME,
        "data_interval": DATA_INTERVAL,
        "side": side,
        "score": score,
        "tags": tags,
        "price": float(price),
        "rsi_5m": rsi_v,
        "vwap": round(vwap, 2) if vwap is not None else None,
        "stop": stop,
        "target": target,
        "change_pct": change_pct,
        "session_open": session_open,
        "session_high": high,
        "session_low": low,
    }
