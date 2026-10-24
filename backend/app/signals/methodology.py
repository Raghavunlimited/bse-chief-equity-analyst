"""
Deterministic baseline signal methodology (transparent, not a profit claim).

baseline_v1 — explicit inputs and thresholds. Does NOT claim proven edge or
guaranteed returns. Insufficient evidence → direction=none.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

METHODOLOGY_ID = "baseline_v1"

METHODOLOGY_DOC = {
    "id": METHODOLOGY_ID,
    "name": "Baseline research rules v1",
    "disclaimer": (
        "These rules organize research evidence into buy / sell / none. "
        "They are not backtested performance claims and do not predict profit."
    ),
    "inputs": [
        "price vs SMA20 / SMA50 (when available)",
        "RSI(14) band",
        "volume vs 20-day average (when available)",
        "session / regime context when provided",
        "OI only when adapter returns available=true",
    ],
    "thresholds": {
        "rsi_buy_min": 45,
        "rsi_buy_max": 70,
        "rsi_sell_min": 70,
        "volume_confirm": 1.5,
        "min_evidence_fields": 2,
    },
}


def score_evidence(evidence: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return {direction, score, rationale, insufficient}.
    Missing/contradictory inputs → none (no forced call).
    """
    th = METHODOLOGY_DOC["thresholds"]
    fields_present = 0
    bull = 0
    bear = 0
    notes = []

    rsi = evidence.get("rsi_14")
    if rsi is not None:
        try:
            rsi_f = float(rsi)
            fields_present += 1
            if th["rsi_buy_min"] <= rsi_f <= th["rsi_buy_max"]:
                bull += 1
                notes.append(f"RSI {rsi_f:.1f} in constructive band")
            elif rsi_f >= th["rsi_sell_min"]:
                bear += 1
                notes.append(f"RSI {rsi_f:.1f} extended / overbought band")
            else:
                notes.append(f"RSI {rsi_f:.1f} neutral / weak for long bias")
        except (TypeError, ValueError):
            notes.append("RSI present but not numeric — ignored")

    price = evidence.get("close")
    sma20 = evidence.get("sma_20")
    if price is not None and sma20 is not None:
        try:
            px = float(price)
            sma = float(sma20)
            fields_present += 1
            if px > sma:
                bull += 1
                notes.append("Close above SMA20")
            else:
                bear += 1
                notes.append("Close at/below SMA20")
        except (TypeError, ValueError):
            notes.append("Price/SMA20 not numeric — ignored")

    vol_ratio = evidence.get("volume_ratio")
    if vol_ratio is not None:
        try:
            vr = float(vol_ratio)
            fields_present += 1
            if vr >= th["volume_confirm"]:
                notes.append(f"Volume ratio {vr:.2f} confirms interest")
                # volume confirms prevailing side; does not alone set direction
            else:
                notes.append(f"Volume ratio {vr:.2f} below confirmation threshold")
        except (TypeError, ValueError):
            notes.append("volume_ratio present but not numeric — ignored")

    oi = evidence.get("oi_available")
    if oi is True and evidence.get("oi_change") is not None:
        try:
            float(evidence.get("oi_change"))
            fields_present += 1
            notes.append("OI observation included (adapter-provided)")
        except (TypeError, ValueError):
            notes.append("OI flagged available but oi_change not numeric — ignored")
    elif evidence.get("oi_note"):
        notes.append(str(evidence["oi_note"]))

    if fields_present < th["min_evidence_fields"]:
        return {
            "methodology_id": METHODOLOGY_ID,
            "direction": "none",
            "score": 0,
            "insufficient": True,
            "rationale": "Insufficient reliable evidence for an actionable signal. "
            + "; ".join(notes[:4]),
        }

    if bull > bear + 0:
        direction = "buy"
        score = min(100, 50 + bull * 15)
    elif bear > bull + 0:
        direction = "sell"
        score = min(100, 50 + bear * 15)
    else:
        direction = "none"
        score = 40

    return {
        "methodology_id": METHODOLOGY_ID,
        "direction": direction,
        "score": score,
        "insufficient": direction == "none",
        "rationale": "; ".join(notes) or "No clear edge from baseline rules",
    }


def apply_baseline(
    symbol: str,
    category: str,
    evidence: Dict[str, Any],
    data_mode: str = "demo",
    timeframe: Optional[str] = None,
) -> Dict[str, Any]:
    graded = score_evidence(evidence)
    tf = timeframe or {
        "intraday": "session",
        "swing": "1w",
        "commodity": "1d",
    }.get(category, "1d")
    return {
        "symbol": symbol.upper(),
        "category": category,
        "direction": graded["direction"],
        "timeframe": tf,
        "rationale": graded["rationale"],
        "evidence": evidence,
        "methodology_id": METHODOLOGY_ID,
        "data_mode": data_mode,
        "risk_notes": (
            "Baseline rules are research heuristics only — not performance-verified. "
            "No guarantee of returns."
        ),
        "score": graded["score"],
        "insufficient": graded["insufficient"],
    }
