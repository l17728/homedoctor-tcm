"""JWT verification middleware — extracts user info from Authorization header."""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.auth import decode_access_token
from app.repository import current_tenant_id

logger = logging.getLogger(__name__)


_PUBLIC_PREFIXES = (
    "/api/health",
    "/api/auth/register",
    "/api/auth/login",
    "/api/herbs/",
    "/api/formulas/",
    "/api/classics/",
    "/api/therapies/",
    "/api/triage/",
    "/api/herbs",
    "/api/formulas",
    "/api/classics",
    "/api/therapies",
    "/api/triage",
)


class AuthMiddleware(BaseHTTPMiddleware):
    """Extract JWT from Authorization header, set tenant_id in contextvar."""

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
        client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or (
            request.client.host if request.client else "unknown"
        )

        current_tenant_id.set("default")

        if path in self.PUBLIC_PATHS or request.method == "OPTIONS":
            return await call_next(request)

        if not path.startswith("/api/"):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            if any(path.startswith(p) for p in _PUBLIC_PREFIXES):
                return await call_next(request)
            logger.warning("AUTH_FAIL path=%s ip=%s reason=no_token", path, client_ip)
            return Response(
                content='{"detail":"未提供认证凭据"}',
                status_code=401,
                media_type="application/json",
            )

        token = auth_header[7:]
        try:
            payload = decode_access_token(token)
            family_id = payload.get("family_id", "default")
            username = payload.get("username", "")
            user_id = payload.get("sub", "")
            current_tenant_id.set(family_id)
            request.state.user = {
                "id": user_id,
                "username": username,
                "family_id": family_id,
            }
            logger.info("AUTH_OK user=%s tenant=%s path=%s ip=%s", username, family_id, path, client_ip)
        except Exception as exc:
            if any(path.startswith(p) for p in _PUBLIC_PREFIXES):
                return await call_next(request)
            logger.warning("AUTH_FAIL path=%s ip=%s reason=invalid_token error=%s", path, client_ip, exc)
            return Response(
                content='{"detail":"无效的认证凭据"}',
                status_code=401,
                media_type="application/json",
            )

        return await call_next(request)
