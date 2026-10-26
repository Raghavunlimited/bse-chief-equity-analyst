"""POST /api/analyze — optional LLM research notes (vault key or ephemeral BYOK)."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.auth_deps import get_optional_user, rate_limit
from app.llm_analyze import (
    DISCLAIMER,
    LOCAL_KEY_SENTINEL,
    LlmAnalyzeError,
    analyze_signal,
    assert_loopback_base_url,
)
from app.platform_db import PlatformDB
from app.config import config

router = APIRouter(prefix="/api", tags=["analyze"])
logger = logging.getLogger(__name__)

MAX_SIGNAL_BYTES = 32_768
MAX_CONTEXT_BYTES = 32_768
MAX_API_KEY_LEN = 256
MIN_API_KEY_LEN = 8

ProviderName = Literal["openai", "anthropic", "local"]


def _json_size(obj: Any) -> int:
    return len(json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"))


class AnalyzeRequest(BaseModel):
    provider: Optional[ProviderName] = None
    model: Optional[str] = Field(
        None,
        max_length=80,
        description="Optional model id e.g. claude-opus-4-20250514, gpt-4o, or llama3.2",
    )
    api_key: Optional[str] = Field(
        None,
        max_length=MAX_API_KEY_LEN,
        description="Ephemeral BYOK — not required for provider=local (Ollama/LM Studio)",
    )
    signal: Dict[str, Any]
    context: Optional[Dict[str, Any]] = None
    use_stored_key: bool = Field(
        True,
        description="If true and no api_key in body, use encrypted vault key for this user",
    )
    local_base_url: Optional[str] = Field(
        None,
        max_length=200,
        description="Override LOCAL_LLM_BASE_URL — loopback host only",
    )

    @field_validator("api_key")
    @classmethod
    def strip_key(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        key = v.strip()
        return key or None

    @field_validator("signal")
    @classmethod
    def signal_size(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        if not v:
            raise ValueError("signal must be a non-empty object")
        if _json_size(v) > MAX_SIGNAL_BYTES:
            raise ValueError(f"signal exceeds {MAX_SIGNAL_BYTES} bytes")
        return v

    @field_validator("context")
    @classmethod
    def context_size(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if v is None:
            return v
        if _json_size(v) > MAX_CONTEXT_BYTES:
            raise ValueError(f"context exceeds {MAX_CONTEXT_BYTES} bytes")
        return v


def _resolve_credentials(
    req: AnalyzeRequest,
    user: Optional[dict],
) -> tuple[str, str, Optional[str], str]:
    """
    Returns (provider, api_key, model, key_source).
    Never logs api_key. Local provider may omit a key.
    """
    provider = (req.provider or "openai").lower().strip()

    if provider == "local" and not req.api_key:
        # Ollama / LM Studio typically ignore Authorization; sentinel is not a secret.
        return "local", LOCAL_KEY_SENTINEL, req.model, "local_no_key"

    if req.api_key:
        if provider != "local" and len(req.api_key) < MIN_API_KEY_LEN:
            raise HTTPException(status_code=422, detail="api_key too short")
        return provider, req.api_key, req.model, "ephemeral_body"

    if req.use_stored_key and user and user.get("id") and user["id"] != "local-dev":
        db = PlatformDB(config.db_path)
        stored = db.get_llm_api_key(user["id"])
        if stored:
            stored_provider, key, model = stored
            return (
                req.provider or stored_provider,
                key,
                req.model or model,
                "server_vault",
            )

    if provider == "local":
        return "local", LOCAL_KEY_SENTINEL, req.model, "local_no_key"

    raise HTTPException(
        status_code=422,
        detail=(
            "No LLM API key available. Configure one via Settings "
            "(stored encrypted server-side), pass api_key in the request body, "
            "or use provider=local with Ollama/LM Studio on loopback."
        ),
    )


@router.post("/analyze")
def post_analyze(
    req: AnalyzeRequest,
    request: Request,
    user: Optional[dict] = Depends(get_optional_user),
):
    """Explicit opt-in LLM research notes — commentary only, not an authoritative signal."""
    if config.auth_enabled and not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    rate_limit(request, "analyze", limit=20, window_sec=60)
    provider, api_key, model, key_source = _resolve_credentials(req, user)

    logger.info(
        "POST /api/analyze provider=%s model=%s key_source=%s signal_keys=%s has_context=%s client=%s",
        provider,
        model or "default",
        key_source,
        sorted(req.signal.keys())[:20],
        req.context is not None,
        request.client.host if request.client else "?",
    )
    local_url = None
    if provider == "local":
        try:
            local_url = assert_loopback_base_url(
                req.local_base_url or config.local_llm_base_url
            )
        except LlmAnalyzeError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    try:
        analysis = analyze_signal(
            req.signal,
            provider,
            api_key,
            context=req.context,
            model=model,
            local_base_url=local_url,
        )
    except LlmAnalyzeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("LLM analyze failed (api_key=[redacted])")
        raise HTTPException(status_code=502, detail="LLM analysis failed") from exc

    cited_inputs = {
        "signal_keys": sorted(req.signal.keys()),
        "context_keys": sorted((req.context or {}).keys()),
        "provider": provider,
        "model": model,
    }

    return {
        "status": "ok",
        "analysis": analysis,
        "ai_generated": True,
        "label": "AI-GENERATED COMMENTARY — not an authoritative trading signal",
        "cited_inputs": cited_inputs,
        "key_source": key_source,
        "disclaimer": DISCLAIMER,
        **{
            k: analysis[k]
            for k in ("summary", "bull_case", "bear_case", "risks", "checklist")
            if k in analysis
        },
    }
