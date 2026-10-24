"""Customer-facing platform: signals history, market data via adapters, disclosures."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.adapters import get_market_adapter
from app.auth_deps import get_current_user, platform
from app.config import config
from app.platform_db import PlatformDB

router = APIRouter(prefix="/api/platform", tags=["platform"])

Category = Literal["intraday", "swing", "commodity"]


DISCLOSURE = {
    "title": "Important risk disclosure",
    "body": (
        "Swing Desk provides research-style analysis and potential signals for educational "
        "and informational purposes only. Analysis is not a guarantee of returns, not "
        "personalized investment advice, and not an offer to buy or sell securities or "
        "commodities. The platform does not execute trades or connect to brokerage accounts. "
        "Past patterns and demo illustrations do not predict future results. "
        "Verify all data independently before acting."
    ),
    "ai_note": (
        "Optional AI commentary is labeled as AI-generated, cites provided inputs only, "
        "and is never an authoritative signal."
    ),
}


@router.get("/disclosure")
def disclosure():
    return {
        **DISCLOSURE,
        "jurisdiction_note": config.jurisdiction_note,
        "data_adapter": config.market_data_adapter,
    }


@router.get("/instruments")
def list_instruments(
    category: Optional[Category] = None,
    user: dict = Depends(get_current_user),
    db: PlatformDB = Depends(platform),
):
    return {
        "instruments": db.list_instruments(category=category, active_only=True),
        "data_mode_default": config.market_data_adapter,
    }


@router.get("/signals")
def list_signals(
    category: Optional[Category] = None,
    symbol: Optional[str] = None,
    status: Optional[str] = None,
    history: bool = Query(False, description="Include expired/revised records"),
    limit: int = Query(100, ge=1, le=500),
    user: dict = Depends(get_current_user),
    db: PlatformDB = Depends(platform),
):
    rows = db.list_signals(
        category=category,
        symbol=symbol,
        status=status,
        include_history=history,
        limit=limit,
    )
    return {
        "signals": rows,
        "count": len(rows),
        "includes_history": history,
        "disclosure": DISCLOSURE["title"],
    }


@router.get("/signals/{signal_id}")
def get_signal(
    signal_id: str,
    user: dict = Depends(get_current_user),
    db: PlatformDB = Depends(platform),
):
    row = db.get_signal(signal_id)
    if not row:
        raise HTTPException(status_code=404, detail="Signal not found")
    return row


def _wrap_adapter(payload: dict) -> dict:
    """Normalize adapter TypedDict into API shape with nested provenance + data_mode."""
    out = dict(payload)
    mode = out.get("provenance") or "demo"
    out["data_mode"] = mode
    out["provenance"] = {
        "data_mode": mode,
        "source": out.get("source") or "unknown",
        "as_of": out.get("as_of"),
        "note": "DEMO adapter data" if mode == "demo" else f"Source={out.get('source')}",
    }
    # Convenience aliases used by UI
    if "last" in out and "price" not in out:
        out["price"] = out["last"]
    out["available"] = True
    return out


def _unavailable(symbol: str, reason: str) -> dict:
    return {
        "symbol": symbol.upper(),
        "available": False,
        "price": None,
        "data_mode": "demo",
        "provenance": {
            "data_mode": "demo",
            "source": "demo",
            "as_of": None,
            "note": reason,
            "incomplete": True,
        },
    }


@router.get("/market/{symbol}/quote")
def market_quote(
    symbol: str,
    category: Category = "swing",
    user: dict = Depends(get_current_user),
):
    _ = category  # reserved for multi-adapter routing
    adapter = get_market_adapter()
    try:
        return _wrap_adapter(dict(adapter.get_quote(symbol)))
    except KeyError:
        return _unavailable(symbol, "Instrument not in demo universe — no fabricated quote")


@router.get("/market/{symbol}/bars")
def market_bars(
    symbol: str,
    category: Category = "swing",
    timeframe: str = "1d",
    limit: int = Query(60, ge=1, le=120),
    user: dict = Depends(get_current_user),
):
    _ = category
    adapter = get_market_adapter()
    try:
        return _wrap_adapter(
            dict(adapter.get_bars(symbol, interval=timeframe, lookback=limit))
        )
    except KeyError:
        return {**_unavailable(symbol, "No demo bars for unknown symbol"), "bars": []}


@router.get("/market/{symbol}/oi")
def market_oi(
    symbol: str,
    category: Category = "swing",
    user: dict = Depends(get_current_user),
):
    _ = category
    adapter = get_market_adapter()
    try:
        raw = dict(adapter.get_oi(symbol))
        wrapped = _wrap_adapter(raw)
        # Honest: equity OI of 0 means not applicable in demo seed
        if float(raw.get("open_interest") or 0) == 0:
            wrapped["available"] = False
            wrapped["note"] = "OI not applicable / zero in demo for this instrument — not fabricated"
            wrapped["provenance"]["incomplete"] = True
        return wrapped
    except KeyError:
        return _unavailable(symbol, "OI unavailable — not fabricated")


@router.get("/market/{symbol}/financials")
def market_financials(
    symbol: str,
    category: Category = "swing",
    user: dict = Depends(get_current_user),
):
    _ = category
    adapter = get_market_adapter()
    try:
        raw = dict(adapter.get_financials(symbol))
        wrapped = _wrap_adapter(raw)
        if raw.get("pe") is None and (raw.get("extras") or {}).get("asset_class") == "commodity":
            wrapped["available"] = False
            wrapped["note"] = "Company financials not applicable to commodities"
            wrapped["provenance"]["incomplete"] = True
        return wrapped
    except KeyError:
        return _unavailable(symbol, "Financials unavailable — not fabricated")


@router.get("/demo/signals")
def demo_signals_bundle(user: dict = Depends(get_current_user), db: PlatformDB = Depends(platform)):
    """
    Clearly labeled demo analyses across swing / intraday / commodity.
    Never implies live market data.
    """
    by_cat = {}
    for cat in ("swing", "intraday", "commodity"):
        by_cat[cat] = db.list_signals(category=cat, include_history=True, limit=50)
    return {
        "data_mode": "demo",
        "label": "DEMO — deterministic sample analyses, not live signals",
        "categories": by_cat,
        "disclosure": DISCLOSURE,
        "jurisdiction_note": config.jurisdiction_note,
    }
