"""Intraday + MCX research signal desks."""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.strategy.intraday import build_intraday_desk
from app.strategy.mcx import build_mcx_desk

router = APIRouter(prefix="/api", tags=["signals"])


@router.get("/intraday/signals")
def intraday_signals(limit: int = Query(20, ge=5, le=30)):
    """Near-live NSE intraday bias board (Yahoo 5m). Research only."""
    return build_intraday_desk(limit=limit)


@router.get("/mcx/signals")
def mcx_signals():
    """Commodity / MCX-major directional board via global futures. Research only."""
    return build_mcx_desk()
