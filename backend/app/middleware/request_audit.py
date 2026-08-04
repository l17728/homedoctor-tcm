"""Request audit middleware — logs all /api/ requests for full traceability.

Records: method, path, user, status_code, duration_ms for every API call.
This is the baseline for reconstructing any user's execution path through the system.
"""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)


class RequestAuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)

        start = time.monotonic()
        method = request.method
        user = getattr(request.state, "user", None)
        username = user.get("username", "anonymous") if user else "anonymous"

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.error("REQ %s %s user=%s status=500 duration=%dms (exception)",
                         method, path, username, duration_ms)
            raise

        duration_ms = int((time.monotonic() - start) * 1000)
        status = response.status_code

        if status >= 400:
            logger.warning("REQ %s %s user=%s status=%d duration=%dms",
                           method, path, username, status, duration_ms)
        else:
            logger.info("REQ %s %s user=%s status=%d duration=%dms",
                        method, path, username, status, duration_ms)

        return response
