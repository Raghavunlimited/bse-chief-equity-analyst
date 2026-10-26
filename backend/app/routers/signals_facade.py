"""
Canonical /api/signals/* facade (Architect contract).

Wraps consultant builders so CRA can migrate off legacy tape paths.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.signals.index_calls import build_index_calls
from app.signals.intraday_calls import build_intraday_calls
from app.signals.mcx_calls import build_mcx_calls
from app.signals.swing_calls import build_swing_calls

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.get("/swing")
def signals_swing(
    capital: float = Query(500_000, ge=10_000),
    risk_pct: float = Query(1.0, ge=0.25, le=5.0),
    max_positions: int = Query(3, ge=1, le=5),
):
    data = build_swing_calls(
        capital=capital, risk_pct=risk_pct, max_positions=max_positions, enrich=True
    )
    return {"schema": "signals.v1", **data}


@router.get("/intraday")
def signals_intraday(limit: int = Query(20, ge=5, le=30)):
    data = build_intraday_calls(limit=limit, enrich=True)
    return {"schema": "signals.v1", **data}


@router.get("/mcx")
def signals_mcx():
    data = build_mcx_calls()
    return {"schema": "signals.v1", **data}


@router.get("/index")
def signals_index():
    data = build_index_calls()
    return {"schema": "signals.v1", **data}
