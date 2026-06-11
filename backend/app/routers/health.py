"""Health check router."""

from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health_check():
    return {"status": "ok", "version": settings.APP_VERSION}
