"""
MCX desk instrument registry — Phase 5 honesty layer.

This desk does **not** consume exchange-listed MCX INR contracts. Feed is
Yahoo Finance continuous global futures (and USDINR FX). Each row declares:

  instrument_class: global_futures_proxy | fx_context
  is_mcx_listed: False (always, until a verified MCX feed exists)
  related_mcx_symbols: informal names only — NOT a validated 1:1 mapping
  currency / unit / price_scale / quote_hours / roll_note

Never present these as INR MCX lots, ticks, or sized orders.
"""
from __future__ import annotations

from typing import Any, Literal

InstrumentClass = Literal["global_futures_proxy", "fx_context"]

# Continuous Yahoo futures — no discrete expiry on the feed we use.
# related_mcx_symbols are research hints only (local naming), not validated
# contract codes, lots, or tick values.
INSTRUMENTS: list[dict[str, Any]] = [
    {
        "id": "GOLD",
        "name": "Gold (COMEX continuous)",
        "yahoo": "GC=F",
        "instrument_class": "global_futures_proxy",
        "is_mcx_listed": False,
        "provider": "yahoo_chart",
        "venue_proxy": "COMEX",
        "currency": "USD",
        "unit": "USD per troy oz",
        "price_scale": 1.0,
        "price_kind": "continuous_futures_ltp",
        "related_mcx_symbols": ["GOLD", "GOLDM"],
        "mcx_mapping_status": "unvalidated_name_hint",
        "quote_hours_note": (
            "Near-24h US futures hours — not MCX INR session (typically "
            "~09:00–23:30 IST with breaks; verify with exchange)."
        ),
        "expiry_note": "Yahoo continuous contract — not a dated MCX expiry.",
        "roll_note": (
            "Continuous series rolls differ from MCX front-month; basis can "
            "diverge near expiry / inventory events."
        ),
        "lot_sizing": "unavailable — app does not compute MCX lots or margins",
        "group": "metals",
        "expectancy_eligible": False,
    },
    {
        "id": "SILVER",
        "name": "Silver (COMEX continuous)",
        "yahoo": "SI=F",
        "instrument_class": "global_futures_proxy",
        "is_mcx_listed": False,
        "provider": "yahoo_chart",
        "venue_proxy": "COMEX",
        "currency": "USD",
        "unit": "USD per troy oz",
        "price_scale": 1.0,
        "price_kind": "continuous_futures_ltp",
        "related_mcx_symbols": ["SILVER", "SILVERM"],
        "mcx_mapping_status": "unvalidated_name_hint",
        "quote_hours_note": (
            "Near-24h US futures hours — not MCX INR session."
        ),
        "expiry_note": "Yahoo continuous contract — not a dated MCX expiry.",
        "roll_note": "Continuous roll ≠ MCX front-month roll.",
        "lot_sizing": "unavailable — app does not compute MCX lots or margins",
        "group": "metals",
        "expectancy_eligible": False,
    },
    {
        "id": "CRUDE",
        "name": "Crude Oil (NYMEX continuous)",
        "yahoo": "CL=F",
        "instrument_class": "global_futures_proxy",
        "is_mcx_listed": False,
        "provider": "yahoo_chart",
        "venue_proxy": "NYMEX",
        "currency": "USD",
        "unit": "USD per barrel",
        "price_scale": 1.0,
        "price_kind": "continuous_futures_ltp",
        "related_mcx_symbols": ["CRUDEOIL", "CRUDEOILM"],
        "mcx_mapping_status": "unvalidated_name_hint",
        "quote_hours_note": (
            "Near-24h US futures hours — not MCX INR session."
        ),
        "expiry_note": "Yahoo continuous contract — not a dated MCX expiry.",
        "roll_note": "Continuous roll ≠ MCX front-month roll; energy basis can jump.",
        "lot_sizing": "unavailable — app does not compute MCX lots or margins",
        "group": "energy",
        "expectancy_eligible": False,
    },
    {
        "id": "NATGAS",
        "name": "Natural Gas (NYMEX continuous)",
        "yahoo": "NG=F",
        "instrument_class": "global_futures_proxy",
        "is_mcx_listed": False,
        "provider": "yahoo_chart",
        "venue_proxy": "NYMEX",
        "currency": "USD",
        "unit": "USD per mmBtu",
        "price_scale": 1.0,
        "price_kind": "continuous_futures_ltp",
        "related_mcx_symbols": ["NATURALGAS"],
        "mcx_mapping_status": "unvalidated_name_hint",
        "quote_hours_note": (
            "Near-24h US futures hours — not MCX INR session."
        ),
        "expiry_note": "Yahoo continuous contract — not a dated MCX expiry.",
        "roll_note": "Continuous roll ≠ MCX front-month roll.",
        "lot_sizing": "unavailable — app does not compute MCX lots or margins",
        "group": "energy",
        "expectancy_eligible": False,
    },
    {
        "id": "COPPER",
        "name": "Copper (COMEX continuous)",
        "yahoo": "HG=F",
        "instrument_class": "global_futures_proxy",
        "is_mcx_listed": False,
        "provider": "yahoo_chart",
        "venue_proxy": "COMEX",
        "currency": "USD",
        "unit": "USD per lb",
        "price_scale": 1.0,
        "price_kind": "continuous_futures_ltp",
        "related_mcx_symbols": ["COPPER"],
        "mcx_mapping_status": "unvalidated_name_hint",
        "quote_hours_note": (
            "Near-24h US futures hours — not MCX INR session."
        ),
        "expiry_note": "Yahoo continuous contract — not a dated MCX expiry.",
        "roll_note": "Continuous roll ≠ MCX front-month roll.",
        "lot_sizing": "unavailable — app does not compute MCX lots or margins",
        "group": "metals",
        "expectancy_eligible": False,
    },
    {
        "id": "USDINR",
        "name": "USD / INR (FX context)",
        "yahoo": "INR=X",
        "instrument_class": "fx_context",
        "is_mcx_listed": False,
        "provider": "yahoo_chart",
        "venue_proxy": "FX",
        "currency": "INR",
        "unit": "INR per 1 USD",
        "price_scale": 1.0,
        "price_kind": "fx_spot_proxy",
        "related_mcx_symbols": [],
        "mcx_mapping_status": "fx_context_only",
        "quote_hours_note": "FX prints nearly continuously; not an MCX commodity session.",
        "expiry_note": "Spot FX proxy — no futures expiry on this row.",
        "roll_note": "N/A — FX context for interpreting USD commodity moves in INR terms.",
        "lot_sizing": "unavailable — not a commodity contract",
        "group": "fx",
        "expectancy_eligible": False,
    },
]


def get_instrument(instrument_id: str) -> dict[str, Any] | None:
    iid = str(instrument_id or "").upper().strip()
    for row in INSTRUMENTS:
        if row["id"] == iid:
            return dict(row)
    return None


def public_catalog() -> list[dict[str, Any]]:
    """API-safe catalog (no secrets)."""
    out = []
    for row in INSTRUMENTS:
        out.append(
            {
                "id": row["id"],
                "name": row["name"],
                "yahoo": row["yahoo"],
                "instrument_class": row["instrument_class"],
                "is_mcx_listed": False,
                "currency": row["currency"],
                "unit": row["unit"],
                "price_scale": row["price_scale"],
                "price_kind": row["price_kind"],
                "related_mcx_symbols": list(row["related_mcx_symbols"]),
                "mcx_mapping_status": row["mcx_mapping_status"],
                "quote_hours_note": row["quote_hours_note"],
                "expiry_note": row["expiry_note"],
                "roll_note": row["roll_note"],
                "lot_sizing": row["lot_sizing"],
                "group": row["group"],
                "expectancy_eligible": False,
                "display_label": (
                    "GLOBAL FUTURES PROXY"
                    if row["instrument_class"] == "global_futures_proxy"
                    else "FX CONTEXT"
                ),
            }
        )
    return out


def assert_no_false_mcx_claims(payload: dict[str, Any]) -> list[str]:
    """Return list of honesty violations (empty = ok). Used in tests."""
    fails: list[str] = []
    if payload.get("is_mcx_listed") is True:
        fails.append("is_mcx_listed_true_without_verified_feed")
    if payload.get("instrument_class") == "mcx_listed":
        fails.append("instrument_class_mcx_listed_not_supported")
    cur = str(payload.get("currency") or "").upper()
    unit = str(payload.get("unit") or "").upper()
    if payload.get("instrument_class") == "global_futures_proxy":
        if cur == "INR" and "INR" in unit and "USD" not in unit:
            fails.append("proxy_presented_as_inr_commodity_unit")
        if payload.get("lot_size") or payload.get("suggested_lots"):
            fails.append("proxy_has_lot_sizing")
    return fails
