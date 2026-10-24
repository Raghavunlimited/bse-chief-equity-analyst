"""Password hashing, session auth, RBAC dependencies, simple rate limiting."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional

import bcrypt
from fastapi import Depends, Header, HTTPException, Request

from app.config import config
from app.platform_db import PlatformDB


def platform() -> PlatformDB:
    return PlatformDB(config.db_path)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except Exception:
        return False


def _extract_token(
    authorization: Optional[str], x_session_token: Optional[str]
) -> Optional[str]:
    if x_session_token and x_session_token.strip():
        return x_session_token.strip()
    if authorization:
        auth = authorization.strip()
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        return auth
    return None


def get_optional_user(
    authorization: Optional[str] = Header(None),
    x_session_token: Optional[str] = Header(None, alias="X-Session-Token"),
    db: PlatformDB = Depends(platform),
) -> Optional[dict]:
    token = _extract_token(authorization, x_session_token)
    if not token:
        return None
    return db.get_session_user(token)


def get_current_user(
    user: Optional[dict] = Depends(get_optional_user),
) -> dict:
    if not config.auth_enabled:
        # Dev bypass: synthetic admin when auth off
        return {
            "id": "local-dev",
            "email": "dev@local",
            "role": "admin",
            "display_name": "Local Dev",
            "is_active": 1,
        }
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return user


def public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "role": user["role"],
        "display_name": user.get("display_name"),
    }


# ---- in-memory rate limiter (per-process; fine for MVP) ----
_buckets: Dict[str, Deque[float]] = defaultdict(deque)


def rate_limit(request: Request, key: str, limit: int = 20, window_sec: int = 60) -> None:
    ip = request.client.host if request.client else "unknown"
    bucket_key = f"{key}:{ip}"
    now = time.time()
    q = _buckets[bucket_key]
    while q and now - q[0] > window_sec:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(status_code=429, detail="Too many requests — try again later")
    q.append(now)
