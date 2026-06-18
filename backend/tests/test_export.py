"""Tests for GET /api/export endpoint — PIPL 合规数据导出.

Covers:
- 200 response with valid JSON structure
- 401 without auth token
- User isolation (user A cannot see user B's data)
- Response includes all expected data tables
- Fresh user returns valid structure with empty arrays
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest
from httpx import AsyncClient

CST = timezone(timedelta(hours=8))


def _today_str() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d")


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
async def test_export_requires_auth(client: AsyncClient):
    """GET /api/export without auth token returns 401."""
    response = await client.get("/api/export")
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
    ):
        assert key in inner, f"Missing key: {key}"
        assert inner[key] == [], f"Fresh user {key} should be empty list"

    # profile may be None for a brand-new user (no profile row yet)
    assert "profile" in inner
