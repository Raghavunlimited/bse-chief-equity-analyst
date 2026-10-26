"""
Event-driven trade simulation — no lookahead.

Entry: next-bar open after signal (or signal close if no next bar).
Exits: gap stop/target at open; else intrabar stop-before-target;
       time stop at max_hold close. R-multiples after India costs.
"""
from __future__ import annotations

from typing import Any, Literal

import pandas as pd

from app.expectancy.costs import DEFAULT_COSTS, IndiaCostAssumptions, r_multiple

Side = Literal["BUY", "SELL"]


def simulate_trade(
    bars: pd.DataFrame,
    *,
    signal_entry: float,
    stop: float,
    target: float,
    side: Side = "BUY",
    max_hold: int = 5,
    product: Literal["delivery", "intraday"] = "delivery",
    assumptions: IndiaCostAssumptions = DEFAULT_COSTS,
) -> dict[str, Any]:
    """
    ``bars`` must start at the signal session (index 0 = signal day).
    Fill at next open when available — classic walk-forward, no same-bar entry.
    """
    if bars is None or bars.empty:
        return {
            "exit_reason": "no_data",
            "r_multiple": None,
            "hold_days": 0,
            "entry_fill": None,
            "exit_price": None,
            "won": None,
        }

    signal_entry = float(signal_entry)
    stop = float(stop)
    target = float(target)

    if len(bars) >= 2:
        fill = float(bars.iloc[1]["open"])
        start_i = 1
    else:
        fill = float(bars.iloc[0]["close"])
        start_i = 0

    def _finish(exit_px: float, reason: str, hold: int) -> dict[str, Any]:
        r = r_multiple(
            fill,
            exit_px,
            stop,
            side=side,
            product=product,
            assumptions=assumptions,
        )
        return {
            "exit_reason": reason,
            "r_multiple": None if r is None else round(float(r), 4),
            "hold_days": hold,
            "entry_fill": round(fill, 4),
            "exit_price": round(float(exit_px), 4),
            "won": None if r is None else bool(r > 0),
            "side": side,
        }

    # Gap through levels at open
    if side == "BUY":
        if fill <= stop:
            return _finish(fill, "gap_stop", 1)
        if fill >= target:
            return _finish(fill, "gap_target", 1)
    else:
        if fill >= stop:
            return _finish(fill, "gap_stop", 1)
        if fill <= target:
            return _finish(fill, "gap_target", 1)

    for i in range(start_i, min(len(bars), start_i + max_hold)):
        row = bars.iloc[i]
        high, low = float(row["high"]), float(row["low"])
        hold = i - start_i + 1

        if side == "BUY":
            # Conservative: stop before target on same bar
            if low <= stop:
                return _finish(stop, "stop", hold)
            if high >= target:
                return _finish(target, "target", hold)
        else:
            if high >= stop:
                return _finish(stop, "stop", hold)
            if low <= target:
                return _finish(target, "target", hold)

    last_i = min(len(bars) - 1, start_i + max_hold - 1)
    exit_px = float(bars.iloc[last_i]["close"])
    return _finish(exit_px, "time", min(max_hold, len(bars) - start_i))
