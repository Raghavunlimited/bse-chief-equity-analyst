"""
Weekly swing strategy — India-research pack ``elite_momentum``.

Single path for live picks and backtest.

Rules:
- Regime: NIFTY close > SMA20 > SMA50 (else cash / no picks) — unchanged
- Absolute strength (Stage 2): close > sma_20 > sma_50
- Relative strength: stock 20D ROC − NIFTY 20D ≥ +rs_min; also roc_20 > 0
- entry_style:
    - breakout: near 20D high (range_position ≥ 0.85), vol ≥ volume_mult, roc_3 > 0
    - pullback: Stage 2 + range_position 0.55–0.85, vol_ratio ≥ 1.3, roc_3 may be slightly negative
- Score ≥ min_score; top N only
- Risk: stop tighter of 1.2×ATR / 3%; target higher of 2×ATR / 6%
- Optional sizing via size_position when capital / risk_pct provided

No guaranteed returns — setups are research candidates only.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Literal

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

PACK_NAME = "elite_momentum"
EntryStyle = Literal["breakout", "pullback"]

ELITE_SECTORS = {
    "Exchange",
    "Aviation",
    "Banking",
    "Realty",
    "Auto Ancillary",
    "Infrastructure",
    "Energy",
    "Defence",
    "Power",
    "Packaging",
    "IT",
    "Pharma",
    "Financial Services",
    "Finance",
    "Capital Goods",
    "Chemicals",
    "Consumer Durables",
    "FMCG",
    "Insurance",
    "Metals",
    "Telecom",
    "Auto",
    "Conglomerate",
    "Unknown",
}


def check_market_regime(nifty_df: pd.DataFrame) -> dict[str, Any]:
    if nifty_df is None or nifty_df.empty or len(nifty_df) < 50:
        return {
            "regime": "UNKNOWN",
            "allow_trading": False,
            "reason": "Insufficient NIFTY history — no new entries",
            "nifty_change_20d": 0.0,
            "nifty_price": None,
        }

    close = nifty_df["close"].astype(float)
    sma_20 = close.rolling(20).mean().iloc[-1]
    sma_50 = close.rolling(50).mean().iloc[-1]
    price = float(close.iloc[-1])
    nifty_change_20d = float((price / float(close.iloc[-20]) - 1) * 100)

    above_20 = price > sma_20
    above_50 = price > sma_50
    stack = sma_20 > sma_50

    if above_20 and above_50 and stack:
        regime, allow, reason = "STRONG_BULL", True, "NIFTY above SMA20 > SMA50"
    elif above_20 and above_50:
        regime, allow, reason = "BULL", True, "NIFTY above SMA20 and SMA50"
    elif above_50:
        regime, allow, reason = "NEUTRAL", False, "NIFTY mixed — stay in cash"
    else:
        regime, allow, reason = "BEAR", False, "NIFTY below SMA50 — no new swings"

    return {
        "regime": regime,
        "allow_trading": allow,
        "reason": reason,
        "nifty_change_20d": nifty_change_20d,
        "nifty_price": price,
        "nifty_sma_20": float(sma_20),
        "nifty_sma_50": float(sma_50),
    }


def _risk_as_fraction(risk_pct: float) -> float:
    """Normalize risk input to a fraction of capital.

    - Config style: 0.02 → 2%
    - API style percent: 1.0 / 2.0 → 1% / 2% (values > 0.2 treated as percent)
    """
    r = float(risk_pct)
    # >0.2 → percent (API: 0.25–5); ≤0.2 → fraction (config: 0.02)
    if r > 0.2:
        return max(0.0, r / 100.0)
    return max(0.0, r)


def size_position(
    capital: float,
    risk_pct: float,
    entry: float,
    stop: float,
) -> dict[str, Any]:
    """
    Pure position-sizing helper.

    Args:
        capital: portfolio capital (₹)
        risk_pct: risk per trade — fraction (0.02) or percent (1 / 2)
        entry: entry price
        stop: stop-loss price

    Returns:
        shares, risk_rs, position_value, portfolio_pct
    """
    if capital <= 0 or entry <= 0:
        return {
            "shares": 0,
            "risk_rs": 0.0,
            "position_value": 0.0,
            "portfolio_pct": 0.0,
        }

    pct = _risk_as_fraction(risk_pct)
    risk_budget = capital * pct
    per_share_risk = entry - stop
    if per_share_risk <= 0:
        return {
            "shares": 0,
            "risk_rs": 0.0,
            "position_value": 0.0,
            "portfolio_pct": 0.0,
        }

    shares = int(math.floor(risk_budget / per_share_risk))
    shares = max(0, shares)
    risk_rs = shares * per_share_risk
    position_value = shares * entry
    portfolio_pct = (position_value / capital) * 100.0 if capital else 0.0

    return {
        "shares": shares,
        "risk_rs": round(risk_rs, 2),
        "position_value": round(position_value, 2),
        "portfolio_pct": round(portfolio_pct, 2),
    }


def _score(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    range_size = (df["hh_20"] - df["ll_20"]).replace(0, np.nan)
    df["range_position"] = ((df["close"] - df["ll_20"]) / range_size).clip(upper=1.5)

    df["breakout_score"] = 0
    df.loc[df["range_position"] >= 0.98, "breakout_score"] = 35
    df.loc[
        (df["range_position"] >= 0.95) & (df["range_position"] < 0.98), "breakout_score"
    ] = 30
    df.loc[
        (df["range_position"] >= 0.90) & (df["range_position"] < 0.95), "breakout_score"
    ] = 25
    df.loc[
        (df["range_position"] >= 0.85) & (df["range_position"] < 0.90), "breakout_score"
    ] = 20
    df.loc[
        (df["range_position"] >= 0.80) & (df["range_position"] < 0.85), "breakout_score"
    ] = 15
    # Pullback zone still gets modest structure points
    df.loc[
        (df["range_position"] >= 0.55) & (df["range_position"] < 0.80), "breakout_score"
    ] = 12

    df["vol_ratio"] = df["volume"] / (df["vol_ma_20"] + 1)
    df["volume_score"] = 0
    df.loc[df["vol_ratio"] >= 3.0, "volume_score"] = 25
    df.loc[(df["vol_ratio"] >= 2.5) & (df["vol_ratio"] < 3.0), "volume_score"] = 22
    df.loc[(df["vol_ratio"] >= 2.0) & (df["vol_ratio"] < 2.5), "volume_score"] = 20
    df.loc[(df["vol_ratio"] >= 1.5) & (df["vol_ratio"] < 2.0), "volume_score"] = 15
    df.loc[(df["vol_ratio"] >= 1.3) & (df["vol_ratio"] < 1.5), "volume_score"] = 10

    df["momentum_score"] = 0
    df.loc[(df["rsi_14"] >= 50) & (df["rsi_14"] <= 60), "momentum_score"] += 10
    df.loc[(df["rsi_14"] > 60) & (df["rsi_14"] <= 70), "momentum_score"] += 15
    df.loc[(df["rsi_14"] > 70) & (df["rsi_14"] <= 75), "momentum_score"] += 8
    df.loc[(df["close"] > df["sma_20"]) & (df["close"] > df["sma_50"]), "momentum_score"] += 10
    df.loc[df["roc_3"] > 2, "momentum_score"] += 5
    df.loc[(df["roc_3"] > 0) & (df["roc_3"] <= 2), "momentum_score"] += 3
    df["momentum_score"] = df["momentum_score"].clip(upper=25)

    df["trend_score"] = 0
    df.loc[df["close"] > df["sma_20"], "trend_score"] += 5
    df.loc[df["close"] > df["sma_50"], "trend_score"] += 5
    df.loc[df["sma_20"] > df["sma_50"], "trend_score"] += 5

    df["score"] = (
        df["breakout_score"]
        + df["volume_score"]
        + df["momentum_score"]
        + df["trend_score"]
    )
    return df


def _entry_mask(
    df: pd.DataFrame,
    *,
    entry_style: EntryStyle,
    min_score: float,
    volume_mult: float,
    rsi_min: float,
    rsi_max: float,
    rs_min: float,
    volume_rising: pd.Series,
) -> pd.Series:
    """Common elite_momentum gates + style-specific entry filters."""
    # Absolute strength (Stage 2) + absolute momentum + RS vs NIFTY
    base = (
        (df["score"] >= min_score)
        & (df["close"] > df["sma_20"])
        & (df["sma_20"] > df["sma_50"])
        & (df["rsi_14"] >= rsi_min)
        & (df["rsi_14"] <= rsi_max)
        & (df["relative_strength"] >= rs_min)
        & (df["roc_20"].fillna(0) > 0)
    )

    if entry_style == "pullback":
        # Stage 2 pullback: mid-range, constructive volume; roc_3 may dip slightly
        return (
            base
            & (df["range_position"] >= 0.55)
            & (df["range_position"] <= 0.85)
            & (df["vol_ratio"] >= 1.3)
            & (df["roc_3"] >= -2.0)
        )

    # breakout (default): near 20D high, strong volume confirmation
    return (
        base
        & (df["vol_ratio"] >= volume_mult)
        & volume_rising
        & (df["roc_3"] > 0)
        & (df["range_position"] >= 0.85)
    )


def generate_weekly_picks(
    snapshot: pd.DataFrame,
    nifty_df: pd.DataFrame,
    *,
    as_of: str,
    sector_map: dict[str, str] | None = None,
    top_n: int = 2,
    min_score: float = 65,
    min_price: float = 100,
    min_turnover: float = 10_00_00_000,
    volume_mult: float = 2.0,
    rsi_min: float = 45,
    rsi_max: float = 75,
    rs_min: float = 3.0,
    risk_per_trade: float = 0.02,
    capital_per_trade: float = 100_000,
    capital: float | None = None,
    risk_pct: float | None = None,
    max_positions: int | None = None,
    reserved_cash_pct: float = 0.0,
    entry_style: str = "breakout",
    require_fresh: bool = False,
    data_status: dict | None = None,
) -> dict[str, Any]:
    """
    Screen as_of snapshot. Same function used by API and backtest.
    If regime blocks trading → empty candidates (cash week).

    When ``capital`` and/or ``risk_pct`` are passed, each candidate gets a
    ``sizing`` block from ``size_position``. ``max_positions`` overrides ``top_n``.
    ``reserved_cash_pct`` reduces deployable capital used for sizing.
    """
    style: EntryStyle = "pullback" if str(entry_style).lower() == "pullback" else "breakout"
    n_picks = int(max_positions) if max_positions is not None else int(top_n)
    n_picks = max(1, n_picks)

    gross_capital = float(capital) if capital is not None else float(capital_per_trade)
    reserved = max(0.0, min(80.0, float(reserved_cash_pct)))
    sizing_capital = gross_capital * (1.0 - reserved / 100.0)
    sizing_risk = float(risk_pct) if risk_pct is not None else float(risk_per_trade)
    risk_frac = _risk_as_fraction(sizing_risk)
    sizing_summary = {
        "capital": gross_capital,
        "risk_rupees": round(gross_capital * risk_frac, 2),
        "deployable": round(sizing_capital, 2),
        "deployable_capital": round(sizing_capital, 2),
        "reserved_cash_pct": reserved,
        "risk_pct": risk_frac * 100.0,
        "risk_pct_fraction": risk_frac,
        "max_positions": n_picks,
        "slot_budget": round(sizing_capital / max(n_picks, 1), 2),
    }

    result: dict[str, Any] = {
        "as_of": as_of,
        "status": "ok",
        "pack": PACK_NAME,
        "entry_style": style,
        "data_status": data_status or {},
        "market_regime": {},
        "candidates": [],
        "message": "",
        "filters": [],
        "stats": {"universe": 0, "passed": 0},
        "sizing": sizing_summary,
        "sizing_inputs": sizing_summary,
    }

    if data_status and data_status.get("status") == "STALE" and require_fresh:
        result["status"] = "stale"
        result["message"] = data_status.get(
            "message", "Data is stale — refresh before trading"
        )
        return result

    regime = check_market_regime(nifty_df)
    result["market_regime"] = regime
    result["filters"].append(f"Regime: {regime['regime']}")
    result["filters"].append(f"Pack: {PACK_NAME} / {style}")

    if snapshot is None or snapshot.empty:
        result["status"] = "empty"
        result["message"] = "No snapshot for date"
        if not regime["allow_trading"]:
            result["status"] = "cash"
            result["message"] = regime["reason"]
        return result

    df = snapshot.copy()
    result["stats"]["universe"] = len(df)
    result["stats"]["radar"] = 0

    if sector_map:
        df["sector"] = df["symbol"].map(lambda s: sector_map.get(s, "Unknown"))
    else:
        df["sector"] = "Unknown"

    needed = [
        "close",
        "sma_20",
        "sma_50",
        "rsi_14",
        "atr_14",
        "vol_ma_20",
        "hh_20",
        "ll_20",
        "volume",
        "roc_3",
        "roc_20",
    ]
    for col in needed:
        if col not in df.columns:
            result["status"] = "error"
            result["message"] = f"Missing column {col}"
            return result

    df = df[
        (df["close"] >= min_price)
        & (df["sma_20"].notna())
        & (df["sma_50"].notna())
        & (df["rsi_14"].notna())
        & (df["atr_14"].notna())
        & (df["vol_ma_20"].notna())
        & (df["hh_20"].notna())
        & (df["turnover"].fillna(0) >= min_turnover)
    ].copy()
    result["filters"].append(f"Price ≥ ₹{min_price}, turnover ≥ 10 Cr")

    # Quality gate + Stage 2 absolute strength seed
    df = df[
        (df["close"] >= df["hh_20"] * 0.70)
        & (df["close"] > df["sma_20"])
        & (df["sma_20"] > df["sma_50"])
        & (df["rsi_14"] >= 30)
    ].copy()

    # Sector allowlist
    df = df[df["sector"].isin(ELITE_SECTORS)].copy()

    if df.empty:
        result["message"] = "No names passed universe / quality filters"
        if not regime["allow_trading"]:
            result["status"] = "cash"
            result["message"] = regime["reason"]
        return result

    df = _score(df)

    # Relative strength vs NIFTY
    nifty_chg = float(regime.get("nifty_change_20d") or 0)
    df["relative_strength"] = df["roc_20"].fillna(0) - nifty_chg

    prev_vol = df["prev_volume"].fillna(df["vol_ma_20"] * 0.8)
    volume_rising = df["volume"] > prev_vol

    # Radar: strongest momentum names even when regime blocks entries
    radar_df = df.sort_values("score", ascending=False).head(8)
    result["radar"] = [
        {
            "symbol": str(r["symbol"]),
            "sector": str(r.get("sector") or "Unknown"),
            "score": int(r["score"]),
            "close": round(float(r["close"]), 2),
            "rsi_14": round(float(r["rsi_14"]), 1),
            "roc_20": round(float(r.get("roc_20") or 0), 2),
            "relative_strength": round(float(r["relative_strength"]), 2),
            "actionable": False,
        }
        for _, r in radar_df.iterrows()
    ]
    result["stats"]["radar"] = len(result["radar"])

    if not regime["allow_trading"]:
        result["message"] = regime["reason"]
        result["status"] = "cash"
        result["candidates"] = []
        return result

    mask = _entry_mask(
        df,
        entry_style=style,
        min_score=min_score,
        volume_mult=volume_mult,
        rsi_min=rsi_min,
        rsi_max=rsi_max,
        rs_min=rs_min,
        volume_rising=volume_rising,
    )
    filtered = df[mask].copy()

    if style == "pullback":
        style_filters = [
            f"Score ≥ {min_score}",
            "Stage 2: close > SMA20 > SMA50",
            "Pullback: range_pos 0.55–0.85, vol ≥ 1.3×, roc_3 ≥ −2%",
            f"RSI {rsi_min}-{rsi_max}",
            f"RS ≥ +{rs_min}% vs NIFTY and roc_20 > 0",
        ]
    else:
        style_filters = [
            f"Score ≥ {min_score}",
            f"Vol ≥ {volume_mult}× and rising",
            f"RSI {rsi_min}-{rsi_max}",
            f"RS ≥ +{rs_min}% vs NIFTY and roc_20 > 0",
            "Stage 2 + near 20D high, ROC3 > 0",
        ]
    result["filters"].extend(style_filters)
    result["stats"]["passed"] = len(filtered)

    if filtered.empty:
        result["message"] = (
            "No setups meet criteria this week — stay in cash "
            "(research screen only; no edge guaranteed)"
        )
        result["status"] = "cash"
        return result

    # Trade plan
    atr_stop = filtered["close"] - filtered["atr_14"] * 1.2
    pct_stop = filtered["close"] * 0.97
    filtered["stop_loss"] = np.maximum(atr_stop, pct_stop)

    atr_tgt = filtered["close"] + filtered["atr_14"] * 2.0
    pct_tgt = filtered["close"] * 1.06
    filtered["target_price"] = np.maximum(atr_tgt, pct_tgt)
    filtered["entry_price"] = filtered["close"]

    filtered["risk_pct"] = (
        (filtered["entry_price"] - filtered["stop_loss"]) / filtered["entry_price"] * 100
    )
    filtered["reward_pct"] = (
        (filtered["target_price"] - filtered["entry_price"])
        / filtered["entry_price"]
        * 100
    )
    filtered["risk_reward"] = filtered["reward_pct"] / filtered["risk_pct"].replace(
        0, np.nan
    )

    filtered = filtered.sort_values("score", ascending=False).head(n_picks)

    candidates = []
    for _, row in filtered.iterrows():
        entry = float(row["entry_price"])
        stop = float(row["stop_loss"])
        sizing = size_position(sizing_capital, sizing_risk, entry, stop)
        # Cap notional to an equal slice of deployable capital (PM Capital Desk)
        slot_budget = sizing_capital / max(n_picks, 1)
        if entry > 0 and sizing["position_value"] > slot_budget:
            capped = int(math.floor(slot_budget / entry))
            per_share_risk = max(entry - stop, 0.01)
            sizing["shares"] = max(0, capped)
            sizing["position_value"] = round(sizing["shares"] * entry, 2)
            sizing["risk_rs"] = round(sizing["shares"] * per_share_risk, 2)
        if gross_capital > 0 and sizing["position_value"]:
            sizing["portfolio_pct"] = round(
                float(sizing["position_value"]) / gross_capital * 100.0, 2
            )
        else:
            sizing["portfolio_pct"] = 0.0
        shares = int(sizing["shares"])

        t1 = round(entry * 1.03, 2)
        t2 = round(float(row["target_price"]), 2)

        if style == "pullback":
            thesis = (
                f"Stage-2 pullback (range {float(row['range_position']):.2f}) with "
                f"{float(row['vol_ratio']):.1f}× volume; "
                f"RS {float(row['relative_strength']):+.1f}% vs NIFTY; "
                f"RSI {float(row['rsi_14']):.0f}."
            )
            entry_plan = "Buy on strength near close / open; prefer holds above SMA20"
        else:
            thesis = (
                f"Breakout near 20D high with {float(row['vol_ratio']):.1f}× volume; "
                f"RS {float(row['relative_strength']):+.1f}% vs NIFTY; "
                f"RSI {float(row['rsi_14']):.0f}."
            )
            entry_plan = "Buy near open next session (or on pullback to entry)"

        cand: dict[str, Any] = {
            "symbol": str(row["symbol"]),
            "sector": str(row["sector"]),
            "score": int(row["score"]),
            "entry_style": style,
            "entry_price": round(entry, 2),
            "stop_loss": round(stop, 2),
            "target_price": t2,
            "targets": {"t1": t1, "t2": t2},
            "risk_pct": round(float(row["risk_pct"]), 2),
            "reward_pct": round(float(row["reward_pct"]), 2),
            "risk_reward": round(float(row["risk_reward"]), 2),
            "position_size": shares,
            "shares": shares,
            "risk_rs": sizing.get("risk_rs"),
            "position_value": sizing.get("position_value"),
            "portfolio_pct": sizing.get("portfolio_pct"),
            "sizing": sizing,
            "thesis": thesis,
            "score_breakdown": {
                "breakout": int(row["breakout_score"]),
                "volume": int(row["volume_score"]),
                "momentum": int(row["momentum_score"]),
                "trend": int(row["trend_score"]),
            },
            "metrics": {
                "vol_ratio": round(float(row["vol_ratio"]), 2),
                "roc_3": round(float(row["roc_3"]), 2),
                "roc_20": round(float(row.get("roc_20") or 0), 2),
                "rsi_14": round(float(row["rsi_14"]), 1),
                "relative_strength": round(float(row["relative_strength"]), 2),
                "range_position": round(float(row["range_position"]), 3),
                "atr_14": round(float(row["atr_14"]), 2),
                "sma_20": round(float(row["sma_20"]), 2),
                "sma_50": round(float(row["sma_50"]), 2),
            },
            "plan": {
                "entry": entry_plan,
                "stop": f"Hard stop ₹{stop:.2f}",
                "trail": "After +1%, trail 1% under swing high",
                "exit": "Hit T2, stop, or Friday / max 5 sessions",
            },
        }
        candidates.append(cand)

    result["candidates"] = candidates
    result["message"] = (
        f"{len(candidates)} {style} setup(s) — research candidates only; "
        "no return guarantee"
    )
    return result
