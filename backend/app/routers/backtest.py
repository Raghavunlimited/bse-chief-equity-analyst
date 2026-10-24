from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.config import config
from app.store import Database
from app.strategy.backtest import run_weekly_backtest
from universe import SECTOR_MAP

router = APIRouter(prefix="/api", tags=["backtest"])
db = Database(config.db_path)


class BacktestRequest(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_capital: float = Field(default=1_000_000, ge=10_000)


@router.post("/backtest")
@router.post("/backtest/run")
def backtest(req: BacktestRequest = BacktestRequest()):
    return run_weekly_backtest(
        db,
        sector_map=SECTOR_MAP,
        start_date=req.start_date,
        end_date=req.end_date,
        top_n=config.top_n,
        min_score=config.min_score,
        min_price=config.min_price,
        min_turnover=config.min_traded_value,
        volume_mult=config.volume_multiplier,
        rsi_min=config.rsi_min,
        rsi_max=config.rsi_max,
        rs_min=config.rs_min_outperformance,
        risk_per_trade=config.risk_per_trade,
        max_hold_days=config.max_hold_days,
        round_trip_cost=config.round_trip_cost,
        initial_capital=req.initial_capital,
    )
