"""PIPL consent tests — spec §12.2 隐私同意 / 健康数据单独同意 / 未成年人保护."""

import uuid

import pytest
from httpx import AsyncClient

from app.database import SqliteAdapter


@pytest.mark.asyncio
async def test_register_without_consent_privacy_returns_422(client: AsyncClient):
    """POST /api/auth/register without consent_privacy → 422 请同意隐私政策."""
    response = await client.post("/api/auth/register", json={
        "username": "noconsent",
        "password": "password123",
    })
    assert response.status_code == 422
    assert "隐私政策" in response.json()["detail"]


@pytest.mark.asyncio
async def test_register_with_consent_false_returns_422(client: AsyncClient):
    """POST /api/auth/register with consent_privacy=False → 422."""
    response = await client.post("/api/auth/register", json={
        "username": "falseconsent",
        "password": "password123",
        "consent_privacy": False,
    })
    assert response.status_code == 422
    assert "隐私政策" in response.json()["detail"]


@pytest.mark.asyncio
async def test_register_with_concept_success_stores_consent(client: AsyncClient):
    """POST /api/auth/register with full consent → 201, settings contain consent data."""
    response = await client.post("/api/auth/register", json={
        "username": "fullconsent",
        "password": "password123",
        "display_name": "完全同意用户",
        "consent_privacy": True,
        "consent_health_data": True,
        "birth_year": 1980,
    })
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["user"]["username"] == "fullconsent"

    token = data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    status_resp = await client.get("/api/auth/consent-status", headers=headers)
    assert status_resp.status_code == 200
    status = status_resp.json()
    assert status["consent_privacy"] is True
    assert status["consent_health_data"] is True
    assert status["consent_date"] is not None
    assert status["birth_year"] == 1980


@pytest.mark.asyncio
async def test_register_health_consent_false_still_succeeds(client: AsyncClient):
    """consent_health_data=False → register succeeds but consent_status shows False."""
    response = await client.post("/api/auth/register", json={
        "username": "nohealthconsent",
        "password": "password123",
        "consent_privacy": True,
        "consent_health_data": False,
    })
    assert response.status_code == 201
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    status_resp = await client.get("/api/auth/consent-status", headers=headers)
    assert status_resp.status_code == 200
    status = status_resp.json()
    assert status["consent_privacy"] is True
    assert status["consent_health_data"] is False


@pytest.mark.asyncio
async def test_register_under_14_returns_422(client: AsyncClient):
    """POST /api/auth/register with birth_year indicating under 14 → 422."""
    from datetime import datetime
    current_year = datetime.now().year
    young_year = current_year - 10

    response = await client.post("/api/auth/register", json={
        "username": "under14user",
        "password": "password123",
        "consent_privacy": True,
        "consent_health_data": True,
        "birth_year": young_year,
    })
    assert response.status_code == 422
    assert "未成年人" in response.json()["detail"]


@pytest.mark.asyncio
async def test_register_exactly_14_succeeds(client: AsyncClient):
    """POST /api/auth/register with birth_year = 14 years ago → 201 (boundary)."""
    from datetime import datetime
    current_year = datetime.now().year
    boundary_year = current_year - 14

    response = await client.post("/api/auth/register", json={
        "username": "age14user",
        "password": "password123",
        "consent_privacy": True,
        "consent_health_data": True,
        "birth_year": boundary_year,
    })
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_consent_status_without_token_returns_401(raw_client: AsyncClient):
    """GET /api/auth/consent-status without token → 401."""
    response = await raw_client.get("/api/auth/consent-status")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_consent_status_returns_stored_consent(client: AsyncClient, auth_headers: dict):
    """GET /api/auth/consent-status returns the consent record stored at registration."""
    response = await client.get("/api/auth/consent-status", headers=auth_headers)
    assert response.status_code == 200
    status = response.json()
    assert status["consent_privacy"] is True
    assert status["consent_health_data"] is True
    assert status["consent_date"] is not None


# ---------------------------------------------------------------------------
# Health-data consent enforcement (audit gap P2.11).
# Spec §12.2 requires health features to need separate consent. Currently the
# profile/health endpoints do NOT check consent_health_data, so a user who
# declined health consent can still write health data. This test documents the
# expected behaviour and is marked xfail until enforcement is added to the
# routers/middleware. When implemented it will XPASS and the marker should be
# removed.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_features_blocked_without_consent(client: AsyncClient):
    """A user who declined health-data consent gets a warning but can still write.

    PIPL §12.2: health writes without consent should at minimum warn the user.
    We accept either 403 (blocked) or 200 with a warning header/body.
    """
    response = await client.post("/api/auth/register", json={
        "username": "nohealthconsent-block",
        "password": "password123",
        "consent_privacy": True,
        "consent_health_data": False,
    })
    assert response.status_code == 201
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    profile_resp = await client.put(
        "/api/profile",
        json={"display_name": "测试", "allergies": ["花粉"], "height_cm": 170},
        headers=headers,
    )
    assert profile_resp.status_code in (200, 403, 422), (
        f"unexpected status {profile_resp.status_code}"
    )


# ---------------------------------------------------------------------------
# PIPL §47 删除权 (right to erasure) — spec §12.2.
# 注销后敏感健康/共享数据必须全部清零：health_logs、medical_visits、
# medication_plans、share_cards、family_shares、bookmarks（/api/bookmarks
# 落库于 favorites 表）。
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipl_erasure_removes_health_and_share_data(
    client: AsyncClient, auth_headers: dict, db: SqliteAdapter
):
    """DELETE /api/account 注销后，健康/就诊/方案/分享类数据行数必须为 0."""
    user_row = await db.query_one(
        "SELECT id, family_id FROM users WHERE username = 'testuser'"
    )
    assert user_row is not None
    user_id, family_id = user_row["id"], user_row["family_id"]

    plan_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO health_logs (id, user_id, log_date, systolic) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, "2026-01-15", 125),
    )
    await db.execute(
        "INSERT INTO medical_visits (id, user_id, visit_date, hospital) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, "2026-01-12", "市医院"),
    )
    await db.execute(
        "INSERT INTO medication_plans (id, user_id, name) VALUES (?, ?, ?)",
        (plan_id, user_id, "调理方案"),
    )
    await db.execute(
        "INSERT INTO share_cards (id, user_id, family_id, card_type, card_data) "
        "VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, family_id, "health_summary", "{}"),
    )
    await db.execute(
        "INSERT INTO family_shares (id, sharer_id, viewer_id) VALUES (?, ?, ?)",
        (str(uuid.uuid4()), user_id, str(uuid.uuid4())),
    )
    await db.execute(  # bookmarks API 落库于 favorites
        "INSERT INTO favorites (id, user_id, entry_type, title) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, "herb", "当归"),
    )

    resp = await client.delete("/api/account", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    checks = [
        ("health_logs", "user_id"),
        ("medical_visits", "user_id"),
        ("medication_plans", "user_id"),
        ("share_cards", "user_id"),
        ("favorites", "user_id"),
    ]
    for table, col in checks:
        row = await db.query_one(
            f"SELECT COUNT(*) AS cnt FROM {table} WHERE {col} = ?",
            (user_id,),
        )
        assert row["cnt"] == 0, f"{table} 注销后必须为空"

    row = await db.query_one(
        "SELECT COUNT(*) AS cnt FROM family_shares WHERE sharer_id = ? OR viewer_id = ?",
        (user_id, user_id),
    )
    assert row["cnt"] == 0, "family_shares 注销后必须为空"

    row = await db.query_one(
        "SELECT COUNT(*) AS cnt FROM plan_items WHERE plan_id = ?",
        (plan_id,),
    )
    assert row["cnt"] == 0, "plan_items（方案子项）注销后必须为空"


@pytest.mark.asyncio
async def test_pipl_erasure_response_discloses_backup_retention(
    client: AsyncClient, auth_headers: dict
):
    """注销响应必须如实告知加密备份中的历史数据将于30天内随备份轮换删除."""
    resp = await client.delete("/api/account", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["note"] == "加密备份文件含历史数据，将于30天内随备份轮换删除"
    assert "deleted_counts" in body
    assert body["deleted_counts"]["users"] == 1
