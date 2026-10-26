"""Platform market + signal history — live adapter only (no demo routes)."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.adapters import DemoAdapterForbidden, get_market_adapter
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
        "Past patterns do not predict future results. "
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
        "demo_allowed": False,
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
    # Strip any legacy demo rows from personal desk views
    live_rows = [r for r in rows if str(r.get("data_mode") or "").lower() != "demo"]
    from app.signal_availability import (
        enrich_ledger_signal,
        summarize_ledger_availability,
    )

    enriched = [enrich_ledger_signal(r) for r in live_rows]
    filtered_demo = len(rows) - len(live_rows)
    return {
        "signals": enriched,
        "count": len(enriched),
        "includes_history": history,
        "disclosure": DISCLOSURE["title"],
        "filtered_demo_rows": filtered_demo,
        "ledger_availability": summarize_ledger_availability(
            published_count=len(enriched),
            filtered_demo_rows=filtered_demo,
            category=category,
        ),
        "research_only": True,
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
    if str(row.get("data_mode") or "").lower() == "demo":
        raise HTTPException(
            status_code=410,
            detail="Demo signals are retired. This record is not available on the live desk.",
        )
    return row


def _wrap_adapter(payload: dict) -> dict:
    out = dict(payload)
    mode = out.get("provenance") or "delayed"
    if mode == "demo":
        raise HTTPException(status_code=500, detail="Demo provenance leaked into live adapter")
    out["data_mode"] = mode
    out["price_kind"] = out.get("price_kind") or "ltp"
    out["provenance"] = {
        "data_mode": mode,
        "source": out.get("source") or "unknown",
        "as_of": out.get("as_of"),
        "feed_status": out.get("feed_status"),
        "quote_age_sec": out.get("quote_age_sec"),
        "note": f"Source={out.get('source')} price_kind={out.get('price_kind')}",
    }
    if "last" in out and "price" not in out:
        out["price"] = out["last"]
    out["available"] = True
    return out


@router.get("/market/{symbol}/quote")
def market_quote(
    symbol: str,
    category: Category = "swing",
    user: dict = Depends(get_current_user),
):
    _ = category
    try:
        adapter = get_market_adapter()
        return _wrap_adapter(dict(adapter.get_quote(symbol)))
    except DemoAdapterForbidden as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (KeyError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"LIVE quote failed for {symbol}: {exc}",
        ) from exc


@router.get("/market/{symbol}/bars")
def market_bars(
    symbol: str,
    category: Category = "swing",
    timeframe: str = "1d",
    limit: int = Query(60, ge=1, le=120),
    user: dict = Depends(get_current_user),
):
    _ = category
    try:
        adapter = get_market_adapter()
        payload = _wrap_adapter(
            dict(adapter.get_bars(symbol, interval=timeframe, lookback=limit))
        )
        payload["price_kind"] = "eod_close"
        return payload
    except DemoAdapterForbidden as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (KeyError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"EOD bars failed for {symbol}: {exc}",
        ) from exc


@router.get("/market/{symbol}/oi")
def market_oi(
    symbol: str,
    category: Category = "swing",
    user: dict = Depends(get_current_user),
):
    _ = category
    try:
        adapter = get_market_adapter()
        return _wrap_adapter(dict(adapter.get_oi(symbol)))
    except DemoAdapterForbidden as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (KeyError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


@router.get("/market/{symbol}/financials")
def market_financials(
    symbol: str,
    category: Category = "swing",
    user: dict = Depends(get_current_user),
):
    _ = category
    try:
        adapter = get_market_adapter()
        return _wrap_adapter(dict(adapter.get_financials(symbol)))
    except DemoAdapterForbidden as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (KeyError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Financials failed for {symbol}: {exc}",
        ) from exc


@router.get("/demo/signals")
def demo_signals_removed():
    """Demo signal bundle permanently removed (Phase 1)."""
    raise HTTPException(
        status_code=410,
        detail=(
            "Demo signals endpoint removed. "
            "This desk no longer serves synthetic analyses."
        ),
    )
