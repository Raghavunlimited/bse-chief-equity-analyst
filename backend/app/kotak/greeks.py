"""
Black-Scholes / Black-76 implied volatility and Greeks.

Index options (NIFTY, BANKNIFTY, …) → Black-76 on forward ≈ spot (r−q≈0 for short T).
Equity options → Black-Scholes with continuous dividend yield q.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Literal, Optional

Model = Literal["black76", "black_scholes"]

_INDEX_UNDERLYINGS = frozenset(
    {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50", "SENSEX", "BANKEX"}
)


@dataclass(frozen=True)
class Greeks:
    iv: Optional[float]  # decimal, e.g. 0.18 = 18%
    delta: Optional[float]
    gamma: Optional[float]
    theta: Optional[float]  # per calendar day
    vega: Optional[float]  # per 1% vol
    model: Model
    ok: bool
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.iv is not None:
            d["iv_pct"] = round(self.iv * 100.0, 4)
        else:
            d["iv_pct"] = None
        return d


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def select_model(underlying: str) -> Model:
    return "black76" if underlying.upper().strip() in _INDEX_UNDERLYINGS else "black_scholes"


def _d1_d2_bs(
    spot: float, strike: float, t: float, r: float, q: float, sigma: float
) -> tuple[float, float]:
    vol_sqrt = sigma * math.sqrt(t)
    d1 = (math.log(spot / strike) + (r - q + 0.5 * sigma * sigma) * t) / vol_sqrt
    d2 = d1 - vol_sqrt
    return d1, d2


def _d1_d2_b76(forward: float, strike: float, t: float, sigma: float) -> tuple[float, float]:
    vol_sqrt = sigma * math.sqrt(t)
    d1 = (math.log(forward / strike) + 0.5 * sigma * sigma * t) / vol_sqrt
    d2 = d1 - vol_sqrt
    return d1, d2


def price_bs(
    spot: float,
    strike: float,
    t: float,
    r: float,
    q: float,
    sigma: float,
    right: str,
) -> float:
    if t <= 0 or sigma <= 0 or spot <= 0 or strike <= 0:
        intrinsic = max(spot - strike, 0.0) if right.upper() == "CE" else max(strike - spot, 0.0)
        return intrinsic
    d1, d2 = _d1_d2_bs(spot, strike, t, r, q, sigma)
    if right.upper() == "CE":
        return spot * math.exp(-q * t) * _norm_cdf(d1) - strike * math.exp(-r * t) * _norm_cdf(d2)
    return strike * math.exp(-r * t) * _norm_cdf(-d2) - spot * math.exp(-q * t) * _norm_cdf(-d1)


def price_b76(
    forward: float,
    strike: float,
    t: float,
    r: float,
    sigma: float,
    right: str,
) -> float:
    if t <= 0 or sigma <= 0 or forward <= 0 or strike <= 0:
        intrinsic = max(forward - strike, 0.0) if right.upper() == "CE" else max(strike - forward, 0.0)
        return math.exp(-r * t) * intrinsic if t > 0 else intrinsic
    d1, d2 = _d1_d2_b76(forward, strike, t, sigma)
    df = math.exp(-r * t)
    if right.upper() == "CE":
        return df * (forward * _norm_cdf(d1) - strike * _norm_cdf(d2))
    return df * (strike * _norm_cdf(-d2) - forward * _norm_cdf(-d1))


def implied_vol(
    *,
    premium: float,
    spot: float,
    strike: float,
    t_years: float,
    right: str,
    r: float = 0.065,
    q: float = 0.0,
    model: Model = "black_scholes",
    forward: Optional[float] = None,
) -> Optional[float]:
    """Newton-Raphson IV. Returns None if unsolvable."""
    if premium is None or premium <= 0 or spot <= 0 or strike <= 0:
        return None
    if t_years <= 1e-8:
        return None
    fwd = forward if forward is not None else spot * math.exp((r - q) * t_years)
    # Intrinsic floor
    if model == "black76":
        intrinsic = math.exp(-r * t_years) * (
            max(fwd - strike, 0.0) if right.upper() == "CE" else max(strike - fwd, 0.0)
        )
    else:
        intrinsic = (
            max(spot * math.exp(-q * t_years) - strike * math.exp(-r * t_years), 0.0)
            if right.upper() == "CE"
            else max(strike * math.exp(-r * t_years) - spot * math.exp(-q * t_years), 0.0)
        )
    if premium < intrinsic * 0.999:
        return None

    sigma = 0.25
    for _ in range(40):
        if model == "black76":
            px = price_b76(fwd, strike, t_years, r, sigma, right)
            d1, _ = _d1_d2_b76(fwd, strike, t_years, sigma)
            vega = math.exp(-r * t_years) * fwd * _norm_pdf(d1) * math.sqrt(t_years)
        else:
            px = price_bs(spot, strike, t_years, r, q, sigma, right)
            d1, _ = _d1_d2_bs(spot, strike, t_years, r, q, sigma)
            vega = spot * math.exp(-q * t_years) * _norm_pdf(d1) * math.sqrt(t_years)
        diff = px - premium
        if abs(diff) < 1e-6:
            return max(1e-4, min(sigma, 5.0))
        if vega < 1e-12:
            break
        sigma -= diff / vega
        if sigma <= 1e-4:
            sigma = 1e-4
        if sigma > 5.0:
            sigma = 5.0
    return max(1e-4, min(sigma, 5.0)) if abs(diff) < 0.05 * max(premium, 1.0) else None


def compute_greeks(
    *,
    premium: Optional[float],
    spot: float,
    strike: float,
    t_years: float,
    right: str,
    underlying: str,
    r: float = 0.065,
    q: float = 0.0,
    forward: Optional[float] = None,
) -> Greeks:
    model = select_model(underlying)
    if premium is None or premium <= 0 or spot <= 0 or strike <= 0:
        return Greeks(None, None, None, None, None, model, False, "missing_premium_or_spot")
    if t_years <= 1e-8:
        # At expiry: delta binary-ish, rest ~0
        if right.upper() == "CE":
            delta = 1.0 if spot > strike else 0.0
        else:
            delta = -1.0 if spot < strike else 0.0
        return Greeks(None, delta, 0.0, 0.0, 0.0, model, True, "expired_or_zero_t")

    fwd = forward if forward is not None else (
        spot if model == "black76" else spot * math.exp((r - q) * t_years)
    )
    iv = implied_vol(
        premium=premium,
        spot=spot,
        strike=strike,
        t_years=t_years,
        right=right,
        r=r,
        q=q,
        model=model,
        forward=fwd,
    )
    if iv is None:
        return Greeks(None, None, None, None, None, model, False, "iv_unsolvable")

    if model == "black76":
        d1, d2 = _d1_d2_b76(fwd, strike, t_years, iv)
        df = math.exp(-r * t_years)
        pdf = _norm_pdf(d1)
        if right.upper() == "CE":
            delta = df * _norm_cdf(d1)
            theta = (
                -df * fwd * pdf * iv / (2.0 * math.sqrt(t_years))
                + r * strike * df * _norm_cdf(d2)
                - r * fwd * df * _norm_cdf(d1)
            ) / 365.0
        else:
            delta = -df * _norm_cdf(-d1)
            theta = (
                -df * fwd * pdf * iv / (2.0 * math.sqrt(t_years))
                - r * strike * df * _norm_cdf(-d2)
                + r * fwd * df * _norm_cdf(-d1)
            ) / 365.0
        gamma = df * pdf / (fwd * iv * math.sqrt(t_years))
        vega = df * fwd * pdf * math.sqrt(t_years) / 100.0
    else:
        d1, d2 = _d1_d2_bs(spot, strike, t_years, r, q, iv)
        pdf = _norm_pdf(d1)
        if right.upper() == "CE":
            delta = math.exp(-q * t_years) * _norm_cdf(d1)
            theta = (
                -spot * math.exp(-q * t_years) * pdf * iv / (2.0 * math.sqrt(t_years))
                - r * strike * math.exp(-r * t_years) * _norm_cdf(d2)
                + q * spot * math.exp(-q * t_years) * _norm_cdf(d1)
            ) / 365.0
        else:
            delta = -math.exp(-q * t_years) * _norm_cdf(-d1)
            theta = (
                -spot * math.exp(-q * t_years) * pdf * iv / (2.0 * math.sqrt(t_years))
                + r * strike * math.exp(-r * t_years) * _norm_cdf(-d2)
                - q * spot * math.exp(-q * t_years) * _norm_cdf(-d1)
            ) / 365.0
        gamma = math.exp(-q * t_years) * pdf / (spot * iv * math.sqrt(t_years))
        vega = spot * math.exp(-q * t_years) * pdf * math.sqrt(t_years) / 100.0

    return Greeks(
        iv=iv,
        delta=round(delta, 6),
        gamma=round(gamma, 8),
        theta=round(theta, 6),
        vega=round(vega, 6),
        model=model,
        ok=True,
    )
