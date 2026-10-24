from __future__ import annotations

from fastapi import APIRouter

from app.config import config
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
    return {"data_status": freshness, **regime}
