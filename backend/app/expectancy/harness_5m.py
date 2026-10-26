"""
5-minute walk-forward for Intraday + Index using shared strategy cores.

No daily OHLCV proxy. Signals from completed 5m bars only; fill at next bar open.
Insufficient history → empty trades + honesty payload (STRONG stays blocked).
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from app.bars_5m import bar_counts, load_bars
from app.expectancy.costs import DEFAULT_COSTS
from app.expectancy.regimes import regime_at
from app.expectancy.simulate import simulate_trade
from app.strategy.intraday_core import (
    STRATEGY_ID as INTRADAY_ID,
    STRATEGY_VERSION as INTRADAY_VER,
    score_intraday_bias,
    session_vwap,
)
from app.strategy.index_core import (
    STRATEGY_ID as INDEX_ID,
    STRATEGY_VERSION as INDEX_VER,
    score_index_mtf,
)

logger = logging.getLogger(__name__)

INTRADAY_MAX_HOLD_BARS = 12  # ~60 minutes
INDEX_MAX_HOLD_BARS = 24  # ~2 hours
MIN_BARS_FOR_RUN = 80
INTRADAY_WARMUP = 18
INDEX_WARMUP = 21


def _cost_assumptions_public() -> dict[str, Any]:
    return {
        "model": "india_mis_intraday",
        "product": "intraday",
        **asdict(DEFAULT_COSTS),
        "note": (
            "Round-trip brokerage/STT/exchange/SEBI/stamp/GST + "
            f"{DEFAULT_COSTS.slippage_pct_per_side * 1e4:.1f} bps slippage/side"
        ),
    }


def _session_slice(df: pd.DataFrame, session_date: str) -> pd.DataFrame:
    return df[df["session_date"] == session_date].reset_index(drop=True)


def _prev_close_before(df: pd.DataFrame, bar_start_unix: int) -> float | None:
    """Last completed close strictly before this bar's session, else session open."""
    row = df[df["bar_start_unix"] == bar_start_unix]
    if row.empty:
        return None
    sess = str(row.iloc[0]["session_date"])
    prior = df[df["session_date"] < sess]
    if not prior.empty:
        return float(prior.iloc[-1]["close"])
    day = df[df["session_date"] == sess]
    if day.empty:
        return None
    return float(day.iloc[0]["open"])


def _session_ohlc_to_i(day: pd.DataFrame, i_in_day: int) -> tuple[float, float, float]:
    win = day.iloc[: i_in_day + 1]
    return (
        float(win.iloc[0]["open"]),
        float(win["high"].max()),
        float(win["low"].min()),
    )


def _vwap_to_i(day: pd.DataFrame, i_in_day: int) -> float | None:
    win = day.iloc[: i_in_day + 1]
    return session_vwap(
        [float(x) for x in win["close"].tolist()],
        [float(x) for x in win["volume"].tolist()],
    )


def insufficient_payload(rule_id: str, desk: str, reason: str) -> dict[str, Any]:
    return {
        "desk": desk,
        "rule_id": rule_id,
        "label": f"{rule_id} (5m — insufficient history)",
        "proxy": False,
        "product": "intraday",
        "timeframe": "5m",
        "data_interval": "5m",
        "trade_count": 0,
        "by_regime": {
            "ALL": {
                "sample_size": 0,
                "win_rate_pct": None,
                "avg_win_r": None,
                "avg_loss_r": None,
                "expectancy_r": None,
                "profit_factor": None,
                "max_drawdown_pct": None,
            }
        },
        "insufficient_history": True,
        "honesty": reason,
        "bars_5m_status": bar_counts(),
        "cost_assumptions": _cost_assumptions_public(),
        "proven": False,
        "disclaimer": (
            "Insufficient 5m history — STRONG badges disabled. "
            "Not described as proven or profitable."
        ),
    }


def run_intraday_5m_trades(
    db,
    *,
    watch: list[str] | None = None,
    max_symbols: int = 25,
    max_hold_bars: int = INTRADAY_MAX_HOLD_BARS,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from app.strategy.intraday import DEFAULT_WATCH

    symbols = list(watch or DEFAULT_WATCH)[:max_symbols]
    trades: list[dict[str, Any]] = []
    meta_base: dict[str, Any] = {
        "strategy_id": INTRADAY_ID,
        "strategy_version": INTRADAY_VER,
        "timeframe": "5m",
        "data_interval": "5m",
        "proxy": False,
        "max_hold_bars": max_hold_bars,
        "cost_assumptions": _cost_assumptions_public(),
        "run_at": datetime.now(timezone.utc).isoformat(),
        "source": "bars_5m",
        "desk": "intraday",
        "rule_id": INTRADAY_ID,
        "label": "Intraday bias (5m shared core)",
        "proven": False,
        "disclaimer": "Walk-forward research metrics only — not a profit claim.",
    }

    total_bars = 0
    for sym in symbols:
        df = load_bars(sym, completed_only=True)
        if df.empty:
            continue
        total_bars += len(df)
        sessions = sorted(df["session_date"].unique())
        nifty_cache: dict[str, str] = {}

        for sess in sessions:
            day = _session_slice(df, str(sess))
            if len(day) < INTRADAY_WARMUP + 2:
                continue
            for i in range(INTRADAY_WARMUP - 1, len(day) - 2):
                win = day.iloc[: i + 1]
                closes = [float(x) for x in win["close"].tolist()]
                vols = [float(x) for x in win["volume"].tolist()]
                price = closes[-1]
                so, sh, sl = _session_ohlc_to_i(day, i)
                ts = int(day.iloc[i]["bar_start_unix"])
                prev = _prev_close_before(df, ts)
                chg = (price / prev - 1.0) * 100.0 if prev and prev > 0 else None
                sig = score_intraday_bias(
                    price=price,
                    closes_5m=closes,
                    volumes_5m=vols,
                    change_pct=chg,
                    session_open=so,
                    session_high=sh,
                    session_low=sl,
                )
                if sig["side"] not in ("LONG", "SHORT"):
                    continue
                if sig["stop"] is None or sig["target"] is None:
                    continue
                side = "BUY" if sig["side"] == "LONG" else "SELL"
                fwd = day.iloc[i : i + max_hold_bars + 3].reset_index(drop=True)
                sim = simulate_trade(
                    fwd,
                    signal_entry=price,
                    stop=float(sig["stop"]),
                    target=float(sig["target"]),
                    side=side,
                    max_hold=max_hold_bars,
                    product="intraday",
                    assumptions=DEFAULT_COSTS,
                )
                if sim.get("r_multiple") is None:
                    continue
                as_of = str(sess)
                if as_of not in nifty_cache:
                    nifty = db.get_nifty_series(end_date=as_of, lookback=80)
                    nifty_cache[as_of] = regime_at(nifty, as_of)["regime"]
                trades.append(
                    {
                        "date": as_of,
                        "bar_start_unix": ts,
                        "symbol": sym,
                        "rule_id": INTRADAY_ID,
                        "regime": nifty_cache[as_of],
                        "side": side,
                        "proxy": False,
                        "strategy_version": INTRADAY_VER,
                        "data_interval": "5m",
                        **sim,
                    }
                )

    honesty = None
    insufficient = total_bars < MIN_BARS_FOR_RUN
    if insufficient:
        honesty = (
            f"Need ≥{MIN_BARS_FOR_RUN} completed 5m bars across watchlist "
            f"(have {total_bars}). Ingest Yahoo/Kotak 5m before claiming edge."
        )
    elif len(trades) == 0:
        honesty = (
            "5m bars present but zero trades under intraday_bias_v1 "
            "(not evidence of profitability)."
        )

    return trades, {
        **meta_base,
        "insufficient_history": insufficient,
        "honesty": honesty,
        "bars_scanned": total_bars,
        "bars_5m_status": bar_counts(),
    }


def run_index_5m_trades(
    db,
    *,
    max_hold_bars: int = INDEX_MAX_HOLD_BARS,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    meta_base: dict[str, Any] = {
        "strategy_id": INDEX_ID,
        "strategy_version": INDEX_VER,
        "timeframe": "5m",
        "data_interval": "5m",
        "proxy": False,
        "max_hold_bars": max_hold_bars,
        "cost_assumptions": _cost_assumptions_public(),
        "run_at": datetime.now(timezone.utc).isoformat(),
        "source": "bars_5m",
        "desk": "index",
        "rule_id": INDEX_ID,
        "label": "Index MTF/VWAP (5m shared core)",
        "proven": False,
        "disclaimer": "Walk-forward research metrics only — not a profit claim.",
    }
    total_bars = 0
    nifty_df = load_bars("NIFTY", completed_only=True)

    for sym in ("NIFTY", "BANKNIFTY"):
        df = load_bars(sym, completed_only=True)
        if df.empty:
            continue
        total_bars += len(df)
        for sess in sorted(df["session_date"].unique()):
            day = _session_slice(df, str(sess))
            if len(day) < INDEX_WARMUP + 2:
                continue
            nifty = db.get_nifty_series(end_date=str(sess), lookback=80)
            prior_dates = (
                nifty[nifty["trade_date"] < str(sess)]["trade_date"].tolist()
                if nifty is not None and not nifty.empty
                else []
            )
            as_of_regime = prior_dates[-1] if prior_dates else None
            reg = (
                regime_at(nifty, as_of_regime)["regime"]
                if as_of_regime
                else "UNKNOWN"
            )
            daily_regime = None
            if nifty is not None and not nifty.empty and as_of_regime:
                from app.strategy.weekly_swing import check_market_regime

                nifty_cut = nifty[nifty["trade_date"] <= as_of_regime]
                daily_regime = check_market_regime(nifty_cut).get("regime")

            for i in range(INDEX_WARMUP - 1, len(day) - 2):
                win = day.iloc[: i + 1]
                closes = [float(x) for x in win["close"].tolist()]
                price = closes[-1]
                _so, sh, sl = _session_ohlc_to_i(day, i)
                vwap = _vwap_to_i(day, i)
                ts = int(day.iloc[i]["bar_start_unix"])
                prev = _prev_close_before(df, ts)
                chg = (price / prev - 1.0) * 100.0 if prev and prev > 0 else None
                rel = None
                if sym == "BANKNIFTY" and not nifty_df.empty:
                    n_row = nifty_df[nifty_df["bar_start_unix"] == ts]
                    if not n_row.empty and chg is not None:
                        n_prev = _prev_close_before(nifty_df, ts)
                        n_px = float(n_row.iloc[0]["close"])
                        if n_prev and n_prev > 0:
                            rel = chg - (n_px / n_prev - 1.0) * 100.0

                sig = score_index_mtf(
                    symbol=sym,
                    price=price,
                    closes_5m=closes,
                    daily_regime=daily_regime,
                    vwap=vwap,
                    change_pct=chg,
                    session_high=sh,
                    session_low=sl,
                    rel_spread=rel,
                )
                if sig["side"] not in ("BUY", "SELL"):
                    continue
                if sig["stop"] is None or sig["target"] is None:
                    continue
                fwd = day.iloc[i : i + max_hold_bars + 3].reset_index(drop=True)
                sim = simulate_trade(
                    fwd,
                    signal_entry=price,
                    stop=float(sig["stop"]),
                    target=float(sig["target"]),
                    side=sig["side"],
                    max_hold=max_hold_bars,
                    product="intraday",
                    assumptions=DEFAULT_COSTS,
                )
                if sim.get("r_multiple") is None:
                    continue
                trades.append(
                    {
                        "date": str(sess),
                        "bar_start_unix": ts,
                        "symbol": sym,
                        "rule_id": INDEX_ID,
                        "regime": reg,
                        "side": sig["side"],
                        "proxy": False,
                        "strategy_version": INDEX_VER,
                        "data_interval": "5m",
                        **sim,
                    }
                )

    honesty = None
    insufficient = total_bars < MIN_BARS_FOR_RUN
    if insufficient:
        honesty = (
            f"Need ≥{MIN_BARS_FOR_RUN} completed 5m bars for NIFTY/BANKNIFTY "
            f"(have {total_bars}). Persist 5m history before gating STRONG."
        )
    elif len(trades) == 0:
        honesty = (
            "5m bars present but zero index_mtf_vwap_v1 trades "
            "(not a profit claim)."
        )

    return trades, {
        **meta_base,
        "insufficient_history": insufficient,
        "honesty": honesty,
        "bars_scanned": total_bars,
        "bars_5m_status": bar_counts(),
    }
