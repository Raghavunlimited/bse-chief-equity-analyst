"""
Weekly goal planner — research sizing math only.

Maps a capital target (%) to required R-multiples vs candidate risk/reward.
Does not forecast or guarantee returns.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any


def _risk_as_fraction(risk_pct: float) -> float:
    """Normalize risk input to a fraction of capital (API % or config fraction)."""
    r = float(risk_pct)
    if r > 0.2:
        return max(0.0, r / 100.0)
    return max(0.0, r)


def iso_week_label(as_of: str | date | datetime | None = None) -> str:
    """Return ISO week label, e.g. ``2026-W43``."""
    if as_of is None:
        d = date.today()
    elif isinstance(as_of, datetime):
        d = as_of.date()
    elif isinstance(as_of, date):
        d = as_of
    else:
        d = datetime.strptime(str(as_of)[:10], "%Y-%m-%d").date()
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


def _candidate_risk_rs(cand: dict[str, Any], default: float) -> float:
    sizing = cand.get("sizing") or {}
    for key in ("risk_rs",):
        if cand.get(key) is not None:
            try:
                return max(0.0, float(cand[key]))
            except (TypeError, ValueError):
                pass
    if sizing.get("risk_rs") is not None:
        try:
            return max(0.0, float(sizing["risk_rs"]))
        except (TypeError, ValueError):
            pass
    return max(0.0, float(default))


def _candidate_rr(cand: dict[str, Any]) -> float:
    try:
        rr = float(cand.get("risk_reward") or 0)
    except (TypeError, ValueError):
        rr = 0.0
    if rr > 0:
        return rr
    try:
        risk_p = float(cand.get("risk_pct") or 0)
        reward_p = float(cand.get("reward_pct") or 0)
        if risk_p > 0:
            return reward_p / risk_p
    except (TypeError, ValueError):
        pass
    return 0.0


def _theoretical_reward_rs(cand: dict[str, Any], risk_rs_default: float) -> float:
    """Optimistic reward in ₹ if target is hit: RR × risk_rs."""
    return _candidate_rr(cand) * _candidate_risk_rs(cand, risk_rs_default)


def plan_week_goal(
    capital: float,
    target_gain_pct: float,
    risk_pct: float,
    max_positions: int,
    candidates: list[dict[str, Any]] | None,
    *,
    as_of: str | None = None,
) -> dict[str, Any]:
    """
    Build a research-only weekly goal plan.

    Simple model:
    - ``required_R_multiple`` = target / (risk_per_trade × max_positions)
      (optimistic: every slot hits its full R)
    - ``required_R`` = target / (risk_per_trade × expected_wins_proxy)
      with expected_wins_proxy ≈ half the book (win-rate proxy)
    - ``reachable`` if any pick RR ≥ needed multiple, or sum of theoretical
      max rewards across top N ≥ target_rupees
    """
    capital = max(0.0, float(capital or 0))
    target_gain_pct = max(0.0, min(30.0, float(target_gain_pct or 0)))
    max_positions = max(1, int(max_positions or 1))
    cands = list(candidates or [])

    week_label = iso_week_label(as_of)
    risk_frac = _risk_as_fraction(risk_pct)
    risk_rupees_per_trade = round(capital * risk_frac, 2)
    target_rupees = round(capital * target_gain_pct / 100.0, 2)

    # Research framing (Stage-2): win-rate proxy ~45%, avg winner RR from book.
    # Optimistic ceiling: T ≤ risk% · N · ρ  (all slots hit full RR).
    # Expectation proxy: T ≲ risk% · N · (p·ρ − (1−p)).
    win_rate_proxy = 0.45
    expected_wins_proxy = max(0.5, max_positions * win_rate_proxy)

    if risk_rupees_per_trade <= 0 or capital <= 0:
        required_R_multiple = None
        required_R = None
    else:
        # Full-book optimistic: need this many R if every slot wins its planned RR
        required_R_multiple = round(
            target_rupees / (risk_rupees_per_trade * max_positions), 3
        )
        # With ~45% win-rate proxy: more R required in expectation
        required_R = round(
            target_rupees / (risk_rupees_per_trade * expected_wins_proxy), 3
        )

    needed = required_R_multiple if required_R_multiple is not None else float("inf")

    # Re-rank favoring RR × score (goal contribution)
    ranked: list[dict[str, Any]] = []
    for c in cands:
        rr = _candidate_rr(c)
        try:
            score = float(c.get("score") or 0)
        except (TypeError, ValueError):
            score = 0.0
        risk_rs = _candidate_risk_rs(c, risk_rupees_per_trade)
        theo = round(rr * risk_rs, 2)
        ranked.append(
            {
                **{k: v for k, v in c.items() if k != "fundamentals"},
                "goal_rank_score": round(rr * score, 2),
                "theoretical_reward_rs": theo,
                "risk_reward": round(rr, 2) if rr else c.get("risk_reward"),
            }
        )
    ranked.sort(
        key=lambda x: (float(x.get("goal_rank_score") or 0), float(x.get("score") or 0)),
        reverse=True,
    )
    suggested = ranked[:max_positions]

    avg_rr = 0.0
    if suggested:
        avg_rr = sum(_candidate_rr(c) for c in suggested) / len(suggested)
    elif ranked:
        avg_rr = sum(_candidate_rr(c) for c in ranked[:max_positions]) / min(
            max_positions, len(ranked)
        )
    # Fallback typical Stage-2 RR when no book yet
    rho = avg_rr if avg_rr > 0 else 2.0
    risk_pct_points = risk_frac * 100.0
    max_plausible_T = round(risk_pct_points * max_positions * rho, 2)
    expected_edge_R = max_positions * (win_rate_proxy * rho - (1.0 - win_rate_proxy))
    expected_plausible_T = round(risk_pct_points * max(0.0, expected_edge_R), 2)

    any_rr_ok = (
        any(_candidate_rr(c) >= needed for c in suggested) if needed < float("inf") else False
    )
    combined_max = round(
        sum(float(c.get("theoretical_reward_rs") or 0) for c in suggested), 2
    )
    combined_ok = combined_max >= target_rupees if target_rupees > 0 else True
    # Structural check from Research: T ≤ R% · N · ρ
    structural_ok = target_gain_pct <= max_plausible_T + 1e-9
    reachable = bool(
        target_rupees <= 0 or ((any_rr_ok or combined_ok) and structural_ok)
    )
    if target_rupees > 0 and not structural_ok:
        reachable = False

    if target_rupees <= 0:
        message = (
            "No gain target set — showing research setups only; "
            "nothing is guaranteed."
        )
    elif not cands:
        message = (
            f"Target ₹{target_rupees:,.0f} ({target_gain_pct:g}% of capital) this week "
            f"({week_label}), but no candidates passed the screen. "
            "Goal is not reachable on current research output — cash is valid. "
            f"At {risk_pct_points:g}% risk × {max_positions} slots × ~{rho:.1f}R, "
            f"a plausible weekly ceiling is ~{max_plausible_T:g}% (best case) / "
            f"~{expected_plausible_T:g}% (45% win-rate proxy) — not a promise."
        )
        reachable = False
    elif reachable:
        message = (
            f"Research model: ₹{target_rupees:,.0f} ({target_gain_pct:g}%) may be "
            f"approachable if top setups realize ~{needed:.1f}R combined "
            f"(book potential ~₹{combined_max:,.0f}; ceiling ~{max_plausible_T:g}% "
            f"if all {max_positions} slots hit ~{rho:.1f}R). "
            "Sizing math only — not a forecast or guarantee."
        )
    else:
        message = (
            f"Not a realistic weekly target at these risk settings: "
            f"₹{target_rupees:,.0f} ({target_gain_pct:g}%) needs ~{needed:.1f}R "
            f"per full-book hit, while Stage-2 math caps roughly at "
            f"~{max_plausible_T:g}% best-case / ~{expected_plausible_T:g}% expected "
            f"({risk_pct_points:g}% risk × {max_positions} × ~{rho:.1f}R, 45% win proxy). "
            "Lower the target, raise risk (drawdowns rise), or compound over more weeks. "
            "Opportunity set below is research only — no path is guaranteed."
        )

    return {
        "week_label": week_label,
        "capital": round(capital, 2),
        "target_gain_pct": target_gain_pct,
        "target_rupees": target_rupees,
        "risk_pct": round(risk_frac * 100.0, 4),
        "risk_rupees_per_trade": risk_rupees_per_trade,
        "max_positions": max_positions,
        "win_rate_proxy": win_rate_proxy,
        "expected_wins_proxy": expected_wins_proxy,
        "avg_setup_rr": round(rho, 3),
        "max_plausible_target_pct": max_plausible_T,
        "expected_plausible_target_pct": expected_plausible_T,
        "required_R": required_R,
        "required_R_multiple": required_R_multiple,
        "combined_theoretical_reward_rs": combined_max,
        "reachable": reachable,
        "message": message,
        "suggested_candidates": suggested,
        "disclaimer": (
            "Research / education only. Past patterns and R-math do not guarantee "
            "future results. Capital at risk."
        ),
    }
