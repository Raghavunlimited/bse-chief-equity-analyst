"""
Week-based backtest using the same generate_weekly_picks path as live.

Conservative fills: gap opens, stop checked before target on same bar,
round-trip cost applied to each trade.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from app.strategy.weekly_swing import generate_weekly_picks

logger = logging.getLogger(__name__)


def _week_ends(dates: list[str]) -> list[str]:
    """Last trading date of each ISO week in the date list."""
    if not dates:
        return []
    by_week: dict[tuple[int, int], str] = {}
    for d in dates:
        dt = datetime.strptime(d, "%Y-%m-%d")
        key = dt.isocalendar()[:2]
        by_week[key] = d
    return [by_week[k] for k in sorted(by_week)]


def _simulate_trade(
    bars: pd.DataFrame,
    entry: float,
    stop: float,
    target: float,
    max_hold: int,
    cost: float,
) -> dict[str, Any]:
    """
    bars: forward OHLCV starting at entry session (index 0 = signal day).
    Enter at next open (index 1) when available; else signal close.
    """
    if bars.empty:
        return {"exit_reason": "no_data", "return_pct": 0.0, "hold_days": 0}

    if len(bars) >= 2:
        fill = float(bars.iloc[1]["open"])
        start_i = 1
    else:
        fill = float(bars.iloc[0]["close"])
        start_i = 0

    # Gap through stop / target at open
    if fill <= stop:
        ret = (fill / entry - 1) * 100 - cost * 100
        return {
            "exit_reason": "gap_stop",
            "return_pct": ret,
            "hold_days": 1,
            "exit_price": fill,
        }
    if fill >= target:
        ret = (fill / entry - 1) * 100 - cost * 100
        return {
            "exit_reason": "gap_target",
            "return_pct": ret,
            "hold_days": 1,
            "exit_price": fill,
        }

    entry_fill = fill
    highest = entry_fill
    trail_active = False
    trail_stop = stop

    for i in range(start_i, min(len(bars), start_i + max_hold)):
        row = bars.iloc[i]
        high, low, close = float(row["high"]), float(row["low"]), float(row["close"])
        highest = max(highest, high)

        if (highest / entry_fill - 1) >= 0.01:
            trail_active = True
            trail_stop = max(trail_stop, highest * 0.99)

        effective_stop = trail_stop if trail_active else stop

        # Conservative: stop before target intraday
        if low <= effective_stop:
            exit_px = effective_stop
            reason = "trail_stop" if trail_active else "stop"
            ret = (exit_px / entry_fill - 1) * 100 - cost * 100
            return {
                "exit_reason": reason,
                "return_pct": ret,
                "hold_days": i - start_i + 1,
                "exit_price": exit_px,
            }
        if high >= target:
            ret = (target / entry_fill - 1) * 100 - cost * 100
            return {
                "exit_reason": "target",
                "return_pct": ret,
                "hold_days": i - start_i + 1,
                "exit_price": target,
            }

    last = bars.iloc[min(len(bars) - 1, start_i + max_hold - 1)]
    exit_px = float(last["close"])
    ret = (exit_px / entry_fill - 1) * 100 - cost * 100
    return {
        "exit_reason": "time",
        "return_pct": ret,
        "hold_days": min(max_hold, len(bars) - start_i),
        "exit_price": exit_px,
    }


def run_weekly_backtest(
    db,
    *,
    sector_map: dict[str, str],
    start_date: str | None = None,
    end_date: str | None = None,
    top_n: int = 2,
    min_score: float = 65,
    min_price: float = 100,
    min_turnover: float = 10_00_00_000,
    volume_mult: float = 2.0,
    rsi_min: float = 45,
    rsi_max: float = 70,
    rs_min: float = 3.0,
    risk_per_trade: float = 0.02,
    max_hold_days: int = 5,
    round_trip_cost: float = 0.0015,
    initial_capital: float = 1_000_000,
) -> dict[str, Any]:
    dates = db.get_trading_dates(end_date=end_date)
    if start_date:
        dates = [d for d in dates if d >= start_date]
    # Need history for indicators / regime
    if len(dates) < 60:
        return {
            "status": "error",
            "message": "Need at least ~60 trading days of history",
            "trades": [],
            "weeks": [],
            "stats": {},
        }

    week_dates = _week_ends(dates)
    # Skip early weeks until indicators stable
    week_dates = [d for d in week_dates if d >= dates[54]]

    trades: list[dict] = []
    weeks: list[dict] = []
    equity = initial_capital
    peak = equity
    equity_curve = [{"date": week_dates[0] if week_dates else None, "equity": equity}]

    for as_of in week_dates:
        snapshot = db.get_joined_snapshot(as_of)
        nifty = db.get_nifty_series(end_date=as_of, lookback=80)
        picks = generate_weekly_picks(
            snapshot,
            nifty,
            as_of=as_of,
            sector_map=sector_map,
            top_n=top_n,
            min_score=min_score,
            min_price=min_price,
            min_turnover=min_turnover,
            volume_mult=volume_mult,
            rsi_min=rsi_min,
            rsi_max=rsi_max,
            rs_min=rs_min,
            risk_per_trade=risk_per_trade,
        )

        week_rets: list[float] = []
        if not picks.get("candidates"):
            weeks.append(
                {
                    "date": as_of,
                    "status": picks.get("status", "cash"),
                    "regime": picks.get("market_regime", {}).get("regime"),
                    "n_picks": 0,
                    "week_return_pct": 0.0,
                }
            )
            equity_curve.append({"date": as_of, "equity": round(equity, 2)})
            continue

        # Equal weight across picks this week
        weight = 1.0 / len(picks["candidates"])
        for cand in picks["candidates"]:
            sym = cand["symbol"]
            hist = db.get_symbol_history(sym, end_date=None, lookback=500)
            hist = hist[hist["trade_date"] >= as_of].head(max_hold_days + 3)
            if hist.empty:
                continue
            sim = _simulate_trade(
                hist,
                entry=cand["entry_price"],
                stop=cand["stop_loss"],
                target=cand["target_price"],
                max_hold=max_hold_days,
                cost=round_trip_cost,
            )
            week_rets.append(sim["return_pct"] * weight)
            trades.append(
                {
                    "date": as_of,
                    "symbol": sym,
                    "score": cand["score"],
                    "entry": cand["entry_price"],
                    "stop": cand["stop_loss"],
                    "target": cand["target_price"],
                    **sim,
                }
            )

        week_ret = float(sum(week_rets)) if week_rets else 0.0
        equity *= 1 + week_ret / 100
        peak = max(peak, equity)
        weeks.append(
            {
                "date": as_of,
                "status": "traded",
                "regime": picks.get("market_regime", {}).get("regime"),
                "n_picks": len(picks["candidates"]),
                "week_return_pct": round(week_ret, 3),
            }
        )
        equity_curve.append({"date": as_of, "equity": round(equity, 2)})

    trade_rets = [t["return_pct"] for t in trades]
    week_rets_all = [w["week_return_pct"] for w in weeks]
    cash_weeks = sum(1 for w in weeks if w["n_picks"] == 0)
    winners = [r for r in trade_rets if r > 0]
    losers = [r for r in trade_rets if r <= 0]
    gross_win = sum(winners) if winners else 0
    gross_loss = abs(sum(losers)) if losers else 0
    pf = (gross_win / gross_loss) if gross_loss > 0 else None

    # Max drawdown from equity curve
    eq = [e["equity"] for e in equity_curve]
    max_dd = 0.0
    if eq:
        run_peak = eq[0]
        for v in eq:
            run_peak = max(run_peak, v)
            dd = (v / run_peak - 1) * 100
            max_dd = min(max_dd, dd)

    stats = {
        "weeks": len(weeks),
        "cash_weeks": cash_weeks,
        "cash_week_pct": round(100 * cash_weeks / len(weeks), 1) if weeks else 0,
        "trades": len(trades),
        "win_rate": round(100 * len(winners) / len(trades), 1) if trades else 0,
        "avg_trade_return_pct": round(float(np.mean(trade_rets)), 3) if trade_rets else 0,
        "median_trade_return_pct": round(float(np.median(trade_rets)), 3)
        if trade_rets
        else 0,
        "avg_week_return_pct": round(float(np.mean(week_rets_all)), 3)
        if week_rets_all
        else 0,
        "median_week_return_pct": round(float(np.median(week_rets_all)), 3)
        if week_rets_all
        else 0,
        "profit_factor": round(pf, 2) if pf is not None else None,
        "max_drawdown_pct": round(max_dd, 2),
        "final_equity": round(equity, 2),
        "total_return_pct": round((equity / initial_capital - 1) * 100, 2),
        "initial_capital": initial_capital,
        "costs_assumed_pct": round(round_trip_cost * 100, 3),
    }

    return {
        "status": "ok",
        "message": f"Backtested {stats['weeks']} weeks, {stats['trades']} trades",
        "stats": stats,
        "weeks": weeks,
        "trades": trades[-200:],  # cap payload
        "equity_curve": equity_curve,
    }
