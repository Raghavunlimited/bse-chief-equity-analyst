"""
Event-driven walk-forward expectancy harness.

Runs multi-desk rules against historical OHLCV + expectancy regimes.
No lookahead: signals use only bars ≤ as_of; fills at next open.
India round-trip costs + slippage applied via simulate.r_multiple path.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd

from app.expectancy.costs import DEFAULT_COSTS
from app.expectancy.metrics import segment_by_regime
from app.expectancy.persist import ensure_expectancy_schema, upsert_metrics_rows
from app.expectancy.regimes import regime_at
from app.expectancy.simulate import simulate_trade

logger = logging.getLogger(__name__)

# Canonical rule IDs (must match gate / UI)
RULE_SWING = "elite_momentum"
RULE_INDEX = "index_mtf_vwap_v1"
RULE_INTRADAY = "intraday_bias_v1"

RULE_META = {
    RULE_SWING: {
        "desk": "swing",
        "label": "India Elite Momentum (weekly swing)",
        "proxy": False,
        "product": "delivery",
        "timeframe": "1d",
        "data_interval": "1d",
        "max_hold": 5,
    },
    RULE_INDEX: {
        "desk": "index",
        "label": "Index MTF/VWAP (5m shared core)",
        "proxy": False,
        "product": "intraday",
        "timeframe": "5m",
        "data_interval": "5m",
        "max_hold_bars": 24,
    },
    RULE_INTRADAY: {
        "desk": "intraday",
        "label": "Intraday bias (5m shared core)",
        "proxy": False,
        "product": "intraday",
        "timeframe": "5m",
        "data_interval": "5m",
        "max_hold_bars": 12,
    },
}


def _week_ends(dates: list[str]) -> list[str]:
    by_week: dict[tuple[int, int], str] = {}
    for d in dates:
        dt = datetime.strptime(d, "%Y-%m-%d")
        key = dt.isocalendar()[:2]
        by_week[key] = d
    return [by_week[k] for k in sorted(by_week)]


def _forward_bars(hist: pd.DataFrame, as_of: str, n: int) -> pd.DataFrame:
    """Bars from signal day inclusive, limited to n+2 for fill+hold."""
    if hist is None or hist.empty:
        return pd.DataFrame()
    fwd = hist[hist["trade_date"] >= as_of].head(n + 3)
    return fwd.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Swing: elite_momentum (same generate_weekly_picks as live)
# ---------------------------------------------------------------------------


def _run_swing_trades(
    db,
    *,
    sector_map: dict[str, str],
    dates: list[str],
    config_kwargs: dict[str, Any],
) -> list[dict[str, Any]]:
    from app.strategy.weekly_swing import generate_weekly_picks

    week_dates = _week_ends(dates)
    week_dates = [d for d in week_dates if d >= dates[min(54, len(dates) - 1)]]
    trades: list[dict[str, Any]] = []
    max_hold = int(RULE_META[RULE_SWING]["max_hold"])

    for as_of in week_dates:
        nifty = db.get_nifty_series(end_date=as_of, lookback=80)
        exp_regime = regime_at(nifty, as_of)["regime"]
        snapshot = db.get_joined_snapshot(as_of)
        picks = generate_weekly_picks(
            snapshot,
            nifty,
            as_of=as_of,
            sector_map=sector_map,
            **config_kwargs,
        )
        for cand in picks.get("candidates") or []:
            sym = str(cand["symbol"])
            hist = db.get_symbol_history(sym, end_date=None, lookback=400)
            bars = _forward_bars(hist, as_of, max_hold)
            sim = simulate_trade(
                bars,
                signal_entry=float(cand["entry_price"]),
                stop=float(cand["stop_loss"]),
                target=float(cand["target_price"]),
                side="BUY",
                max_hold=max_hold,
                product="delivery",
                assumptions=DEFAULT_COSTS,
            )
            if sim.get("r_multiple") is None:
                continue
            trades.append(
                {
                    "date": as_of,
                    "symbol": sym,
                    "rule_id": RULE_SWING,
                    "regime": exp_regime,
                    "side": "BUY",
                    **sim,
                }
            )
    return trades


# Daily proxy runners removed in Phase 3 — see harness_5m.py (shared 5m cores).


def run_walk_forward(
    db,
    *,
    sector_map: dict[str, str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    rules: list[str] | None = None,
) -> dict[str, Any]:
    """
    Run walk-forward for selected rules. Returns trades + per-rule regime metrics.
    Does not write to DB (use run_and_persist).
    """
    from app.config import config

    if sector_map is None:
        try:
            from universe import SECTOR_MAP

            sector_map = SECTOR_MAP
        except Exception:  # noqa: BLE001
            sector_map = {}

    dates = db.get_trading_dates(end_date=end_date)
    if start_date:
        dates = [d for d in dates if d >= start_date]
    if len(dates) < 60:
        return {
            "status": "error",
            "message": "Need ≥60 trading days of OHLCV history",
            "rules": {},
            "trades": [],
        }

    wanted = rules or [RULE_SWING, RULE_INDEX, RULE_INTRADAY]
    swing_kwargs = {
        "top_n": getattr(config, "top_n", 2),
        "min_score": getattr(config, "min_score", 65),
        "min_price": getattr(config, "min_price", 100),
        "min_turnover": getattr(config, "min_traded_value", 10_00_00_000),
        "volume_mult": getattr(config, "volume_multiplier", 2.0),
        "rsi_min": getattr(config, "rsi_min", 45),
        "rsi_max": getattr(config, "rsi_max", 70),
        "rs_min": getattr(config, "rs_min_outperformance", 3.0),
        "risk_per_trade": getattr(config, "risk_per_trade", 0.02),
    }

    out_rules: dict[str, Any] = {}
    all_trades: list[dict[str, Any]] = []

    if RULE_SWING in wanted:
        logger.info("Walk-forward: %s", RULE_SWING)
        t = _run_swing_trades(
            db, sector_map=sector_map, dates=dates, config_kwargs=swing_kwargs
        )
        by = segment_by_regime(t)
        out_rules[RULE_SWING] = {
            **RULE_META[RULE_SWING],
            "rule_id": RULE_SWING,
            "trade_count": len(t),
            "by_regime": by,
        }
        all_trades.extend(t)

    if RULE_INDEX in wanted:
        from app.expectancy.harness_5m import run_index_5m_trades

        logger.info("Walk-forward: %s (5m shared core)", RULE_INDEX)
        t, meta = run_index_5m_trades(db)
        by = segment_by_regime(t) if t else meta.get("by_regime") or {
            "ALL": {
                "sample_size": 0,
                "win_rate_pct": None,
                "avg_win_r": None,
                "avg_loss_r": None,
                "expectancy_r": None,
                "profit_factor": None,
                "max_drawdown_pct": None,
            }
        }
        if t:
            by = segment_by_regime(t)
        out_rules[RULE_INDEX] = {
            **RULE_META[RULE_INDEX],
            **meta,
            "rule_id": RULE_INDEX,
            "trade_count": len(t),
            "by_regime": by,
        }
        all_trades.extend(t)

    if RULE_INTRADAY in wanted:
        from app.expectancy.harness_5m import run_intraday_5m_trades

        logger.info("Walk-forward: %s (5m shared core)", RULE_INTRADAY)
        t, meta = run_intraday_5m_trades(db)
        by = (
            segment_by_regime(t)
            if t
            else {
                "ALL": {
                    "sample_size": 0,
                    "win_rate_pct": None,
                    "avg_win_r": None,
                    "avg_loss_r": None,
                    "expectancy_r": None,
                    "profit_factor": None,
                    "max_drawdown_pct": None,
                }
            }
        )
        out_rules[RULE_INTRADAY] = {
            **RULE_META[RULE_INTRADAY],
            **meta,
            "rule_id": RULE_INTRADAY,
            "trade_count": len(t),
            "by_regime": by,
        }
        all_trades.extend(t)

    return {
        "status": "ok",
        "message": (
            f"Walk-forward complete: {len(all_trades)} trades across "
            f"{len(out_rules)} rules"
        ),
        "as_of": dates[-1] if dates else None,
        "date_start": dates[0] if dates else None,
        "date_end": dates[-1] if dates else None,
        "cost_model": "india_cnc_delivery_or_mis_intraday",
        "rules": out_rules,
        "trades": all_trades[-500:],
        "trade_count": len(all_trades),
        "disclaimer": (
            "Metrics are research walk-forward results after India costs. "
            "Passing gates does not mean the strategy is proven or profitable."
        ),
    }


def run_and_persist(
    db,
    *,
    sector_map: dict[str, str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    rules: list[str] | None = None,
) -> dict[str, Any]:
    """Run walk-forward and upsert expectancy_metrics rows."""
    ensure_expectancy_schema(db)
    result = run_walk_forward(
        db,
        sector_map=sector_map,
        start_date=start_date,
        end_date=end_date,
        rules=rules,
    )
    if result.get("status") != "ok":
        return result

    for rule_id, payload in (result.get("rules") or {}).items():
        by = payload.get("by_regime") or {}
        upsert_metrics_rows(
            db,
            rule_id=rule_id,
            desk=str(payload.get("desk") or ""),
            by_regime=by,
            as_of=result.get("as_of"),
            meta={
                "proxy": bool(payload.get("proxy")),
                "label": payload.get("label"),
                "honesty": payload.get("honesty"),
                "trade_count": payload.get("trade_count"),
                "timeframe": payload.get("timeframe"),
                "data_interval": payload.get("data_interval"),
                "strategy_version": payload.get("strategy_version"),
                "strategy_id": payload.get("strategy_id") or rule_id,
                "insufficient_history": bool(payload.get("insufficient_history")),
                "cost_assumptions": payload.get("cost_assumptions"),
                "run_at": payload.get("run_at"),
                "source": payload.get("source"),
                "proven": False,
                "disclaimer": payload.get("disclaimer")
                or (
                    "Research walk-forward only — not a profit or proven-edge claim."
                ),
            },
        )
    result["persisted"] = True
    return result
