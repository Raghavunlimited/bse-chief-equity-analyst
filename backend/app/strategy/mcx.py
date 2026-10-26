"""
Commodities research desk — global futures proxy (not exchange-listed MCX).

Feed: Yahoo continuous futures + USDINR FX. Prices are USD (or INR for FX).
Related MCX names are unvalidated hints only. No lot/margin/order instructions.
Expectancy gate: intentionally disabled (proxy data ≠ MCX strategy).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app import live_quotes
from app.market_types import LiveQuote
from app.strategy.mcx_instruments import INSTRUMENTS, public_catalog

# Back-compat alias for older imports / playbooks
COMMODITIES = [
    {
        "id": r["id"],
        "name": r["name"],
        "yahoo": r["yahoo"],
        "mcx_hint": (
            " / ".join(r["related_mcx_symbols"])
            if r["related_mcx_symbols"]
            else r.get("mcx_mapping_status", "")
        ),
        "unit": r["unit"],
        "group": r["group"],
    }
    for r in INSTRUMENTS
]

DESK_DISCLAIMER = (
    "Research only — not MCX advice and not order instructions. "
    "Quotes are global futures / FX proxies (usually USD), not INR MCX contracts. "
    "Related MCX names are unvalidated hints. Confirm contract, lot, tick, "
    "margin, and session with your broker. App does not size lots."
)


def _snap_to_dict(snap: LiveQuote | dict[str, Any] | None) -> dict[str, Any] | None:
    """Normalize LiveQuote or dict to a flat quote dict with ``price``."""
    if snap is None:
        return None
    if isinstance(snap, LiveQuote):
        d = snap.to_dict()
    elif isinstance(snap, dict):
        d = dict(snap)
    else:
        return None
    if d.get("price") is None and d.get("ltp") is not None:
        d["price"] = d["ltp"]
    return d


def _bias(snap: dict[str, Any]) -> dict[str, Any]:
    """Directional bias on the *proxy* tape (USD continuous), not MCX INR."""
    price = snap.get("price")
    change = snap.get("change_pct")
    high = snap.get("session_high")
    low = snap.get("session_low")
    opens = snap.get("session_open")
    closes = list(snap.get("closes_5m") or [])
    feed_status = snap.get("feed_status") or snap.get("market_data_state")

    if price is None or feed_status in ("ERROR", "UNAVAILABLE"):
        return {
            "side": "FLAT",
            "score": 0.0,
            "tags": ["NO_QUOTE", "FEED_ERROR"],
            "stop": None,
            "target": None,
            "change_pct": change,
            "price": None,
            "available": False,
        }

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

    if len(closes) >= 10 and closes[-10]:
        mom = (closes[-1] / closes[-10] - 1.0) * 100.0
        score += max(-10.0, min(10.0, mom * 3.0))
        tags.append("MOM_UP" if mom > 0 else "MOM_DOWN")

    score = round(max(0.0, min(100.0, score)), 1)
    if score >= 60:
        side = "LONG"
    elif score <= 40:
        side = "SHORT"
    else:
        side = "FLAT"

    # Stops/targets are % on the *proxy* price — not MCX tick stops
    stop = target = None
    if side == "LONG" and price:
        stop = round(float(price) * 0.992, 4)
        target = round(float(price) * 1.008, 4)
    elif side == "SHORT" and price:
        stop = round(float(price) * 1.008, 4)
        target = round(float(price) * 0.992, 4)

    tags = list(dict.fromkeys([*tags, "PROXY_TAPE", "NOT_MCX_CONTRACT"]))
    return {
        "side": side,
        "score": score,
        "tags": tags,
        "stop": stop,
        "target": target,
        "change_pct": change,
        "price": float(price) if price is not None else None,
        "available": True,
    }


def _instrument_public(inst: dict[str, Any]) -> dict[str, Any]:
    related = list(inst.get("related_mcx_symbols") or [])
    return {
        "id": inst["id"],
        "name": inst["name"],
        "yahoo": inst["yahoo"],
        "yahoo_symbol": inst["yahoo"],
        "instrument_class": inst["instrument_class"],
        "is_mcx_listed": False,
        "provider": inst["provider"],
        "venue_proxy": inst["venue_proxy"],
        "currency": inst["currency"],
        "unit": inst["unit"],
        "price_scale": inst["price_scale"],
        "price_kind": inst["price_kind"],
        "related_mcx_symbols": related,
        "mcx_hint": (
            f"Related MCX names (unvalidated): {' / '.join(related)}"
            if related
            else "FX context only — not an MCX commodity"
        ),
        "mcx_mapping_status": inst["mcx_mapping_status"],
        "quote_hours_note": inst["quote_hours_note"],
        "expiry_note": inst["expiry_note"],
        "roll_note": inst["roll_note"],
        "lot_sizing": inst["lot_sizing"],
        "group": inst["group"],
        "display_label": (
            "GLOBAL FUTURES PROXY"
            if inst["instrument_class"] == "global_futures_proxy"
            else "FX CONTEXT"
        ),
        "expectancy_eligible": False,
        "expectancy_note": (
            "No expectancy / STRONG gate — proxy tape and costs are not "
            "MCX-contract walk-forward."
        ),
    }


def build_mcx_desk() -> dict[str, Any]:
    snaps = live_quotes.fetch_many([c["yahoo"] for c in INSTRUMENTS])
    rows: list[dict[str, Any]] = []

    for inst in INSTRUMENTS:
        meta = _instrument_public(inst)
        raw = snaps.get(inst["yahoo"])
        snap = _snap_to_dict(raw)
        if not snap or snap.get("price") is None:
            rows.append(
                {
                    **meta,
                    "side": "FLAT",
                    "score": 0,
                    "thesis": (
                        f"{meta['display_label']}: quote unavailable "
                        f"({inst['yahoo']}) — research tape offline"
                    ),
                    "price": None,
                    "tags": ["NO_QUOTE", "PROXY_UNAVAILABLE", "NOT_MCX_CONTRACT"],
                    "available": False,
                    "stop": None,
                    "target": None,
                    "change_pct": None,
                    "feed_status": (snap or {}).get("feed_status") or "UNAVAILABLE",
                    "market_data_state": (snap or {}).get("market_data_state"),
                    "quote_source": (snap or {}).get("source") or "yahoo_chart",
                }
            )
            continue

        bias = _bias(snap)
        # Enforce registry currency/unit — never inherit a misleading INR from feed
        currency = meta["currency"]
        scale = float(meta["price_scale"] or 1.0)
        px = bias["price"]
        if px is not None and scale != 1.0:
            px = round(float(px) * scale, 6)
            bias["price"] = px
            if bias.get("stop") is not None:
                bias["stop"] = round(float(bias["stop"]) * scale, 6)
            if bias.get("target") is not None:
                bias["target"] = round(float(bias["target"]) * scale, 6)

        chg = bias.get("change_pct")
        thesis = (
            f"{bias['side']} bias on {meta['display_label']} · {meta['name']} "
            f"@ {px} {meta['unit']}"
            + (f" ({chg:+.2f}%)" if chg is not None else "")
            + " — not an INR MCX contract"
        )
        rows.append(
            {
                **meta,
                **bias,
                "thesis": thesis,
                "currency": currency,
                "exchange": snap.get("exchange") or meta["venue_proxy"],
                "session_high": snap.get("session_high"),
                "session_low": snap.get("session_low"),
                "feed_status": snap.get("feed_status"),
                "market_data_state": snap.get("market_data_state"),
                "quote_source": snap.get("source") or "yahoo_chart",
                "quote_age_sec": snap.get("age_sec"),
                "is_current_live": False,  # never broker MCX LIVE
                "provenance": "fallback",
                "provider_class": "research_fallback",
            }
        )

    rows.sort(key=lambda r: float(r.get("score") or 0), reverse=True)
    actionable = [
        r
        for r in rows
        if r.get("side") in ("LONG", "SHORT")
        and r.get("id") != "USDINR"
        and r.get("available", True)
    ]

    return {
        "desk": "mcx",
        "desk_mode": "global_futures_proxy_research",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "poll_seconds": 15,
        "count": len(rows),
        "signals": rows,
        "actionable": actionable,
        "instrument_catalog": public_catalog(),
        "expectancy_gated": False,
        "expectancy_note": (
            "Expectancy / STRONG badges disabled for this desk — "
            "data is a global proxy, not MCX contract walk-forward."
        ),
        "message": (
            "Global futures / FX research tape (Yahoo). Not exchange-listed "
            "MCX INR contracts. Related MCX names are unvalidated hints only. "
            "No lot sizing or order instructions."
        ),
        "disclaimer": DESK_DISCLAIMER,
    }
