"""Tenant middleware — ensures tenant_id is set from JWT context."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.repository import current_tenant_id


class TenantMiddleware(BaseHTTPMiddleware):
    """Set tenant_id in contextvar from request state (populated by AuthMiddleware)."""

    async def dispatch(self, request: Request, call_next):
        # AuthMiddleware already sets tenant_id, but this is a safety net
        # for routes that might need it
        user = getattr(request.state, "user", None)
        if user and user.get("family_id"):
            current_tenant_id.set(user["family_id"])
        else:
            current_tenant_id.set("default")

        response = await call_next(request)
        return response
