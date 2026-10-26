"""Index consultant calls — NIFTY + BANKNIFTY BUY/SELL/HOLD."""
from __future__ import annotations

from typing import Any

from app.signals.models import make_call
from app.strategy.index_desk import build_index_desk

INDEX_DISCLAIMER = (
    "Index research bias only — not investment advice. "
    "Nifty / BankNifty F&O is leveraged; size risk yourself. "
    "PCR / Call-Put walls apply only when Kotak option chain is live."
)


def build_index_calls() -> dict[str, Any]:
    desk = build_index_desk()
    session = desk.get("session") or {}
    in_session = bool(session.get("in_session"))
    calls: list[dict[str, Any]] = []
    for s in desk.get("signals") or []:
        side = str(s.get("side") or "HOLD").upper()
        if side not in ("BUY", "SELL", "HOLD"):
            side = "HOLD"
        conf = float(s.get("confidence") or 50)
        tags = list(s.get("tags") or [])
        if in_session:
            tags = list(dict.fromkeys([*tags, "IN_SESSION"]))
        else:
            conf = min(conf, 52.0)
            tags = list(dict.fromkeys([*tags, "OFF_SESSION", "RESIDUE"]))
        call = make_call(
            desk="index",
            symbol=str(s.get("symbol") or ""),
            side=side,
            confidence=conf,
            thesis=str(s.get("thesis") or ""),
            entry=s.get("price"),
            stop=s.get("stop"),
            targets={"t1": s["target"]} if s.get("target") is not None else {},
            tags=list(dict.fromkeys([*tags, "INDEX"])),
            sources=["yahoo_5m", "index_mtf_vwap_v1", "nifty_regime"],
            horizon="intraday",
            ttl_hours=0.35,
            as_of=desk.get("as_of"),
            disclaimer=INDEX_DISCLAIMER,
            extras={
                "label": s.get("label"),
                "change_pct": s.get("change_pct"),
                "vwap": s.get("vwap"),
                "ema9": s.get("ema9"),
                "ema21": s.get("ema21"),
                "rsi_5m": s.get("rsi_5m"),
                "daily": s.get("daily"),
                "rel_vs_nifty_pct": s.get("rel_vs_nifty_pct"),
                "lot_hint": s.get("lot_hint"),
                "strategy": desk.get("strategy"),
                "score": s.get("score"),
                "option_chain": s.get("option_chain"),
            },
        )
        call["market_data_state"] = s.get("market_data_state") or s.get("feed_status")
        call["quote_source"] = s.get("quote_source") or s.get("source")
        call["quote_age_sec"] = s.get("quote_age_sec") or s.get("age_sec")
        call["is_current_live"] = s.get("is_current_live") is True
        call["is_last_observation"] = s.get("is_last_observation") is True
        call["signal_generation"] = s.get("signal_generation")
        if s.get("observation"):
            call["observation"] = s.get("observation")
        calls.append(call)

    from app.config import config
    from app.expectancy.gate import gate_calls
    from app.store import Database

    db = Database(config.db_path)
    as_of = desk.get("as_of")
    if isinstance(as_of, str) and "T" in as_of:
        as_of_day = as_of[:10]
    else:
        as_of_day = as_of if isinstance(as_of, str) else None
    calls, exp_regime = gate_calls(
        calls, db=db, desk="index", as_of=as_of_day, auto_refresh=True
    )

    from app.signal_availability import attach_board_availability

    return attach_board_availability(
        {
            "desk": "index",
            "horizon": desk.get("horizon"),
            "strategy": desk.get("strategy") or "index_desk",
            "strategy_notes": desk.get("strategy_notes"),
            "session": session,
            "feed_health": desk.get("feed_health"),
            "live_calls_allowed": desk.get("live_calls_allowed"),
            "poll_seconds": desk.get("poll_seconds", 20),
            "as_of": desk.get("as_of"),
            "relative_bn_vs_nifty_pct": desk.get("relative_bn_vs_nifty_pct"),
            "option_chains": desk.get("option_chains") or {},
            "expectancy_regime": exp_regime,
            "calls": calls,
            "signals": calls,
            "count": len(calls),
            "buy_count": sum(1 for c in calls if c.get("side") == "BUY"),
            "sell_count": sum(1 for c in calls if c.get("side") == "SELL"),
            "hold_count": sum(1 for c in calls if c.get("side") == "HOLD"),
            "message": desk.get("message"),
            "brief": desk.get("message"),
            "disclaimer": INDEX_DISCLAIMER,
        }
    )
