"""
Professional Signal Consultant rules — pure grading + brief copy.

Three desks share one voice: risk first, no hype, research-only.
These functions do not fetch data; they grade already-built strategy outputs.
"""
from __future__ import annotations

from typing import Any

# --- Confidence clamps -------------------------------------------------------

_CONF_MIN = 0.0
_CONF_MAX = 100.0

# Outside NSE cash session, intraday residue is not fresh edge
_INTRADAY_OFF_SESSION_MULT = 0.62
_INTRADAY_OFF_SESSION_FLOOR = 18.0
# Off-session BUY needs a stronger raw score before confidence is meaningful
_INTRADAY_OFF_SESSION_BUY_MIN = 72.0

# Swing score → confidence (strategy scores are roughly 0–100)
_SWING_BUY_MIN_SCORE = 55
_SWING_CONF_FLOOR_BUY = 42.0
_SWING_CONF_CEIL_BUY = 88.0
_SWING_HOLD_CONF_CAP = 45.0

# Intraday / MCX score bands (strategy: LONG ≥62 / ≥60, SHORT ≤38 / ≤40)
_INTRADAY_BUY_MIN = 62.0
_INTRADAY_SELL_MAX = 38.0
_MCX_BUY_MIN = 60.0
_MCX_SELL_MAX = 40.0

_BLOCKING_REGIMES = frozenset({"BEAR", "NEUTRAL", "UNKNOWN", "CASH"})


def clamp_confidence(value: float | int | None, *, lo: float = _CONF_MIN, hi: float = _CONF_MAX) -> float:
    """Clamp confidence to [lo, hi], round to 1 decimal."""
    try:
        v = float(value if value is not None else 0.0)
    except (TypeError, ValueError):
        v = 0.0
    return round(max(lo, min(hi, v)), 1)


def _regime_name(regime: dict[str, Any] | str | None) -> str:
    if regime is None:
        return "UNKNOWN"
    if isinstance(regime, str):
        return regime.strip().upper() or "UNKNOWN"
    name = regime.get("regime") or regime.get("name") or "UNKNOWN"
    return str(name).strip().upper() or "UNKNOWN"


def _allow_swing_entries(regime: dict[str, Any] | str | None) -> bool:
    if regime is None:
        return False
    if isinstance(regime, str):
        return _regime_name(regime) not in _BLOCKING_REGIMES
    if "allow_trading" in regime:
        return bool(regime.get("allow_trading"))
    return _regime_name(regime) not in _BLOCKING_REGIMES


def _score_of(obj: dict[str, Any], default: float = 50.0) -> float:
    raw = obj.get("score")
    if raw is None:
        raw = obj.get("confidence")
    try:
        return float(raw if raw is not None else default)
    except (TypeError, ValueError):
        return default


def _in_session_flag(signal: dict[str, Any]) -> bool | None:
    """True / False if known; None if caller did not attach session state."""
    if "in_session" in signal:
        return bool(signal.get("in_session"))
    session = signal.get("session")
    if isinstance(session, dict) and "in_session" in session:
        return bool(session.get("in_session"))
    return None


def _map_bias_side(raw: str | None) -> str:
    """Strategy LONG/SHORT/FLAT (or already BUY/SELL/HOLD) → consultant side."""
    s = str(raw or "HOLD").strip().upper()
    if s in ("BUY", "LONG", "BULL"):
        return "BUY"
    if s in ("SELL", "SHORT", "BEAR"):
        return "SELL"
    return "HOLD"


# --- Swing desk --------------------------------------------------------------


def grade_swing(
    candidate: dict[str, Any] | None,
    regime: dict[str, Any] | str | None,
) -> dict[str, Any]:
    """
    Swing consultant: BUY or HOLD only (no new short book on this desk).

    BEAR / blocked regime → HOLD / cash — never a new BUY.
    """
    regime_name = _regime_name(regime)
    allow = _allow_swing_entries(regime)
    tags: list[str] = [f"REGIME_{regime_name}"]

    if not candidate:
        return {
            "side": "HOLD",
            "confidence": clamp_confidence(25.0),
            "reason": (
                f"No swing candidate under {regime_name}. "
                "Prefer cash until a Stage-2 setup clears filters."
            ),
            "tags": tags + ["CASH", "NO_CANDIDATE"],
            "symbol": None,
        }

    symbol = str(candidate.get("symbol") or "").upper() or None
    score = _score_of(candidate, default=0.0)
    rr = candidate.get("risk_reward")
    thesis = str(candidate.get("thesis") or "").strip()

    # Hard rule: blocked / BEAR → no new swing BUYs
    if not allow or regime_name == "BEAR":
        reason = (
            f"{symbol or 'Market'}: regime {regime_name} — no new swing entries. "
            "Stay in cash / manage existing risk only."
        )
        if isinstance(regime, dict) and regime.get("reason"):
            reason = f"{reason} ({regime['reason']})"
        conf = clamp_confidence(min(_SWING_HOLD_CONF_CAP, max(20.0, score * 0.35)))
        return {
            "side": "HOLD",
            "confidence": conf,
            "reason": reason,
            "tags": tags + ["CASH", "NO_NEW_BUY", "BEAR_GATE" if regime_name == "BEAR" else "REGIME_GATE"],
            "symbol": symbol,
        }

    # Actionable BUY only when score clears desk threshold
    if score >= _SWING_BUY_MIN_SCORE:
        # Map score into a professional confidence band (not 100% certainty)
        conf = clamp_confidence(
            _SWING_CONF_FLOOR_BUY
            + (min(score, 100.0) - _SWING_BUY_MIN_SCORE)
            * (_SWING_CONF_CEIL_BUY - _SWING_CONF_FLOOR_BUY)
            / max(1.0, 100.0 - _SWING_BUY_MIN_SCORE)
        )
        if regime_name == "STRONG_BULL":
            conf = clamp_confidence(conf + 4.0)
            tags.append("STRONG_BULL_TAILWIND")
        elif regime_name == "BULL":
            tags.append("BULL_OK")
        if rr is not None:
            try:
                if float(rr) < 1.5:
                    conf = clamp_confidence(conf - 6.0)
                    tags.append("RR_THIN")
                elif float(rr) >= 2.0:
                    tags.append("RR_OK")
            except (TypeError, ValueError):
                pass
        reason = (
            f"{symbol}: BUY bias — score {score:.0f} under {regime_name}. "
            + (thesis if thesis else "Stage-2 / momentum screen cleared.")
            + " Size to stop; invalidate if regime flips BEAR."
        )
        return {
            "side": "BUY",
            "confidence": conf,
            "reason": reason,
            "tags": tags + ["SWING_SETUP"],
            "symbol": symbol,
        }

    conf = clamp_confidence(min(_SWING_HOLD_CONF_CAP, 28.0 + score * 0.15))
    return {
        "side": "HOLD",
        "confidence": conf,
        "reason": (
            f"{symbol or 'Name'}: score {score:.0f} below swing BUY threshold "
            f"({_SWING_BUY_MIN_SCORE}). Watchlist / radar only."
        ),
        "tags": tags + ["WATCH", "BELOW_THRESHOLD"],
        "symbol": symbol,
    }


# --- Intraday desk -----------------------------------------------------------


def grade_intraday(signal: dict[str, Any] | None) -> dict[str, Any]:
    """
    Intraday consultant: BUY / SELL / HOLD from LONG / SHORT / FLAT bias.

    Outside NSE session → confidence reduced (last-session residue).
    """
    if not signal:
        return {
            "side": "HOLD",
            "confidence": clamp_confidence(15.0),
            "reason": "No intraday tape — HOLD.",
            "tags": ["NO_SIGNAL"],
            "symbol": None,
        }

    symbol = str(signal.get("symbol") or "").upper() or None
    raw_side = signal.get("side")
    side = _map_bias_side(str(raw_side) if raw_side is not None else None)
    score = _score_of(signal, default=50.0)
    tags: list[str] = list(signal.get("tags") or [])
    thesis = str(signal.get("thesis") or "").strip()

    # Reconcile side with score bands if strategy said FLAT but score extreme
    if side == "HOLD":
        if score >= _INTRADAY_BUY_MIN:
            side = "BUY"
        elif score <= _INTRADAY_SELL_MAX:
            side = "SELL"

    conf = clamp_confidence(score)
    in_session = _in_session_flag(signal)
    if in_session is False:
        # Residue: BUY only if score clears a higher bar; else demote to HOLD
        if side == "BUY" and score < _INTRADAY_OFF_SESSION_BUY_MIN:
            side = "HOLD"
            tags = list(dict.fromkeys([*tags, "OFF_SESSION_BUY_BLOCK"]))
        conf = clamp_confidence(max(_INTRADAY_OFF_SESSION_FLOOR, conf * _INTRADAY_OFF_SESSION_MULT))
        tags = list(dict.fromkeys([*tags, "OFF_SESSION", "RESIDUE"]))
        session_note = " Outside NSE cash hours — treat as residue, not fresh edge."
    elif in_session is True:
        tags = list(dict.fromkeys([*tags, "IN_SESSION"]))
        session_note = ""
    else:
        session_note = ""

    if side == "BUY":
        reason = (
            f"{symbol}: BUY bias (intraday) · score {score:.1f}. "
            + (thesis + " " if thesis else "")
            + "Hard stop required; size 0.25–0.5% risk."
            + session_note
        )
    elif side == "SELL":
        reason = (
            f"{symbol}: SELL / short bias (intraday) · score {score:.1f}. "
            + (thesis + " " if thesis else "")
            + "Hard stop required; avoid overnight unless planned."
            + session_note
        )
    else:
        conf = clamp_confidence(min(conf, 55.0))
        if "OFF_SESSION_BUY_BLOCK" in tags:
            reason = (
                f"{symbol or 'Name'}: HOLD — off-session BUY needs score "
                f"≥ {_INTRADAY_OFF_SESSION_BUY_MIN:.0f} (got {score:.1f}); residue only."
                + session_note
            )
        else:
            reason = (
                f"{symbol or 'Name'}: HOLD — no clear intraday edge (score {score:.1f})."
                + session_note
            )
        tags = list(dict.fromkeys([*tags, "FLAT"]))

    return {
        "side": side,
        "confidence": conf,
        "reason": reason.strip(),
        "tags": tags,
        "symbol": symbol,
    }


# --- MCX / commodity desk ----------------------------------------------------


def grade_mcx(signal: dict[str, Any] | None) -> dict[str, Any]:
    """
    Commodity consultant: BUY / SELL / HOLD from global-futures proxy bias.

    Always tags HIGH_LEVERAGE for MCX-mapped names (lots/margins amplify risk).
    """
    if not signal:
        return {
            "side": "HOLD",
            "confidence": clamp_confidence(15.0),
            "reason": "No commodity tape — HOLD.",
            "tags": ["NO_SIGNAL", "HIGH_LEVERAGE"],
            "symbol": None,
        }

    symbol = str(
        signal.get("id") or signal.get("symbol") or signal.get("name") or ""
    ).upper() or None
    raw_side = signal.get("side")
    side = _map_bias_side(str(raw_side) if raw_side is not None else None)
    score = _score_of(signal, default=50.0)
    tags: list[str] = list(signal.get("tags") or [])
    thesis = str(signal.get("thesis") or "").strip()
    group = str(signal.get("group") or "").lower()

    if side == "HOLD":
        if score >= _MCX_BUY_MIN:
            side = "BUY"
        elif score <= _MCX_SELL_MAX:
            side = "SELL"

    conf = clamp_confidence(score)

    # Leverage warning — always on for commodity desk (FX context included)
    tags = list(dict.fromkeys([*tags, "HIGH_LEVERAGE", "MCX_PROXY"]))
    if group == "energy":
        tags = list(dict.fromkeys([*tags, "GAP_RISK"]))
        conf = clamp_confidence(conf * 0.95)  # slightly more conservative on energy
    if symbol == "USDINR" or group == "fx":
        tags = list(dict.fromkeys([*tags, "FX_CONTEXT"]))
        # FX row is context, not a leveraged MCX lot call — soft HOLD preference
        if side != "HOLD" and abs(score - 50.0) < 12:
            side = "HOLD"

    leverage_note = (
        " HIGH_LEVERAGE: map to front-month MCX lot/margin yourself; "
        "gaps and margin calls can exceed cash risk."
    )

    if side == "BUY":
        reason = (
            f"{symbol}: BUY bias (commodity proxy) · score {score:.1f}. "
            + (thesis + " " if thesis else "")
            + leverage_note
        )
    elif side == "SELL":
        reason = (
            f"{symbol}: SELL bias (commodity proxy) · score {score:.1f}. "
            + (thesis + " " if thesis else "")
            + leverage_note
        )
    else:
        conf = clamp_confidence(min(conf, 55.0))
        reason = (
            f"{symbol or 'Contract'}: HOLD — no clear directional edge "
            f"(score {score:.1f})."
            + leverage_note
        )

    return {
        "side": side,
        "confidence": conf,
        "reason": reason.strip(),
        "tags": tags,
        "symbol": symbol,
    }


# --- Briefs ------------------------------------------------------------------


def _fmt_line(graded: dict[str, Any], *, desk: str) -> str:
    sym = graded.get("symbol") or "—"
    side = graded.get("side") or "HOLD"
    conf = graded.get("confidence")
    conf_s = f"{conf:.0f}" if isinstance(conf, (int, float)) else "—"
    return f"- **{sym}** · {desk} · `{side}` · conf {conf_s}"


def daily_brief(
    intraday_list: list[dict[str, Any]] | None,
    mcx_list: list[dict[str, Any]] | None,
) -> str:
    """
    Markdown-ish same-day brief from intraday + MCX graded (or raw) rows.

    Accepts either already-graded dicts (side BUY/SELL/HOLD) or raw strategy
    signals (LONG/SHORT/FLAT); raw rows are graded inline.
    """
    intra = list(intraday_list or [])
    mcx = list(mcx_list or [])

    graded_i: list[dict[str, Any]] = []
    for row in intra:
        if str(row.get("side") or "").upper() in ("BUY", "SELL", "HOLD") and "confidence" in row:
            graded_i.append(row)
        else:
            graded_i.append(grade_intraday(row))

    graded_m: list[dict[str, Any]] = []
    for row in mcx:
        if str(row.get("side") or "").upper() in ("BUY", "SELL", "HOLD") and "confidence" in row:
            graded_m.append(row)
        else:
            graded_m.append(grade_mcx(row))

    def _actionable(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [r for r in rows if r.get("side") in ("BUY", "SELL")]

    buys_i = [r for r in graded_i if r.get("side") == "BUY"]
    sells_i = [r for r in graded_i if r.get("side") == "SELL"]
    act_m = _actionable(graded_m)

    off = any("OFF_SESSION" in (r.get("tags") or []) for r in graded_i)

    lines = [
        "## Daily desk brief (Intraday + MCX)",
        "",
        "_Research only. Risk capital you can lose. Not a profit guarantee._",
        "",
        "### Session posture",
        (
            "- NSE cash: **outside session** — intraday confidence is discounted (residue)."
            if off
            else "- NSE cash: treat intraday lines as **same-session research** when in hours."
        ),
        "- MCX: every actionable line carries **HIGH_LEVERAGE** — confirm lot, margin, expiry.",
        "",
        "### Intraday",
        f"- Tape graded: {len(graded_i)} · BUY {len(buys_i)} · SELL {len(sells_i)}",
    ]
    top_i = sorted(
        _actionable(graded_i),
        key=lambda r: float(r.get("confidence") or 0),
        reverse=True,
    )[:5]
    if top_i:
        lines.append("")
        lines.append("Top actionable:")
        lines.extend(_fmt_line(r, desk="intraday") for r in top_i)
    else:
        lines.append("- No clear BUY/SELL — default **HOLD / stand down**.")

    lines.extend(
        [
            "",
            "### MCX / commodities",
            f"- Tape graded: {len(graded_m)} · actionable {len(act_m)}",
        ]
    )
    top_m = sorted(
        act_m,
        key=lambda r: float(r.get("confidence") or 0),
        reverse=True,
    )[:5]
    if top_m:
        lines.append("")
        lines.append("Top actionable:")
        lines.extend(_fmt_line(r, desk="mcx") for r in top_m)
    else:
        lines.append("- No clear commodity edge — **HOLD**; do not force leverage.")

    lines.extend(
        [
            "",
            "### Risk first",
            "- Define stop before entry; size so one loss is small and planned.",
            "- Do not stack correlated MCX energy/metals risk without an explicit book limit.",
            "",
        ]
    )
    return "\n".join(lines)


def weekly_brief(
    swing_list: list[dict[str, Any]] | None,
    regime: dict[str, Any] | str | None,
) -> str:
    """
    Markdown-ish weekly swing brief. BEAR / blocked regime → cash week language.
    """
    regime_name = _regime_name(regime)
    allow = _allow_swing_entries(regime)
    regime_reason = ""
    if isinstance(regime, dict):
        regime_reason = str(regime.get("reason") or "").strip()

    rows = list(swing_list or [])
    graded: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("side") or "").upper() in ("BUY", "HOLD") and "confidence" in row:
            # Still re-check BEAR gate if raw BUY slipped through
            if not allow or regime_name == "BEAR":
                graded.append(grade_swing(row, regime))
            else:
                graded.append(row)
        else:
            graded.append(grade_swing(row, regime))

    buys = [r for r in graded if r.get("side") == "BUY"]
    holds = [r for r in graded if r.get("side") == "HOLD"]

    lines = [
        "## Weekly swing brief",
        "",
        "_Research only. Weekly horizon · hard stops · no return guarantee._",
        "",
        "### Regime",
        f"- **{regime_name}**"
        + (f" — {regime_reason}" if regime_reason else ""),
    ]

    if not allow or regime_name == "BEAR":
        lines.extend(
            [
                "- **Cash week:** no new swing BUYs. Manage open risk only; prefer Intraday/MCX research or wait.",
                "",
                "### Candidates",
                f"- Graded names: {len(graded)} · forced HOLD {len(holds)} · BUY {len(buys)} (should be 0 under gate)",
                "- Radar may still list momentum leaders — **not actionable** while the gate is closed.",
            ]
        )
    else:
        lines.extend(
            [
                "- New swing entries allowed under desk filters (still research-only).",
                "",
                "### Candidates",
                f"- Graded: {len(graded)} · BUY {len(buys)} · HOLD {len(holds)}",
            ]
        )
        top = sorted(buys, key=lambda r: float(r.get("confidence") or 0), reverse=True)[:8]
        if top:
            lines.append("")
            lines.append("BUY book (confidence order):")
            lines.extend(_fmt_line(r, desk="swing") for r in top)
            for r in top[:3]:
                reason = str(r.get("reason") or "").strip()
                if reason:
                    lines.append(f"  - _{reason[:220]}_")
        else:
            lines.append("- No BUY cleared threshold — **cash is a position**.")

    lines.extend(
        [
            "",
            "### Process",
            "- Invalidation: flip to BEAR / break of plan stop / Friday or max-hold exit — whichever first.",
            "- Do not average losers; size from stop distance, not conviction language.",
            "",
        ]
    )
    return "\n".join(lines)
