"""MCX consultant calls — LONG→BUY, SHORT→SELL, FLAT→HOLD."""
from __future__ import annotations

from typing import Any

from app.signals.consultant_rules import grade_mcx
from app.signals.models import DISCLAIMER, make_call
from app.strategy.mcx import build_mcx_desk

MCX_DISCLAIMER = (
    "Commodities research only — not MCX advice. Global futures are a directional "
    "proxy; confirm front-month contract, lot size, and margin with your broker. "
    "Leveraged products can gap; no return guarantee."
)


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
        calls.append(
            make_call(
                desk="mcx",
                symbol=str(sym),
                side=g["side"],
                confidence=g["confidence"],
                thesis=thesis,
                entry=s.get("price"),
                stop=s.get("stop"),
                targets={"t1": s["target"]} if s.get("target") is not None else {},
                tags=g.get("tags") or [],
                sources=["yahoo_futures", "mcx_proxy"],
                horizon="intraday",
                ttl_hours=0.5,
                as_of=desk.get("as_of"),
                disclaimer=MCX_DISCLAIMER,
                extras={
                    "name": s.get("name"),
                    "mcx_hint": s.get("mcx_hint"),
                    "unit": s.get("unit"),
                    "group": s.get("group"),
                    "change_pct": s.get("change_pct"),
                    "raw_side": s.get("side"),
                    "score": s.get("score"),
                },
            )
        )

    actionable = [c for c in calls if c["side"] in ("BUY", "SELL") and c["symbol"] != "USDINR"]
    return {
        "desk": "mcx",
        "horizon": "daily",
        "poll_seconds": desk.get("poll_seconds", 15),
        "as_of": desk.get("as_of"),
        "calls": calls,
        "actionable": actionable,
        "count": len(calls),
        "buy_count": sum(1 for c in calls if c["side"] == "BUY"),
        "sell_count": sum(1 for c in calls if c["side"] == "SELL"),
        "hold_count": sum(1 for c in calls if c["side"] == "HOLD"),
        "message": desk.get("message"),
        "disclaimer": desk.get("disclaimer") or MCX_DISCLAIMER or DISCLAIMER,
    }
