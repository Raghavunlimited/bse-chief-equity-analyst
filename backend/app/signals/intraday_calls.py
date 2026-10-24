"""Intraday consultant calls — LONG→BUY, SHORT→SELL, FLAT→HOLD."""
from __future__ import annotations

from typing import Any

from app.config import config
from app.signals.consultant_rules import daily_brief, grade_intraday
from app.signals.enrichment import attach_enrichment
from app.signals.models import DISCLAIMER, make_call
from app.store import Database
from app.strategy.intraday import build_intraday_desk

INTRADAY_DISCLAIMER = (
    "Intraday research bias only — not investment advice. "
    "Tape is noisy; no signal guarantees profit. Prefer hard stops and "
    "size risk ~0.25–0.5% of capital per idea."
)


def build_intraday_calls(
    *,
    limit: int = 20,
    enrich: bool = True,
    enrich_top_n: int = 6,
) -> dict[str, Any]:
    desk = build_intraday_desk(limit=limit)
    session = desk.get("session") or {}
    calls: list[dict[str, Any]] = []
    for s in desk.get("signals") or []:
        # Attach session so grade_intraday can discount off-hours residue
        graded_input = {**s, "session": session, "in_session": session.get("in_session")}
        g = grade_intraday(graded_input)
        thesis = str(g.get("reason") or s.get("thesis") or "")
        thesis = (
            thesis.replace("LONG bias", "BUY bias")
            .replace("SHORT bias", "SELL bias")
            .replace("FLAT bias", "HOLD bias")
        )
        calls.append(
            make_call(
                desk="intraday",
                symbol=str(s.get("symbol") or g.get("symbol") or ""),
                side=g["side"],
                confidence=g["confidence"],
                thesis=thesis,
                entry=s.get("price"),
                stop=s.get("stop"),
                targets={"t1": s["target"]} if s.get("target") is not None else {},
                tags=g.get("tags") or [],
                sources=["yahoo_5m", "intraday_desk"],
                horizon="intraday",
                ttl_hours=0.5,
                as_of=desk.get("as_of"),
                disclaimer=INTRADAY_DISCLAIMER,
                extras={
                    "change_pct": s.get("change_pct"),
                    "rsi_5m": s.get("rsi_5m"),
                    "raw_side": s.get("side"),
                    "score": s.get("score"),
                },
            )
        )

    if enrich and calls:
        # Top N BUY/SELL only — Screener rate limit; volume from local store
        db = Database(config.db_path)
        attach_enrichment(
            calls,
            db=db,
            top_n=enrich_top_n,
            sides=("BUY", "SELL"),
        )

    return {
        "desk": "intraday",
        "horizon": "daily",
        "session": session,
        "poll_seconds": desk.get("poll_seconds", 15),
        "as_of": desk.get("as_of"),
        "calls": calls,
        "brief": daily_brief(calls, []),
        "count": len(calls),
        "buy_count": sum(1 for c in calls if c["side"] == "BUY"),
        "sell_count": sum(1 for c in calls if c["side"] == "SELL"),
        "hold_count": sum(1 for c in calls if c["side"] == "HOLD"),
        "message": desk.get("message"),
        "disclaimer": desk.get("disclaimer") or INTRADAY_DISCLAIMER or DISCLAIMER,
    }
