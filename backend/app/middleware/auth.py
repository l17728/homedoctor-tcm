"""JWT verification middleware — extracts user info from Authorization header."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.auth import decode_access_token
from app.repository import current_tenant_id


class AuthMiddleware(BaseHTTPMiddleware):
    """Extract JWT from Authorization header, set tenant_id in contextvar."""

    # Paths that don't require authentication
    PUBLIC_PATHS = {
        "/api/health",
        "/api/auth/register",
        "/api/auth/login",
        "/docs",
        "/openapi.json",
        "/redoc",
    }

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Set default tenant
        current_tenant_id.set("default")

        # Skip auth for public paths and preflight requests
        if path in self.PUBLIC_PATHS or request.method == "OPTIONS":
            return await call_next(request)

        # Skip auth for non-API paths
        if not path.startswith("/api/"):
            return await call_next(request)

        # Try to extract token
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = decode_access_token(token)
                # Set tenant_id from JWT family_id
                family_id = payload.get("family_id", "default")
                current_tenant_id.set(family_id)
                # Store user info in request state
                request.state.user = {
                    "id": payload.get("sub"),
                    "username": payload.get("username"),
                    "family_id": family_id,
                }
            except Exception:
                # Invalid token — for read-only endpoints, still allow access
                # (herbs, formulas are public knowledge)
                if path.startswith("/api/herbs") or path.startswith("/api/formulas"):
                    return await call_next(request)
                # For other endpoints, return 401
                return Response(
                    content='{"detail":"无效的认证凭据"}',
                    status_code=401,
                    media_type="application/json",
                )

        return await call_next(request)
