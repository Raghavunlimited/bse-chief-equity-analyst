"""Trade journal API — research log only."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app import journal as journal_store

router = APIRouter(prefix="/api/journal", tags=["journal"])


class JournalEntryIn(BaseModel):
    week: Optional[str] = Field(None, min_length=4, max_length=16, description="ISO week e.g. 2026-W43")
    week_label: Optional[str] = Field(
        None, min_length=4, max_length=16, description="Alias for week"
    )
    symbol: str = Field(..., min_length=1, max_length=32)
    invested: bool = False
    capital_deployed: Optional[float] = Field(None, ge=0)
    pnl_rupees: Optional[float] = None
    pnl_pct: Optional[float] = None
    notes: Optional[str] = Field(None, max_length=2000)


@router.post("")
@router.post("/")
def create_journal_entry(body: JournalEntryIn):
    """Log a research trade / watch for a week. Not advice; no guarantees."""
    week = (body.week or body.week_label or "").strip()
    if not week:
        raise HTTPException(status_code=422, detail="week is required")
    try:
        entry = journal_store.add_entry(
            week=week,
            symbol=body.symbol,
            invested=body.invested,
            capital_deployed=body.capital_deployed,
            pnl_rupees=body.pnl_rupees,
            pnl_pct=body.pnl_pct,
            notes=body.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "status": "ok",
        "entry": entry,
        "message": "Logged to research journal only — not a broker fill or return guarantee.",
    }


@router.get("")
@router.get("/")
def get_journal(
    week: Optional[str] = Query(None, description="ISO week filter e.g. 2026-W43"),
    limit: int = Query(100, ge=1, le=500),
):
    entries = journal_store.list_entries(week=week, limit=limit)
    return {
        "status": "ok",
        "week": week,
        "count": len(entries),
        "entries": entries,
        "message": "Research journal only — past P&L does not imply future results.",
    }


@router.get("/weeks")
def get_journal_weeks(limit: int = Query(26, ge=1, le=104)):
    weeks = journal_store.list_weeks(limit=limit)
    return {
        "status": "ok",
        "count": len(weeks),
        "weeks": weeks,
        "message": "Recent journal weeks — research log only.",
    }
