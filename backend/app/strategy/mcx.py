"""
MCX / commodities desk — research signals on major metals & energy.

Uses global futures (Yahoo) as a liquid proxy for Indian commodity direction
(Gold, Silver, Crude, NatGas, Copper). INR spot FX shown for context.
Not a substitute for MCX contract specs / margins / lot sizes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app import live_quotes

# Display name → Yahoo futures / FX
COMMODITIES: list[dict[str, str]] = [
    {
        "id": "GOLD",
        "name": "Gold",
        "yahoo": "GC=F",
        "mcx_hint": "GOLD / GOLDM",
        "unit": "USD/oz",
        "group": "metals",
    },
    {
        "id": "SILVER",
        "name": "Silver",
        "yahoo": "SI=F",
        "mcx_hint": "SILVER / SILVERM",
        "unit": "USD/oz",
        "group": "metals",
    },
    {
        "id": "CRUDE",
        "name": "Crude Oil",
        "yahoo": "CL=F",
        "mcx_hint": "CRUDEOIL / CRUDEOILM",
        "unit": "USD/bbl",
        "group": "energy",
    },
    {
        "id": "NATGAS",
        "name": "Natural Gas",
        "yahoo": "NG=F",
        "mcx_hint": "NATURALGAS",
        "unit": "USD/mmBtu",
        "group": "energy",
    },
    {
        "id": "COPPER",
        "name": "Copper",
        "yahoo": "HG=F",
        "mcx_hint": "COPPER",
        "unit": "USD/lb",
        "group": "metals",
    },
    {
        "id": "USDINR",
        "name": "USD / INR",
        "yahoo": "INR=X",
        "mcx_hint": "FX context for MCX INR pricing",
        "unit": "INR per USD",
        "group": "fx",
    },
]


def _bias(snap: dict[str, Any]) -> dict[str, Any]:
    price = snap.get("price")
    change = snap.get("change_pct")
    high = snap.get("session_high")
    low = snap.get("session_low")
    opens = snap.get("session_open")
    closes = list(snap.get("closes_5m") or [])

    score = 50.0
    tags: list[str] = []
    if change is not None:
        score += max(-18.0, min(18.0, float(change) * 4.0))
        if change >= 1.0:
            tags.append("TREND_UP")
        elif change <= -1.0:
            tags.append("TREND_DOWN")

    if opens and price:
        day = (float(price) / float(opens) - 1.0) * 100.0
        score += max(-8.0, min(8.0, day * 2.0))

    if high and low and high > low and price:
        loc = (float(price) - float(low)) / (float(high) - float(low))
        if loc > 0.8:
            tags.append("RANGE_HIGH")
            score += 5
        elif loc < 0.2:
            tags.append("RANGE_LOW")
            score -= 5

    if len(closes) >= 10:
        mom = (closes[-1] / closes[-10] - 1.0) * 100.0 if closes[-10] else 0.0
        score += max(-10.0, min(10.0, mom * 3.0))
        tags.append("MOM_UP" if mom > 0 else "MOM_DOWN")

    score = round(max(0.0, min(100.0, score)), 1)
    if score >= 60:
        side = "LONG"
    elif score <= 40:
        side = "SHORT"
    else:
        side = "FLAT"

    stop = target = None
    if side == "LONG" and price:
        stop = round(float(price) * 0.992, 4)
        target = round(float(price) * 1.008, 4)
    elif side == "SHORT" and price:
        stop = round(float(price) * 1.008, 4)
        target = round(float(price) * 0.992, 4)

    return {
        "side": side,
        "score": score,
        "tags": tags,
        "stop": stop,
        "target": target,
        "change_pct": change,
        "price": price,
    }


def build_mcx_desk() -> dict[str, Any]:
    snaps = live_quotes.fetch_many([c["yahoo"] for c in COMMODITIES])
    rows: list[dict[str, Any]] = []
    for c in COMMODITIES:
        snap = snaps.get(c["yahoo"])
        if not snap:
            rows.append(
                {
                    **c,
                    "side": "FLAT",
                    "score": 0,
                    "thesis": "Quote unavailable",
                    "price": None,
                    "tags": ["NO_QUOTE"],
                }
            )
            continue
        bias = _bias(snap)
        thesis = (
            f"{bias['side']} · {c['name']} @ {bias['price']} {c['unit']} "
            f"({bias['change_pct']:+.2f}%)" if bias.get("change_pct") is not None
            else f"{bias['side']} · {c['name']}"
        )
        rows.append(
            {
                **c,
                **bias,
                "thesis": thesis,
                "currency": snap.get("currency"),
                "exchange": snap.get("exchange"),
                "session_high": snap.get("session_high"),
                "session_low": snap.get("session_low"),
                "yahoo_symbol": c["yahoo"],
            }
        )

    rows.sort(key=lambda r: float(r.get("score") or 0), reverse=True)
    actionable = [r for r in rows if r.get("side") in ("LONG", "SHORT") and r.get("id") != "USDINR"]

    return {
        "desk": "mcx",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "poll_seconds": 15,
        "count": len(rows),
        "signals": rows,
        "actionable": actionable,
        "message": (
            "Global futures tape as directional research for MCX majors "
            "(Gold, Silver, Crude, NatGas, Copper) + USDINR context. "
            "Map to the front-month MCX contract yourself — lots/margins differ."
        ),
        "disclaimer": (
            "Commodities are leveraged and can gap. Research only — not MCX advice. "
            "Confirm contract, lot size, and margin with your broker before any order."
        ),
    }
