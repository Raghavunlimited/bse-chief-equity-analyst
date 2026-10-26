"""
LiveQuote fetch helpers + desk entrypoint.

Prefer Kotak Neo WebSocket via ``providers.live_quote_provider``. Yahoo chart
5m is an explicit research FALLBACK when ``ALLOW_YAHOO_LTP_FALLBACK`` is true.
Never fabricates prices. Failures → ERROR / UNAVAILABLE (no demo).
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.config import config
from app.market_session import annotate_live_quote, assess_quote_age, session_snapshot
from app.market_types import LiveQuote

logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) SwingDesk/5.2"
_lock = threading.Lock()
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _cache_ttl() -> float:
    return max(0.5, min(2.0, float(config.live_quote_stale_sec) * 0.4))


def _fetch_chart(symbol: str, interval: str = "5m", range_: str = "1d") -> dict[str, Any] | None:
    key = f"{symbol}|{interval}|{range_}"
    now = time.time()
    ttl = _cache_ttl()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
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
        logger.error("Yahoo chart fetch FAILED %s: %s", symbol, exc)
        return None

    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        logger.error("Yahoo chart empty result %s", symbol)
        return None
    data = result[0]
    with _lock:
        _cache[key] = (now, data)
    return data


def unavailable_quote(
    yahoo_symbol: str,
    err: str,
    *,
    session: dict[str, Any] | None = None,
    source: str = "unavailable",
) -> LiveQuote:
    """Honest empty quote — never a synthetic price."""
    now = time.time()
    sess = session or session_snapshot()
    status, age, _ = assess_quote_age(None, now_unix=now, session=sess)
    if sess.get("in_regular_hours"):
        status = "ERROR"
    raw = LiveQuote(
        symbol=yahoo_symbol.replace(".NS", "").replace("^", ""),
        ltp=None,
        quote_ts_unix=0.0,
        fetched_at_unix=now,
        age_sec=age if age >= 0 else -1.0,
        feed_status="ERROR" if sess.get("in_regular_hours") else status,
        source=source,
        timeframe="ltp",
        yahoo_symbol=yahoo_symbol,
        error=err,
    )
    return annotate_live_quote(raw, now_unix=now, session=sess)


def yahoo_chart_quote(yahoo_symbol: str) -> LiveQuote:
    """
    Research FALLBACK tape from Yahoo chart API only.

    Callers must not present this as Kotak/broker LIVE (annotate → FALLBACK).
    """
    sess = session_snapshot()
    fetched_at = time.time()
    data = _fetch_chart(yahoo_symbol, "5m", "1d")
    if not data:
        return unavailable_quote(yahoo_symbol, "chart_fetch_failed", session=sess, source="yahoo_chart")

    meta = data.get("meta") or {}
    indicators = (data.get("indicators") or {}).get("quote") or [{}]
    q = indicators[0] if indicators else {}
    raw_closes = q.get("close") or []
    raw_volumes = q.get("volume") or []
    highs = [c for c in (q.get("high") or []) if c is not None]
    lows = [c for c in (q.get("low") or []) if c is not None]
    opens = [c for c in (q.get("open") or []) if c is not None]
    ts = data.get("timestamp") or []

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
    if price is None:
        return unavailable_quote(yahoo_symbol, "no_ltp_in_payload", session=sess, source="yahoo_chart")

    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    change_pct = None
    if prev:
        try:
            change_pct = round((float(price) / float(prev) - 1.0) * 100.0, 3)
        except (TypeError, ValueError, ZeroDivisionError):
            change_pct = None

    session_open = opens[0] if opens else meta.get("regularMarketOpen")
    session_high = max(highs) if highs else None
    session_low = min(lows) if lows else None
    last_vol = volumes[-1] if volumes else None
    vol_sum = sum(volumes) if volumes else None

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

    quote_ts = meta.get("regularMarketTime")
    if quote_ts is None and ts:
        quote_ts = ts[-1]
    if quote_ts is None:
        quote_ts = fetched_at

    feed_status, age_sec, _allowed = assess_quote_age(
        float(quote_ts), now_unix=fetched_at, session=sess
    )

    nse_sym = yahoo_symbol
    if yahoo_symbol.endswith(".NS"):
        nse_sym = yahoo_symbol[:-3]
    elif yahoo_symbol.startswith("^"):
        nse_sym = {"^NSEI": "NIFTY", "^NSEBANK": "BANKNIFTY"}.get(
            yahoo_symbol, yahoo_symbol.lstrip("^")
        )

    # Persist completed 5m bars for expectancy (best-effort; never blocks quote)
    try:
        from app.bars_5m import bars_from_yahoo_chart_payload, upsert_bars

        persist_rows = bars_from_yahoo_chart_payload(
            symbol=nse_sym,
            timestamps=[int(x) for x in ts if x is not None],
            opens=list(q.get("open") or []),
            highs=list(q.get("high") or []),
            lows=list(q.get("low") or []),
            closes=list(raw_closes),
            volumes=list(raw_volumes),
            source="yahoo_chart",
            now_unix=fetched_at,
            drop_incomplete=True,
        )
        if persist_rows:
            upsert_bars(persist_rows)
    except Exception as exc:  # noqa: BLE001
        logger.debug("bars_5m persist skipped: %s", exc)

    raw = LiveQuote(
        symbol=nse_sym,
        ltp=float(price),
        quote_ts_unix=float(quote_ts),
        fetched_at_unix=fetched_at,
        age_sec=float(age_sec),
        feed_status=feed_status,
        source="yahoo_chart",
        timeframe="5m",
        prev_close=float(prev) if prev is not None else None,
        change_pct=change_pct,
        session_open=float(session_open) if session_open is not None else None,
        session_high=float(session_high) if session_high is not None else None,
        session_low=float(session_low) if session_low is not None else None,
        last_volume=last_vol,
        session_volume=vol_sum,
        vwap=vwap,
        currency=str(meta.get("currency") or "INR"),
        exchange=meta.get("exchangeName") or meta.get("fullExchangeName"),
        closes_5m=tuple(closes[-48:]),
        volumes_5m=tuple(volumes[-48:]),
        bars_5m=len(closes),
        yahoo_symbol=yahoo_symbol,
        error=None,
    )
    return annotate_live_quote(raw, now_unix=fetched_at, session=sess)


def quote_snapshot(yahoo_symbol: str) -> LiveQuote:
    """Desk entrypoint — broker preferred, Yahoo only if fallback policy allows."""
    from app.providers.live_quote_provider import resolve_live_quote

    return resolve_live_quote(yahoo_symbol).quote


def fetch_many(yahoo_symbols: list[str], max_workers: int = 6) -> dict[str, LiveQuote]:
    out: dict[str, LiveQuote] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = {pool.submit(quote_snapshot, s): s for s in yahoo_symbols}
        for fut in as_completed(futs):
            sym = futs[fut]
            try:
                out[sym] = fut.result()
            except Exception as exc:  # noqa: BLE001
                logger.error("quote worker crashed %s: %s", sym, exc)
                out[sym] = unavailable_quote(sym, f"worker_exception:{type(exc).__name__}")
    return out


def fetch_live_quotes(yahoo_symbols: list[str], max_workers: int = 6) -> dict[str, dict[str, Any]]:
    return {k: v.to_dict() for k, v in fetch_many(yahoo_symbols, max_workers=max_workers).items()}
