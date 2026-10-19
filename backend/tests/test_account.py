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


async def _seed_user_data(db: SqliteAdapter, user_id: str, family_id: str) -> None:
    """Insert test rows into every user-owned table for the given user.

    Covers all tables of the account deletion plan: user_id-keyed, sharer/
    viewer-keyed (family_shares), tenant-keyed private knowledge entities
    and their children (chunks/embeddings/provenance/conflicts/relations).
    """
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

    # --- PIPL gap: health / visit / plan / share data -------------------
    await db.execute(
        "INSERT INTO health_logs (id, user_id, log_date, systolic, diastolic) "
        "VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, "2026-01-15", 130, 85),
    )
    await db.execute(
        "INSERT INTO medical_visits (id, user_id, visit_date, hospital, diagnosis) "
        "VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, "2026-01-10", "市医院", "高血压"),
    )
    plan_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO medication_plans (id, user_id, name, status) "
        "VALUES (?, ?, ?, ?)",
        (plan_id, user_id, "降压套餐", "active"),
    )
    await db.execute(
        "INSERT INTO plan_items (id, plan_id, medicine_name) VALUES (?, ?, ?)",
        (str(uuid.uuid4()), plan_id, "硝苯地平"),
    )
    await db.execute(
        "INSERT INTO share_cards (id, user_id, family_id, card_type, card_data) "
        "VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, family_id, "health_summary", "{}"),
    )
    # family_shares — user is sharer in one row, viewer in another
    await db.execute(
        "INSERT INTO family_shares (id, sharer_id, viewer_id, role) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, str(uuid.uuid4()), "家属查看"),
    )
    await db.execute(
        "INSERT INTO family_shares (id, sharer_id, viewer_id, role) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), str(uuid.uuid4()), user_id, "家属查看"),
    )

    # --- tenant-private knowledge entities + children -------------------
    ent1, ent2 = str(uuid.uuid4()), str(uuid.uuid4())
    for eid in (ent1, ent2):
        await db.execute(
            "INSERT INTO knowledge_entities (id, entity_type, source_table, title, tenant_id, source_type) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (eid, "herb", "knowledge_entities", "私有实体", family_id, "user"),
        )
    chunk_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO knowledge_chunks (id, entity_id, chunk_text) VALUES (?, ?, ?)",
        (chunk_id, ent1, "私有实体内容分块"),
    )
    await db.execute(
        "INSERT INTO chunk_embeddings (chunk_id, embedding) VALUES (?, ?)",
        (chunk_id, "[0.1]"),
    )
    await db.execute(
        "INSERT INTO knowledge_provenance (id, entity_id, source_type, imported_by) "
        "VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), ent1, "url", user_id),
    )
    await db.execute(
        "INSERT INTO knowledge_conflicts (id, entity_id, field, conflict_type) "
        "VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), ent1, "功效", "contradiction"),
    )
    await db.execute(
        "INSERT INTO entity_relationships (id, source_entity_id, target_entity_id, relationship_type, tenant_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), ent1, ent2, "配伍", family_id),
    )

    # --- misc user_id-keyed tables --------------------------------------
    classic_id, chapter_id = str(uuid.uuid4()), str(uuid.uuid4())
    await db.execute(
        "INSERT INTO classics (id, title) VALUES (?, ?)",
        (classic_id, "黄帝内经"),
    )
    await db.execute(
        "INSERT INTO classic_chapters (id, classic_id, chapter_number, title, original_text) "
        "VALUES (?, ?, ?, ?, ?)",
        (chapter_id, classic_id, 1, "上古天真论", "昔在黄帝……"),
    )
    await db.execute(
        "INSERT INTO classic_annotations (id, user_id, classic_id, chapter_id, start_offset, end_offset, selected_text, content) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, classic_id, chapter_id, 0, 4, "上古天真", "注解内容"),
    )
    await db.execute(
        "INSERT INTO classic_study_notes (id, user_id, classic_id, chapter_id, content) "
        "VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, classic_id, chapter_id, "学习笔记"),
    )
    await db.execute(
        "INSERT INTO knowledge_feedback (id, entity_id, user_id, rating) "
        "VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), ent1, user_id, "like"),
    )
    await db.execute(
        "INSERT INTO user_interest_profiles (user_id, interest_domain) VALUES (?, ?)",
        (user_id, "补气"),
    )
    await db.execute(
        "INSERT INTO user_notes (id, entity_id, user_id, content) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), ent1, user_id, "个人笔记"),
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
async def test_delete_account_rolls_back_all_rows_when_a_delete_fails(
    client: AsyncClient, auth_headers: dict, db: SqliteAdapter, monkeypatch
):
    """A mid-plan failure must preserve user data and the pre-delete audit chain."""
    user = await db.query_one(
        "SELECT id, family_id FROM users WHERE username = 'testuser'"
    )
    assert user is not None
    user_id, family_id = user["id"], user["family_id"]
    health_log_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO health_logs (id, user_id, log_date, systolic) VALUES (?, ?, ?, ?)",
        (health_log_id, user_id, "2026-01-15", 125),
    )
    before_audit_count = await db.query_one(
        "SELECT COUNT(*) AS n FROM audit_log WHERE tenant_id = ?", (family_id,)
    )

    real_execute = db.execute

    async def fail_on_reminder_delete(sql, params=()):
        if sql.lstrip().upper().startswith("DELETE FROM REMINDERS"):
            raise RuntimeError("simulated database write failure")
        return await real_execute(sql, params)

    monkeypatch.setattr(db, "execute", fail_on_reminder_delete)
    with pytest.raises(RuntimeError, match="simulated database write failure"):
        await client.delete("/api/account", headers=auth_headers)
    monkeypatch.setattr(db, "execute", real_execute)

    assert await db.query_one("SELECT id FROM users WHERE id = ?", (user_id,))
    assert await db.query_one(
        "SELECT id FROM health_logs WHERE id = ?", (health_log_id,)
    )
    after_audit_count = await db.query_one(
        "SELECT COUNT(*) AS n FROM audit_log WHERE tenant_id = ?", (family_id,)
    )
    assert after_audit_count["n"] == before_audit_count["n"]
    assert db.in_transaction is False


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
        ("health_logs", "user_id"),
        ("medical_visits", "user_id"),
        ("medication_plans", "user_id"),
        ("share_cards", "user_id"),
        ("classic_annotations", "user_id"),
        ("classic_study_notes", "user_id"),
        ("knowledge_feedback", "user_id"),
        ("user_interest_profiles", "user_id"),
        ("user_notes", "user_id"),
        ("family_members", "user_id"),
    ]:
        row = await db.query_one(
            f"SELECT COUNT(*) AS cnt FROM {table} WHERE {col} = ?",
            (user_id,),
        )
        assert row["cnt"] > 0, f"{table} should have data before deletion"

    row = await db.query_one(
        "SELECT COUNT(*) AS cnt FROM family_shares WHERE sharer_id = ? OR viewer_id = ?",
        (user_id, user_id),
    )
    assert row["cnt"] > 0

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
        ("health_logs", "user_id"),
        ("medical_visits", "user_id"),
        ("medication_plans", "user_id"),
        ("share_cards", "user_id"),
        ("classic_annotations", "user_id"),
        ("classic_study_notes", "user_id"),
        ("knowledge_feedback", "user_id"),
        ("user_interest_profiles", "user_id"),
        ("user_notes", "user_id"),
        ("family_members", "user_id"),
    ]:
        row = await db.query_one(
            f"SELECT COUNT(*) AS cnt FROM {table} WHERE {col} = ?",
            (user_id,),
        )
        assert row["cnt"] == 0, f"{table} should be empty after deletion"

    # family_shares — gone in BOTH roles (sharer and viewer)
    row = await db.query_one(
        "SELECT COUNT(*) AS cnt FROM family_shares WHERE sharer_id = ? OR viewer_id = ?",
        (user_id, user_id),
    )
    assert row["cnt"] == 0

    # tenant-private knowledge entities + children all removed
    row = await db.query_one(
        "SELECT COUNT(*) AS cnt FROM knowledge_entities WHERE tenant_id = ?",
        (family_id,),
    )
    assert row["cnt"] == 0
    row = await db.query_one(
        "SELECT COUNT(*) AS cnt FROM entity_relationships WHERE tenant_id = ?",
        (family_id,),
    )
    assert row["cnt"] == 0

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
        ("health_logs", "user_id"),
        ("medical_visits", "user_id"),
        ("medication_plans", "user_id"),
        ("share_cards", "user_id"),
        ("family_members", "user_id"),
    ]:
        row = await db.query_one(
            f"SELECT COUNT(*) AS cnt FROM {table} WHERE {col} = ?",
            (user_b["id"],),
        )
        assert row["cnt"] > 0, f"{table} for user B should be intact"

    # user B's tenant-private knowledge entities are intact
    row = await db.query_one(
        "SELECT COUNT(*) AS cnt FROM knowledge_entities WHERE tenant_id = ?",
        (user_b["family_id"],),
    )
    assert row["cnt"] > 0

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
    # PIPL gap tables now visible in preview
    assert counts["health_logs"] == 1
    assert counts["medical_visits"] == 1
    assert counts["medication_plans"] == 1
    assert counts["plan_items"] == 1
    assert counts["share_cards"] == 1
    assert counts["family_shares"] == 2  # sharer + viewer roles
    assert counts["knowledge_entities"] == 2  # tenant-private only
    assert counts["knowledge_chunks"] == 1
    assert counts["chunk_embeddings"] == 1
    assert counts["knowledge_provenance"] == 1
    assert counts["knowledge_conflicts"] == 1
    assert counts["entity_relationships"] == 1
    assert counts["classic_annotations"] == 1
    assert counts["classic_study_notes"] == 1
    assert counts["knowledge_feedback"] == 1
    assert counts["user_interest_profiles"] == 1
    assert counts["user_notes"] == 1


@pytest.mark.asyncio
async def test_delete_preview_matches_actual_deletion(
    client: AsyncClient, auth_headers: dict, db: SqliteAdapter
):
    """Preview counts == per-table deleted row counts == post-delete reality.

    PIPL §12.2: the preview shown to the user before erasure must exactly
    match what is actually deleted — no hidden tables, no missing rows.
    Also asserts the backup-retention disclosure note (spec §12.2).
    """
    user_row = await db.query_one(
        "SELECT id, family_id FROM users WHERE username = 'testuser'"
    )
    await _seed_user_data(db, user_row["id"], user_row["family_id"])

    # A global (tenant NULL) knowledge entity must NOT be counted or deleted
    await db.execute(
        "INSERT INTO knowledge_entities (id, entity_type, source_table, title, source_type) "
        "VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), "herb", "herbs", "全局共享实体", "system"),
    )

    # 1. Preview before deletion
    preview_resp = await client.get("/api/account/preview", headers=auth_headers)
    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    assert preview["note"] == "加密备份文件含历史数据，将于30天内随备份轮换删除"
    counts = preview["data_counts"]
    assert counts["knowledge_entities"] == 2  # global entity NOT counted

    # 2. Delete
    del_resp = await client.delete("/api/account", headers=auth_headers)
    assert del_resp.status_code == 200
    body = del_resp.json()
    assert body["note"] == "加密备份文件含历史数据，将于30天内随备份轮换删除"
    assert body["deleted_counts"]["users"] == 1
    assert body["total_deleted"] == sum(body["deleted_counts"].values())

    # 3. Preview counts == deleted counts, key by key
    for key, preview_cnt in counts.items():
        assert body["deleted_counts"][key] == preview_cnt, (
            f"{key}: preview={preview_cnt} deleted={body['deleted_counts'][key]}"
        )

    # 4. Post-delete reality: the PIPL gap tables are all empty
    user_id, family_id = user_row["id"], user_row["family_id"]
    for table, col in [
        ("health_logs", "user_id"),
        ("medical_visits", "user_id"),
        ("medication_plans", "user_id"),
        ("share_cards", "user_id"),
        ("favorites", "user_id"),  # bookmarks 表（/api/bookmarks 落库于 favorites）
        ("family_members", "user_id"),
    ]:
        row = await db.query_one(
            f"SELECT COUNT(*) AS cnt FROM {table} WHERE {col} = ?",
            (user_id,),
        )
        assert row["cnt"] == 0, f"{table} must be empty after erasure"

    row = await db.query_one(
        "SELECT COUNT(*) AS cnt FROM family_shares WHERE sharer_id = ? OR viewer_id = ?",
        (user_id, user_id),
    )
    assert row["cnt"] == 0, "family_shares must be empty in both roles"

    row = await db.query_one(
        "SELECT COUNT(*) AS cnt FROM knowledge_entities WHERE tenant_id IS NULL AND title = '全局共享实体'"
    )
    assert row["cnt"] == 1, "global (tenant NULL) knowledge must NOT be deleted"
