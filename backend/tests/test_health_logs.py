"""Tests for /api/health-logs — daily health log CRUD (血压/血糖/体重/睡眠/心情)."""

from datetime import datetime, timezone, timedelta

import pytest
from httpx import AsyncClient

CST = timezone(timedelta(hours=8))


def _today_str(offset_days: int = 0) -> str:
    return (datetime.now(CST) + timedelta(days=offset_days)).strftime("%Y-%m-%d")


def _sample_log(date_str: str | None = None, **overrides) -> dict:
    payload = {
        "log_date": date_str or _today_str(),
        "systolic": 120,
        "diastolic": 80,
        "blood_sugar": 5.6,
        "weight": 65.5,
        "sleep_hours": 7.5,
        "mood": "好",
        "notes": "感觉良好",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_health_log_full(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/health-logs", headers=auth_headers, json=_sample_log()
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["systolic"] == 120
    assert data["diastolic"] == 80
    assert data["blood_sugar"] == 5.6
    assert data["weight"] == 65.5
    assert data["sleep_hours"] == 7.5
    assert data["mood"] == "好"
    assert data["notes"] == "感觉良好"


@pytest.mark.asyncio
async def test_create_health_log_minimal_notes_only(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/health-logs",
        headers=auth_headers,
        json={"log_date": _today_str(), "notes": "今天没量"},
    )
    assert response.status_code == 201
    assert response.json()["notes"] == "今天没量"


@pytest.mark.asyncio
async def test_create_log_rejects_empty(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/health-logs",
        headers=auth_headers,
        json={"log_date": _today_str()},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_log_rejects_invalid_mood(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/health-logs",
        headers=auth_headers,
        json={"log_date": _today_str(), "mood": "happy"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_log_rejects_bp_pair_incomplete(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/health-logs",
        headers=auth_headers,
        json={"log_date": _today_str(), "systolic": 120},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_log_rejects_systolic_le_diastolic(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/health-logs",
        headers=auth_headers,
        json={"log_date": _today_str(), "systolic": 80, "diastolic": 120},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_log_duplicate_date_conflict(client: AsyncClient, auth_headers: dict):
    today = _today_str()
    first = await client.post(
        "/api/health-logs", headers=auth_headers, json=_sample_log(today)
    )
    assert first.status_code == 201
    second = await client.post(
        "/api/health-logs", headers=auth_headers, json=_sample_log(today, weight=70.0)
    )
    assert second.status_code == 409


# ---------------------------------------------------------------------------
# List / Latest
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_health_logs_orders_recent_first(client: AsyncClient, auth_headers: dict):
    await client.post(
        "/api/health-logs",
        headers=auth_headers,
        json=_sample_log(_today_str(-3), weight=60.0),
    )
    await client.post(
        "/api/health-logs",
        headers=auth_headers,
        json=_sample_log(_today_str(-1), weight=62.0),
    )
    await client.post(
        "/api/health-logs",
        headers=auth_headers,
        json=_sample_log(_today_str(0), weight=63.0),
    )
    response = await client.get("/api/health-logs?days=30", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    dates = [item["log_date"] for item in data["items"]]
    assert dates == sorted(dates, reverse=True)


@pytest.mark.asyncio
async def test_list_health_logs_days_filter(client: AsyncClient, auth_headers: dict):
    await client.post(
        "/api/health-logs",
        headers=auth_headers,
        json=_sample_log(_today_str(-20), weight=60.0),
    )
    await client.post(
        "/api/health-logs",
        headers=auth_headers,
        json=_sample_log(_today_str(0), weight=63.0),
    )
    response = await client.get("/api/health-logs?days=7", headers=auth_headers)
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["weight"] == 63.0


@pytest.mark.asyncio
async def test_get_latest_returns_most_recent(client: AsyncClient, auth_headers: dict):
    await client.post(
        "/api/health-logs",
        headers=auth_headers,
        json=_sample_log(_today_str(-2), weight=60.0, notes="two days ago"),
    )
    await client.post(
        "/api/health-logs",
        headers=auth_headers,
        json=_sample_log(_today_str(0), weight=63.0, notes="today"),
    )
    response = await client.get("/api/health-logs/latest", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["item"] is not None
    assert data["item"]["notes"] == "today"


@pytest.mark.asyncio
async def test_get_latest_when_empty(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/health-logs/latest", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["item"] is None


# ---------------------------------------------------------------------------
# Update / Delete
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_health_log(client: AsyncClient, auth_headers: dict):
    create = await client.post(
        "/api/health-logs", headers=auth_headers, json=_sample_log(weight=60.0)
    )
    log_id = create.json()["id"]
    update = await client.put(
        f"/api/health-logs/{log_id}",
        headers=auth_headers,
        json={"weight": 62.5, "notes": "更新备注"},
    )
    assert update.status_code == 200
    data = update.json()
    assert data["weight"] == 62.5
    assert data["notes"] == "更新备注"


@pytest.mark.asyncio
async def test_delete_health_log(client: AsyncClient, auth_headers: dict):
    create = await client.post(
        "/api/health-logs", headers=auth_headers, json=_sample_log()
    )
    log_id = create.json()["id"]
    delete = await client.delete(f"/api/health-logs/{log_id}", headers=auth_headers)
    assert delete.status_code == 200
    missing = await client.get(f"/api/health-logs/{log_id}", headers=auth_headers)
    assert missing.status_code == 404


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_log_isolated_between_users(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    await client.post(
        "/api/health-logs",
        headers=auth_headers,
        json=_sample_log(_today_str(), weight=70.0, notes="user1"),
    )
    await client.post(
        "/api/health-logs",
        headers=second_user_headers,
        json=_sample_log(_today_str(), weight=80.0, notes="user2"),
    )
    r1 = await client.get("/api/health-logs", headers=auth_headers)
    r2 = await client.get("/api/health-logs", headers=second_user_headers)
    assert r1.json()["total"] == 1
    assert r1.json()["items"][0]["notes"] == "user1"
    assert r2.json()["total"] == 1
    assert r2.json()["items"][0]["notes"] == "user2"


@pytest.mark.asyncio
async def test_health_log_requires_auth(client: AsyncClient):
    response = await client.get("/api/health-logs")
    assert response.status_code in (401, 403)
