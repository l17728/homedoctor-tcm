"""Tests for tenant and user scoped in-app notification receipts."""

import pytest

from app.audit import log_audit


@pytest.mark.asyncio
async def test_weekly_notification_can_be_listed_and_marked_read(client, db):
    me = (await client.get("/api/auth/me")).json()
    await log_audit(
        db,
        tenant_id=me["family_id"],
        user_id=me["id"],
        action="create",
        entity_type="notification",
        entity_id="weekly_digest:shared-user",
        changes={"title": "本周健康摘要已生成", "target": "/remote-assist"},
    )
    notification = await db.query_one(
        "SELECT id FROM audit_log WHERE tenant_id = ? AND user_id = ? AND entity_type = 'notification' ORDER BY rowid DESC LIMIT 1",
        (me["family_id"], me["id"]),
    )
    notification_id = notification["id"]

    listed = await client.get("/api/notifications")
    assert listed.status_code == 200
    entry = next(item for item in listed.json()["items"] if item["id"] == notification_id)
    assert entry["title"] == "本周健康摘要已生成"
    assert entry["unread"] is True

    marked = await client.post(f"/api/notifications/{notification_id}/read")
    assert marked.status_code == 200
    assert marked.json()["unread"] is False
    listed_after = await client.get("/api/notifications")
    entry_after = next(item for item in listed_after.json()["items"] if item["id"] == notification_id)
    assert entry_after["unread"] is False


@pytest.mark.asyncio
async def test_notification_read_receipt_is_user_scoped(client, db):
    me = (await client.get("/api/auth/me")).json()
    await log_audit(
        db,
        tenant_id=me["family_id"],
        user_id="another-user",
        action="create",
        entity_type="notification",
        entity_id="weekly_digest:shared-user",
        changes={"title": "Private notification"},
    )
    notification = await db.query_one(
        "SELECT id FROM audit_log WHERE entity_type = 'notification' AND user_id = 'another-user' ORDER BY rowid DESC LIMIT 1"
    )
    notification_id = notification["id"]

    response = await client.post(f"/api/notifications/{notification_id}/read")
    assert response.status_code == 404
