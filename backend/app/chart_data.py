"""
Chart workstation data — multi-timeframe OHLCV (+ OI), previous-day levels,
VWAP bands helpers, and live bar merge from Kotak FeedHub.

Intervals: 1m, 5m, 15m, 1h, 1d. No synthetic candles.
"""
from __future__ import annotations

import json
import logging
import math
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional
from zoneinfo import ZoneInfo

from app.config import config
from app.store import Database

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

Interval = Literal["1m", "5m", "15m", "1h", "1d"]
_VALID = frozenset({"1m", "5m", "15m", "1h", "1d"})
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) SwingDesk/4.4"

# Yahoo chart interval / range pairs that return usable series
_YAHOO = {
    "1m": ("1m", "1d"),
    "5m": ("5m", "5d"),
    "15m": ("15m", "5d"),
    "1h": ("60m", "1mo"),
}


def _yahoo_symbol(symbol: str) -> str:
    s = symbol.upper().strip()
    if s in ("NIFTY", "NIFTY50", "NSEI"):
        return "^NSEI"
    if s in ("BANKNIFTY", "NSEBANK"):
        return "^NSEBANK"
    if s.startswith("^") or s.endswith(".NS") or s.endswith(".BO"):
        return s
    return f"{s}.NS"


def _fetch_yahoo_chart(yahoo_symbol: str, interval: str, range_: str) -> dict[str, Any] | None:
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}"
        f"?interval={interval}&range={range_}&includePrePost=false"
    )
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as e:
        logger.error("yahoo chart %s failed: %s", yahoo_symbol, e)
        return None
    result = (payload.get("chart") or {}).get("result") or []
    return result[0] if result else None


def _bars_from_yahoo(data: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    """Parse Yahoo chart result → OHLCV bars.

    Returns (bars, missing_skipped) where missing_skipped counts timestamps
    with null OHLCV (never interpolated / filled).
    """
    ts = data.get("timestamp") or []
    q = ((data.get("indicators") or {}).get("quote") or [{}])[0]
    opens = q.get("open") or []
    highs = q.get("high") or []
    lows = q.get("low") or []
    closes = q.get("close") or []
    vols = q.get("volume") or []
    out: list[dict[str, Any]] = []
    missing = 0
    for i, t in enumerate(ts):
        o = opens[i] if i < len(opens) else None
        h = highs[i] if i < len(highs) else None
        l_ = lows[i] if i < len(lows) else None
        c = closes[i] if i < len(closes) else None
        v = vols[i] if i < len(vols) else 0
        if c is None or o is None or h is None or l_ is None:
            missing += 1
            continue
        out.append(
            {
                "time": int(t),
                "open": float(o),
                "high": float(h),
                "low": float(l_),
                "close": float(c),
                "volume": float(v or 0),
                "oi": None,
            }
        )
    return out, missing


def _freshness_for_bars(
    bars: list[dict[str, Any]], *, interval: str
) -> dict[str, Any]:
    """Age / status of the last candle — never invents prices."""
    if not bars:
        return {
            "status": "unavailable",
            "age_sec": None,
            "last_bar_time": None,
            "label": "UNAVAILABLE",
        }
    last_t = bars[-1]["time"]
    now = time.time()
    if isinstance(last_t, str):
        # Daily YYYY-MM-DD — treat as IST session close ~15:30
        try:
            d = datetime.strptime(str(last_t)[:10], "%Y-%m-%d").replace(tzinfo=IST)
            close_guess = d.replace(hour=15, minute=30, second=0)
            age = max(0.0, now - close_guess.timestamp())
        except ValueError:
            age = None
        # EOD: stale if older than ~2 calendar days
        if age is None:
            status, label = "unknown", "UNKNOWN"
        elif age > 3 * 86400:
            status, label = "stale", "STALE"
        else:
            status, label = "ok", "EOD"
        return {
            "status": status,
            "age_sec": round(age, 1) if age is not None else None,
            "last_bar_time": last_t,
            "label": label,
            "timezone": "Asia/Kolkata",
        }
    age = max(0.0, now - float(last_t))
    # Soft thresholds by interval (research UI, not trading SLA)
    soft = {"1m": 180, "5m": 600, "15m": 1800, "1h": 7200}.get(interval, 900)
    hard = soft * 4
    if age > hard:
        status, label = "stale", "STALE"
    elif age > soft:
        status, label = "aging", "AGING"
    else:
        status, label = "ok", "FRESH"
    return {
        "status": status,
        "age_sec": round(age, 1),
        "last_bar_time": int(last_t),
        "last_bar_ist": datetime.fromtimestamp(int(last_t), tz=IST).isoformat(),
        "label": label,
        "timezone": "Asia/Kolkata",
    }


def _optional_feature_block(
    *,
    walls: dict[str, Any] | None,
    oi_series: list[dict[str, Any]],
    source: str,
) -> dict[str, Any]:
    """Honest availability for L2 / OI / walls / PCR — never placeholders."""
    has_kotak_merge = "+kotak_ws" in source
    walls_ok = bool(
        walls
        and (
            walls.get("call_wall") is not None
            or walls.get("put_wall") is not None
            or walls.get("max_pain") is not None
        )
    )
    return {
        "oi": {
            "available": bool(oi_series),
            "reason": None
            if oi_series
            else "oi_requires_kotak_ws_bar_merge_not_present",
        },
        "walls": {
            "available": walls_ok,
            "reason": None
            if walls_ok
            else "option_chain_inactive_or_no_analytics",
        },
        "pcr": {
            "available": False,
            "reason": "pcr_only_via_active_kotak_option_chain_panel_not_chart",
        },
        "depth_l2": {
            "available": False,
            "reason": "l2_not_rendered_on_chart_subscribe_path_not_e2e_verified",
        },
        "kotak_live_bars_merged": has_kotak_merge,
    }


def _bars_from_eod(symbol: str, limit: int) -> list[dict[str, Any]]:
    db = Database(config.db_path)
    hist = db.get_symbol_history(symbol, lookback=max(limit + 5, limit))
    if hist is None or hist.empty:
        # NIFTY special series
        if symbol.upper() in ("NIFTY", "NIFTY50"):
            hist = db.get_nifty_series(lookback=max(limit + 5, limit))
    if hist is None or hist.empty:
        return []
    hist = hist.tail(limit)
    out: list[dict[str, Any]] = []
    for _, r in hist.iterrows():
        # Lightweight Charts expects unix seconds (UTC) for daily as YYYY-MM-DD string OR unix
        # Use date string for daily to avoid TZ shift
        d = str(r["trade_date"])[:10]
        out.append(
            {
                "time": d,
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": float(r.get("volume") or 0),
                "oi": None,
            }
        )
    return out


def previous_day_levels(symbol: str) -> dict[str, Any] | None:
    """PDH / PDL / PDC from last completed EOD session."""
    db = Database(config.db_path)
    hist = db.get_symbol_history(symbol.upper(), lookback=5)
    if (hist is None or hist.empty) and symbol.upper() in ("NIFTY", "NIFTY50"):
        hist = db.get_nifty_series(lookback=5)
    if hist is None or hist.empty or len(hist) < 1:
        return None
    # Last row is most recent EOD — if market still open that may be prior day
    last = hist.iloc[-1]
    return {
        "date": str(last["trade_date"])[:10],
        "high": float(last["high"]),
        "low": float(last["low"]),
        "close": float(last["close"]),
        "open": float(last["open"]),
    }


def compute_session_vwap_bands(bars: list[dict[str, Any]]) -> dict[str, Any] | None:
    """
    Intraday VWAP + ±1/±2 SD bands from typical price.

    SD ≈ sqrt(Σ vol·(tp−vwap)² / Σ vol)
    """
    if not bars:
        return None
    # Restrict to today's IST session when times are unix
    today = datetime.now(IST).date()
    session: list[dict[str, Any]] = []
    for b in bars:
        t = b.get("time")
        if isinstance(t, int):
            d = datetime.fromtimestamp(t, tz=IST).date()
            if d == today:
                session.append(b)
        else:
            session.append(b)
    if len(session) < 2:
        session = bars
    num = den = 0.0
    points: list[tuple[Any, float, float, float]] = []  # time, vwap, vol, tp
    for b in session:
        tp = (float(b["high"]) + float(b["low"]) + float(b["close"])) / 3.0
        vol = max(float(b.get("volume") or 0), 0.0)
        if vol <= 0:
            vol = 1.0  # still advance VWAP path on thin bars
        num += tp * vol
        den += vol
        vwap = num / den if den else tp
        points.append((b["time"], vwap, vol, tp))

    if den <= 0:
        return None
    vwap_final = num / den
    var = 0.0
    for _, _, vol, tp in points:
        var += vol * (tp - vwap_final) ** 2
    sd = math.sqrt(var / den) if den else 0.0

    series = [{"time": t, "value": round(v, 4)} for t, v, _, _ in points]
    return {
        "vwap": round(vwap_final, 4),
        "sd": round(sd, 4),
        "band_1_upper": round(vwap_final + sd, 4),
        "band_1_lower": round(vwap_final - sd, 4),
        "band_2_upper": round(vwap_final + 2 * sd, 4),
        "band_2_lower": round(vwap_final - 2 * sd, 4),
        "series": series,
        "band_1_upper_series": [{"time": t, "value": round(v + sd, 4)} for t, v, _, _ in points],
        "band_1_lower_series": [{"time": t, "value": round(v - sd, 4)} for t, v, _, _ in points],
        "band_2_upper_series": [{"time": t, "value": round(v + 2 * sd, 4)} for t, v, _, _ in points],
        "band_2_lower_series": [{"time": t, "value": round(v - 2 * sd, 4)} for t, v, _, _ in points],
    }


def _ema_series(closes: list[float], period: int) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(closes)
    if len(closes) < period:
        return out
    k = 2.0 / (period + 1)
    e = sum(closes[:period]) / period
    out[period - 1] = e
    for i in range(period, len(closes)):
        e = closes[i] * k + e * (1 - k)
        out[i] = e
    return out


def ema_ribbon(bars: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    closes = [float(b["close"]) for b in bars]
    times = [b["time"] for b in bars]
    ribbon: dict[str, list[dict[str, Any]]] = {}
    for period in (9, 21, 50, 200):
        series = _ema_series(closes, period)
        ribbon[f"ema{period}"] = [
            {"time": times[i], "value": round(v, 4)}
            for i, v in enumerate(series)
            if v is not None
        ]
    return ribbon


def rsi_series(bars: list[dict[str, Any]], period: int = 14) -> list[dict[str, Any]]:
    closes = [float(b["close"]) for b in bars]
    times = [b["time"] for b in bars]
    if len(closes) < period + 1:
        return []
    out: list[dict[str, Any]] = []
    gains = []
    losses = []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
        if i < period:
            continue
        if i == period:
            ag = sum(gains[:period]) / period
            al = sum(losses[:period]) / period
        else:
            ag = (ag * (period - 1) + gains[i - 1]) / period
            al = (al * (period - 1) + losses[i - 1]) / period
        rs = ag / al if al > 1e-12 else 100.0
        rsi = 100.0 - (100.0 / (1.0 + rs)) if al > 1e-12 else 100.0
        out.append({"time": times[i], "value": round(rsi, 4)})
    return out


def macd_series(
    bars: list[dict[str, Any]], fast: int = 12, slow: int = 26, signal: int = 9
) -> dict[str, list[dict[str, Any]]]:
    closes = [float(b["close"]) for b in bars]
    times = [b["time"] for b in bars]
    ema_fast = _ema_series(closes, fast)
    ema_slow = _ema_series(closes, slow)
    macd_line: list[Optional[float]] = []
    for i in range(len(closes)):
        if ema_fast[i] is None or ema_slow[i] is None:
            macd_line.append(None)
        else:
            macd_line.append(ema_fast[i] - ema_slow[i])  # type: ignore[operator]
    # signal on macd values (skip Nones)
    macd_vals = [v if v is not None else 0.0 for v in macd_line]
    sig = _ema_series(macd_vals, signal)
    macd_out = []
    signal_out = []
    hist_out = []
    for i, t in enumerate(times):
        if macd_line[i] is None or sig[i] is None or i < slow - 1:
            continue
        m = float(macd_line[i])  # type: ignore[arg-type]
        s = float(sig[i])  # type: ignore[arg-type]
        macd_out.append({"time": t, "value": round(m, 6)})
        signal_out.append({"time": t, "value": round(s, 6)})
        hist_out.append(
            {
                "time": t,
                "value": round(m - s, 6),
                "color": "rgba(62,207,142,0.7)" if m >= s else "rgba(240,113,120,0.7)",
            }
        )
    return {"macd": macd_out, "signal": signal_out, "histogram": hist_out}


def _merge_live_bars(
    symbol: str, interval: Interval, bars: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Overlay FeedHub aggregated bars when Kotak WS is streaming this symbol."""
    if interval not in ("1m", "5m", "15m"):
        return bars
    try:
        from app.kotak.feed_hub import get_feed_hub
        from app.kotak.scrip_master import get_scrip_master

        hub = get_feed_hub()
        st = hub.status()
        if not (st.get("ws") or {}).get("connected"):
            return bars
        # Resolve key
        q = hub.get_quote(symbol.upper())
        key = None
        if q and q.instrument_token and q.exchange_segment:
            key = f"{q.exchange_segment}|{q.instrument_token}"
        else:
            try:
                inst = get_scrip_master().resolve_equity(symbol)
                key = inst.key()
            except Exception:
                # Index aliases
                for alias in (symbol.upper(), "NIFTY 50", "Nifty Bank"):
                    q2 = hub.get_quote(alias)
                    if q2 and q2.instrument_token:
                        key = f"{q2.exchange_segment}|{q2.instrument_token}"
                        break
        if not key:
            return bars
        live = hub.get_bars(key, interval=interval, limit=500)
        if not live:
            return bars
        by_t = {b["time"]: dict(b) for b in bars if isinstance(b.get("time"), int)}
        for lb in live:
            t = int(lb["bucket_start_unix"])
            by_t[t] = {
                "time": t,
                "open": float(lb["open"]),
                "high": float(lb["high"]),
                "low": float(lb["low"]),
                "close": float(lb["close"]),
                "volume": float(lb["volume"]),
                "oi": float(lb["oi"]) if lb.get("oi") is not None else None,
                "closed": bool(lb.get("closed")),
            }
        merged = [by_t[k] for k in sorted(by_t)]
        return merged
    except Exception as e:  # noqa: BLE001
        logger.debug("live bar merge skipped: %s", e)
        return bars


def _walls_for(symbol: str) -> dict[str, Any] | None:
    try:
        from app.kotak.option_chain import get_option_chain_engine

        eng = get_option_chain_engine()
        und = symbol.upper()
        if und in ("NIFTY50", "NSEI"):
            und = "NIFTY"
        if und in ("NSEBANK",):
            und = "BANKNIFTY"
        st = eng.status(und)
        if not st.get("active"):
            return None
        snap = eng.snapshot(und)
        a = snap.get("analytics") or {}
        return {
            "call_wall": a.get("call_wall"),
            "put_wall": a.get("put_wall"),
            "max_pain": a.get("max_pain"),
            "expiry": snap.get("expiry"),
            "atm": snap.get("atm"),
        }
    except Exception:
        return None


def build_chart_payload(
    symbol: str,
    *,
    interval: str = "1d",
    limit: int = 300,
) -> dict[str, Any]:
    sym = symbol.upper().strip()
    iv = interval.lower().strip()
    if iv not in _VALID:
        raise ValueError(f"interval must be one of {sorted(_VALID)}")
    limit = max(20, min(int(limit), 2000))

    source = "unknown"
    bars: list[dict[str, Any]] = []
    missing_skipped = 0
    provider_range: dict[str, Any] = {"limit_requested": limit}
    price_kind = "unknown"
    bar_time_format = "unix_seconds_utc"

    if iv == "1d":
        bars = _bars_from_eod(sym, limit)
        source = "kotak_eod_db" if bars else "empty"
        bar_time_format = "date_yyyy_mm_dd_ist_session"
        price_kind = "eod_close"
        provider_range["primary"] = "sqlite_eod"
        if not bars:
            # Yahoo daily fallback (market data, not demo)
            ydata = _fetch_yahoo_chart(_yahoo_symbol(sym), "1d", "1y")
            if ydata:
                raw, missing_skipped = _bars_from_yahoo(ydata)
                raw = raw[-limit:]
                # IST calendar date — avoid UTC day-shift for NSE names
                bars = []
                for b in raw:
                    d = datetime.fromtimestamp(int(b["time"]), tz=IST).strftime(
                        "%Y-%m-%d"
                    )
                    bars.append({**b, "time": d})
                source = "yahoo_chart_1d"
                price_kind = "yahoo_daily_close"
                provider_range.update(
                    {
                        "yahoo_interval": "1d",
                        "yahoo_range": "1y",
                        "yahoo_symbol": _yahoo_symbol(sym),
                    }
                )
    else:
        y_iv, y_range = _YAHOO[iv]  # type: ignore[index]
        provider_range.update(
            {
                "yahoo_interval": y_iv,
                "yahoo_range": y_range,
                "yahoo_symbol": _yahoo_symbol(sym),
            }
        )
        ydata = _fetch_yahoo_chart(_yahoo_symbol(sym), y_iv, y_range)
        if ydata:
            raw, missing_skipped = _bars_from_yahoo(ydata)
            bars = raw[-limit:]
            source = f"yahoo_chart_{iv}"
            price_kind = "intraday_bar_close"
        bars = _merge_live_bars(sym, iv, bars)  # type: ignore[arg-type]
        if any(b.get("oi") is not None for b in bars):
            source = f"{source}+kotak_ws"
            price_kind = "intraday_bar_close_kotak_merge"

    walls = _walls_for(sym)
    pd = previous_day_levels(sym)
    as_of = datetime.now(timezone.utc).isoformat()
    tz_meta = {
        "display_timezone": "Asia/Kolkata",
        "bar_time_format": bar_time_format,
        "note": (
            "Intraday bar `time` is Unix seconds (UTC instant); UI should label IST. "
            "Daily bars use YYYY-MM-DD as IST session date (no intraday clock)."
        ),
    }

    if not bars:
        return {
            "symbol": sym,
            "interval": iv,
            "bars": [],
            "volume": [],
            "has_data": False,
            "status": "unavailable",
            "source": source if source != "unknown" else "empty",
            "price_kind": price_kind,
            "message": (
                f"No candles for {sym} @ {iv} — ingest EOD or wait for live tape. "
                "No synthetic bars."
            ),
            "previous_day": pd,
            "walls": None,
            "oi": [],
            "freshness": _freshness_for_bars([], interval=iv),
            "missing_bars_skipped": missing_skipped,
            "range": {**provider_range, "returned_bars": 0},
            "timezone": tz_meta,
            "optional_features": _optional_feature_block(
                walls=None, oi_series=[], source=source
            ),
            "indicators_note": (
                "EMA ribbon matches index_core.ema on the same closes. "
                "Chart RSI pane uses Wilder smoothing; desk strategies use "
                "simple-period RSI — same closes, different formula."
            ),
            "as_of": as_of,
            "demo": False,
        }

    vwap = compute_session_vwap_bands(bars) if iv != "1d" else None
    ribbon = ema_ribbon(bars)
    rsi = rsi_series(bars)
    macd = macd_series(bars)
    oi_series = [
        {"time": b["time"], "value": float(b["oi"])}
        for b in bars
        if b.get("oi") is not None
    ]

    vol_colors = []
    for b in bars:
        up = float(b["close"]) >= float(b["open"])
        vol_colors.append(
            {
                "time": b["time"],
                "value": float(b["volume"]),
                "color": "rgba(62, 207, 142, 0.55)" if up else "rgba(240, 113, 120, 0.55)",
            }
        )

    freshness = _freshness_for_bars(bars, interval=iv)
    status = "ok" if freshness.get("status") == "ok" else freshness.get("status", "ok")
    if freshness.get("status") in ("stale", "aging"):
        status = freshness["status"]

    last_close = float(bars[-1]["close"])
    return {
        "symbol": sym,
        "interval": iv,
        "bars": bars,
        "volume": vol_colors,
        "has_data": True,
        "status": status,
        "source": source,
        "price_kind": price_kind,
        "previous_day": pd,
        "vwap": vwap,
        "ema_ribbon": ribbon,
        "rsi": rsi,
        "macd": macd,
        "oi": oi_series,
        "walls": walls if walls else None,
        "ltp": last_close,
        "ltp_note": (
            "Last bar close — not broker tick LTP unless Kotak WS merge is active"
            if "kotak" not in source
            else "Last bar close; Kotak LTP may appear on /live poll when subscribed"
        ),
        "freshness": freshness,
        "missing_bars_skipped": missing_skipped,
        "range": {**provider_range, "returned_bars": len(bars)},
        "timezone": tz_meta,
        "optional_features": _optional_feature_block(
            walls=walls, oi_series=oi_series, source=source
        ),
        "indicators_note": (
            "Overlays computed from the returned OHLCV only (no fill-forward). "
            "EMA9/21/50/200 match strategy index_core.ema on identical closes. "
            "Chart RSI = Wilder; desk RSI = simple period average."
        ),
        "as_of": as_of,
        "demo": False,
    }


def live_bar_update(symbol: str, interval: str = "5m") -> dict[str, Any]:
    """Latest bar + LTP for series.update() polling."""
    sym = symbol.upper().strip()
    iv = interval.lower().strip()
    if iv not in _VALID:
        raise ValueError(f"interval must be one of {sorted(_VALID)}")
    payload = build_chart_payload(sym, interval=iv, limit=5)
    bars = payload.get("bars") or []
    last = bars[-1] if bars else None
    ltp = payload.get("ltp")
    ltp_source = "bar_close"
    try:
        from app.kotak.feed_hub import get_feed_hub

        q = get_feed_hub().get_quote(sym) or get_feed_hub().quote_for_yahoo_symbol(
            _yahoo_symbol(sym)
        )
        if q and q.ltp is not None:
            ltp = float(q.ltp)
            ltp_source = "kotak_ws"
    except Exception:
        pass
    walls = payload.get("walls")
    opt = payload.get("optional_features") or {}
    return {
        "symbol": sym,
        "interval": iv,
        "bar": last,
        "ltp": ltp,
        "ltp_source": ltp_source,
        "price_kind": payload.get("price_kind"),
        "walls": walls,
        "walls_available": bool((opt.get("walls") or {}).get("available")),
        "freshness": payload.get("freshness"),
        "status": payload.get("status") or ("unavailable" if not last else "ok"),
        "as_of": datetime.now(timezone.utc).isoformat(),
        "source": payload.get("source"),
        "has_data": bool(payload.get("has_data")),
    }
