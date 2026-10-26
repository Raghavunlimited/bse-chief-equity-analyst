"""
Regime-segmented edge metrics from walk-forward trades.

Expectancy_R = (Win% × AvgWin_R) − (Loss% × AvgLoss_R)
where AvgLoss_R is the absolute magnitude of losing R multiples.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from app.expectancy.regimes import REGIME_LABELS


def _max_drawdown_pct(r_series: list[float]) -> float:
    """Max drawdown of an equity curve that starts at 1 and compounds by R≈risk unit.

    We treat each trade's R as additive risk-units on a unit bankroll curve
    equity_{t+1} = equity_t * (1 + 0.01 * R) — 1R ≈ 1% bankroll — so DD% is
    comparable across desks without needing rupee equity.
    """
    if not r_series:
        return 0.0
    eq = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in r_series:
        eq *= 1.0 + 0.01 * float(r)
        peak = max(peak, eq)
        if peak > 0:
            dd = (eq / peak - 1.0) * 100.0
            max_dd = min(max_dd, dd)
    return round(float(max_dd), 2)


def compute_edge_metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate metrics for a flat list of simulated trades (must have r_multiple)."""
    rs = [
        float(t["r_multiple"])
        for t in trades
        if t.get("r_multiple") is not None and not (
            isinstance(t.get("r_multiple"), float) and np.isnan(t["r_multiple"])
        )
    ]
    n = len(rs)
    if n == 0:
        return {
            "sample_size": 0,
            "win_rate_pct": None,
            "avg_win_r": None,
            "avg_loss_r": None,
            "expectancy_r": None,
            "profit_factor": None,
            "max_drawdown_pct": None,
        }

    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    win_rate = len(wins) / n
    loss_rate = 1.0 - win_rate
    avg_win = float(np.mean(wins)) if wins else 0.0
    # Avg loss as positive magnitude of R given back
    avg_loss_mag = float(np.mean([-r for r in losses])) if losses else 0.0
    expectancy = (win_rate * avg_win) - (loss_rate * avg_loss_mag)

    gross_win = float(sum(wins)) if wins else 0.0
    gross_loss = float(sum(-r for r in losses)) if losses else 0.0
    if gross_loss > 0:
        pf = gross_win / gross_loss
    elif gross_win > 0:
        pf = None  # infinite — store as None, gate treats as fail-safe high?
        # Spec wants PF >= 1.2; no losses → treat as very high
        pf = 99.0
    else:
        pf = 0.0

    return {
        "sample_size": n,
        "win_rate_pct": round(100.0 * win_rate, 2),
        "avg_win_r": round(avg_win, 4),
        "avg_loss_r": round(avg_loss_mag, 4),
        "expectancy_r": round(expectancy, 4),
        "profit_factor": round(pf, 4) if pf is not None else None,
        "max_drawdown_pct": _max_drawdown_pct(rs),
    }


def segment_by_regime(
    trades: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Per-regime metrics; always includes all four labels (empty → sample_size 0)."""
    out: dict[str, dict[str, Any]] = {}
    for label in REGIME_LABELS:
        subset = [t for t in trades if str(t.get("regime") or "") == label]
        m = compute_edge_metrics(subset)
        m["regime"] = label
        out[label] = m
    # Also overall
    overall = compute_edge_metrics(trades)
    overall["regime"] = "ALL"
    out["ALL"] = overall
    return out
