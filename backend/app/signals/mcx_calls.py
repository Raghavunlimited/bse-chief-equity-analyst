"""MCX consultant calls — proxy tape graded BUY/SELL/HOLD (not MCX lots)."""
from __future__ import annotations

from typing import Any

from app.signals.consultant_rules import grade_mcx
from app.signals.models import DISCLAIMER, make_call
from app.strategy.mcx import DESK_DISCLAIMER, build_mcx_desk

MCX_DISCLAIMER = DESK_DISCLAIMER

# Cap confidence — proxy research, no expectancy gate
_PROXY_CONF_CAP = 58.0


def build_mcx_calls() -> dict[str, Any]:
    desk = build_mcx_desk()
    calls: list[dict[str, Any]] = []
    for s in desk.get("signals") or []:
        g = grade_mcx(s)
        sym = s.get("id") or s.get("name") or g.get("symbol") or "UNKNOWN"
        thesis = str(g.get("reason") or s.get("thesis") or "")
        thesis = (
            thesis.replace("LONG ·", "BUY ·")
            .replace("SHORT ·", "SELL ·")
            .replace("FLAT ·", "HOLD ·")
        )
        conf = min(float(g.get("confidence") or 0), _PROXY_CONF_CAP)
        if not s.get("available", True):
            conf = min(conf, 25.0)

        tags = list(g.get("tags") or [])
        tags = list(
            dict.fromkeys(
                [
                    *tags,
                    "GLOBAL_FUTURES_PROXY",
                    "NOT_MCX_LISTED",
                    "NO_EXPECTANCY_GATE",
                    "RESEARCH_ONLY",
                ]
            )
        )
        if s.get("instrument_class") == "fx_context":
            tags = list(dict.fromkeys([*tags, "FX_CONTEXT"]))

        extras = {
            "name": s.get("name"),
            "mcx_hint": s.get("mcx_hint"),
            "unit": s.get("unit"),
            "group": s.get("group"),
            "change_pct": s.get("change_pct"),
            "raw_side": s.get("side"),
            "score": s.get("score"),
            "instrument_class": s.get("instrument_class"),
            "is_mcx_listed": False,
            "currency": s.get("currency"),
            "price_scale": s.get("price_scale"),
            "price_kind": s.get("price_kind"),
            "related_mcx_symbols": s.get("related_mcx_symbols"),
            "mcx_mapping_status": s.get("mcx_mapping_status"),
            "quote_hours_note": s.get("quote_hours_note"),
            "expiry_note": s.get("expiry_note"),
            "roll_note": s.get("roll_note"),
            "lot_sizing": s.get("lot_sizing"),
            "display_label": s.get("display_label"),
            "expectancy_eligible": False,
            "available": s.get("available", True),
            "yahoo_symbol": s.get("yahoo_symbol") or s.get("yahoo"),
        }

        call = make_call(
            desk="mcx",
            symbol=str(sym),
            side=g["side"],
            confidence=conf,
            thesis=thesis,
            entry=s.get("price"),
            stop=s.get("stop"),
            targets={"t1": s["target"]} if s.get("target") is not None else {},
            tags=tags,
            sources=["yahoo_futures_proxy", "not_mcx_listed"],
            horizon="intraday",
            ttl_hours=0.5,
            as_of=desk.get("as_of"),
            disclaimer=MCX_DISCLAIMER,
            extras=extras,
        )
        # Flatten key honesty fields for UI (SignalBoard reads top-level)
        call["mcx_hint"] = extras["mcx_hint"]
        call["unit"] = extras["unit"]
        call["currency"] = extras["currency"]
        call["display_label"] = extras["display_label"]
        call["instrument_class"] = extras["instrument_class"]
        call["is_mcx_listed"] = False
        call["badge"] = g["side"]  # never STRONG_*
        call["expectancy"] = {
            "available": False,
            "gated": False,
            "sample_size": 0,
            "proven": False,
            "status_label": "proxy_desk_no_expectancy",
            "disclaimer": desk.get("expectancy_note"),
            "gates": {
                "passed": False,
                "fail_reasons": ["MCX_PROXY_DESK_NO_WALKFORWARD"],
            },
        }
        calls.append(call)

    actionable = [
        c
        for c in calls
        if c["side"] in ("BUY", "SELL") and c["symbol"] != "USDINR"
    ]
    from app.signal_availability import attach_board_availability

    return attach_board_availability(
        {
            "desk": "mcx",
            "strategy": "mcx_proxy",
            "desk_mode": desk.get("desk_mode"),
            "horizon": "daily",
            "poll_seconds": desk.get("poll_seconds", 15),
            "as_of": desk.get("as_of"),
            "feed_health": desk.get("feed_health"),
            "live_calls_allowed": desk.get("live_calls_allowed"),
            "calls": calls,
            "actionable": actionable,
            "count": len(calls),
            "buy_count": sum(1 for c in calls if c["side"] == "BUY"),
            "sell_count": sum(1 for c in calls if c["side"] == "SELL"),
            "hold_count": sum(1 for c in calls if c["side"] == "HOLD"),
            "instrument_catalog": desk.get("instrument_catalog"),
            "expectancy_gated": False,
            "expectancy_note": desk.get("expectancy_note"),
            "message": desk.get("message"),
            "disclaimer": desk.get("disclaimer") or MCX_DISCLAIMER or DISCLAIMER,
        }
    )
