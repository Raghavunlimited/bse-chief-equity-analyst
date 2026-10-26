"""
Risk-based position sizing — research calculation only.

Does **not** place orders. Returns ``available=false`` with explicit blockers
(no fabricated size) when required inputs are missing, stale, or unverified —
including lot size, contract mapping, stop, or required margin.

Options premium / multiplier math runs only when those inputs are verified.
"""
from __future__ import annotations

import math
from typing import Any, Literal, Optional

InstrumentKind = Literal["EQ", "FUT", "OPT", "MCX_PROXY", "UNKNOWN"]
Direction = Literal["LONG", "SHORT"]

DISCLAIMER = (
    "Research calculation only — not an order instruction and does not place trades. "
    "Confirm lot size, margin, and fills with your broker before any order."
)

FORMULA_FIXED_FRACTIONAL = (
    "risk_budget = capital × (risk_pct/100) − fixed_costs; "
    "units = floor(risk_budget / per_unit_risk) rounded down to whole lots; "
    "then capped by max_position_pct / max_notional / max_lots / remaining exposure / "
    "affordable margin when applicable."
)


def _f(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    if math.isnan(v) or math.isinf(v):
        return default
    return v


def _unavailable(
    blockers: list[str],
    *,
    assumptions: list[str] | None = None,
    contract: dict[str, Any] | None = None,
    inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "available": False,
        "size": None,
        "blockers": list(blockers),
        "formula": FORMULA_FIXED_FRACTIONAL,
        "assumptions": assumptions or [],
        "disclaimer": DISCLAIMER,
        "contract": contract,
        "inputs": inputs,
        "is_order_instruction": False,
    }


def resolve_contract(
    *,
    instrument_kind: str,
    symbol: str = "",
    lot_size: Optional[int] = None,
    multiplier: Optional[float] = None,
    lot_size_verified: bool = False,
    contract_mapping_verified: bool = False,
    source: str = "unverified",
    expiry: Optional[str] = None,
    underlying: Optional[str] = None,
    option_right: Optional[str] = None,
    quote_stale: bool = False,
    mapping_stale: bool = False,
) -> dict[str, Any]:
    """
    Build a contract descriptor. Cash EQ may use lot_size=1 / multiplier=1 when
    the caller marks cash equity as verified. F&O requires verified lot + mapping.
    """
    kind_raw = (instrument_kind or "UNKNOWN").strip().upper()
    if kind_raw in ("EQUITY", "CASH", "STOCK", "NSE_EQ"):
        kind_raw = "EQ"
    if kind_raw in ("FUTURE", "FUTURES", "NSE_FUT"):
        kind_raw = "FUT"
    if kind_raw in ("OPTION", "OPTIONS", "NSE_OPT"):
        kind_raw = "OPT"
    if kind_raw in ("MCX", "COMMODITY", "PROXY"):
        kind_raw = "MCX_PROXY"
    if kind_raw not in ("EQ", "FUT", "OPT", "MCX_PROXY"):
        kind_raw = "UNKNOWN"

    blockers: list[str] = []
    if quote_stale:
        blockers.append("quote_or_inputs_stale")
    if mapping_stale:
        blockers.append("contract_mapping_stale")

    verified_lot: Optional[int] = None
    verified_mult: Optional[float] = None
    verified = False
    assumptions: list[str] = []

    if kind_raw == "MCX_PROXY":
        blockers.append("mcx_proxy_lot_sizing_unavailable")
        blockers.append("contract_mapping_unverified")
    elif kind_raw == "UNKNOWN":
        blockers.append("instrument_kind_unknown")
        blockers.append("contract_mapping_unverified")
    elif kind_raw == "EQ":
        # Cash equity: 1 share = 1 unit, multiplier 1 — only if mapping verified.
        if not contract_mapping_verified:
            blockers.append("contract_mapping_unverified")
        if lot_size is None:
            ls = 1
            assumptions.append(
                "Cash equity uses lot_size=1 share and multiplier=1 when mapping is verified."
            )
            lot_ok = bool(contract_mapping_verified)
        else:
            ls = int(lot_size)
            lot_ok = bool(lot_size_verified)
            if not lot_size_verified:
                blockers.append("lot_size_unverified")
        mult = 1.0 if multiplier is None else float(multiplier)
        if ls <= 0:
            blockers.append("lot_size_invalid")
            lot_ok = False
        if mult <= 0:
            blockers.append("multiplier_invalid")
            lot_ok = False
        if not blockers and lot_ok and contract_mapping_verified:
            verified_lot = ls
            verified_mult = mult
            verified = True
            lot_size_verified = True
    else:
        # FUT / OPT — require verified expiry-specific lot + mapping + multiplier.
        if not contract_mapping_verified:
            blockers.append("contract_mapping_unverified")
        if lot_size is None:
            blockers.append("lot_size_missing")
        elif int(lot_size) <= 0:
            blockers.append("lot_size_invalid")
        elif not lot_size_verified:
            blockers.append("lot_size_unverified")
        if multiplier is None:
            blockers.append("multiplier_missing")
        elif float(multiplier) <= 0:
            blockers.append("multiplier_invalid")
        if kind_raw in ("FUT", "OPT") and not expiry:
            assumptions.append(
                "Expiry not supplied — lot must still be expiry-specific and verified by caller."
            )
        if (
            not blockers
            and lot_size_verified
            and contract_mapping_verified
            and lot_size is not None
            and multiplier is not None
        ):
            verified_lot = int(lot_size)
            verified_mult = float(multiplier)
            verified = True

    return {
        "instrument_kind": kind_raw,
        "symbol": (symbol or "").upper(),
        "lot_size": verified_lot if verified else (int(lot_size) if lot_size is not None else None),
        "multiplier": verified_mult
        if verified
        else (_f(multiplier) if multiplier is not None else None),
        "lot_size_verified": bool(lot_size_verified) and verified_lot is not None,
        "contract_mapping_verified": bool(contract_mapping_verified) and verified,
        "verified": verified,
        "source": source,
        "expiry": expiry,
        "underlying": underlying,
        "option_right": option_right.upper() if option_right else None,
        "blockers": blockers,
        "assumptions": assumptions,
    }


def _apply_caps(
    *,
    lots: int,
    lot_size: int,
    entry: float,
    multiplier: float,
    capital: float,
    max_position_pct: Optional[float],
    max_notional: Optional[float],
    max_lots: Optional[int],
    open_exposure_notional: float,
    max_total_exposure_pct: Optional[float],
    margin_per_lot: Optional[float],
) -> tuple[int, list[str]]:
    """Return capped lots and list of caps that bound the result."""
    applied: list[str] = []
    if lots <= 0:
        return 0, applied

    units = lots * lot_size
    notional = units * entry * multiplier

    if max_lots is not None and max_lots >= 0 and lots > int(max_lots):
        lots = int(max_lots)
        applied.append("max_lots")
        units = lots * lot_size
        notional = units * entry * multiplier

    if max_notional is not None and max_notional > 0 and notional > max_notional:
        # floor lots so notional <= max
        per_lot_notional = lot_size * entry * multiplier
        if per_lot_notional <= 0:
            return 0, applied + ["max_notional"]
        lots = int(math.floor(max_notional / per_lot_notional))
        applied.append("max_notional")
        units = lots * lot_size
        notional = units * entry * multiplier

    if max_position_pct is not None and max_position_pct > 0 and capital > 0:
        cap_notional = capital * (max_position_pct / 100.0)
        if notional > cap_notional:
            per_lot_notional = lot_size * entry * multiplier
            if per_lot_notional <= 0:
                return 0, applied + ["max_position_pct"]
            lots = int(math.floor(cap_notional / per_lot_notional))
            applied.append("max_position_pct")
            units = lots * lot_size
            notional = units * entry * multiplier

    if max_total_exposure_pct is not None and max_total_exposure_pct > 0 and capital > 0:
        remaining = capital * (max_total_exposure_pct / 100.0) - open_exposure_notional
        if remaining <= 0:
            return 0, applied + ["max_total_exposure_pct_exhausted"]
        if notional > remaining:
            per_lot_notional = lot_size * entry * multiplier
            if per_lot_notional <= 0:
                return 0, applied + ["max_total_exposure_pct"]
            lots = int(math.floor(remaining / per_lot_notional))
            applied.append("max_total_exposure_pct")
            units = lots * lot_size
            notional = units * entry * multiplier

    if margin_per_lot is not None and margin_per_lot > 0 and capital > 0:
        affordable = int(math.floor(capital / margin_per_lot))
        if lots > affordable:
            lots = max(0, affordable)
            applied.append("margin_capital")

    return max(0, lots), applied


def calculate_size(
    *,
    capital: float,
    risk_pct: float,
    entry: float,
    stop: Optional[float] = None,
    direction: Direction = "LONG",
    instrument_kind: str = "EQ",
    symbol: str = "",
    lot_size: Optional[int] = None,
    multiplier: Optional[float] = None,
    lot_size_verified: bool = False,
    contract_mapping_verified: bool = False,
    contract_source: str = "unverified",
    expiry: Optional[str] = None,
    underlying: Optional[str] = None,
    option_right: Optional[str] = None,
    fixed_costs: float = 0.0,
    cost_per_unit: float = 0.0,
    cost_per_lot: float = 0.0,
    round_trip_cost_pct: float = 0.0,
    max_position_pct: Optional[float] = None,
    max_notional: Optional[float] = None,
    max_lots: Optional[int] = None,
    max_total_exposure_pct: Optional[float] = None,
    open_exposure_notional: float = 0.0,
    margin_per_lot: Optional[float] = None,
    margin_verified: bool = False,
    option_premium: Optional[float] = None,
    quote_stale: bool = False,
    mapping_stale: bool = False,
) -> dict[str, Any]:
    """
    Fixed-fractional risk sizing with lot rounding and exposure caps.

    Returns ``available=True`` and a size block only when all required inputs
    are present and verified; otherwise ``available=False`` with blockers.
    """
    capital = _f(capital)
    risk_pct = _f(risk_pct)
    entry = _f(entry)
    stop_v = None if stop is None else _f(stop)
    fixed_costs = max(0.0, _f(fixed_costs))
    cost_per_unit = max(0.0, _f(cost_per_unit))
    cost_per_lot = max(0.0, _f(cost_per_lot))
    round_trip_cost_pct = max(0.0, _f(round_trip_cost_pct))
    direction = "SHORT" if str(direction).upper() == "SHORT" else "LONG"

    inputs = {
        "capital": capital,
        "risk_pct": risk_pct,
        "entry": entry,
        "stop": stop_v,
        "direction": direction,
        "fixed_costs": fixed_costs,
        "cost_per_unit": cost_per_unit,
        "cost_per_lot": cost_per_lot,
        "round_trip_cost_pct": round_trip_cost_pct,
        "max_position_pct": max_position_pct,
        "max_notional": max_notional,
        "max_lots": max_lots,
        "max_total_exposure_pct": max_total_exposure_pct,
        "open_exposure_notional": open_exposure_notional,
        "margin_per_lot": margin_per_lot,
        "margin_verified": margin_verified,
        "option_premium": option_premium,
        "quote_stale": quote_stale,
        "mapping_stale": mapping_stale,
    }

    contract = resolve_contract(
        instrument_kind=instrument_kind,
        symbol=symbol,
        lot_size=lot_size,
        multiplier=multiplier,
        lot_size_verified=lot_size_verified,
        contract_mapping_verified=contract_mapping_verified,
        source=contract_source,
        expiry=expiry,
        underlying=underlying,
        option_right=option_right,
        quote_stale=quote_stale,
        mapping_stale=mapping_stale,
    )

    blockers = list(contract.get("blockers") or [])
    assumptions = list(contract.get("assumptions") or [])
    assumptions.append(
        "Fixed-fractional risk (Van Tharp-style): risk a configured % of capital per idea."
    )
    assumptions.append(
        "Size is research math only — not an order ticket and not broker-confirmed."
    )

    if capital <= 0:
        blockers.append("capital_missing_or_invalid")
    if risk_pct <= 0:
        blockers.append("risk_pct_missing_or_invalid")
    if entry <= 0:
        blockers.append("entry_missing_or_invalid")

    kind = contract["instrument_kind"]

    # --- Kind-specific required inputs ---
    if kind == "EQ":
        if stop_v is None:
            blockers.append("stop_missing")
        elif stop_v <= 0:
            blockers.append("stop_invalid")
        elif direction == "LONG" and stop_v >= entry:
            blockers.append("stop_not_below_entry_for_long")
        elif direction == "SHORT" and stop_v <= entry:
            blockers.append("stop_not_above_entry_for_short")
        # CNC equity does not require broker margin for this research calc.
        assumptions.append("Cash equity sizing does not apply futures-style margin.")

    elif kind == "FUT":
        if stop_v is None:
            blockers.append("stop_missing")
        elif stop_v <= 0:
            blockers.append("stop_invalid")
        elif direction == "LONG" and stop_v >= entry:
            blockers.append("stop_not_below_entry_for_long")
        elif direction == "SHORT" and stop_v <= entry:
            blockers.append("stop_not_above_entry_for_short")
        if margin_per_lot is None or _f(margin_per_lot) <= 0:
            blockers.append("margin_per_lot_missing")
        elif not margin_verified:
            blockers.append("margin_unverified")

    elif kind == "OPT":
        prem = _f(option_premium) if option_premium is not None else entry
        if prem <= 0:
            blockers.append("option_premium_missing_or_invalid")
        else:
            entry = prem  # size against premium
            inputs["entry"] = entry
            assumptions.append(
                "Options sizing uses verified premium as entry; multiplier × lot applied."
            )
        if direction == "SHORT":
            if margin_per_lot is None or _f(margin_per_lot) <= 0:
                blockers.append("margin_per_lot_missing")
            elif not margin_verified:
                blockers.append("margin_unverified")
            if stop_v is None:
                blockers.append("stop_missing")
            assumptions.append(
                "Short options require verified margin; stop is on premium."
            )
        else:
            # Long options: full premium is max loss if no stop; stop optional tighter.
            if stop_v is not None:
                if stop_v < 0:
                    blockers.append("stop_invalid")
                elif stop_v >= entry:
                    blockers.append("stop_not_below_premium_for_long_option")
            else:
                assumptions.append(
                    "Long option with no stop: risk per unit = full premium (max loss)."
                )
            assumptions.append("Long option does not require futures-style margin here.")

    # Deduplicate blockers while preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for b in blockers:
        if b not in seen:
            seen.add(b)
            uniq.append(b)
    blockers = uniq

    if blockers or not contract.get("verified"):
        if not contract.get("verified") and "contract_mapping_unverified" not in blockers:
            if kind not in ("MCX_PROXY", "UNKNOWN") and "lot_size_unverified" not in blockers:
                if "lot_size_missing" not in blockers and "multiplier_missing" not in blockers:
                    blockers.append("contract_unverified")
        return _unavailable(
            blockers or ["contract_unverified"],
            assumptions=assumptions,
            contract=contract,
            inputs=inputs,
        )

    lot = int(contract["lot_size"])
    mult = float(contract["multiplier"])
    risk_budget = capital * (risk_pct / 100.0) - fixed_costs
    if risk_budget <= 0:
        return _unavailable(
            ["risk_budget_non_positive_after_costs"],
            assumptions=assumptions,
            contract=contract,
            inputs=inputs,
        )

    # Per-unit / per-lot risk
    price_risk = abs(entry - (stop_v if stop_v is not None else 0.0))
    if kind == "OPT" and direction == "LONG" and stop_v is None:
        price_risk = entry  # full premium

    rt_per_unit = entry * (round_trip_cost_pct / 100.0) if round_trip_cost_pct else 0.0
    per_unit_risk = price_risk * mult + cost_per_unit + rt_per_unit
    per_lot_risk = per_unit_risk * lot + cost_per_lot

    if per_lot_risk <= 0:
        return _unavailable(
            ["per_lot_risk_non_positive"],
            assumptions=assumptions,
            contract=contract,
            inputs=inputs,
        )

    raw_lots = int(math.floor(risk_budget / per_lot_risk))
    margin_for_cap = (
        float(margin_per_lot)
        if margin_per_lot is not None and margin_verified and _f(margin_per_lot) > 0
        else None
    )
    # FUT / short OPT always passed verified margin above; use it for capital affordability.
    if kind == "FUT" or (kind == "OPT" and direction == "SHORT"):
        margin_for_cap = float(margin_per_lot)  # type: ignore[arg-type]

    lots, caps_applied = _apply_caps(
        lots=raw_lots,
        lot_size=lot,
        entry=entry,
        multiplier=mult,
        capital=capital,
        max_position_pct=max_position_pct,
        max_notional=max_notional,
        max_lots=max_lots,
        open_exposure_notional=_f(open_exposure_notional),
        max_total_exposure_pct=max_total_exposure_pct,
        margin_per_lot=margin_for_cap,
    )

    units = lots * lot
    notional = round(units * entry * mult, 2)
    risk_rs = round(lots * per_lot_risk, 2)
    est_costs = round(
        fixed_costs
        + units * cost_per_unit
        + lots * cost_per_lot
        + units * rt_per_unit,
        2,
    )

    formula_detail = (
        f"risk_budget = {capital:.2f} × ({risk_pct}/100) − {fixed_costs:.2f} "
        f"= {risk_budget:.2f}; "
        f"per_lot_risk = (|{entry} − {stop_v if stop_v is not None else 'premium'}| "
        f"× multiplier {mult} + unit_costs) × lot {lot} + lot_costs = {per_lot_risk:.4f}; "
        f"lots = floor({risk_budget:.2f} / {per_lot_risk:.4f}) = {raw_lots}, "
        f"after caps = {lots}."
    )

    size = {
        "lots": lots,
        "units": units,
        "shares": units if kind == "EQ" else None,
        "lot_size": lot,
        "multiplier": mult,
        "notional": notional,
        "risk_rs": risk_rs,
        "risk_budget": round(risk_budget, 2),
        "per_unit_risk": round(per_unit_risk, 6),
        "per_lot_risk": round(per_lot_risk, 6),
        "estimated_costs_in_sizing": est_costs,
        "raw_lots_before_caps": raw_lots,
        "caps_applied": caps_applied,
        "portfolio_risk_pct": round((risk_rs / capital) * 100.0, 4) if capital else 0.0,
        "portfolio_notional_pct": round((notional / capital) * 100.0, 4) if capital else 0.0,
    }

    if lots <= 0:
        assumptions.append(
            "Risk budget / caps yield zero lots after floor rounding — no fabricated size."
        )

    return {
        "available": True,
        "size": size,
        "blockers": [],
        "formula": FORMULA_FIXED_FRACTIONAL,
        "formula_detail": formula_detail,
        "assumptions": assumptions,
        "disclaimer": DISCLAIMER,
        "contract": contract,
        "inputs": inputs,
        "is_order_instruction": False,
    }
