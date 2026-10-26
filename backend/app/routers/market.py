from __future__ import annotations

from fastapi import APIRouter

from app.config import config
from app.market_session import session_snapshot
from app.store import Database
from app.strategy.weekly_swing import check_market_regime

router = APIRouter(prefix="/api", tags=["market"])
db = Database(config.db_path)


@router.get("/market-regime")
def market_regime():
    freshness = db.freshness(config.max_data_age_days)
    as_of = freshness.get("latest_date")
    nifty = db.get_nifty_series(end_date=as_of, lookback=80) if as_of else db.get_nifty_series()
    regime = check_market_regime(nifty)
    sess = session_snapshot()
    return {
        "data_status": freshness,
        "session": sess,
        "price_basis": {
            "regime_uses": "eod_close",
            "note": "NIFTY regime is computed from EOD closes, not LTP.",
        },
        **regime,
    }


@router.get("/market/session")
def market_session():
    """IST session clock + staleness policy for the personal desk UI."""
    sess = session_snapshot()
    label = str(sess.get("session_label") or "")
    if sess.get("in_regular_hours"):
        badge = "REGULAR SESSION (broker LIVE only via Kotak WS)"
    elif label == "WEEKEND":
        badge = "WEEKEND / EOD SNAPSHOT"
    elif label == "HOLIDAY":
        badge = "HOLIDAY / EOD SNAPSHOT"
    elif label == "PRE-MARKET":
        badge = "PRE-MARKET"
    else:
        badge = "POST-MARKET / EOD SNAPSHOT"
    return {
        **sess,
        "badge": badge,
        "live_ticks_frozen": not bool(sess.get("in_regular_hours")),
        "stale_policy_sec": sess.get("stale_sec_threshold"),
        "process_vs_data": {
            "note": (
                "/api/health = process liveness; "
                "/api/health/ready = EOD data readiness (not LTP)."
            )
        },
    }
