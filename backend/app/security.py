"""Optional API key gate for mutating / expensive routes when API_KEY is set."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import config

# Paths that require X-API-Key when config.api_key is non-empty
_PROTECTED_PREFIXES = (
    "/api/ingest",
    "/api/backtest",
    "/api/feeds/kotak/test",
    "/api/kotak/session/login",
    "/api/ledger",
)
# Expensive strategy walk-forward — POST body or GET ?run_harness=true
_PROTECTED_POST_PATHS = frozenset({"/api/strategy-evaluation/evaluate"})
_PROTECTED_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Secret-free inventory for health / meta (no key material)
API_KEY_GATE_INVENTORY = {
    "when": "API_KEY env non-empty",
    "header": "X-API-Key",
    "prefixes": list(_PROTECTED_PREFIXES),
    "post_paths": sorted(_PROTECTED_POST_PATHS),
    "also": [
        "POST /api/journal",
        "GET /api/strategy-evaluation?run_harness=true",
    ],
    "not_gated": [
        "GET /api/strategy-evaluation/meta",
        "GET /api/strategy-evaluation/audit",
        "GET /api/strategy-evaluation?run_harness=false",
        "POST /api/analyze (uses vault/BYOK separately)",
        "POST /api/position-sizing/calculate",
    ],
    "local_default": "API_KEY empty → gate off (personal loopback)",
}


def _truthy_query(value: str | None) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def path_requires_api_key(method: str, path: str, *, run_harness: str | None = None) -> bool:
    """Pure helper for tests — mirrors middleware matching."""
    method = method.upper()
    path_n = path.rstrip("/") or path
    if method in _PROTECTED_METHODS and any(
        path == p or path.startswith(p.rstrip("/") + "/") or path.startswith(p)
        for p in _PROTECTED_PREFIXES
    ):
        return True
    if method == "POST" and path_n in _PROTECTED_POST_PATHS:
        return True
    if method == "POST" and (
        path_n == "/api/journal" or path.startswith("/api/journal/")
    ):
        return True
    # Same expensive harness as POST /evaluate
    if method == "GET" and path_n in {
        "/api/strategy-evaluation",
    } and _truthy_query(run_harness):
        return True
    return False


class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not config.api_key:
            return await call_next(request)

        path = request.url.path
        method = request.method.upper()
        run_harness = request.query_params.get("run_harness")
        needs = path_requires_api_key(method, path, run_harness=run_harness)

        if needs:
            provided = (
                request.headers.get("X-API-Key")
                or request.headers.get("x-api-key")
                or ""
            ).strip()
            if provided != config.api_key:
                return JSONResponse(
                    {"detail": "Invalid or missing X-API-Key"},
                    status_code=401,
                )
        return await call_next(request)
