"""Tests for GET /api/export endpoint — PIPL 合规数据导出.

Covers:
- 200 response with valid JSON structure
- 401 without auth token
- User isolation (user A cannot see user B's data)
- Response includes all expected data tables
- Fresh user returns valid structure with empty arrays
- Full-data export: every section non-empty after seeding all data classes
  (esp. medication_logs keyed by family_members.id, not user_id)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

import pytest
from httpx import AsyncClient

from app.database import SqliteAdapter

CST = timezone(timedelta(hours=8))


def _today_str() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d")


async def _seed_all_data_classes(
    db: SqliteAdapter, user_id: str, family_id: str
) -> str:
    """Seed one row into every exported data class. Returns family_member id."""
    member_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO family_members (id, family_id, user_id, name, relation) "
        "VALUES (?, ?, ?, ?, ?)",
        (member_id, family_id, user_id, "王阿姨", "self"),
    )
    # medication_logs — keyed by family_members.id (NOT user_id)
    await db.execute(
        "INSERT INTO medication_logs (id, family_member_id, date, medicine_id, taken) "
        "VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), member_id, "2026-01-15", "med-001", 1),
    )
    await db.execute(
        "INSERT INTO user_profiles (user_id, display_name, gender) VALUES (?, ?, ?)",
        (user_id, "测试导出", "女"),
    )
    await db.execute(
        "INSERT INTO medicines (id, tenant_id, name, type, quantity) "
        "VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), family_id, "黄芪", "herbal", 50),
    )
    await db.execute(
        "INSERT INTO reminders (id, user_id, title, frequency, times, start_date) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, "早晚服药", "daily", '["08:00","20:00"]', "2026-01-01"),
    )
    await db.execute(
        "INSERT INTO constitution_assessments (id, user_id, primary_type, results, raw_answers) "
        "VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, "阳虚质", "{}", "{}"),
    )
    await db.execute(
        "INSERT INTO conversations (id, user_id, title, model_id) "
        "VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, "导出对话", "mock-v1"),
    )
    await db.execute(
        "INSERT INTO knowledge_entries (id, user_id, entry_type, title, content) "
        "VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, "knowledge_card", "导出知识", "内容"),
    )
    await db.execute(
        "INSERT INTO health_logs (id, user_id, log_date, systolic, diastolic, mood) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, "2026-01-15", 120, 80, "平静"),
    )
    await db.execute(
        "INSERT INTO medical_visits (id, user_id, visit_date, hospital, diagnosis, attachments) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, "2026-01-10", "市中医院", "气虚证", "[]"),
    )
    plan_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO medication_plans (id, user_id, name, status, start_date) "
        "VALUES (?, ?, ?, ?, ?)",
        (plan_id, user_id, "冬季调理套餐", "active", "2026-01-01"),
    )
    await db.execute(
        "INSERT INTO plan_items (id, plan_id, medicine_name, dosage, times, sort_order) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), plan_id, "补中益气丸", "8粒", '["08:00"]', 0),
    )
    await db.execute(
        "INSERT INTO favorites (id, user_id, entry_type, entry_id, title, tags, is_starred) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, "herb", "herb-001", "黄芪", '["补气"]', 1),
    )
    await db.execute(
        "INSERT INTO share_cards (id, user_id, family_id, card_type, card_data, is_monthly_report) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, family_id, "health_summary", "{}", 0),
    )
    return member_id


@pytest.mark.asyncio
async def test_export_returns_valid_json(client: AsyncClient, auth_headers: dict):
    """GET /api/export returns 200 with valid JSON envelope."""
    response = await client.get("/api/export", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    # Top-level envelope keys
    assert "export_date" in data
    assert "user" in data
    assert "data" in data

    # export_date should be ISO-8601
    export_date = data["export_date"]
    assert isinstance(export_date, str)
    # Should parse as ISO datetime
    datetime.fromisoformat(export_date)

    # user sub-object shape
    user = data["user"]
    assert "id" in user
    assert "username" in user
    assert "family_id" in user
    assert user["username"] == "testuser"


@pytest.mark.asyncio
async def test_export_requires_auth(raw_client: AsyncClient):
    """GET /api/export without auth token returns 401."""
    response = await raw_client.get("/api/export")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_export_user_isolation(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    """User A's data must not appear in user B's export.

    User A creates a medicine + reminder; user B's export should not contain them.
    """
    # --- User A creates a medicine ---
    med_resp = await client.post(
        "/api/medicines",
        headers=auth_headers,
        json={"name": "用户A专属药", "type": "western", "quantity": 10},
    )
    assert med_resp.status_code == 201
    med_a_name = med_resp.json()["name"]

    # --- User A creates a reminder ---
    rem_resp = await client.post(
        "/api/reminders",
        headers=auth_headers,
        json={
            "title": "用户A专属提醒",
            "frequency": "daily",
            "times": ["08:00"],
            "start_date": _today_str(),
        },
    )
    assert rem_resp.status_code == 201
    rem_a_title = rem_resp.json()["title"]

    # --- User B exports their data ---
    b_export = await client.get("/api/export", headers=second_user_headers)
    assert b_export.status_code == 200
    b_data = b_export.json()["data"]

    # User B must NOT see user A's medicine
    b_med_names = [m.get("name") for m in b_data["medicines"]]
    assert med_a_name not in b_med_names

    # User B must NOT see user A's reminders
    b_rem_titles = [r.get("title") for r in b_data["reminders"]]
    assert rem_a_title not in b_rem_titles

    # --- User A exports and SHOULD see their own data ---
    a_export = await client.get("/api/export", headers=auth_headers)
    assert a_export.status_code == 200
    a_data = a_export.json()["data"]

    a_med_names = [m.get("name") for m in a_data["medicines"]]
    assert med_a_name in a_med_names

    a_rem_titles = [r.get("title") for r in a_data["reminders"]]
    assert rem_a_title in a_rem_titles


@pytest.mark.asyncio
async def test_export_includes_all_tables(client: AsyncClient, auth_headers: dict):
    """Export response data object contains all expected table keys."""
    # Seed a few records so we can also verify structure parsing
    await client.post(
        "/api/medicines",
        headers=auth_headers,
        json={"name": "测试药品", "type": "western", "quantity": 5},
    )
    await client.post(
        "/api/reminders",
        headers=auth_headers,
        json={
            "title": "测试提醒",
            "frequency": "daily",
            "times": ["09:00"],
            "start_date": _today_str(),
        },
    )

    response = await client.get("/api/export", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]

    # All tables defined by the export endpoint must be present
    expected_keys = {
        "profile",
        "medicines",
        "reminders",
        "constitution_assessments",
        "conversations",
        "knowledge_entries",
        "medication_logs",
        "health_logs",
        "medical_visits",
        "medication_plans",
        "favorites",
        "share_cards",
    }
    assert expected_keys.issubset(set(data.keys())), (
        f"Missing keys: {expected_keys - set(data.keys())}"
    )

    # medicines & reminders should be non-empty lists (we just created them)
    assert isinstance(data["medicines"], list)
    assert len(data["medicines"]) >= 1
    assert isinstance(data["reminders"], list)
    assert len(data["reminders"]) >= 1

    # Each medicine row should have JSON fields parsed (not raw strings)
    med = data["medicines"][0]
    # active_ingredients / batches / photos should be list-like (parsed), not a str
    for field in ("active_ingredients", "batches", "photos"):
        val = med.get(field)
        assert val is None or isinstance(val, list), (
            f"medicine.{field} should be list, got {type(val).__name__}"
        )
    # herbal_fields / properties should be dict-like
    for field in ("herbal_fields", "properties"):
        val = med.get(field)
        assert val is None or isinstance(val, dict), (
            f"medicine.{field} should be dict, got {type(val).__name__}"
        )

    # reminder times should be a list
    rem = data["reminders"][0]
    assert isinstance(rem.get("times"), list)
    # enabled should be a bool
    assert isinstance(rem.get("enabled"), bool)


@pytest.mark.asyncio
async def test_export_empty_user(client: AsyncClient, auth_headers: dict):
    """Fresh user (no records) returns valid structure with empty arrays."""
    response = await client.get("/api/export", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    # Envelope still present
    assert "export_date" in data
    assert "user" in data
    assert "data" in data

    inner = data["data"]
    # All list-typed tables must be empty lists (not None, not missing)
    for key in (
        "medicines",
        "reminders",
        "constitution_assessments",
        "conversations",
        "knowledge_entries",
        "medication_logs",
        "health_logs",
        "medical_visits",
        "medication_plans",
        "favorites",
        "share_cards",
    ):
        assert key in inner, f"Missing key: {key}"
        assert inner[key] == [], f"Fresh user {key} should be empty list"

    # profile may be None for a brand-new user (no profile row yet)
    assert "profile" in inner


@pytest.mark.asyncio
async def test_export_full_data_all_sections_nonempty(
    client: AsyncClient, auth_headers: dict, db: SqliteAdapter
):
    """Seed one row per data class → every exported section is non-empty.

    Regression: medication_logs is keyed by family_members.id — a log row
    whose family_member_id equals the *user_id* must NOT match, only the
    row joined through the user's family member must be exported.
    """
    user_row = await db.query_one(
        "SELECT id, family_id FROM users WHERE username = 'testuser'"
    )
    assert user_row is not None

    # Decoy: a log keyed by a family_member_id that equals user_id must not
    # leak into the export (old buggy WHERE family_member_id = user_id match).
    await db.execute(
        "INSERT INTO medication_logs (id, family_member_id, date, medicine_id) "
        "VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), user_row["id"], "2026-01-16", "med-decoy"),
    )

    member_id = await _seed_all_data_classes(
        db, user_row["id"], user_row["family_id"]
    )

    response = await client.get("/api/export", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]

    # profile
    assert isinstance(data["profile"], dict)
    assert data["profile"]["user_id"] == user_row["id"]

    # every list section non-empty
    for key in (
        "medicines",
        "reminders",
        "constitution_assessments",
        "conversations",
        "knowledge_entries",
        "medication_logs",
        "health_logs",
        "medical_visits",
        "medication_plans",
        "favorites",
        "share_cards",
    ):
        assert isinstance(data[key], list) and len(data[key]) >= 1, (
            f"{key} should be non-empty after seeding"
        )

    # medication_logs — joined through family_members, with member name
    logs = data["medication_logs"]
    assert len(logs) == 1, "decoy row (family_member_id == user_id) must not match"
    assert logs[0]["family_member_id"] == member_id
    assert logs[0]["family_member_name"] == "王阿姨"
    assert logs[0]["taken"] is True

    # health_logs / medical_visits / share_cards / favorites content checks
    assert data["health_logs"][0]["systolic"] == 120
    assert data["medical_visits"][0]["hospital"] == "市中医院"
    assert data["medical_visits"][0]["attachments"] == []
    assert data["favorites"][0]["title"] == "黄芪"
    assert data["favorites"][0]["tags"] == ["补气"]
    assert data["favorites"][0]["is_starred"] is True
    assert data["share_cards"][0]["card_type"] == "health_summary"
    assert data["share_cards"][0]["card_data"] == {}

    # medication_plans carry their nested items
    plan = data["medication_plans"][0]
    assert plan["name"] == "冬季调理套餐"
    assert len(plan["items"]) == 1
    assert plan["items"][0]["medicine_name"] == "补中益气丸"
    assert plan["items"][0]["times"] == ["08:00"]
