"""Risk-based position sizing API — research calculation only; no orders."""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import position_sizing as ps

router = APIRouter(prefix="/api/position-sizing", tags=["position-sizing"])


class SizeRequest(BaseModel):
    capital: float = Field(..., gt=0, description="Portfolio capital (INR)")
    risk_pct: float = Field(..., gt=0, le=100, description="Risk per idea as % of capital")
    entry: float = Field(..., gt=0)
    stop: Optional[float] = Field(None, description="Stop price (required for EQ/FUT)")
    direction: Literal["LONG", "SHORT"] = "LONG"
    instrument_kind: Literal["EQ", "FUT", "OPT", "MCX_PROXY", "UNKNOWN"] = "EQ"
    symbol: str = Field("", max_length=64)
    lot_size: Optional[int] = Field(None, gt=0)
    multiplier: Optional[float] = Field(None, gt=0)
    lot_size_verified: bool = False
    contract_mapping_verified: bool = False
    contract_source: str = Field("user_supplied", max_length=128)
    expiry: Optional[str] = Field(None, max_length=32)
    underlying: Optional[str] = Field(None, max_length=32)
    option_right: Optional[str] = Field(None, max_length=4)
    fixed_costs: float = Field(0, ge=0)
    cost_per_unit: float = Field(0, ge=0)
    cost_per_lot: float = Field(0, ge=0)
    round_trip_cost_pct: float = Field(0, ge=0, le=10)
    max_position_pct: Optional[float] = Field(None, gt=0, le=100)
    max_notional: Optional[float] = Field(None, gt=0)
    max_lots: Optional[int] = Field(None, ge=0)
    max_total_exposure_pct: Optional[float] = Field(None, gt=0, le=500)
    open_exposure_notional: float = Field(0, ge=0)
    margin_per_lot: Optional[float] = Field(None, gt=0)
    margin_verified: bool = False
    option_premium: Optional[float] = Field(None, gt=0)
    quote_stale: bool = False
    mapping_stale: bool = False


@router.get("/meta")
def sizing_meta() -> dict[str, Any]:
    return {
        "status": "ok",
        "disclaimer": ps.DISCLAIMER,
        "formula": ps.FORMULA_FIXED_FRACTIONAL,
        "is_order_instruction": False,
        "supported_kinds": ["EQ", "FUT", "OPT"],
        "unsupported_kinds": ["MCX_PROXY", "UNKNOWN"],
        "notes": [
            "Cash EQ: mark contract_mapping_verified; lot_size defaults to 1 share.",
            "FUT/OPT: require verified lot_size, multiplier, and contract mapping.",
            "FUT and short OPT also require verified margin_per_lot.",
            "Stale quote/mapping or missing stop → available=false (no fabricated size).",
        ],
    }


@router.post("/calculate")
def calculate(body: SizeRequest) -> dict[str, Any]:
    result = ps.calculate_size(
        capital=body.capital,
        risk_pct=body.risk_pct,
        entry=body.entry,
        stop=body.stop,
        direction=body.direction,
        instrument_kind=body.instrument_kind,
        symbol=body.symbol,
        lot_size=body.lot_size,
        multiplier=body.multiplier,
        lot_size_verified=body.lot_size_verified,
        contract_mapping_verified=body.contract_mapping_verified,
        contract_source=body.contract_source,
        expiry=body.expiry,
        underlying=body.underlying,
        option_right=body.option_right,
        fixed_costs=body.fixed_costs,
        cost_per_unit=body.cost_per_unit,
        cost_per_lot=body.cost_per_lot,
        round_trip_cost_pct=body.round_trip_cost_pct,
        max_position_pct=body.max_position_pct,
        max_notional=body.max_notional,
        max_lots=body.max_lots,
        max_total_exposure_pct=body.max_total_exposure_pct,
        open_exposure_notional=body.open_exposure_notional,
        margin_per_lot=body.margin_per_lot,
        margin_verified=body.margin_verified,
        option_premium=body.option_premium,
        quote_stale=body.quote_stale,
        mapping_stale=body.mapping_stale,
    )
    return {"status": "ok", **result}
