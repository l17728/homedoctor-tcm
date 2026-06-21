"""CSRF middleware — Origin check for write operations."""

from __future__ import annotations

import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


def _build_allowed_origins() -> set[str]:
    """Build allowed origins from defaults + env var EXTRA_ALLOWED_ORIGINS."""
    defaults = {
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    }
    extra = os.environ.get("EXTRA_ALLOWED_ORIGINS", "")
    if extra:
        for origin in extra.split(","):
            origin = origin.strip()
            if origin:
                defaults.add(origin)
    return defaults


class CsrfMiddleware(BaseHTTPMiddleware):
    """Check Origin header for write operations (POST/PUT/DELETE/PATCH)."""

    ALLOWED_ORIGINS = _build_allowed_origins()

    async def dispatch(self, request: Request, call_next):
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            origin = request.headers.get("Origin", "")
            if origin and origin not in self.ALLOWED_ORIGINS:
                return Response(
                    content='{"detail":"请求来源不被允许"}',
                    status_code=403,
                    media_type="application/json",
                )

        return await call_next(request)
