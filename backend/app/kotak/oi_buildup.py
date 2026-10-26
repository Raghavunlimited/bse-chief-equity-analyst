"""
4-quadrant OI buildup classifier.

Price Δ vs OI Δ → Long Buildup | Short Buildup | Short Covering | Long Unwinding.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal, Optional

BuildupLabel = Literal[
    "Long Buildup",
    "Short Buildup",
    "Short Covering",
    "Long Unwinding",
    "Neutral",
    "Unknown",
]


@dataclass(frozen=True)
class BuildupResult:
    label: BuildupLabel
    price_change: Optional[float]
    oi_change: Optional[float]
    price_dir: Literal["up", "down", "flat", "unknown"]
    oi_dir: Literal["up", "down", "flat", "unknown"]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _dir(delta: Optional[float], *, eps: float) -> Literal["up", "down", "flat", "unknown"]:
    if delta is None:
        return "unknown"
    if abs(delta) <= eps:
        return "flat"
    return "up" if delta > 0 else "down"


def classify_oi_buildup(
    price_change: Optional[float],
    oi_change: Optional[float],
    *,
    price_eps: float = 1e-9,
    oi_eps: float = 0.0,
) -> BuildupResult:
    """
    Classic futures/options OI matrix:

    |               | OI ↑              | OI ↓              |
    |-------------|-------------------|-------------------|
    | Price ↑     | Long Buildup      | Short Covering    |
    | Price ↓     | Short Buildup     | Long Unwinding    |
    """
    pdir = _dir(price_change, eps=price_eps)
    odir = _dir(oi_change, eps=oi_eps)
    if pdir == "unknown" or odir == "unknown":
        label: BuildupLabel = "Unknown"
    elif pdir == "flat" or odir == "flat":
        label = "Neutral"
    elif pdir == "up" and odir == "up":
        label = "Long Buildup"
    elif pdir == "down" and odir == "up":
        label = "Short Buildup"
    elif pdir == "up" and odir == "down":
        label = "Short Covering"
    elif pdir == "down" and odir == "down":
        label = "Long Unwinding"
    else:
        label = "Neutral"
    return BuildupResult(
        label=label,
        price_change=price_change,
        oi_change=oi_change,
        price_dir=pdir,
        oi_dir=odir,
    )


def max_pain_strike(
    strikes: list[float],
    call_oi: dict[float, float],
    put_oi: dict[float, float],
) -> Optional[float]:
    """
    Strike that minimizes total option-writer intrinsic payout at expiry.

    pain(P) = Σ_K  CE_OI(K)·max(P−K,0) + PE_OI(K)·max(K−P,0)
    """
    if not strikes:
        return None
    uniq = sorted({float(s) for s in strikes})
    best_p: Optional[float] = None
    best_pain = float("inf")
    for p in uniq:
        pain = 0.0
        for k in uniq:
            ce = float(call_oi.get(k) or 0.0)
            pe = float(put_oi.get(k) or 0.0)
            pain += ce * max(p - k, 0.0) + pe * max(k - p, 0.0)
        if pain < best_pain:
            best_pain = pain
            best_p = p
    return best_p
