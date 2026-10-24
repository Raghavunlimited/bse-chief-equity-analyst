"""Admin: instruments, signal publication, settings, audit trail."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth_deps import platform, require_admin
from app.platform_db import PlatformDB

router = APIRouter(prefix="/api/admin", tags=["admin"])

Direction = Literal["buy", "sell", "none"]
Category = Literal["intraday", "swing", "commodity"]
DataMode = Literal["live", "delayed", "stale", "demo"]
Status = Literal["draft", "published", "expired", "revised"]


class InstrumentBody(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    category: Category
    name: Optional[str] = Field(None, max_length=120)
    market: str = Field("NSE", max_length=32)
    is_active: bool = True
    metadata: Optional[Dict[str, Any]] = None


class PublishSignalBody(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    category: Category
    direction: Direction
    timeframe: str = Field(min_length=1, max_length=32)
    rationale: str = Field(min_length=1, max_length=4000)
    evidence: Optional[Dict[str, Any]] = None
    provenance: Optional[Dict[str, Any]] = None
    risk_notes: str = Field(
        default="Research only — not a guarantee of returns. Verify independently.",
        max_length=2000,
    )
    methodology_id: str = Field(default="baseline_v1", max_length=64)
    data_mode: DataMode = "demo"
    expires_in_hours: Optional[int] = Field(None, ge=1, le=24 * 30)
    status: Status = "published"
    instrument_id: Optional[str] = None


class ReviseSignalBody(BaseModel):
    direction: Optional[Direction] = None
    timeframe: Optional[str] = Field(None, max_length=32)
    rationale: Optional[str] = Field(None, max_length=4000)
    evidence: Optional[Dict[str, Any]] = None
    provenance: Optional[Dict[str, Any]] = None
    risk_notes: Optional[str] = Field(None, max_length=2000)
    data_mode: Optional[DataMode] = None
    expires_in_hours: Optional[int] = Field(None, ge=1, le=24 * 30)
    status: Optional[Status] = "published"


class SettingBody(BaseModel):
    value: Any


@router.get("/instruments")
def admin_list_instruments(
    category: Optional[Category] = None,
    admin: dict = Depends(require_admin),
    db: PlatformDB = Depends(platform),
):
    return {"instruments": db.list_instruments(category=category, active_only=False)}


@router.post("/instruments")
def admin_upsert_instrument(
    body: InstrumentBody,
    admin: dict = Depends(require_admin),
    db: PlatformDB = Depends(platform),
):
    inst = db.upsert_instrument(
        symbol=body.symbol,
        category=body.category,
        name=body.name,
        market=body.market,
        is_active=body.is_active,
        metadata=body.metadata,
    )
    db.audit(admin["id"], "instrument.upsert", "instrument", inst["id"], {"symbol": body.symbol})
    return inst


@router.post("/signals")
def admin_publish_signal(
    body: PublishSignalBody,
    admin: dict = Depends(require_admin),
    db: PlatformDB = Depends(platform),
):
    expires_at = None
    if body.expires_in_hours:
        expires_at = (
            datetime.now(timezone.utc) + timedelta(hours=body.expires_in_hours)
        ).replace(microsecond=0).isoformat()
    payload = body.model_dump()
    payload.pop("expires_in_hours", None)
    payload["expires_at"] = expires_at
    payload["provenance"] = body.provenance or {
        "data_mode": body.data_mode,
        "source": "admin_publish",
        "note": "Published via admin workflow",
    }
    return db.publish_signal(payload, actor_id=admin["id"])


@router.post("/signals/{signal_id}/revise")
def admin_revise_signal(
    signal_id: str,
    body: ReviseSignalBody,
    admin: dict = Depends(require_admin),
    db: PlatformDB = Depends(platform),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    hours = updates.pop("expires_in_hours", None)
    if hours:
        updates["expires_at"] = (
            datetime.now(timezone.utc) + timedelta(hours=hours)
        ).replace(microsecond=0).isoformat()
    try:
        return db.revise_signal(signal_id, updates, actor_id=admin["id"])
    except KeyError:
        raise HTTPException(status_code=404, detail="Signal not found") from None


@router.get("/audit")
def admin_audit(
    limit: int = 100,
    admin: dict = Depends(require_admin),
    db: PlatformDB = Depends(platform),
):
    return {"entries": db.list_audit(limit=limit)}


@router.put("/settings/{key}")
def admin_set_setting(
    key: str,
    body: SettingBody,
    admin: dict = Depends(require_admin),
    db: PlatformDB = Depends(platform),
):
    if len(key) > 64 or not key.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(status_code=422, detail="Invalid setting key")
    db.set_setting(key, body.value, actor_id=admin["id"])
    return {"key": key, "value": body.value}


@router.get("/settings/{key}")
def admin_get_setting(
    key: str,
    admin: dict = Depends(require_admin),
    db: PlatformDB = Depends(platform),
):
    return {"key": key, "value": db.get_setting(key)}
