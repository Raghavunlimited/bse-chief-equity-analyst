"""
Live / near-live quotes via Yahoo chart API.

Used for Intraday + MCX desks. Cached briefly to avoid rate limits.
Research feed only — not a broker quote stream.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) SwingDesk/3.2"
_lock = threading.Lock()
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL = 12.0  # seconds — realtime-ish poll window


def _fetch_chart(symbol: str, interval: str = "5m", range_: str = "1d") -> dict[str, Any] | None:
    key = f"{symbol}|{interval}|{range_}"
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < _CACHE_TTL:
            return hit[1]

    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?interval={interval}&range={range_}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("quote fetch failed %s: %s", symbol, exc)
        return None

    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        return None
    data = result[0]
    with _lock:
        _cache[key] = (now, data)
    return data


def quote_snapshot(yahoo_symbol: str) -> dict[str, Any] | None:
    """Latest price + session change from 5m chart meta / last bar."""
    data = _fetch_chart(yahoo_symbol, "5m", "1d")
    if not data:
        return None
    meta = data.get("meta") or {}
    indicators = (data.get("indicators") or {}).get("quote") or [{}]
    q = indicators[0] if indicators else {}
    raw_closes = q.get("close") or []
    raw_volumes = q.get("volume") or []
    highs = [c for c in (q.get("high") or []) if c is not None]
    lows = [c for c in (q.get("low") or []) if c is not None]
    opens = [c for c in (q.get("open") or []) if c is not None]
    ts = data.get("timestamp") or []

    # Keep close/volume bar-aligned for session VWAP (skip null closes)
    closes: list[float] = []
    volumes: list[float] = []
    for i, c in enumerate(raw_closes):
        if c is None:
            continue
        closes.append(float(c))
        v = raw_volumes[i] if i < len(raw_volumes) else None
        volumes.append(float(v) if v is not None else 0.0)

    price = meta.get("regularMarketPrice")
    if price is None and closes:
        price = closes[-1]
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    change_pct = None
    if price is not None and prev:
        try:
            change_pct = round((float(price) / float(prev) - 1.0) * 100.0, 3)
        except (TypeError, ValueError, ZeroDivisionError):
            change_pct = None

    session_open = opens[0] if opens else meta.get("regularMarketOpen")
    session_high = max(highs) if highs else None
    session_low = min(lows) if lows else None
    last_vol = volumes[-1] if volumes else None
    vol_sum = sum(volumes) if volumes else None

    # Session VWAP from typical price × volume (research tape)
    vwap = None
    raw_h = q.get("high") or []
    raw_l = q.get("low") or []
    raw_c = q.get("close") or []
    raw_v = q.get("volume") or []
    num = den = 0.0
    for i in range(min(len(raw_c), len(raw_v))):
        c = raw_c[i]
        v = raw_v[i]
        if c is None or v is None or float(v) <= 0:
            continue
        h = raw_h[i] if i < len(raw_h) and raw_h[i] is not None else c
        l_ = raw_l[i] if i < len(raw_l) and raw_l[i] is not None else c
        typical = (float(h) + float(l_) + float(c)) / 3.0
        num += typical * float(v)
        den += float(v)
    if den > 0:
        vwap = round(num / den, 4)

    return {
        "yahoo_symbol": yahoo_symbol,
        "price": float(price) if price is not None else None,
        "prev_close": float(prev) if prev is not None else None,
        "change_pct": change_pct,
        "currency": meta.get("currency"),
        "exchange": meta.get("exchangeName") or meta.get("fullExchangeName"),
        "session_open": float(session_open) if session_open is not None else None,
        "session_high": float(session_high) if session_high is not None else None,
        "session_low": float(session_low) if session_low is not None else None,
        "last_volume": last_vol,
        "session_volume": vol_sum,
        "vwap": vwap,
        "bars_5m": len(closes),
        "last_ts": ts[-1] if ts else None,
        "closes_5m": closes[-48:],  # ~4h
        "volumes_5m": volumes[-48:],  # aligned with closes_5m for VWAP
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def fetch_many(yahoo_symbols: list[str], max_workers: int = 6) -> dict[str, dict[str, Any]]:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    out: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = {pool.submit(quote_snapshot, s): s for s in yahoo_symbols}
        for fut in as_completed(futs):
            sym = futs[fut]
            try:
                snap = fut.result()
            except Exception as exc:  # noqa: BLE001
                logger.warning("quote worker %s: %s", sym, exc)
                continue
            if snap:
                out[sym] = snap
    return out
