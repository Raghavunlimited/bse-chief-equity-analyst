"""
Consultant signal desk APIs — BUY / SELL / HOLD envelopes.

Preserves existing /api/weekly-picks and /api/intraday|mcx/signals routes untouched.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Query

from app.signals.index_calls import INDEX_DISCLAIMER, build_index_calls
from app.signals.intraday_calls import INTRADAY_DISCLAIMER, build_intraday_calls
from app.signals.mcx_calls import MCX_DISCLAIMER, build_mcx_calls
from app.signals.models import RESEARCH_DISCLAIMER
from app.signals.swing_calls import SWING_DISCLAIMER, build_swing_calls

router = APIRouter(prefix="/api/consultant", tags=["consultant"])

EntryStyleQuery = Literal["breakout", "pullback"]


@router.get("/swing")
def consultant_swing(
    as_of: Optional[str] = Query(None),
    capital: float = Query(500_000, ge=10_000, le=1_000_000_000),
    risk_pct: float = Query(1.0, ge=0.25, le=5.0),
    max_positions: int = Query(3, ge=1, le=5),
    reserved_cash_pct: float = Query(20.0, ge=0.0, le=80.0),
    entry_style: EntryStyleQuery = Query("breakout"),
):
    """Weekly swing consultant calls (BUY setups or HOLD NIFTY on cash weeks)."""
    return build_swing_calls(
        as_of=as_of,
        capital=capital,
        risk_pct=risk_pct,
        max_positions=max_positions,
        reserved_cash_pct=reserved_cash_pct,
        entry_style=entry_style,
    )


@router.get("/intraday")
def consultant_intraday(limit: int = Query(20, ge=5, le=30)):
    """Near-live NSE intraday consultant board (BUY/SELL/HOLD)."""
    return build_intraday_calls(limit=limit)


@router.get("/mcx")
def consultant_mcx():
    """Commodities board via Yahoo global futures proxy — not MCX INR contracts."""
    return build_mcx_calls()


@router.get("/mcx/instruments")
def consultant_mcx_instruments():
    """Public instrument catalog with honesty fields (currency, proxy class, roll notes)."""
    from app.strategy.mcx_instruments import public_catalog

    return {
        "status": "ok",
        "is_mcx_listed_feed": False,
        "expectancy_gated": False,
        "instruments": public_catalog(),
        "disclaimer": MCX_DISCLAIMER,
    }

@router.get("/index")
def consultant_index():
    """Nifty + BankNifty multi-timeframe index bias (EMA/VWAP/RSI + daily SMA)."""
    return build_index_calls()


@router.get("/daily")
def consultant_daily(limit: int = Query(20, ge=5, le=30)):
    """Daily snapshot: intraday equities + index + MCX commodities."""
    intraday = build_intraday_calls(limit=limit)
    index = build_index_calls()
    mcx = build_mcx_calls()
    return {
        "snapshot": "daily",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "desks": ["intraday", "index", "mcx"],
        "intraday": intraday,
        "index": index,
        "mcx": mcx,
        "message": "Combined intraday + index + MCX research snapshot.",
        "disclaimer": RESEARCH_DISCLAIMER,
        "desk_disclaimers": {
            "intraday": INTRADAY_DISCLAIMER,
            "index": INDEX_DISCLAIMER,
            "mcx": MCX_DISCLAIMER,
        },
    }


@router.get("/weekly")
def consultant_weekly(
    as_of: Optional[str] = Query(None),
    capital: float = Query(500_000, ge=10_000, le=1_000_000_000),
    risk_pct: float = Query(1.0, ge=0.25, le=5.0),
    max_positions: int = Query(3, ge=1, le=5),
    reserved_cash_pct: float = Query(20.0, ge=0.0, le=80.0),
    entry_style: EntryStyleQuery = Query("breakout"),
):
    """Weekly snapshot: swing consultant calls (same engine as /swing)."""
    swing = build_swing_calls(
        as_of=as_of,
        capital=capital,
        risk_pct=risk_pct,
        max_positions=max_positions,
        reserved_cash_pct=reserved_cash_pct,
        entry_style=entry_style,
    )
    return {
        "snapshot": "weekly",
        "as_of": swing.get("as_of"),
        "desks": ["swing"],
        "swing": swing,
        "week_label": swing.get("week_label"),
        "message": swing.get("message") or "Weekly swing research snapshot.",
        "disclaimer": SWING_DISCLAIMER,
    }
