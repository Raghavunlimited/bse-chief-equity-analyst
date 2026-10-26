"""Live option chain / PCR / OI buildup API."""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/kotak/option-chain", tags=["option-chain"])


class ActivateBody(BaseModel):
    underlying: str = Field(..., examples=["NIFTY", "BANKNIFTY", "RELIANCE"])
    expiry: Optional[str] = None
    expiry_mode: Literal["nearest", "weekly", "monthly"] = "nearest"
    wing: int = Field(15, ge=1, le=40)
    exchange_segment: str = "nse_fo"
    spot_hint: Optional[float] = None


@router.get("/status")
def chain_status(underlying: Optional[str] = None) -> dict[str, Any]:
    """Option chain / PCR availability — optional; inactive until Kotak activate."""
    from app.kotak.option_chain import get_option_chain_engine

    st = get_option_chain_engine().status(underlying)
    active = bool(st.get("active")) if isinstance(st, dict) else False
    if isinstance(st, dict) and underlying and "active" not in st:
        # Multi-underlying map — leave as-is but add honesty envelope
        return {
            **st,
            "feature": "kotak_option_chain",
            "verified_in_ci": False,
            "requires": ["kotak_session_login", "activate"],
            "note": (
                "PCR / walls / Greeks only when a chain is activated after "
                "Kotak Neo login. Idle = unavailable, not zero PCR."
            ),
        }
    return {
        **(st if isinstance(st, dict) else {"raw": st}),
        "available": active,
        "status": "ok" if active else "unavailable",
        "feature": "kotak_option_chain",
        "verified_in_ci": False,
        "requires": ["kotak_session_login", "activate"],
        "reason": None
        if active
        else "chain_inactive_activate_after_kotak_login",
        "note": (
            "PCR / walls / Greeks only when a chain is activated after "
            "Kotak Neo login. Idle = unavailable, not zero PCR."
        ),
    }


@router.post("/activate")
def activate_chain(body: ActivateBody) -> dict[str, Any]:
    from app.kotak.option_chain import get_option_chain_engine

    try:
        return get_option_chain_engine().activate(
            body.underlying,
            expiry=body.expiry,
            expiry_mode=body.expiry_mode,
            wing=body.wing,
            exchange_segment=body.exchange_segment,
            spot_hint=body.spot_hint,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/{underlying}/expiries")
def list_expiries(underlying: str, exchange_segment: str = "nse_fo") -> dict[str, Any]:
    from app.kotak.option_chain import pick_expiry
    from app.kotak.scrip_master import get_scrip_master

    sm = get_scrip_master()
    sm.ensure_loaded()
    exps = sm.list_expiries(underlying, kind="OPT", exchange_segment=exchange_segment)
    nearest = weekly = monthly = None
    try:
        nearest = pick_expiry(
            underlying, mode="nearest", exchange_segment=exchange_segment
        ).isoformat()
        weekly = pick_expiry(
            underlying, mode="weekly", exchange_segment=exchange_segment
        ).isoformat()
        monthly = pick_expiry(
            underlying, mode="monthly", exchange_segment=exchange_segment
        ).isoformat()
    except LookupError:
        pass
    return {
        "underlying": underlying.upper(),
        "expiries": exps,
        "nearest": nearest,
        "weekly": weekly,
        "monthly": monthly,
        "oi_included": False,
        "note": (
            "Expiry catalog from scrip master only — OI/volume/IV require "
            "an activated Kotak WS chain for that expiry."
        ),
    }


@router.get("/{underlying}/oi-viz")
def oi_visualization(underlying: str) -> dict[str, Any]:
    """
    Call/put OI comparison payload with field-level availability.

    Does not invent OI. Inactive chain → available=false (HTTP 200 with
    honest unavailable body — not fake zeros).
    """
    from app.options_oi import build_oi_visualization

    return build_oi_visualization(underlying)


@router.get("/{underlying}/analytics")
def get_analytics(underlying: str) -> dict[str, Any]:
    from app.kotak.option_chain import get_option_chain_engine

    try:
        snap = get_option_chain_engine().snapshot(underlying)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {
        "underlying": snap["underlying"],
        "expiry": snap["expiry"],
        "spot": snap["spot"],
        "atm": snap["atm"],
        "analytics": snap["analytics"],
        "future": snap.get("future"),
        "as_of": snap["as_of"],
        "signal_disclaimer": (
            "PCR / walls / max-pain are descriptive research metrics — "
            "not standalone trading signals."
        ),
    }


@router.get("/{underlying}")
def get_chain(
    underlying: str,
    activate_if_needed: bool = Query(
        False,
        description="If true, auto-activate nearest expiry when no chain is live",
    ),
    expiry_mode: Literal["nearest", "weekly", "monthly"] = "nearest",
    wing: int = Query(15, ge=1, le=40),
) -> dict[str, Any]:
    from app.kotak.option_chain import get_option_chain_engine

    eng = get_option_chain_engine()
    try:
        return eng.snapshot(underlying)
    except LookupError:
        if not activate_if_needed:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No active chain for {underlying}. "
                    "Activate first or pass activate_if_needed=true"
                ),
            )
        try:
            return eng.activate(underlying, expiry_mode=expiry_mode, wing=wing)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
