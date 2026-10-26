"""
Signal availability honesty — classify why a desk shows signals or not.

Does not change strategy thresholds, invent quotes, or publish ledger rows.
Research-only: never implies execution or guaranteed returns.
"""
from __future__ import annotations

from typing import Any, Optional

# Stable codes for API + UI
QUALIFYING = "qualifying"
NO_QUALIFYING = "no_qualifying"
DATA_BLOCKED = "data_blocked"
GATE_BLOCKED = "gate_blocked"
LEDGER_EMPTY = "ledger_empty"
LEDGER_DEMO_FILTERED = "ledger_demo_filtered"
LEDGER_HAS_ROWS = "ledger_has_published"

CATEGORY_DESK = {
    "swing": "swing",
    "intraday": "intraday",
    "commodity": "mcx",
}

STRATEGY_BY_DESK = {
    "swing": "weekly_swing",
    "intraday": "intraday_desk",
    "index": "index_desk",
    "mcx": "mcx_proxy",
}

_LABELS = {
    QUALIFYING: "Qualifying strategy signal(s)",
    NO_QUALIFYING: "No qualifying signal — strategy conditions not met",
    DATA_BLOCKED: "Signal evaluation blocked — data stale or unavailable",
    GATE_BLOCKED: "No actionable signal — insufficient history or expectancy/risk gates failed",
    LEDGER_EMPTY: "No published ledger signals for this desk",
    LEDGER_DEMO_FILTERED: "Legacy demo ledger rows are hidden",
    LEDGER_HAS_ROWS: "Published ledger signal(s)",
}

RESEARCH_BOUNDARY = (
    "Research only — not an order instruction and not a return guarantee."
)


def _upper(v: Any) -> str:
    return str(v or "").strip().upper()


def _side_actionable(side: Any) -> bool:
    return _upper(side) in ("BUY", "SELL", "LONG", "SHORT")


def _freshness_blocked(data_status: Optional[dict]) -> bool:
    if not isinstance(data_status, dict):
        return False
    st = _upper(data_status.get("status"))
    return st in ("STALE", "EMPTY", "ERROR", "UNAVAILABLE", "MISSING")


def _feed_blocked(board: dict[str, Any]) -> bool:
    fh = board.get("feed_health") or {}
    if isinstance(fh, dict):
        if fh.get("live_calls_allowed") is False:
            return True
        mds = _upper(fh.get("market_data_state") or fh.get("feed_status"))
        if mds in ("STALE", "UNAVAILABLE", "ERROR", "HALTED"):
            return True
    if board.get("live_calls_allowed") is False:
        return True
    status = str(board.get("status") or "").lower()
    if status in ("stale", "empty", "error"):
        return True
    return False


def _calls_list(board: dict[str, Any]) -> list[dict[str, Any]]:
    raw = board.get("calls") or board.get("signals") or []
    return [c for c in raw if isinstance(c, dict)]


def _gate_failure_dominant(calls: list[dict[str, Any]]) -> bool:
    """True when no BUY/SELL remain and expectancy marks insufficient/failed gates."""
    if any(_side_actionable(c.get("side")) for c in calls):
        return False
    saw_gate = False
    for c in calls:
        exp = c.get("expectancy")
        if not isinstance(exp, dict):
            continue
        if exp.get("insufficient_history") or exp.get("status_label") == "insufficient_5m_history":
            saw_gate = True
            continue
        gates = exp.get("gates")
        if isinstance(gates, dict) and gates.get("passed") is False:
            reasons = gates.get("fail_reasons") or []
            # Proxy-desk "no walkforward" alone is desk policy, not a failed qualifying path
            if reasons and reasons != ["MCX_PROXY_DESK_NO_WALKFORWARD"]:
                saw_gate = True
            elif "INSUFFICIENT_5M_HISTORY" in reasons or "PROXY" in "".join(map(str, reasons)).upper():
                saw_gate = True
    return saw_gate


def gate_result_for_call(call: dict[str, Any]) -> dict[str, Any]:
    """Normalize expectancy/gate fields for display."""
    exp = call.get("expectancy") if isinstance(call.get("expectancy"), dict) else {}
    gates = exp.get("gates") if isinstance(exp.get("gates"), dict) else {}
    insuff = bool(
        exp.get("insufficient_history")
        or exp.get("status_label") == "insufficient_5m_history"
    )
    passed = gates.get("passed")
    fail_reasons = list(gates.get("fail_reasons") or [])
    if insuff and "INSUFFICIENT_5M_HISTORY" not in fail_reasons:
        fail_reasons = [*fail_reasons, "INSUFFICIENT_5M_HISTORY"]
    if passed is True and not insuff:
        code = "gate_pass_research"
        label = "Gate pass (research — not proven edge)"
    elif insuff:
        code = "insufficient_history"
        label = "Insufficient history — STRONG / edge blocked"
    elif passed is False:
        code = "gate_failed"
        label = "Expectancy/risk gate failed"
    elif exp.get("proxy") or exp.get("status_label") == "proxy_desk_no_expectancy":
        code = "proxy_ungated"
        label = "Proxy desk — expectancy not gated"
    elif not exp:
        code = "gate_pending"
        label = "Gate metrics pending"
    else:
        code = "gate_n_a"
        label = "Gate not applicable"
    return {
        "code": code,
        "label": label,
        "passed": bool(passed) if passed is not None else None,
        "insufficient_history": insuff,
        "fail_reasons": fail_reasons,
        "status_label": exp.get("status_label"),
    }


def data_status_for_call(
    call: dict[str, Any],
    *,
    board: Optional[dict[str, Any]] = None,
) -> str:
    """LIVE | FALLBACK | EOD | STALE | DELAYED | UNAVAILABLE."""
    state = (
        call.get("market_data_state")
        or (call.get("observation") or {}).get("market_data_state")
        or call.get("feed_status")
        or call.get("data_status")
    )
    if state:
        u = _upper(state)
        if u in ("LIVE", "FALLBACK", "EOD", "STALE", "DELAYED", "UNAVAILABLE", "ERROR"):
            return "UNAVAILABLE" if u == "ERROR" else u
        if u in ("POST_MARKET", "PRE_MARKET", "WEEKEND", "HOLIDAY"):
            return "DELAYED"
    if call.get("is_current_live") is True:
        return "LIVE"
    if call.get("is_last_observation") or _upper(call.get("signal_generation")) == "HALTED":
        return "STALE"
    dm = str(call.get("data_mode") or "").lower()
    if dm in ("live", "fallback", "eod", "stale", "delayed"):
        return dm.upper() if dm != "fallback" else "FALLBACK"
    if board:
        fh = board.get("feed_health") or {}
        if isinstance(fh, dict):
            mds = _upper(fh.get("market_data_state") or fh.get("feed_status"))
            if mds:
                return mds if mds != "ERROR" else "UNAVAILABLE"
        ds = board.get("data_status")
        if isinstance(ds, dict) and ds.get("status"):
            st = _upper(ds.get("status"))
            if st == "FRESH" or st == "RECENT":
                return "EOD"
            if st in ("STALE", "EMPTY"):
                return "STALE" if st == "STALE" else "UNAVAILABLE"
    # Swing EOD default when desk is swing and no live flags
    desk = str(call.get("desk") or (board or {}).get("desk") or "").lower()
    if desk == "swing":
        return "EOD"
    return "DELAYED"


def annotate_call_display(
    call: dict[str, Any],
    *,
    board: Optional[dict[str, Any]] = None,
    desk: Optional[str] = None,
    strategy: Optional[str] = None,
) -> dict[str, Any]:
    """Attach display honesty fields; never flips side or invents prices."""
    out = dict(call)
    d = desk or out.get("desk") or (board or {}).get("desk") or "unknown"
    strat = (
        strategy
        or out.get("strategy")
        or (board or {}).get("strategy")
        or STRATEGY_BY_DESK.get(str(d).lower())
        or out.get("methodology_id")
        or "unspecified"
    )
    sources = out.get("sources")
    if isinstance(sources, list) and sources:
        data_source = ",".join(str(s) for s in sources[:3])
    else:
        data_source = (
            out.get("quote_source")
            or out.get("source")
            or ((out.get("provenance") or {}).get("source") if isinstance(out.get("provenance"), dict) else None)
            or "unknown"
        )
    ts = (
        out.get("as_of")
        or out.get("data_timestamp")
        or ((out.get("observation") or {}).get("as_of") if isinstance(out.get("observation"), dict) else None)
        or (board or {}).get("as_of")
    )
    status = data_status_for_call(out, board=board)
    gate = gate_result_for_call(out)
    # Stale / unavailable / halted must never look like a fresh actionable signal
    if status in ("STALE", "UNAVAILABLE") or _upper(out.get("signal_generation")) == "HALTED":
        if _side_actionable(out.get("side")):
            # Defensive: should already be frozen upstream; coerce for honesty
            out["side"] = "HOLD"
            if _upper(out.get("badge")) in ("BUY", "SELL", "STRONG_BUY", "STRONG_SELL"):
                out["badge"] = "HOLD"
    out["desk"] = d
    out["strategy"] = strat
    out["instrument"] = out.get("symbol") or out.get("instrument") or "—"
    out["direction"] = out.get("side") or out.get("direction") or "HOLD"
    out["data_source"] = data_source
    out["data_timestamp"] = ts
    out["data_status"] = status
    out["gate_result"] = gate
    out["research_only"] = True
    return out


def summarize_board_availability(board: dict[str, Any]) -> dict[str, Any]:
    """
    Classify a consultant desk payload.

    Priority: data_blocked > gate_blocked > no_qualifying > qualifying.
    """
    calls = _calls_list(board)
    annotated = [
        annotate_call_display(c, board=board, desk=board.get("desk"))
        for c in calls
    ]
    buy = sum(1 for c in annotated if _upper(c.get("side")) in ("BUY", "LONG"))
    sell = sum(1 for c in annotated if _upper(c.get("side")) in ("SELL", "SHORT"))
    actionable = buy + sell

    data_blocked = _freshness_blocked(
        board.get("data_status") if isinstance(board.get("data_status"), dict) else None
    ) or _feed_blocked(board)
    if not data_blocked and annotated:
        # Entire tape missing quotes / feed errors → blocked (not a strategy miss)
        err_n = sum(
            1
            for c in annotated
            if "NO_QUOTE" in (c.get("tags") or [])
            or "FEED_ERROR" in (c.get("tags") or [])
            or "NO_DATA" in (c.get("tags") or [])
        )
        if err_n == len(annotated) and actionable == 0:
            data_blocked = True

    if data_blocked and actionable == 0:
        code = DATA_BLOCKED
        detail = (
            (board.get("feed_health") or {}).get("message")
            if isinstance(board.get("feed_health"), dict)
            else None
        ) or board.get("message") or _LABELS[DATA_BLOCKED]
    elif _gate_failure_dominant(annotated) and actionable == 0:
        code = GATE_BLOCKED
        detail = board.get("message") or _LABELS[GATE_BLOCKED]
    elif actionable == 0:
        code = NO_QUALIFYING
        detail = board.get("message") or _LABELS[NO_QUALIFYING]
    else:
        code = QUALIFYING
        detail = f"{buy} BUY / {sell} SELL research call(s) — not orders."

    return {
        "code": code,
        "label": _LABELS[code],
        "detail": detail,
        "buy_count": buy,
        "sell_count": sell,
        "hold_count": sum(1 for c in annotated if _upper(c.get("side")) == "HOLD"),
        "actionable_count": actionable,
        "research_only": True,
        "boundary": RESEARCH_BOUNDARY,
    }


def summarize_expectancy_honesty(calls: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Board-level counts for Index/Intraday UI prominence.

    Does not change gate thresholds or invent metrics — reads call.expectancy only.
    """
    insuff = 0
    proxy = 0
    gate_fail = 0
    fail_reasons: list[str] = []
    for c in calls:
        if not isinstance(c, dict):
            continue
        exp = c.get("expectancy")
        if not isinstance(exp, dict):
            continue
        if exp.get("insufficient_history") or exp.get("status_label") == "insufficient_5m_history":
            insuff += 1
        if exp.get("proxy") or exp.get("status_label") in (
            "proxy_disabled",
            "proxy_desk_no_expectancy",
        ):
            proxy += 1
        gates = exp.get("gates") if isinstance(exp.get("gates"), dict) else {}
        if gates.get("passed") is False:
            gate_fail += 1
            for r in gates.get("fail_reasons") or []:
                s = str(r)
                if s and s not in fail_reasons:
                    fail_reasons.append(s)
                if len(fail_reasons) >= 6:
                    break
    prominent = (insuff + proxy + gate_fail) > 0
    parts: list[str] = []
    if insuff:
        parts.append(
            f"{insuff} call(s) lack sufficient 5m history — STRONG / edge blocked"
        )
    if proxy:
        parts.append(
            f"{proxy} call(s) use proxy or ungated metrics — STRONG blocked"
        )
    if gate_fail:
        reason_bit = (
            f" ({', '.join(fail_reasons[:3])})" if fail_reasons else ""
        )
        parts.append(
            f"{gate_fail} call(s) failed expectancy/risk gates{reason_bit}"
        )
    return {
        "prominent": prominent,
        "insufficient_history_count": insuff,
        "proxy_count": proxy,
        "gate_failed_count": gate_fail,
        "fail_reasons": fail_reasons,
        "label": (
            "Expectancy honesty — proxy / thin 5m history / gate fails"
            if prominent
            else "Expectancy honesty — no board-level blocks"
        ),
        "detail": (
            " · ".join(parts)
            if parts
            else "No proxy, insufficient-history, or gate-fail flags on this board."
        ),
        "research_only": True,
        "boundary": (
            "Research only — gate pass ≠ proven edge. "
            "Stale or unavailable data never creates a fresh signal."
        ),
    }


def attach_board_availability(board: dict[str, Any]) -> dict[str, Any]:
    """Mutate-safe: return board with annotated calls + signal_availability."""
    out = dict(board)
    desk = out.get("desk")
    strategy = out.get("strategy") or STRATEGY_BY_DESK.get(str(desk or "").lower())
    calls = _calls_list(out)
    annotated = [
        annotate_call_display(c, board=out, desk=desk, strategy=strategy)
        for c in calls
    ]
    out["calls"] = annotated
    if "signals" in out and isinstance(out["signals"], list):
        # Keep signals in sync when both keys exist (index desk)
        if out.get("signals") is not calls:
            out["signals"] = [
                annotate_call_display(c, board=out, desk=desk, strategy=strategy)
                for c in out["signals"]
                if isinstance(c, dict)
            ]
        else:
            out["signals"] = annotated
    avail = summarize_board_availability({**out, "calls": annotated})
    out["signal_availability"] = avail
    out["expectancy_honesty"] = summarize_expectancy_honesty(annotated)
    # Keep top-level counts aligned with honesty coercions (stale→HOLD)
    out["buy_count"] = avail["buy_count"]
    out["sell_count"] = avail["sell_count"]
    out["hold_count"] = avail["hold_count"]
    return out


def summarize_ledger_availability(
    *,
    published_count: int,
    filtered_demo_rows: int,
    category: Optional[str] = None,
) -> dict[str, Any]:
    """Explain empty platform ledger without suggesting seed_platform."""
    desk = CATEGORY_DESK.get(str(category or "").lower()) if category else None
    if published_count > 0:
        code = LEDGER_HAS_ROWS
        detail = f"{published_count} published non-demo ledger row(s)."
    elif filtered_demo_rows > 0:
        code = LEDGER_DEMO_FILTERED
        detail = (
            f"{filtered_demo_rows} legacy demo row(s) hidden. "
            "Admin publish with data_mode live/delayed/eod to appear here. "
            "Consultant desk calls are not auto-written to this ledger. "
            "seed_platform is retired and will not populate this ledger."
        )
    else:
        code = LEDGER_EMPTY
        detail = (
            "No published ledger signals. "
            "Ask an admin to publish a research note (non-demo data_mode). "
            "seed_platform is retired and will not populate this ledger."
        )
    return {
        "code": code,
        "label": _LABELS[code],
        "detail": detail,
        "published_count": published_count,
        "filtered_demo_rows": filtered_demo_rows,
        "desk": desk,
        "category": category,
        "research_only": True,
        "boundary": RESEARCH_BOUNDARY,
    }


def enrich_ledger_signal(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize a platform signal_records row for UI display fields."""
    out = dict(row)
    cat = str(out.get("category") or "").lower()
    desk = CATEGORY_DESK.get(cat, cat or "unknown")
    prov = out.get("provenance") if isinstance(out.get("provenance"), dict) else {}
    evidence = out.get("evidence") if isinstance(out.get("evidence"), dict) else {}
    dm = str(out.get("data_mode") or "delayed").lower()
    data_status = {
        "live": "LIVE",
        "delayed": "DELAYED",
        "stale": "STALE",
        "eod": "EOD",
        "fallback": "FALLBACK",
    }.get(dm, dm.upper() if dm else "DELAYED")
    direction = str(out.get("direction") or "none").lower()
    side = {"buy": "BUY", "sell": "SELL"}.get(direction, "HOLD")
    out["desk"] = desk
    out["strategy"] = out.get("methodology_id") or "admin_publish"
    out["instrument"] = out.get("symbol")
    out["direction"] = side
    out["data_source"] = prov.get("source") or evidence.get("source") or "admin_publish"
    out["data_timestamp"] = out.get("published_at") or out.get("created_at")
    out["data_status"] = data_status
    out["gate_result"] = {
        "code": "ledger_manual",
        "label": "Admin-published research note (not auto-gated)",
        "passed": None,
        "insufficient_history": False,
        "fail_reasons": [],
    }
    out["research_only"] = True
    return out
