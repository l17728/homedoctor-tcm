"""CSRF middleware — Origin check for write operations."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class CsrfMiddleware(BaseHTTPMiddleware):
    """Check Origin header for write operations (POST/PUT/DELETE/PATCH)."""

    # Allowed origins for local deployment
    ALLOWED_ORIGINS = {
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    }

    async def dispatch(self, request: Request, call_next):
        # Only check write operations
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            origin = request.headers.get("Origin", "")
            # Allow requests without Origin header (CLI, curl, tests)
            if origin and origin not in self.ALLOWED_ORIGINS:
                return Response(
                    content='{"detail":"请求来源不被允许"}',
                    status_code=403,
                    media_type="application/json",
                )

        return await call_next(request)
