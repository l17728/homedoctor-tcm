"""Health check router — probes DB liveness, not just process liveness.

Deployment probes (docker-compose healthcheck, start-local.ps1) hit
GET /api/health and treat any non-2xx as down, so a broken/unresponsive
database must surface as 503 here.
"""

import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import get_db


logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])

DB_PROBE_TIMEOUT_SECONDS = 1.0


@router.get("/api/health")
async def health_check():
    try:
        db = get_db()
        await asyncio.wait_for(db.query("SELECT 1"), timeout=DB_PROBE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.warning("health: DB probe timed out after %.1fs", DB_PROBE_TIMEOUT_SECONDS)
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "database": "error"},
        )
    except Exception as exc:
        logger.warning("health: DB probe failed: %s", exc)
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "database": "error"},
        )
    return {"status": "ok", "database": "ok", "version": settings.APP_VERSION}
