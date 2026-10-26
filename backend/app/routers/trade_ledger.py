"""Manual trade journal + capital API — user-entered records only."""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app import trade_ledger as ledger

router = APIRouter(prefix="/api/ledger", tags=["ledger"])


class CapitalIn(BaseModel):
    kind: Literal["starting_capital", "deposit", "withdrawal"]
    amount: float = Field(..., ge=0)
    occurred_at: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=2000)


class CapitalCorrectIn(BaseModel):
    amount: float = Field(..., ge=0)
    reason: str = Field(..., min_length=3, max_length=500)
    notes: Optional[str] = Field(None, max_length=2000)
    occurred_at: Optional[str] = None


class TradeOpenIn(BaseModel):
    instrument: str = Field(..., min_length=1, max_length=32)
    direction: Literal["LONG", "SHORT"]
    quantity: float = Field(..., gt=0)
    entry_price: float = Field(..., gt=0)
    entry_at: Optional[str] = None
    lots: Optional[float] = Field(None, ge=0)
    fees: float = Field(0, ge=0)
    notes: Optional[str] = Field(None, max_length=4000)


class TradeExitIn(BaseModel):
    quantity: float = Field(..., gt=0)
    price: float = Field(..., gt=0)
    exited_at: Optional[str] = None
    fees: float = Field(0, ge=0)
    notes: Optional[str] = Field(None, max_length=2000)


class TradeCorrectIn(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)
    notes: Optional[str] = Field(None, max_length=4000)
    entry_price: Optional[float] = Field(None, gt=0)
    lots: Optional[float] = Field(None, ge=0)


class SoftDeleteIn(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


@router.get("/summary")
def get_summary() -> dict[str, Any]:
    return {
        "status": "ok",
        **ledger.capital_summary(),
    }


@router.get("/trades")
def get_trades(
    status: Optional[Literal["open", "closed"]] = None,
    include_inactive: bool = False,
) -> dict[str, Any]:
    trades = ledger.list_trades(status=status, include_inactive=include_inactive)
    return {
        "status": "ok",
        "count": len(trades),
        "trades": trades,
        "disclaimer": ledger.DISCLAIMER,
        "source_label": ledger.SOURCE_LABEL,
    }


@router.post("/trades")
def post_trade(body: TradeOpenIn) -> dict[str, Any]:
    try:
        trade = ledger.open_trade(
            instrument=body.instrument,
            direction=body.direction,
            quantity=body.quantity,
            entry_price=body.entry_price,
            entry_at=body.entry_at,
            lots=body.lots,
            fees=body.fees,
            notes=body.notes,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"status": "ok", "trade": trade, "disclaimer": ledger.DISCLAIMER}


@router.post("/trades/{trade_id}/exits")
def post_exit(trade_id: str, body: TradeExitIn) -> dict[str, Any]:
    try:
        out = ledger.record_exit(
            trade_id,
            quantity=body.quantity,
            price=body.price,
            exited_at=body.exited_at,
            fees=body.fees,
            notes=body.notes,
        )
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"status": "ok", **out}


@router.patch("/trades/{trade_id}")
def patch_trade(trade_id: str, body: TradeCorrectIn) -> dict[str, Any]:
    try:
        trade = ledger.correct_trade(
            trade_id,
            reason=body.reason,
            notes=body.notes,
            entry_price=body.entry_price,
            lots=body.lots,
        )
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"status": "ok", "trade": trade}


@router.post("/trades/{trade_id}/soft-delete")
def delete_trade(trade_id: str, body: SoftDeleteIn) -> dict[str, Any]:
    try:
        out = ledger.soft_delete_trade(trade_id, reason=body.reason)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"status": "ok", **out}


@router.get("/capital/movements")
def get_movements(include_inactive: bool = False) -> dict[str, Any]:
    moves = ledger.list_capital_movements(include_inactive=include_inactive)
    return {
        "status": "ok",
        "count": len(moves),
        "movements": moves,
        "disclaimer": ledger.DISCLAIMER,
    }


@router.post("/capital/movements")
def post_movement(body: CapitalIn) -> dict[str, Any]:
    try:
        move = ledger.add_capital_movement(
            kind=body.kind,
            amount=body.amount,
            occurred_at=body.occurred_at,
            notes=body.notes,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"status": "ok", "movement": move, "disclaimer": ledger.DISCLAIMER}


@router.post("/capital/movements/{movement_id}/correct")
def correct_movement(movement_id: str, body: CapitalCorrectIn) -> dict[str, Any]:
    try:
        move = ledger.correct_capital_movement(
            movement_id,
            amount=body.amount,
            reason=body.reason,
            notes=body.notes,
            occurred_at=body.occurred_at,
        )
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"status": "ok", "movement": move, "disclaimer": ledger.DISCLAIMER}


@router.get("/audit")
def get_audit(limit: int = Query(100, ge=1, le=500)) -> dict[str, Any]:
    rows = ledger.list_audit(limit=limit)
    return {
        "status": "ok",
        "count": len(rows),
        "events": rows,
        "note": "Correction history retained — prior values soft-superseded, not erased.",
    }
