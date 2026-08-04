"""Tenant middleware — ensures tenant_id is set from JWT context."""

from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.repository import current_tenant_id, current_member_id

logger = logging.getLogger(__name__)


class TenantMiddleware(BaseHTTPMiddleware):
    """Set tenant_id and member_id contextvars for each request."""

    async def dispatch(self, request: Request, call_next):
        user = getattr(request.state, "user", None)
        if user and user.get("family_id"):
            current_tenant_id.set(user["family_id"])
        else:
            current_tenant_id.set("default")

        member_id = request.headers.get("X-Member-Id")
        current_member_id.set(member_id if member_id else None)

        if member_id:
            logger.debug("TENANT tenant=%s member=%s path=%s",
                         current_tenant_id.get(), member_id, request.url.path)

        response = await call_next(request)
        return response
