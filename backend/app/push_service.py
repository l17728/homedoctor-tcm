"""Local Web Push support. VAPID secrets stay in environment configuration."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

from app.config import settings
from app.url_validator import validate_external_url

logger = logging.getLogger(__name__)


def _vapid_raw_private_key(pem: str) -> str:
    from cryptography.hazmat.primitives import serialization

    key = serialization.load_pem_private_key(pem.encode("ascii"), password=None)
    raw = key.private_numbers().private_value.to_bytes(32, "big")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def push_is_configured() -> bool:
    return bool(settings.PUSH_VAPID_PUBLIC_KEY and settings.PUSH_VAPID_PRIVATE_KEY)


async def load_user_subscriptions(db: Any, user_id: str) -> list[dict[str, Any]]:
    row = await db.query_one("SELECT settings FROM users WHERE id = ?", (user_id,))
    raw = (row or {}).get("settings") or "{}"
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        value = {}
    subscriptions = value.get("push_subscriptions", []) if isinstance(value, dict) else []
    return [item for item in subscriptions if isinstance(item, dict)]


async def save_user_subscriptions(db: Any, user_id: str, subscriptions: list[dict[str, Any]]) -> None:
    row = await db.query_one("SELECT settings FROM users WHERE id = ?", (user_id,))
    if not row:
        return
    raw = row.get("settings") or "{}"
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        value = {}
    if not isinstance(value, dict):
        value = {}
    value["push_subscriptions"] = subscriptions[-10:]
    await db.execute("UPDATE users SET settings = ? WHERE id = ?", (json.dumps(value, ensure_ascii=False), user_id))


async def send_user_push(db: Any, user_id: str, title: str, body: str, target: str = "/") -> int:
    """Send to a user's active browser subscriptions; isolate stale/invalid endpoints."""
    if not push_is_configured():
        return 0
    try:
        import requests
        from pywebpush import WebPushException, webpush
    except ImportError:
        logger.error("Web Push configured but pywebpush is not installed")
        return 0

    subscriptions = await load_user_subscriptions(db, user_id)
    class NoRedirectSession(requests.Session):
        def post(self, url, **kwargs):
            kwargs["allow_redirects"] = False
            return super().post(url, **kwargs)

    active: list[dict[str, Any]] = []
    delivered = 0
    for subscription in subscriptions:
        endpoint = subscription.get("endpoint", "")
        # Subscription endpoints are user-controlled URLs. Revalidate DNS and
        # protocol immediately before every outbound request to reduce SSRF risk.
        if not validate_external_url(endpoint) or not endpoint.startswith("https://"):
            continue
        try:
            await asyncio.to_thread(
                webpush,
                subscription_info=subscription,
                data=json.dumps({"title": title[:120], "body": body[:300], "url": target[:300]}),
                vapid_private_key=_vapid_raw_private_key(settings.PUSH_VAPID_PRIVATE_KEY.replace("\\n", "\n")),
                vapid_claims={"sub": settings.PUSH_VAPID_SUBJECT},
                timeout=8,
                requests_session=NoRedirectSession(),
            )
            delivered += 1
            active.append(subscription)
        except WebPushException as exc:
            response = getattr(exc, "response", None)
            if getattr(response, "status_code", None) not in (404, 410):
                active.append(subscription)
                logger.warning("Web Push send failed (status=%s)", getattr(response, "status_code", "unknown"))
        except Exception:
            active.append(subscription)
            logger.exception("Web Push send failed")
    if len(active) != len(subscriptions):
        await save_user_subscriptions(db, user_id, active)
    return delivered
