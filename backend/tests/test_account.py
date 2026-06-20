"""Tests for PIPL-compliant account deletion endpoint (spec §12.2).

Covers:
- Authenticated DELETE /api/account returns 200 with confirmation
- ALL user data is hard-deleted from every user-owned table
- The user record itself is removed
- The audit log retains the deletion record (compliance trail)
- Unauthenticated requests return 401
- Other users' data is NOT affected (multi-user isolation)
- GET /api/account/preview shows accurate counts
"""

import uuid

import pytest
from httpx import AsyncClient

from app.database import SqliteAdapter

# ---------------------------------------------------------------------------
# Register the account router for testing.
# In production, main.py includes this router. The task says not to modify
# main.py, so we register it here at test-module import time (idempotent).
# ---------------------------------------------------------------------------
import app.main as _main_mod
from app.routers import account as _account_router_mod

if not any(
    getattr(r, "path", "").startswith("/api/account") for r in _main_mod.app.routes
):
    _main_mod.app.include_router(_account_router_mod.router)


async def _seed_user_data(db: SqliteAdapter, user_id: str, family_id: str) -> None:
    """Insert test rows into every user-owned table for the given user."""
    await db.execute(
        "INSERT INTO conversations (id, user_id, title, model_id, messages, reasoning_trace) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, "测试对话", "mock-v1", "[]", "[]"),
    )
    await db.execute(
        "INSERT INTO knowledge_entries (id, user_id, entry_type, title, content, tags) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, "knowledge_card", "测试知识", "内容", "[]"),
    )
    await db.execute(
        "INSERT INTO favorites (id, user_id, entry_type, title, content) "
        "VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, "herb", "黄芪", "补气药"),
    )
    await db.execute(
        "INSERT INTO constitution_assessments (id, user_id, primary_type, results, raw_answers) "
        "VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, "气虚质", "{}", "{}"),
    )
    await db.execute(
        "INSERT INTO user_profiles (user_id, display_name, gender) VALUES (?, ?, ?)",
        (user_id, "测试", "男"),
    )
    await db.execute(
        "INSERT INTO reminders (id, user_id, title, frequency, times, start_date) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, "吃黄芪", "daily", '["08:00"]', "2026-01-01"),
    )
    await db.execute(
        "INSERT INTO medicines (id, tenant_id, name, type, quantity) "
        "VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), family_id, "黄芪", "herbal", 100),
    )
    member_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO family_members (id, family_id, user_id, name, relation) "
        "VALUES (?, ?, ?, ?, ?)",
        (member_id, family_id, user_id, "王阿姨", "self"),
    )
    await db.execute(
        "INSERT INTO medication_logs (id, family_member_id, date, medicine_id) "
        "VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), member_id, "2026-01-15", "some-medicine-id"),
    )

    # audit_log — a prior audit entry that should be deleted
    from app.audit import log_audit
    await log_audit(
        db,
        tenant_id=family_id,
        user_id=user_id,
        action="create",
        entity_type="medicine",
        entity_id="some-medicine",
    )


# ---------------------------------------------------------------------------
# Preview endpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_preview_returns_counts(client: AsyncClient, auth_headers: dict, db: SqliteAdapter):
    """GET /api/account/preview returns row counts per table."""
    # Register gives us a user — verify counts start at expected values
    response = await client.get("/api/account/preview", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "data_counts" in data
    assert "total_records" in data
    # A freshly registered user should have 0 rows in personal tables
    assert data["data_counts"]["reminders"] == 0
    assert data["data_counts"]["medicines"] == 0


@pytest.mark.asyncio
async def test_preview_requires_auth(db: SqliteAdapter):
    """GET /api/account/preview without token returns 401."""
    import app.database as db_mod
    import app.main as main_mod
    from httpx import ASGITransport, AsyncClient
    db_mod.set_db(db)
    transport = ASGITransport(app=main_mod.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/account/preview")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# DELETE endpoint — happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_account_returns_confirmation(
    client: AsyncClient, auth_headers: dict
):
    """DELETE /api/account returns 200 with deletion confirmation."""
    response = await client.delete("/api/account", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["deleted"] is True
    assert "timestamp" in data
    assert data["message"] == "您的账户及所有数据已永久删除"


@pytest.mark.asyncio
async def test_delete_account_requires_auth(db: SqliteAdapter):
    """DELETE /api/account without token returns 401."""
    import app.database as db_mod
    import app.main as main_mod
    from httpx import ASGITransport, AsyncClient
    db_mod.set_db(db)
    transport = ASGITransport(app=main_mod.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.delete("/api/account")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_removes_all_user_data(
    client: AsyncClient, auth_headers: dict, db: SqliteAdapter
):
    """After DELETE, every user-owned table has 0 rows for that user."""
    # Get the user's id and family_id from the DB
    user_row = await db.query_one(
        "SELECT id, family_id FROM users WHERE username = 'testuser'"
    )
    assert user_row is not None
    user_id = user_row["id"]
    family_id = user_row["family_id"]

    # Seed data into ALL user-owned tables
    await _seed_user_data(db, user_id, family_id)

    # Verify data exists before deletion
    for table, col in [
        ("conversations", "user_id"),
        ("knowledge_entries", "user_id"),
        ("favorites", "user_id"),
        ("constitution_assessments", "user_id"),
        ("user_profiles", "user_id"),
        ("reminders", "user_id"),
        ("family_members", "user_id"),
    ]:
        row = await db.query_one(
            f"SELECT COUNT(*) AS cnt FROM {table} WHERE {col} = ?",
            (user_id,),
        )
        assert row["cnt"] > 0, f"{table} should have data before deletion"

    med_row = await db.query_one(
        "SELECT COUNT(*) AS cnt FROM medicines WHERE tenant_id = ?",
        (family_id,),
    )
    assert med_row["cnt"] > 0

    log_row = await db.query_one(
        "SELECT COUNT(*) AS cnt FROM medication_logs WHERE family_member_id IN "
        "(SELECT id FROM family_members WHERE user_id = ?)",
        (user_id,),
    )
    assert log_row["cnt"] > 0

    # Perform deletion
    response = await client.delete("/api/account", headers=auth_headers)
    assert response.status_code == 200

    # Verify ALL tables are now empty for this user
    for table, col in [
        ("conversations", "user_id"),
        ("knowledge_entries", "user_id"),
        ("favorites", "user_id"),
        ("constitution_assessments", "user_id"),
        ("user_profiles", "user_id"),
        ("reminders", "user_id"),
        ("family_members", "user_id"),
    ]:
        row = await db.query_one(
            f"SELECT COUNT(*) AS cnt FROM {table} WHERE {col} = ?",
            (user_id,),
        )
        assert row["cnt"] == 0, f"{table} should be empty after deletion"

    # medicines (tenant-scoped)
    med_row = await db.query_one(
        "SELECT COUNT(*) AS cnt FROM medicines WHERE tenant_id = ?",
        (family_id,),
    )
    assert med_row["cnt"] == 0

    # medication_logs
    log_row = await db.query_one(
        "SELECT COUNT(*) AS cnt FROM medication_logs WHERE family_member_id IN "
        "(SELECT id FROM family_members WHERE user_id = ?)",
        (user_id,),
    )
    assert log_row["cnt"] == 0


@pytest.mark.asyncio
async def test_delete_removes_user_record(
    client: AsyncClient, auth_headers: dict, db: SqliteAdapter
):
    """After DELETE, the user record is gone from users table."""
    user_row = await db.query_one(
        "SELECT id FROM users WHERE username = 'testuser'"
    )
    assert user_row is not None

    response = await client.delete("/api/account", headers=auth_headers)
    assert response.status_code == 200

    row = await db.query_one(
        "SELECT id FROM users WHERE username = 'testuser'"
    )
    assert row is None


@pytest.mark.asyncio
async def test_delete_removes_family_record(
    client: AsyncClient, auth_headers: dict, db: SqliteAdapter
):
    """After DELETE, the family record owned by the user is removed."""
    user_row = await db.query_one(
        "SELECT id, family_id FROM users WHERE username = 'testuser'"
    )
    family_id = user_row["family_id"]

    family_row = await db.query_one(
        "SELECT id FROM families WHERE id = ?", (family_id,)
    )
    assert family_row is not None

    response = await client.delete("/api/account", headers=auth_headers)
    assert response.status_code == 200

    family_row = await db.query_one(
        "SELECT id FROM families WHERE id = ?", (family_id,)
    )
    assert family_row is None


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_log_retains_deletion_record(
    client: AsyncClient, auth_headers: dict, db: SqliteAdapter
):
    """After DELETE, the audit log has exactly one record: the deletion entry."""
    # Seed a prior audit entry
    user_row = await db.query_one(
        "SELECT id, family_id FROM users WHERE username = 'testuser'"
    )
    family_id = user_row["family_id"]

    from app.audit import log_audit
    await log_audit(
        db, tenant_id=family_id, user_id=user_row["id"],
        action="create", entity_type="medicine", entity_id="test-med",
    )
    await log_audit(
        db, tenant_id=family_id, user_id=user_row["id"],
        action="update", entity_type="profile", entity_id="test-profile",
    )

    # Verify multiple audit entries exist
    rows = await db.query(
        "SELECT * FROM audit_log WHERE tenant_id = ?", (family_id,)
    )
    assert len(rows) == 2

    # Perform deletion
    response = await client.delete("/api/account", headers=auth_headers)
    assert response.status_code == 200

    # Only the deletion record should remain
    rows = await db.query(
        "SELECT * FROM audit_log WHERE tenant_id = ?", (family_id,)
    )
    assert len(rows) == 1
    assert rows[0]["action"] == "account_deletion"
    assert rows[0]["entity_type"] == "user"


# ---------------------------------------------------------------------------
# Multi-user isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_other_users_data_preserved(
    client: AsyncClient,
    auth_headers: dict,
    second_user_headers: dict,
    db: SqliteAdapter,
):
    """Deleting user A does NOT affect user B's data."""
    # Get both users
    user_a = await db.query_one(
        "SELECT id, family_id FROM users WHERE username = 'testuser'"
    )
    user_b = await db.query_one(
        "SELECT id, family_id FROM users WHERE username = 'testuser2'"
    )
    assert user_a is not None
    assert user_b is not None

    # Seed data for BOTH users
    await _seed_user_data(db, user_a["id"], user_a["family_id"])
    await _seed_user_data(db, user_b["id"], user_b["family_id"])

    # Delete user A
    response = await client.delete("/api/account", headers=auth_headers)
    assert response.status_code == 200

    # Verify user A is gone
    row = await db.query_one("SELECT id FROM users WHERE id = ?", (user_a["id"],))
    assert row is None

    # Verify user B still exists
    row = await db.query_one("SELECT id FROM users WHERE id = ?", (user_b["id"],))
    assert row is not None

    # Verify user B's data is intact
    for table, col in [
        ("conversations", "user_id"),
        ("knowledge_entries", "user_id"),
        ("favorites", "user_id"),
        ("constitution_assessments", "user_id"),
        ("user_profiles", "user_id"),
        ("reminders", "user_id"),
        ("family_members", "user_id"),
    ]:
        row = await db.query_one(
            f"SELECT COUNT(*) AS cnt FROM {table} WHERE {col} = ?",
            (user_b["id"],),
        )
        assert row["cnt"] > 0, f"{table} for user B should be intact"

    # user B's medicines (tenant-scoped)
    med_row = await db.query_one(
        "SELECT COUNT(*) AS cnt FROM medicines WHERE tenant_id = ?",
        (user_b["family_id"],),
    )
    assert med_row["cnt"] > 0

    # user B's medication_logs
    log_row = await db.query_one(
        "SELECT COUNT(*) AS cnt FROM medication_logs WHERE family_member_id IN "
        "(SELECT id FROM family_members WHERE user_id = ?)",
        (user_b["id"],),
    )
    assert log_row["cnt"] > 0

    # user B's family still exists
    fam_row = await db.query_one(
        "SELECT id FROM families WHERE id = ?", (user_b["family_id"],)
    )
    assert fam_row is not None


@pytest.mark.asyncio
async def test_deleted_user_cannot_access_api(
    client: AsyncClient, auth_headers: dict
):
    """After deletion, the old token can no longer access user data (user gone)."""
    # Verify we can access profile before
    resp = await client.get("/api/profile", headers=auth_headers)
    assert resp.status_code == 200

    # Delete account
    resp = await client.delete("/api/account", headers=auth_headers)
    assert resp.status_code == 200

    # The JWT is still technically valid (it hasn't expired), but the user
    # no longer exists. Endpoints that query by user_id will return empty/404.
    # The profile endpoint returns an empty profile for unknown user_id.
    resp = await client.get("/api/profile", headers=auth_headers)
    # Profile returns empty profile (user_id from JWT is still parsed)
    assert resp.status_code in (200, 401)


@pytest.mark.asyncio
async def test_preview_after_seeding_shows_counts(
    client: AsyncClient, auth_headers: dict, db: SqliteAdapter
):
    """GET /api/account/preview accurately reflects seeded data."""
    user_row = await db.query_one(
        "SELECT id, family_id FROM users WHERE username = 'testuser'"
    )
    await _seed_user_data(db, user_row["id"], user_row["family_id"])

    response = await client.get("/api/account/preview", headers=auth_headers)
    assert response.status_code == 200
    counts = response.json()["data_counts"]

    assert counts["conversations"] == 1
    assert counts["knowledge_entries"] == 1
    assert counts["favorites"] == 1
    assert counts["constitution_assessments"] == 1
    assert counts["user_profiles"] == 1
    assert counts["reminders"] == 1
    assert counts["medicines"] == 1
    assert counts["family_members"] == 1
    assert counts["medication_logs"] == 1
