"""Authenticated browser push subscription management."""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, HttpUrl

from app.auth import get_current_user
from app.database import DbAdapter, get_db
from app.push_service import load_user_subscriptions, push_is_configured, save_user_subscriptions
from app.url_validator import validate_external_url

router = APIRouter(prefix="/api/push", tags=["push"])


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=20, max_length=256)
    auth: str = Field(min_length=8, max_length=128)


class PushSubscriptionRequest(BaseModel):
    endpoint: HttpUrl
    keys: PushKeys


class PushUnsubscribeRequest(BaseModel):
    endpoint: HttpUrl


@router.get("/config")
async def get_push_config():
    """Return only the public VAPID key needed by browser clients."""
    from app.config import settings
    enabled = push_is_configured()
    return {"enabled": enabled, "public_key": settings.PUSH_VAPID_PUBLIC_KEY if enabled else ""}


@router.post("/subscriptions", status_code=status.HTTP_201_CREATED)
async def subscribe_push(
    body: PushSubscriptionRequest,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Save an HTTPS public push endpoint in this user's settings JSON."""
    if not push_is_configured():
        raise HTTPException(status_code=503, detail="Web Push 尚未配置 VAPID 密钥")
    endpoint = str(body.endpoint)
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or parsed.port not in (None, 443) or not validate_external_url(endpoint):
        raise HTTPException(status_code=422, detail="推送地址必须是公网 HTTPS 443 地址")
    subscription = {"endpoint": endpoint, "keys": body.keys.model_dump()}
    subscriptions = await load_user_subscriptions(db, current_user["id"])
    subscriptions = [item for item in subscriptions if item.get("endpoint") != endpoint]
    subscriptions.append(subscription)
    await save_user_subscriptions(db, current_user["id"], subscriptions)
    return {"success": True, "subscription_count": min(len(subscriptions), 10)}


@router.delete("/subscriptions")
async def unsubscribe_push(
    body: PushUnsubscribeRequest,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    endpoint = str(body.endpoint)
    subscriptions = await load_user_subscriptions(db, current_user["id"])
    remaining = [item for item in subscriptions if item.get("endpoint") != endpoint]
    await save_user_subscriptions(db, current_user["id"], remaining)
    return {"success": True, "subscription_count": len(remaining)}
