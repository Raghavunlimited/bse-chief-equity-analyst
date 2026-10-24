"""Customer authentication — register / login / logout / me."""
from __future__ import annotations

from typing import Optional

import re

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.auth_deps import (
    _extract_token,
    get_current_user,
    get_optional_user,
    hash_password,
    platform,
    public_user,
    rate_limit,
    verify_password,
)
from app.config import config
from app.platform_db import PlatformDB

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Allow demo .local addresses; EmailStr rejects reserved TLDs.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterBody(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    display_name: Optional[str] = Field(None, max_length=80)

    @field_validator("email")
    @classmethod
    def valid_email(cls, v: str) -> str:
        email = v.strip().lower()
        if not _EMAIL_RE.match(email):
            raise ValueError("Invalid email format")
        return email


class LoginBody(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def valid_email(cls, v: str) -> str:
        email = v.strip().lower()
        if not _EMAIL_RE.match(email):
            raise ValueError("Invalid email format")
        return email


@router.get("/status")
def auth_status(user: Optional[dict] = Depends(get_optional_user)):
    return {
        "auth_enabled": config.auth_enabled,
        "authenticated": bool(user) if config.auth_enabled else True,
        "user": public_user(user) if user else None,
        "jurisdiction_note": config.jurisdiction_note,
    }


@router.post("/register")
def register(body: RegisterBody, request: Request, db: PlatformDB = Depends(platform)):
    rate_limit(request, "auth_register", limit=10, window_sec=60)
    if db.get_user_by_email(body.email):
        raise HTTPException(status_code=409, detail="Email already registered")
    user = db.create_user(
        email=str(body.email),
        password_hash=hash_password(body.password),
        role="customer",
        display_name=body.display_name,
    )
    token = db.create_session(user["id"], ttl_hours=config.session_ttl_hours)
    db.audit(user["id"], "auth.register", "user", user["id"], {})
    return {"token": token, "user": public_user(user)}


@router.post("/login")
def login(body: LoginBody, request: Request, db: PlatformDB = Depends(platform)):
    rate_limit(request, "auth_login", limit=15, window_sec=60)
    user = db.get_user_by_email(str(body.email))
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.get("is_active"):
        raise HTTPException(status_code=403, detail="Account disabled")
    token = db.create_session(user["id"], ttl_hours=config.session_ttl_hours)
    db.audit(user["id"], "auth.login", "user", user["id"], {})
    return {"token": token, "user": public_user(user)}


@router.post("/logout")
def logout(
    db: PlatformDB = Depends(platform),
    user: Optional[dict] = Depends(get_optional_user),
    authorization: Optional[str] = Header(None),
    x_session_token: Optional[str] = Header(None, alias="X-Session-Token"),
):
    token = _extract_token(authorization, x_session_token)
    if token:
        db.delete_session(token)
    if user:
        db.audit(user["id"], "auth.logout", "user", user["id"], {})
    return {"ok": True}


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return public_user(user)
