"""
Realistic NSE India equity transaction costs + slippage.

Delivery (CNC) round-trip model — percentages of traded value unless noted.
No fake flat “0.15%” black box: each leg is explicit and auditable.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

Side = Literal["BUY", "SELL"]


@dataclass(frozen=True)
class IndiaCostAssumptions:
    """Discount-broker style CNC equity assumptions (NSE)."""

    brokerage_pct: float = 0.0003  # 0.03% of turnover per order
    brokerage_flat_cap: float = 20.0  # ₹20 cap per order (Zerodha-style)
    stt_sell_delivery_pct: float = 0.001  # 0.1% on sell side (delivery)
    exchange_txn_pct: float = 0.0000297  # ~0.00297% NSE per side
    sebi_turnover_pct: float = 0.000001  # ₹10/crore ≈ 0.0001%
    stamp_duty_buy_pct: float = 0.00015  # 0.015% on buy
    gst_rate: float = 0.18  # on (brokerage + exchange + sebi)
    slippage_pct_per_side: float = 0.0005  # 5 bps bid-ask / impact per side
    # Intraday (MIS) STT is lower on sell; we default delivery for swing
    stt_sell_intraday_pct: float = 0.00025  # 0.025% sell (futures-like; cash MIS ~0.025%)


DEFAULT_COSTS = IndiaCostAssumptions()


def _brokerage(notional: float, assumptions: IndiaCostAssumptions) -> float:
    pct_fee = abs(notional) * assumptions.brokerage_pct
    return min(pct_fee, assumptions.brokerage_flat_cap) if notional else 0.0


def leg_cost_inr(
    *,
    price: float,
    qty: float,
    side: Side,
    product: Literal["delivery", "intraday"] = "delivery",
    assumptions: IndiaCostAssumptions = DEFAULT_COSTS,
) -> dict[str, float]:
    """Absolute ₹ cost for one fill (excluding the share notional itself)."""
    notional = abs(float(price) * float(qty))
    brokerage = _brokerage(notional, assumptions)
    exchange = notional * assumptions.exchange_txn_pct
    sebi = notional * assumptions.sebi_turnover_pct
    stamp = notional * assumptions.stamp_duty_buy_pct if side == "BUY" else 0.0
    if side == "SELL":
        stt_pct = (
            assumptions.stt_sell_delivery_pct
            if product == "delivery"
            else assumptions.stt_sell_intraday_pct
        )
        stt = notional * stt_pct
    else:
        stt = 0.0
    taxable = brokerage + exchange + sebi
    gst = taxable * assumptions.gst_rate
    slippage = notional * assumptions.slippage_pct_per_side
    total = brokerage + exchange + sebi + stamp + stt + gst + slippage
    return {
        "notional": notional,
        "brokerage": brokerage,
        "exchange": exchange,
        "sebi": sebi,
        "stamp": stamp,
        "stt": stt,
        "gst": gst,
        "slippage": slippage,
        "total": total,
    }


def round_trip_cost_fraction(
    entry: float,
    exit: float,
    *,
    qty: float = 1.0,
    side: Side = "BUY",
    product: Literal["delivery", "intraday"] = "delivery",
    assumptions: IndiaCostAssumptions = DEFAULT_COSTS,
) -> dict[str, Any]:
    """
    Round-trip cost as a fraction of entry notional (for return/R math).

    Long: buy at entry, sell at exit.
    Short: sell at entry, buy at exit (intraday-style).
    """
    entry = float(entry)
    exit = float(exit)
    if entry <= 0 or qty <= 0:
        return {"cost_fraction": 0.0, "cost_inr": 0.0, "legs": {}}
    if side == "BUY":
        buy = leg_cost_inr(price=entry, qty=qty, side="BUY", product=product, assumptions=assumptions)
        sell = leg_cost_inr(price=exit, qty=qty, side="SELL", product=product, assumptions=assumptions)
    else:
        sell = leg_cost_inr(price=entry, qty=qty, side="SELL", product=product, assumptions=assumptions)
        buy = leg_cost_inr(price=exit, qty=qty, side="BUY", product=product, assumptions=assumptions)
    total = buy["total"] + sell["total"]
    entry_notional = abs(entry * qty)
    return {
        "cost_fraction": total / entry_notional if entry_notional else 0.0,
        "cost_inr": total,
        "legs": {"open": buy if side == "BUY" else sell, "close": sell if side == "BUY" else buy},
        "assumptions": asdict(assumptions),
    }


def net_return_pct(
    entry: float,
    exit: float,
    *,
    side: Side = "BUY",
    product: Literal["delivery", "intraday"] = "delivery",
    assumptions: IndiaCostAssumptions = DEFAULT_COSTS,
) -> float:
    """Percent return after full India round-trip costs + slippage."""
    if entry <= 0:
        return 0.0
    if side == "BUY":
        gross = (exit / entry - 1.0) * 100.0
    else:
        gross = (entry / exit - 1.0) * 100.0 if exit else 0.0
    costs = round_trip_cost_fraction(
        entry, exit, side=side, product=product, assumptions=assumptions
    )
    return gross - costs["cost_fraction"] * 100.0


def r_multiple(
    entry: float,
    exit: float,
    stop: float,
    *,
    side: Side = "BUY",
    product: Literal["delivery", "intraday"] = "delivery",
    assumptions: IndiaCostAssumptions = DEFAULT_COSTS,
) -> float | None:
    """PnL in R after costs. Risk = |entry − stop|."""
    risk = abs(float(entry) - float(stop))
    if risk < 1e-9:
        return None
    if side == "BUY":
        gross_pnl = float(exit) - float(entry)
    else:
        gross_pnl = float(entry) - float(exit)
    costs = round_trip_cost_fraction(
        entry, exit, side=side, product=product, assumptions=assumptions
    )
    # Convert cost ₹ (qty=1) into price units
    net_pnl = gross_pnl - costs["cost_inr"]
    return net_pnl / risk
