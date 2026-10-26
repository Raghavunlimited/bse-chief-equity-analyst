"""
Phase 7 — personal/local deployment posture (not enterprise hardening).

Defaults assume a single-operator research desk on loopback with AUTH off.
Public binds without auth require an explicit opt-in.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

from app.config import config

logger = logging.getLogger(__name__)

_DEFAULT_SECRET = "dev-only-change-me-swing-desk-32c"

# Expected core tables for SQLite personal desk (CREATE IF NOT EXISTS on use).
_REQUIRED_TABLES = frozenset(
    {
        "eod",
        "indicators",
        "screener_results",
        "expectancy_metrics",
        "bars_5m",
        "ingest_runs",
    }
)

_LOCAL_CORS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
)


def is_loopback_host(host: str) -> bool:
    h = (host or "").strip().lower()
    return h in ("127.0.0.1", "localhost", "::1")


def is_public_bind_host(host: str) -> bool:
    h = (host or "").strip().lower()
    if not h or is_loopback_host(h):
        return False
    return h in ("0.0.0.0", "::", "[::]", "*") or not is_loopback_host(h)


def secret_key_is_default() -> bool:
    return (config.secret_key or "").strip() == _DEFAULT_SECRET


def resolve_cors_origins() -> list[str]:
    """
    Auth-off personal desk: prefer localhost origins over ``*``.
    Explicit CORS_ORIGINS always wins. ``*`` only if operator sets it.
    """
    raw = (config.cors_origins or "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    if config.auth_enabled or config.allow_public_bind:
        # Operator opted into broader exposure — still prefer localhost until set
        return list(_LOCAL_CORS)
    return list(_LOCAL_CORS)


def security_posture() -> dict[str, Any]:
    """Public, secret-free summary for /api/health."""
    bind = config.bind_host
    public = is_public_bind_host(bind)
    return {
        "deployment_model": "personal_local_research_desk",
        "production_ready_claim": False,
        "auth_enabled": bool(config.auth_enabled),
        "bind_host": bind,
        "bind_is_loopback": is_loopback_host(bind),
        "allow_public_bind": bool(config.allow_public_bind),
        "unauthenticated_public_bind_blocked": (
            not config.auth_enabled and public and not config.allow_public_bind
        ),
        "cors_mode": (
            "explicit"
            if (config.cors_origins or "").strip()
            else "localhost_default_auth_off"
        ),
        "cors_origins_count": len(resolve_cors_origins()),
        "api_docs_enabled": bool(config.enable_api_docs),
        "api_key_gate_configured": bool(config.api_key),
        "api_key_gate": _api_key_gate_summary(),
        "secret_key_is_default": secret_key_is_default(),
        "demo_allowed": False,
        "note": (
            "AUTH_ENABLED=false is intentional for local personal use. "
            "Do not publish the API to a LAN/WAN without auth + non-default SECRET_KEY. "
            "This build is not claimed production-ready for multi-user or public hosting. "
            "When API_KEY is set, expensive POST /api/strategy-evaluation/evaluate "
            "(and GET ?run_harness=true) require X-API-Key; leave API_KEY empty on "
            "loopback for zero-friction personal UI."
        ),
    }


def _api_key_gate_summary() -> dict[str, Any]:
    from app.security import API_KEY_GATE_INVENTORY

    return {
        "configured": bool(config.api_key),
        # Never include the key value
        "inventory": API_KEY_GATE_INVENTORY,
    }


def assert_safe_boot() -> None:
    """
    Fail closed when auth-off desk would listen on a non-loopback host
    without ALLOW_PUBLIC_BIND=true.
    """
    bind = config.bind_host
    if (
        not config.auth_enabled
        and is_public_bind_host(bind)
        and not config.allow_public_bind
    ):
        raise RuntimeError(
            f"Refusing boot: AUTH_ENABLED=false and BIND_HOST={bind!r} would expose "
            "an unauthenticated desk. Bind to 127.0.0.1 (default) or set "
            "ALLOW_PUBLIC_BIND=true after enabling AUTH_ENABLED / API_KEY and a "
            "non-default SECRET_KEY."
        )
    if config.allow_public_bind and not config.auth_enabled and secret_key_is_default():
        logger.warning(
            "ALLOW_PUBLIC_BIND=true with AUTH_ENABLED=false and default SECRET_KEY — "
            "insecure for any shared network"
        )
    if secret_key_is_default() and not is_loopback_host(bind):
        logger.warning(
            "SECRET_KEY is still the example default — set a unique value in backend/.env"
        )
    posture = security_posture()
    logger.info(
        "deployment_posture model=%s auth=%s bind=%s loopback=%s docs=%s",
        posture["deployment_model"],
        posture["auth_enabled"],
        posture["bind_host"],
        posture["bind_is_loopback"],
        posture["api_docs_enabled"],
    )


def check_sqlite_schema(db_path: Path | None = None) -> dict[str, Any]:
    """
    Migration / presence check for SQLite personal DB.

    Ensures known schemas exist (idempotent CREATE IF NOT EXISTS), then reports
    which required tables are present. Not a versioned migration framework.
    """
    path = Path(db_path or config.db_path)
    # Ensure schemas
    try:
        from app.bars_5m import ensure_bars_5m_schema
        from app.ingest_journal import ensure_journal_schema
        from app.platform_db import PlatformDB
        from app.store import Database

        Database(path)
        ensure_bars_5m_schema(path)
        ensure_journal_schema(path)
        PlatformDB(path)
    except Exception as e:  # noqa: BLE001
        from app.kotak.tick_guard import sanitize_error_text

        return {
            "ok": False,
            "db_path_basename": path.name,
            "error": sanitize_error_text(e),
            "required_tables": sorted(_REQUIRED_TABLES),
            "present_tables": [],
            "missing_tables": sorted(_REQUIRED_TABLES),
        }

    present: set[str] = set()
    try:
        con = sqlite3.connect(str(path))
        try:
            rows = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            present = {str(r[0]) for r in rows}
        finally:
            con.close()
    except Exception as e:  # noqa: BLE001
        from app.kotak.tick_guard import sanitize_error_text

        return {
            "ok": False,
            "db_path_basename": path.name,
            "error": sanitize_error_text(e),
            "required_tables": sorted(_REQUIRED_TABLES),
            "present_tables": [],
            "missing_tables": sorted(_REQUIRED_TABLES),
        }

    missing = sorted(_REQUIRED_TABLES - present)
    return {
        "ok": len(missing) == 0,
        "db_path_basename": path.name,
        "engine": "sqlite",
        "required_tables": sorted(_REQUIRED_TABLES),
        "present_tables": sorted(present & _REQUIRED_TABLES),
        "missing_tables": missing,
        "note": (
            "SQLite personal desk — no Alembic. Schemas applied via CREATE IF NOT EXISTS. "
            "Backup with scripts/backup_sqlite.sh before risky upgrades."
        ),
    }


def env_bind_hint() -> str:
    return os.getenv("BIND_HOST", os.getenv("UVICORN_HOST", "127.0.0.1")).strip() or "127.0.0.1"
