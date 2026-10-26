"""
Signal gating by research expectancy thresholds.

STRONG BUY / STRONG SELL badges are blocked unless the active expectancy
regime shows: Sample Size ≥ 30, Expectancy > 0.25R, Profit Factor ≥ 1.2.

Gate pass is research evidence only — not a proven edge or profit claim.
Never attach ``EDGE_PROVEN`` (removed); use ``GATE_PASS_RESEARCH`` instead.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

from app.expectancy.harness import (
    RULE_INDEX,
    RULE_INTRADAY,
    RULE_SWING,
    run_and_persist,
)
from app.expectancy.persist import (
    ensure_expectancy_schema,
    load_metrics,
    metrics_stale,
)
from app.expectancy.regimes import regime_at

logger = logging.getLogger(__name__)

STRONG_GATES = {
    "min_sample_size": 30,
    "min_expectancy_r": 0.25,
    "min_profit_factor": 1.2,
}

DESK_RULE = {
    "swing": RULE_SWING,
    "intraday": RULE_INTRADAY,
    "index": RULE_INDEX,
}

_refresh_lock = threading.Lock()
_refreshing = False


def get_active_regime(db, as_of: str | None = None) -> dict[str, Any]:
    nifty = db.get_nifty_series(end_date=as_of, lookback=80)
    return regime_at(nifty, as_of)


def _passes_gates(m: dict[str, Any] | None) -> tuple[bool, list[str]]:
    if not m:
        return False, ["NO_METRICS"]
    fails: list[str] = []
    meta = m.get("meta") if isinstance(m.get("meta"), dict) else {}
    if not meta and m.get("meta_json"):
        import json

        try:
            meta = json.loads(m["meta_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            meta = {}

    # Phase 3: never STRONG on proxy / insufficient 5m / wrong interval
    if meta.get("proxy"):
        fails.append("PROXY_METRICS_NOT_LIVE_RULE")
    if meta.get("insufficient_history"):
        fails.append("INSUFFICIENT_5M_HISTORY")
    rid = str(m.get("rule_id") or meta.get("strategy_id") or "")
    if rid in (RULE_INDEX, RULE_INTRADAY):
        interval = meta.get("data_interval") or meta.get("timeframe")
        if interval and interval != "5m":
            fails.append(f"WRONG_INTERVAL:{interval}")
        if not interval and meta.get("proxy") is not False:
            # Legacy rows without interval metadata
            fails.append("LEGACY_OR_MISSING_5M_META")

    n = int(m.get("sample_size") or 0)
    if n < STRONG_GATES["min_sample_size"]:
        fails.append(f"N<{STRONG_GATES['min_sample_size']} (got {n})")
    exp = m.get("expectancy_r")
    if exp is None or float(exp) <= STRONG_GATES["min_expectancy_r"]:
        fails.append(
            f"E≤{STRONG_GATES['min_expectancy_r']}R (got {exp})"
        )
    pf = m.get("profit_factor")
    if pf is None or float(pf) < STRONG_GATES["min_profit_factor"]:
        fails.append(
            f"PF<{STRONG_GATES['min_profit_factor']} (got {pf})"
        )
    return (len(fails) == 0), fails


def load_rule_metrics(
    db,
    rule_id: str,
    regime: str,
) -> dict[str, Any] | None:
    ensure_expectancy_schema(db)
    return load_metrics(db, rule_id=rule_id, regime=regime)


def ensure_metrics_fresh(
    db,
    *,
    force: bool = False,
    background: bool = True,
) -> dict[str, Any] | None:
    """
    Auto-run walk-forward if any core rule is missing/stale.

    Default ``background=True`` so consultant endpoints stay responsive;
    STRONG badges stay blocked until metrics land.
    """
    global _refreshing
    ensure_expectancy_schema(db)
    need = force or any(
        metrics_stale(db, rule_id=rid)
        for rid in (RULE_SWING, RULE_INDEX, RULE_INTRADAY)
    )
    if not need:
        return None

    def _job() -> dict[str, Any]:
        global _refreshing
        if not _refresh_lock.acquire(blocking=False):
            return {"status": "busy", "message": "Expectancy refresh already running"}
        try:
            _refreshing = True
            logger.info("Running expectancy walk-forward (stale/missing metrics)")
            return run_and_persist(db)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Expectancy refresh failed: %s", exc)
            return {"status": "error", "message": str(exc)}
        finally:
            _refreshing = False
            _refresh_lock.release()

    if background and not force:
        if _refreshing:
            return {"status": "busy"}
        t = threading.Thread(target=_job, name="expectancy-refresh", daemon=True)
        t.start()
        return {"status": "started", "message": "Expectancy walk-forward started in background"}
    return _job()


def _public_metrics(m: dict[str, Any] | None, *, regime: str, rule_id: str) -> dict[str, Any]:
    """Card-facing metrics — never invent numbers."""
    if not m:
        return {
            "rule_id": rule_id,
            "regime": regime,
            "sample_size": 0,
            "win_rate_pct": None,
            "expectancy_r": None,
            "profit_factor": None,
            "avg_win_r": None,
            "avg_loss_r": None,
            "max_drawdown_pct": None,
            "available": False,
        }
    return {
        "rule_id": rule_id,
        "regime": regime,
        "sample_size": int(m.get("sample_size") or 0),
        "win_rate_pct": m.get("win_rate_pct"),
        "expectancy_r": m.get("expectancy_r"),
        "profit_factor": m.get("profit_factor"),
        "avg_win_r": m.get("avg_win_r"),
        "avg_loss_r": m.get("avg_loss_r"),
        "max_drawdown_pct": m.get("max_drawdown_pct"),
        "as_of": m.get("as_of"),
        "computed_at": m.get("computed_at"),
        "available": int(m.get("sample_size") or 0) > 0,
    }


def derive_badge(
    side: str,
    *,
    confidence: float | None,
    gates_ok: bool,
    strong_conf_floor: float = 68.0,
) -> str:
    """
    Map side → display badge. STRONG_* only when gates_ok and confidence clears floor.
    """
    s = str(side or "HOLD").upper()
    conf = float(confidence or 0.0)
    if s == "BUY":
        if gates_ok and conf >= strong_conf_floor:
            return "STRONG_BUY"
        return "BUY"
    if s == "SELL":
        if gates_ok and conf >= strong_conf_floor:
            return "STRONG_SELL"
        return "SELL"
    return "HOLD"


def apply_expectancy_gate(
    call: dict[str, Any],
    *,
    db,
    regime: str | None = None,
    rule_id: str | None = None,
    auto_refresh: bool = False,
) -> dict[str, Any]:
    """
    Mutate/return call with badge + expectancy block.

    Blocks STRONG badges when edge gates fail. Always attaches real metrics
    (or available=false) — never hardcoded win rates.
    """
    desk = str(call.get("desk") or "").lower()
    rid = rule_id or DESK_RULE.get(desk) or RULE_SWING

    if auto_refresh:
        ensure_metrics_fresh(db)

    if not regime:
        as_of = call.get("as_of")
        if isinstance(as_of, str) and len(as_of) >= 10:
            as_of = as_of[:10]
        else:
            as_of = db.get_max_trade_date()
        regime = str(get_active_regime(db, as_of).get("regime") or "UNKNOWN")

    m = load_rule_metrics(db, rid, regime)
    # UNKNOWN regime → fall back to ALL for display, but never allow STRONG
    if (not m or int(m.get("sample_size") or 0) == 0) and regime != "ALL":
        m_all = load_rule_metrics(db, rid, "ALL")
        display_m = m_all if m_all else m
        display_regime = "ALL" if m_all and not m else regime
    else:
        display_m = m
        display_regime = regime

    gates_ok, fail_reasons = _passes_gates(m if regime != "UNKNOWN" else None)
    if regime == "UNKNOWN":
        gates_ok = False
        fail_reasons = ["REGIME_UNKNOWN"]

    side = str(call.get("side") or "HOLD").upper()
    badge = derive_badge(side, confidence=call.get("confidence"), gates_ok=gates_ok)

    # Strip STRONG / legacy "proven" tags; never re-attach EDGE_PROVEN
    _drop = ("STRONG_BUY", "STRONG_SELL", "EDGE_PROVEN")
    tags = [
        t
        for t in (call.get("tags") or [])
        if not any(x in str(t) for x in _drop)
    ]
    if badge == "STRONG_BUY":
        tags = list(dict.fromkeys([*tags, "STRONG_BUY", "GATE_PASS_RESEARCH"]))
    elif badge == "STRONG_SELL":
        tags = list(dict.fromkeys([*tags, "STRONG_SELL", "GATE_PASS_RESEARCH"]))
    elif side in ("BUY", "SELL") and not gates_ok:
        tags = list(dict.fromkeys([*tags, "EDGE_UNPROVEN"]))

    metrics_pub = _public_metrics(display_m, regime=str(display_regime), rule_id=rid)
    metrics_pub["active_regime"] = regime
    metrics_pub["gates"] = {
        **STRONG_GATES,
        "passed": gates_ok,
        "fail_reasons": fail_reasons,
    }
    # Honesty / reproducibility for UI (never claim proven merely from a pass)
    meta = {}
    if display_m and isinstance(display_m.get("meta"), dict):
        meta = display_m["meta"]
    metrics_pub["proxy"] = bool(meta.get("proxy"))
    metrics_pub["insufficient_history"] = bool(meta.get("insufficient_history"))
    metrics_pub["timeframe"] = meta.get("timeframe") or meta.get("data_interval")
    metrics_pub["data_interval"] = meta.get("data_interval")
    metrics_pub["strategy_version"] = meta.get("strategy_version")
    metrics_pub["honesty"] = meta.get("honesty")
    metrics_pub["proven"] = False
    metrics_pub["disclaimer"] = meta.get("disclaimer") or (
        "Research walk-forward after India costs — not a profit guarantee. "
        "Gate pass ≠ proven edge."
    )
    if metrics_pub["insufficient_history"] or "INSUFFICIENT_5M_HISTORY" in fail_reasons:
        metrics_pub["status_label"] = "insufficient_5m_history"
    elif metrics_pub["proxy"]:
        metrics_pub["status_label"] = "proxy_disabled"
    elif not gates_ok:
        metrics_pub["status_label"] = "edge_unproven"
    else:
        metrics_pub["status_label"] = "gates_passed_research_only"

    call = dict(call)
    call["badge"] = badge
    call["tags"] = tags
    ctx = dict(call.get("context") or {})
    ctx["expectancy"] = metrics_pub
    call["context"] = ctx
    # Top-level convenience for UI (also inside context)
    call["expectancy"] = metrics_pub
    return call


def gate_calls(
    calls: list[dict[str, Any]],
    *,
    db,
    desk: str | None = None,
    as_of: str | None = None,
    auto_refresh: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Apply gate to a list of calls; return (calls, regime_info)."""
    if auto_refresh:
        ensure_metrics_fresh(db)
    reg = get_active_regime(db, as_of)
    regime = str(reg.get("regime") or "UNKNOWN")
    rid = DESK_RULE.get(str(desk or "").lower()) if desk else None
    out = [
        apply_expectancy_gate(
            c,
            db=db,
            regime=regime,
            rule_id=rid or DESK_RULE.get(str(c.get("desk") or "").lower()),
            auto_refresh=False,
        )
        for c in calls
    ]
    return out, reg
