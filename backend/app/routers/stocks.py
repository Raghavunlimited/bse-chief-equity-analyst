from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.config import config
from app.fundamentals import fetch_fundamentals
from app.store import Database
from app.universe_nse import all_eq_symbols, search_eq_symbols
from universe import SECTOR_MAP

router = APIRouter(prefix="/api", tags=["stocks"])
db = Database(config.db_path)


def _safe_float(v):
    if v is None:
        return None
    try:
        f = float(v)
        if f != f:  # NaN
            return None
        return f
    except (TypeError, ValueError):
        return None


@router.get("/stocks")
def list_stocks(
    q: str = Query("", max_length=40),
    page: int = Query(1, ge=1),
    page_size: int = Query(60, ge=1, le=200),
    in_db_only: bool = Query(False),
):
    """
    Browse NSE EQ cash names. Defaults to the full listed universe (~2,500).
    Marks which symbols already have EOD in the desk database.
    """
    db_syms = set(db.get_all_symbols())
    qn = (q or "").upper().strip()

    if in_db_only:
        universe = sorted(db_syms)
        if qn:
            universe = [s for s in universe if qn in s]
    elif qn:
        universe = search_eq_symbols(qn, limit=500)
        # Prefer DB hits first when searching
        universe = sorted(universe, key=lambda s: (0 if s in db_syms else 1, s))
    else:
        universe = all_eq_symbols()
        if not universe:
            universe = sorted(db_syms)

    total = len(universe)
    start = (page - 1) * page_size
    chunk = universe[start : start + page_size]
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "listed_eq_approx": len(all_eq_symbols()) or total,
        "in_database": len(db_syms),
        "results": [
            {
                "symbol": s,
                "sector": SECTOR_MAP.get(s, "Unknown"),
                "has_eod": s in db_syms,
            }
            for s in chunk
        ],
    }


@router.get("/stock/{symbol}")
def stock_detail(symbol: str):
    symbol = symbol.upper().strip()
    hist = db.get_symbol_history(symbol, lookback=120)
    fundamentals = fetch_fundamentals(symbol)

    latest = None
    indicators = {}
    if not hist.empty:
        last = hist.iloc[-1]
        latest = {
            "trade_date": str(last["trade_date"]),
            "open": float(last["open"]),
            "high": float(last["high"]),
            "low": float(last["low"]),
            "close": float(last["close"]),
            "volume": float(last["volume"]),
            "turnover": float(last.get("turnover") or 0),
        }
        snap = db.get_joined_snapshot(str(last["trade_date"]))
        row = snap[snap["symbol"] == symbol]
        if not row.empty:
            ind = row.iloc[0].to_dict()
            indicators = {
                k: _safe_float(ind.get(k))
                for k in (
                    "sma_20",
                    "sma_50",
                    "rsi_14",
                    "atr_14",
                    "vol_ma_20",
                    "hh_20",
                    "ll_20",
                    "roc_3",
                    "roc_20",
                )
                if k in ind
            }

    # Stock can be opened from full NSE list even without local EOD
    if latest is None and not fundamentals.get("available"):
        listed = set(all_eq_symbols())
        if symbol not in listed and symbol not in set(db.get_all_symbols()):
            raise HTTPException(404, f"Unknown symbol {symbol}")

    if latest is not None:
        latest = {
            **latest,
            "price_kind": "eod_close",
            "note": "Kotak/Yahoo EOD settlement close — not live LTP",
        }
    return {
        "symbol": symbol,
        "sector": SECTOR_MAP.get(symbol, "Unknown"),
        "has_eod": latest is not None,
        "latest": latest,
        "price_kind": "eod_close" if latest is not None else None,
        "indicators": indicators,
        "fundamentals": fundamentals,
    }


@router.get("/stock/{symbol}/fundamentals")
def stock_fundamentals(
    symbol: str,
    refresh: bool = Query(False, description="Bypass cache and refetch"),
):
    return fetch_fundamentals(symbol.upper().strip(), bypass_cache=refresh)


@router.get("/chart/{symbol}")
def chart(
    symbol: str,
    days: int = Query(90, ge=20, le=500),
    interval: str = Query(
        "1d",
        description="1m | 5m | 15m | 1h | 1d — Phase 4 workstation timeframes",
    ),
    limit: int = Query(300, ge=20, le=2000),
):
    """
    Multi-timeframe OHLCV (+ OI when streamed) for the Lightweight Charts workstation.

    ``days`` retained for back-compat on daily charts (maps to limit when interval=1d).
    """
    from app.chart_data import build_chart_payload

    symbol = symbol.upper().strip()
    iv = (interval or "1d").lower().strip()
    lim = days if iv == "1d" and limit == 300 else limit
    if iv == "1d":
        lim = max(days, 20)
    try:
        payload = build_chart_payload(symbol, interval=iv, limit=lim)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    # Back-compat fields for any legacy ProStockChart consumers
    legacy_bars = []
    for b in payload.get("bars") or []:
        legacy_bars.append(
            {
                "date": b["time"] if isinstance(b["time"], str) else str(b["time"]),
                "open": b["open"],
                "high": b["high"],
                "low": b["low"],
                "close": b["close"],
                "volume": b["volume"],
                "sma20": None,
                "sma50": None,
            }
        )
    # Attach SMA20/50 onto legacy daily bars from EMA ribbon when present
    ribbon = payload.get("ema_ribbon") or {}
    if iv == "1d" and ribbon.get("ema21"):
        by_t = {x["time"]: x["value"] for x in ribbon.get("ema21") or []}
        by_t50 = {x["time"]: x["value"] for x in ribbon.get("ema50") or []}
        for row in legacy_bars:
            row["sma20"] = by_t.get(row["date"])
            row["sma50"] = by_t50.get(row["date"])

    overlays = ["ema9", "ema21", "ema50", "ema200", "pdh_pdl_pdc"]
    if iv != "1d":
        overlays.append("vwap")
    opt = payload.get("optional_features") or {}
    if (opt.get("walls") or {}).get("available"):
        overlays.append("walls")
    if (opt.get("oi") or {}).get("available"):
        overlays.append("oi")

    return {
        **payload,
        "bars_legacy": legacy_bars,
        "has_eod": bool(payload.get("has_data") and iv == "1d"),
        "range_days": days if iv == "1d" else None,
        "overlays": overlays,
        "overlays_note": (
            "walls/oi listed only when optional_features mark them available; "
            "never inferred."
        ),
    }


@router.get("/chart/{symbol}/live")
def chart_live(
    symbol: str,
    interval: str = Query("5m", description="1m | 5m | 15m | 1h | 1d"),
):
    """Latest bar + LTP for lightweight-charts series.update() polling."""
    from app.chart_data import live_bar_update

    try:
        return live_bar_update(symbol.upper().strip(), interval=interval)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/stocks/search")
def search(q: str = Query(..., min_length=1)):
    q = q.upper().strip()
    db_syms = set(db.get_all_symbols())
    # Full NSE EQ search so users can open any listed name
    hits = search_eq_symbols(q, limit=30)
    if not hits:
        hits = [s for s in sorted(db_syms) if q in s][:30]
    return {
        "results": [
            {
                "symbol": s,
                "sector": SECTOR_MAP.get(s, "Unknown"),
                "has_eod": s in db_syms,
            }
            for s in hits
        ]
    }
