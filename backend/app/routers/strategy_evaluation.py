"""Strategy evaluation API — research evidence only; never crowns a winner."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app import strategy_evaluation as se
from app.config import config
from app.expectancy.gate import STRONG_GATES
from app.store import Database

router = APIRouter(prefix="/api/strategy-evaluation", tags=["strategy-evaluation"])
db = Database(config.db_path)


class EvaluateRequest(BaseModel):
    rules: Optional[list[str]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    oos_fraction: float = Field(0.3, ge=0.1, le=0.5)
    run_harness: bool = True


@router.get("/meta")
def evaluation_meta() -> dict[str, Any]:
    from app.security import API_KEY_GATE_INVENTORY

    return {
        "status": "ok",
        "strategy_evaluation_version": se.STRATEGY_VERSION,
        "disclaimer": se.DISCLAIMER,
        "selects_best": False,
        "proven": False,
        "catalog": se.CANDIDATE_CATALOG,
        "gates": STRONG_GATES,
        "cost_model": se.cost_assumptions_public(),
        "bias_checklist": se.bias_checklist(),
        "honesty": {
            "selects_best": False,
            "labels_proven": False,
            "oi_pcr_directional": False,
            "guarantees_returns": False,
        },
        "access": {
            "api_key_gate_configured": bool(config.api_key),
            "evaluate_requires_api_key_when_configured": True,
            "get_run_harness_requires_api_key_when_configured": True,
            "meta_audit_summary_open": True,
            "auth_enabled": bool(config.auth_enabled),
            "inventory": API_KEY_GATE_INVENTORY,
            "local_dev_note": (
                "Leave API_KEY empty on loopback so the UI 'Run walk-forward' "
                "button works without a header. When API_KEY is set, send "
                "X-API-Key on POST /evaluate (and GET ?run_harness=true)."
            ),
        },
    }


@router.get("/audit")
def evaluation_audit() -> dict[str, Any]:
    return {"status": "ok", "disclaimer": se.DISCLAIMER, **se.audit_availability(db)}


@router.get("")
@router.get("/")
def evaluation_summary(
    run_harness: bool = Query(
        False,
        description="If true, runs walk-forward (slow). Default: stored metrics + audit.",
    ),
) -> dict[str, Any]:
    return se.build_evaluation_report(db, run_harness=run_harness)


@router.post("/evaluate")
def evaluation_run(body: EvaluateRequest = EvaluateRequest()) -> dict[str, Any]:
    try:
        from universe import SECTOR_MAP
    except Exception:  # noqa: BLE001
        SECTOR_MAP = {}
    return se.build_evaluation_report(
        db,
        rules=body.rules,
        start_date=body.start_date,
        end_date=body.end_date,
        oos_fraction=body.oos_fraction,
        run_harness=body.run_harness,
        sector_map=SECTOR_MAP,
    )
