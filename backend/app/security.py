"""Optional API key gate for mutating routes when API_KEY is set."""
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
)
_PROTECTED_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not config.api_key:
            return await call_next(request)

        path = request.url.path
        method = request.method.upper()
        needs = method in _PROTECTED_METHODS and any(
            path == p or path.startswith(p.rstrip("/") + "/") or path.startswith(p)
            for p in _PROTECTED_PREFIXES
        )
        # Journal writes
        if method == "POST" and (
            path.rstrip("/") == "/api/journal" or path.startswith("/api/journal/")
        ):
            needs = True

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
