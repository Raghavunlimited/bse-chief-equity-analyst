"""Market events calendar API — identifiable sources only; no invented dates."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Query

from app import market_events as me

router = APIRouter(prefix="/api/market-events", tags=["market-events"])


@router.get("/meta")
def events_meta() -> dict[str, Any]:
    return {
        "status": "ok",
        "disclaimer": me.DISCLAIMER,
        "content_kinds": sorted(me.CONTENT_KINDS),
        "honesty": {
            "invents_dates": False,
            "invents_forecasts": False,
            "invents_outcomes": False,
            "invents_market_impact": False,
            "model_commentary_as_fact": False,
        },
        "licensing_note": (
            "No commercial economic-calendar license. Operator NSE/holiday snapshots "
            "and optional Kotak scrip-master expiries only."
        ),
    }


@router.get("")
@router.get("/")
def list_events(
    include_fo: bool = Query(True, description="Include F&O expiries when scrip master cache available"),
    from_date: Optional[str] = Query(None, description="Inclusive YYYY-MM-DD filter on local event date"),
    to_date: Optional[str] = Query(None, description="Inclusive YYYY-MM-DD filter on local event date"),
) -> dict[str, Any]:
    cal = me.build_calendar(include_fo=include_fo)
    events = cal["events"]
    if from_date or to_date:
        filtered = []
        for ev in events:
            local = (ev.get("event_time_local") or "")[:10]
            if from_date and local < from_date[:10]:
                continue
            if to_date and local > to_date[:10]:
                continue
            filtered.append(ev)
        cal = {**cal, "events": filtered, "count": len(filtered)}
    return cal
