"""
Intraday equity bias signals — research only.

Uses near-live 5m Yahoo quotes for liquid NSE names.
Rules (desk-style, not a profit promise):
- Session bias vs open / prev close
- Session VWAP from 5m close×volume when bar volume exists (else skip / VWAP_PROXY)
- Momentum (last bars slope)
- ORB-lite: break of first-hour high/low when enough bars exist
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app import live_quotes


def _session_vwap(closes: list[float], volumes: list[float]) -> float | None:
    """Cumulative session VWAP = Σ(close×volume) / Σ(volume). None if no usable volume."""
    n = min(len(closes), len(volumes))
    if n == 0:
        return None
    pv = 0.0
    vv = 0.0
    for i in range(n):
        v = volumes[i]
        if v is None or v <= 0:
            continue
        pv += float(closes[i]) * float(v)
        vv += float(v)
    if vv <= 0:
        return None
    return pv / vv

# Liquid NSE watchlist (Yahoo .NS)
DEFAULT_WATCH = [
    "RELIANCE",
    "TCS",
    "INFY",
    "HDFCBANK",
    "ICICIBANK",
    "SBIN",
    "ITC",
    "BHARTIARTL",
    "LT",
    "AXISBANK",
    "KOTAKBANK",
    "BAJFINANCE",
    "MARUTI",
    "TATAMOTORS",
    "TATASTEEL",
    "SUNPHARMA",
    "HCLTECH",
    "WIPRO",
    "NTPC",
    "ONGC",
    "POWERGRID",
    "ADANIENT",
    "ADANIPORTS",
    "ULTRACEMCO",
    "TITAN",
]


def _session_state_ist() -> dict[str, Any]:
    """Rough NSE cash session flags (IST = UTC+5:30)."""
    now = datetime.now(timezone.utc)
    # Convert to IST minutes from midnight
    ist_min = (now.hour * 60 + now.minute + 330) % (24 * 60)
    open_m, close_m = 9 * 60 + 15, 15 * 60 + 30
    pre = 9 * 60
    in_session = open_m <= ist_min <= close_m
    return {
        "in_session": in_session,
        "pre_market": pre <= ist_min < open_m,
        "ist_minute": ist_min,
        "note": "NSE cash ~09:15–15:30 IST. Outside hours, signals are last-session residue.",
    }


def _rsi(closes: list[float], period: int = 14) -> float | None:
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
    rs = ag / al
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


def _signal_for(symbol: str, snap: dict[str, Any]) -> dict[str, Any]:
    price = snap.get("price")
    opens = snap.get("session_open")
    high = snap.get("session_high")
    low = snap.get("session_low")
    prev = snap.get("prev_close")
    closes = list(snap.get("closes_5m") or [])
    volumes = list(snap.get("volumes_5m") or [])
    change = snap.get("change_pct")

    score = 50.0
    tags: list[str] = []
    side = "FLAT"
    vwap: float | None = None

    if price is None:
        return {
            "symbol": symbol,
            "side": "FLAT",
            "score": 0,
            "thesis": "No live quote",
            "tags": ["NO_QUOTE"],
            "price": None,
        }

    # Bias vs previous close
    if change is not None:
        score += max(-15.0, min(15.0, change * 3.0))
        if change >= 0.8:
            tags.append("STRONG_UP")
        elif change <= -0.8:
            tags.append("STRONG_DOWN")

    # Vs session open
    if opens and price:
        day_pct = (price / opens - 1.0) * 100.0
        score += max(-10.0, min(10.0, day_pct * 2.5))
        tags.append("ABOVE_OPEN" if day_pct > 0 else "BELOW_OPEN")

    # Range position
    if high and low and high > low and price:
        loc = (price - low) / (high - low)
        if loc >= 0.75:
            score += 6
            tags.append("NEAR_HIGH")
        elif loc <= 0.25:
            score -= 6
            tags.append("NEAR_LOW")

    # Short momentum (last ~6 bars vs prior 6)
    if len(closes) >= 12:
        a = sum(closes[-6:]) / 6
        b = sum(closes[-12:-6]) / 6
        if b:
            mom = (a / b - 1.0) * 100.0
            score += max(-12.0, min(12.0, mom * 8.0))
            tags.append("MOM_UP" if mom > 0 else "MOM_DOWN")

    rsi = _rsi(closes) if closes else None
    if rsi is not None:
        if rsi >= 65:
            score += 4
            tags.append("RSI_HOT")
        elif rsi <= 35:
            score -= 4
            tags.append("RSI_COLD")

    # Session VWAP from 5m close×volume (research bias tag — not exchange tick VWAP)
    vwap = _session_vwap(closes, volumes) if closes else None
    if vwap is not None and price:
        if price >= vwap:
            score += 5
            tags.append("VWAP_ABOVE")
        else:
            score -= 5
            tags.append("VWAP_BELOW")
    elif closes:
        # No usable bar volume — do not invent a typical-price "edge"; label only
        tags.append("VWAP_PROXY")

    # ORB-lite: first ~12 bars (~60m) range break
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
    if score >= 62:
        side = "LONG"
    elif score <= 38:
        side = "SHORT"
    else:
        side = "FLAT"

    stop = None
    target = None
    if side == "LONG" and price and low:
        stop = round(min(low, price * 0.992), 2)
        target = round(price * 1.006, 2)
    elif side == "SHORT" and price and high:
        stop = round(max(high, price * 1.008), 2)
        target = round(price * 0.994, 2)

    thesis_bits = [
        f"{side} bias @ ₹{price:,.2f}",
        f"day {change:+.2f}%" if change is not None else None,
        f"RSI {rsi}" if rsi is not None else None,
        ", ".join(tags[:4]) if tags else None,
    ]
    thesis = " · ".join(t for t in thesis_bits if t)

    return {
        "symbol": symbol,
        "yahoo_symbol": snap.get("yahoo_symbol"),
        "side": side,
        "score": score,
        "thesis": thesis,
        "tags": tags,
        "price": price,
        "change_pct": change,
        "prev_close": prev,
        "session_open": opens,
        "session_high": high,
        "session_low": low,
        "rsi_5m": rsi,
        "vwap": round(vwap, 2) if vwap is not None else None,
        "stop": stop,
        "target": target,
        "currency": snap.get("currency") or "INR",
        "bars_5m": snap.get("bars_5m"),
        "disclaimer": "Intraday research bias only — not advice; scalp/risk yourself.",
    }


def build_intraday_desk(limit: int = 20) -> dict[str, Any]:
    session = _session_state_ist()
    # Prefer names we already store EOD for (more liquid / known)
    try:
        from app.config import config
        from app.store import Database

        stored = {s.upper() for s in Database(config.db_path).get_all_symbols()}
    except Exception:  # noqa: BLE001
        stored = set()
    watch = [s for s in DEFAULT_WATCH if not stored or s in stored] or list(DEFAULT_WATCH)
    watch = watch[: max(5, min(30, int(limit)))]

    yahoo_map = {s: f"{s}.NS" for s in watch}
    snaps = live_quotes.fetch_many(list(yahoo_map.values()))

    signals: list[dict[str, Any]] = []
    for sym, ysym in yahoo_map.items():
        snap = snaps.get(ysym)
        if not snap:
            signals.append(
                {
                    "symbol": sym,
                    "side": "FLAT",
                    "score": 0,
                    "thesis": "Quote unavailable",
                    "tags": ["NO_QUOTE"],
                    "price": None,
                }
            )
            continue
        signals.append(_signal_for(sym, snap))

    signals.sort(key=lambda x: float(x.get("score") or 0), reverse=True)
    longs = [s for s in signals if s.get("side") == "LONG"]
    shorts = [s for s in signals if s.get("side") == "SHORT"]

    return {
        "desk": "intraday",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "session": session,
        "poll_seconds": 15,
        "count": len(signals),
        "long_count": len(longs),
        "short_count": len(shorts),
        "signals": signals,
        "top_longs": longs[:5],
        "top_shorts": shorts[:5],
        "message": (
            "Live 5m Yahoo bias for liquid NSE cash. "
            + (
                "Session open — treat as active research tape."
                if session["in_session"]
                else "Outside NSE hours — last session residue; wait for open for fresh edge."
            )
        ),
        "disclaimer": (
            "Educational research only. Intraday markets are noisy; "
            "no signal guarantees profit. Use hard stops and size risk 0.25–0.5% per idea."
        ),
    }
