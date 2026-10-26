"""Server-side encrypted LLM API key vault — never return plaintext to browser."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.auth_deps import get_current_user, platform, rate_limit
from app.platform_db import PlatformDB

router = APIRouter(prefix="/api/me/llm", tags=["llm-vault"])

Provider = Literal["openai", "anthropic", "local"]


class LlmKeyBody(BaseModel):
    provider: Provider
    # Local provider may store a sentinel; cloud keys stay min 8 chars (validated below).
    api_key: str = Field(min_length=1, max_length=256)
    model: Optional[str] = Field(None, max_length=80)

    @field_validator("api_key")
    @classmethod
    def strip_key(cls, v: str) -> str:
        return v.strip()


@router.get("")
def llm_status(user: dict = Depends(get_current_user), db: PlatformDB = Depends(platform)):
    """Metadata only — never includes api_key."""
    meta = db.get_llm_secret_meta(user["id"])
    return {**meta, "api_key": None, "note": "API key is stored encrypted server-side and never returned"}


@router.put("")
def llm_put(
    body: LlmKeyBody,
    request: Request,
    user: dict = Depends(get_current_user),
    db: PlatformDB = Depends(platform),
):
    rate_limit(request, "llm_vault", limit=10, window_sec=60)
    if user.get("id") == "local-dev":
        raise HTTPException(
            status_code=400,
            detail="Enable AUTH_ENABLED and sign in to store an LLM key",
        )
    key = body.api_key.strip()
    if body.provider != "local" and len(key) < 8:
        raise HTTPException(status_code=422, detail="api_key too short")
    if body.provider == "local" and not key:
        key = "local-no-key-required"
    return db.set_llm_secret(
        user_id=user["id"],
        provider=body.provider,
        api_key=key,
        model=body.model,
    )


@router.delete("")
def llm_delete(user: dict = Depends(get_current_user), db: PlatformDB = Depends(platform)):
    if user.get("id") == "local-dev":
        return {"ok": True, "configured": False}
    db.delete_llm_secret(user["id"])
    return {"ok": True, "configured": False}
