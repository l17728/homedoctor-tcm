"""Member context middleware — sets current_member_id from X-Member-Id header."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.repository import current_member_id


class MemberContextMiddleware(BaseHTTPMiddleware):
    """Read X-Member-Id header and set the current_member_id contextvar.

    When the header is absent, current_member_id is set to None so that
    queries return ALL data regardless of member (backward compatible).
    """

    async def dispatch(self, request: Request, call_next):
        member_id = request.headers.get("X-Member-Id")
        current_member_id.set(member_id if member_id else None)
        response = await call_next(request)
        return response
