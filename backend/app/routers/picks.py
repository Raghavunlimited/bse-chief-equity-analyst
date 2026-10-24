from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Query

from app.config import config
from app.fundamentals import fetch_fundamentals_many
from app.meta import data_provenance
from app.store import Database
from app.goal_planner import iso_week_label, plan_week_goal
from app.strategy.weekly_swing import generate_weekly_picks
from universe import SECTOR_MAP

router = APIRouter(prefix="/api", tags=["picks"])
db = Database(config.db_path)

EntryStyleQuery = Literal["breakout", "pullback"]


@router.get("/weekly-picks")
@router.get("/weekly-swing-picks")
def weekly_picks(
    as_of: Optional[str] = Query(None),
    fundamentals: bool = Query(
        True, description="Attach Screener fundamentals to each pick"
    ),
    capital: float = Query(
        500_000,
        ge=10_000,
        le=1_000_000_000,
        description="Trading capital (INR) for position sizing",
    ),
    risk_pct: float = Query(
        1.0,
        ge=0.25,
        le=5.0,
        description="Risk % of capital per trade (e.g. 1.0 = 1%)",
    ),
    max_positions: int = Query(
        3,
        ge=1,
        le=5,
        description="Max candidates / concurrent swing positions",
    ),
    reserved_cash_pct: float = Query(
        20.0,
        ge=0.0,
        le=80.0,
        description="Cash reserved; sizing uses remaining deployable capital",
    ),
    entry_style: EntryStyleQuery = Query(
        "breakout",
        description="elite_momentum entry: breakout (near HH20) or pullback (Stage 2)",
    ),
    target_gain_pct: Optional[float] = Query(
        None,
        ge=0.0,
        le=30.0,
        description="Optional weekly gain target % of capital (0–30); attaches goal_plan",
    ),
):
    freshness = db.freshness(config.max_data_age_days)
    provenance = data_provenance(config.db_path)
    as_of_date = as_of or freshness.get("latest_date")
    week = iso_week_label(as_of_date)
    if not as_of_date:
        empty = {
            "status": "empty",
            "data_status": freshness,
            "provenance": provenance,
            "candidates": [],
            "week_label": week,
            "message": "No data — run Refresh data",
        }
        if target_gain_pct is not None:
            empty["goal_plan"] = plan_week_goal(
                capital,
                target_gain_pct,
                risk_pct,
                max_positions,
                [],
                as_of=None,
            )
        return empty

    snapshot = db.get_joined_snapshot(as_of_date)
    nifty = db.get_nifty_series(end_date=as_of_date, lookback=80)
    result = generate_weekly_picks(
        snapshot,
        nifty,
        as_of=as_of_date,
        sector_map=SECTOR_MAP,
        top_n=max_positions,
        min_score=config.min_score,
        min_price=config.min_price,
        min_turnover=config.min_traded_value,
        volume_mult=config.volume_multiplier,
        rsi_min=config.rsi_min,
        rsi_max=config.rsi_max,
        rs_min=config.rs_min_outperformance,
        risk_per_trade=risk_pct / 100.0,
        capital_per_trade=capital,
        capital=capital,
        risk_pct=risk_pct,
        max_positions=max_positions,
        reserved_cash_pct=reserved_cash_pct,
        entry_style=entry_style,
        require_fresh=True,
        data_status=freshness,
    )
    result["provenance"] = provenance
    result["week_label"] = week

    if fundamentals and result.get("candidates"):
        batch = fetch_fundamentals_many(
            [c["symbol"] for c in result["candidates"]],
            max_workers=4,
        )
        for cand in result["candidates"]:
            cand["fundamentals"] = batch.get(cand["symbol"]) or {
                "symbol": cand["symbol"],
                "available": False,
            }

    if target_gain_pct is not None:
        result["goal_plan"] = plan_week_goal(
            capital,
            target_gain_pct,
            risk_pct,
            max_positions,
            result.get("candidates") or [],
            as_of=as_of_date,
        )
        # Surface suggested order for UI without dropping radar/cash state
        suggested = result["goal_plan"].get("suggested_candidates") or []
        if suggested and result.get("candidates"):
            order = {s["symbol"]: i for i, s in enumerate(suggested)}
            result["candidates"] = sorted(
                result["candidates"],
                key=lambda c: order.get(c["symbol"], 99),
            )

    return result
