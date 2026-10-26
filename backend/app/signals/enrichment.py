"""
Signal enrichment: Screener fundamentals + EOD volume context.

NSE F&O open interest is intentionally empty — fabricating OI would mislead
clients. See ``OI_NOTE`` / ``how_to_enable`` for the vendor path.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

from app.fundamentals import fetch_fundamentals_many

logger = logging.getLogger(__name__)

# Cap Screener / quote fan-out when enriching desks
DEFAULT_TOP_N = 8

OI_NOTE = (
    "Open interest comes from the live Kotak Neo option-chain feed when that "
    "underlying is activated. Until then oi.available stays false — we do not invent OI."
)

OI_HOW_TO_ENABLE = (
    "POST /api/kotak/session/login then POST /api/kotak/option-chain/activate "
    "with the underlying (e.g. NIFTY / RELIANCE). Futures + ATM±wing options stream OI."
)

# Compact fundamentals keys attached to each call (full payload still on /api/stock)
_FUND_KEYS = (
    "available",
    "source",
    "name",
    "live_price",
    "market_cap_cr",
    "pe_ttm",
    "pb",
    "roe_pct",
    "roce_pct",
    "eps_ttm",
    "debt_to_equity",
    "dividend_yield_pct",
    "fifty_two_week_high",
    "fifty_two_week_low",
    "message",
    "cached",
)


def _safe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        if f != f:  # NaN
            return None
        return f
    except (TypeError, ValueError):
        return None


def _empty_oi() -> dict[str, Any]:
    return {
        "available": False,
        "oi": None,
        "oi_change": None,
        "oi_pct_change": None,
        "oi_note": OI_NOTE,
        "how_to_enable": OI_HOW_TO_ENABLE,
    }


def _oi_from_option_chain(symbol: str) -> dict[str, Any]:
    """Pull futures OI / PCR summary from an active Kotak option chain."""
    try:
        from app.kotak.option_chain import get_option_chain_engine

        eng = get_option_chain_engine()
        st = eng.status(symbol)
        if not st.get("active"):
            return _empty_oi()
        snap = eng.snapshot(symbol)
        fut = snap.get("future") or {}
        fq = fut.get("quote") or {}
        analytics = snap.get("analytics") or {}
        oi = fq.get("oi")
        prev = fq.get("prev_day_oi")
        oi_chg = None
        oi_pct = None
        if oi is not None and prev not in (None, 0):
            oi_chg = float(oi) - float(prev)
            oi_pct = (oi_chg / float(prev)) * 100.0
        elif oi is not None and fut.get("buildup"):
            oi_chg = (fut["buildup"] or {}).get("oi_change")
        return {
            "available": oi is not None or analytics.get("total_oi_pcr") is not None,
            "oi": oi,
            "oi_change": oi_chg,
            "oi_pct_change": round(oi_pct, 3) if oi_pct is not None else None,
            "total_oi_pcr": analytics.get("total_oi_pcr"),
            "atm_pcr": analytics.get("atm_pcr"),
            "max_pain": analytics.get("max_pain"),
            "call_wall": analytics.get("call_wall"),
            "put_wall": analytics.get("put_wall"),
            "future_buildup": fut.get("buildup"),
            "expiry": snap.get("expiry"),
            "source": "kotak_neo_ws",
            "oi_note": "Live Kotak F&O OI via option-chain engine",
            "how_to_enable": OI_HOW_TO_ENABLE,
        }
    except Exception as e:  # noqa: BLE001
        logger.debug("OI chain enrich skip %s: %s", symbol, e)
        return _empty_oi()


def _fundamentals_slice(payload: dict[str, Any] | None, symbol: str) -> dict[str, Any]:
    if not payload:
        return {"symbol": symbol, "available": False, "message": "Fundamentals unavailable"}
    out = {"symbol": symbol}
    for k in _FUND_KEYS:
        if k in payload:
            out[k] = payload[k]
    if "available" not in out:
        out["available"] = False
    return out


def _volume_rows_from_store(db: Any, symbols: list[str], as_of: str | None) -> dict[str, dict[str, Any]]:
    """Best-effort EOD volume vs vol_ma_20 from joined snapshot."""
    out: dict[str, dict[str, Any]] = {}
    if db is None or not symbols:
        return out
    try:
        freshness = db.freshness() if hasattr(db, "freshness") else {}
        trade_date = as_of or (freshness.get("latest_date") if isinstance(freshness, dict) else None)
        if not trade_date:
            return out
        snap = db.get_joined_snapshot(trade_date)
        if snap is None or getattr(snap, "empty", True):
            return out
        want = {s.upper() for s in symbols}
        subset = snap[snap["symbol"].isin(want)] if "symbol" in snap.columns else snap
        for _, row in subset.iterrows():
            sym = str(row.get("symbol") or "").upper()
            if not sym:
                continue
            vol = _safe_float(row.get("volume"))
            vol_ma = _safe_float(row.get("vol_ma_20"))
            ratio = None
            if vol is not None and vol_ma is not None and vol_ma > 0:
                ratio = round(vol / vol_ma, 3)
            out[sym] = {
                "available": vol is not None or vol_ma is not None,
                "trade_date": str(row.get("trade_date") or trade_date),
                "volume": vol,
                "vol_ma_20": vol_ma,
                "vol_vs_ma20": ratio,
                "note": (
                    f"EOD volume {ratio:.2f}× 20d avg"
                    if ratio is not None
                    else "EOD volume / vol_ma_20 from local store"
                ),
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("volume enrich failed: %s", e)
    return out


def enrich_symbols(
    symbols: Iterable[str],
    *,
    db: Any = None,
    as_of: str | None = None,
    top_n: int = DEFAULT_TOP_N,
    max_workers: int = 4,
) -> dict[str, dict[str, Any]]:
    """
    Map symbol → enrichment block for consultant calls.

    Fields per symbol:
      fundamentals  — Screener/Yahoo slice (cached; rate-limited via top_n)
      volume        — EOD volume vs vol_ma_20 when store has data, else unavailable
      oi / oi_note  — honest empty placeholder (no fake OI)
    """
    seen: list[str] = []
    for s in symbols:
        if not s:
            continue
        u = str(s).upper().strip()
        if u and u not in seen:
            seen.append(u)
    syms = seen[: max(0, int(top_n))]
    if not syms:
        return {}

    try:
        fins = fetch_fundamentals_many(syms, max_workers=max_workers)
    except Exception as e:  # noqa: BLE001
        logger.warning("fundamentals enrich failed: %s", e)
        fins = {}

    vol_map = _volume_rows_from_store(db, syms, as_of)

    out: dict[str, dict[str, Any]] = {}
    for s in syms:
        vol = vol_map.get(s) or {
            "available": False,
            "trade_date": None,
            "volume": None,
            "vol_ma_20": None,
            "vol_vs_ma20": None,
            "note": "No local EOD volume / vol_ma_20 for this symbol yet",
        }
        oi = _oi_from_option_chain(s)
        out[s] = {
            "fundamentals": _fundamentals_slice(fins.get(s), s),
            "volume": vol,
            "oi": oi,
            "oi_note": oi.get("oi_note") or OI_NOTE,
        }
    return out


def attach_enrichment(
    calls: list[dict[str, Any]],
    *,
    db: Any = None,
    as_of: str | None = None,
    top_n: int = DEFAULT_TOP_N,
    sides: Optional[Iterable[str]] = None,
) -> list[dict[str, Any]]:
    """
    Merge enrichment into call ``context`` for the first matching top_n symbols.

    If ``sides`` is set (e.g. BUY/SELL), only those calls are enriched (rate limit).
    """
    if not calls:
        return calls
    side_filter = {str(x).upper() for x in sides} if sides else None
    candidates = [
        c
        for c in calls
        if c.get("symbol")
        and (side_filter is None or str(c.get("side") or "").upper() in side_filter)
    ]
    # Fall back to board order when filter yields nothing (e.g. all HOLD)
    pool = candidates or [c for c in calls if c.get("symbol")]
    symbols = [str(c["symbol"]).upper() for c in pool]
    ctx = enrich_symbols(symbols, db=db, as_of=as_of, top_n=top_n)
    for c in calls:
        sym = str(c.get("symbol") or "").upper()
        if sym in ctx:
            c["context"] = {**(c.get("context") or {}), **ctx[sym]}
    return calls
