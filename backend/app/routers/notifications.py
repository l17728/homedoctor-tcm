"""In-app notifications backed by append-only audit log events."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.audit import log_audit
from app.auth import get_current_user
from app.database import DbAdapter, get_db

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _parse_changes(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


@router.get("")
async def list_notifications(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Return the current user's notifications without exposing other tenant events."""
    user_id = current_user["id"]
    tenant_id = current_user.get("family_id") or "default"
    rows = await db.query(
        """SELECT id, entity_id, changes, created_at FROM audit_log
           WHERE tenant_id = ? AND user_id = ? AND entity_type = 'notification'
           ORDER BY created_at DESC LIMIT 100""",
        (tenant_id, user_id),
    )
    receipts = await db.query(
        """SELECT entity_id FROM audit_log
           WHERE tenant_id = ? AND user_id = ? AND entity_type = 'notification_read'""",
        (tenant_id, user_id),
    )
    read_ids = {row["entity_id"] for row in receipts if row.get("entity_id")}
    return {
        "items": [
            {
                "id": row["id"],
                "type": row.get("entity_id"),
                **_parse_changes(row.get("changes")),
                "created_at": row.get("created_at"),
                "unread": row["id"] not in read_ids,
            }
            for row in rows
        ]
    }


@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Append an idempotent read receipt for a notification owned by this user."""
    user_id = current_user["id"]
    tenant_id = current_user.get("family_id") or "default"
    notification = await db.query_one(
        """SELECT id FROM audit_log
           WHERE id = ? AND tenant_id = ? AND user_id = ?
             AND entity_type = 'notification'""",
        (notification_id, tenant_id, user_id),
    )
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="通知不存在",
        )
    existing = await db.query_one(
        """SELECT id FROM audit_log
           WHERE tenant_id = ? AND user_id = ? AND entity_type = 'notification_read'
             AND entity_id = ? LIMIT 1""",
        (tenant_id, user_id, notification_id),
    )
    if not existing:
        await log_audit(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            action="read",
            entity_type="notification_read",
            entity_id=notification_id,
        )
    return {"success": True, "notification_id": notification_id, "unread": False}
