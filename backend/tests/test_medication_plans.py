"""Tests for medication plans (用药套餐) — CRUD, auto-reminder generation, pause/resume, cascade delete."""

from datetime import datetime, timezone, timedelta

import pytest
from httpx import AsyncClient

CST = timezone(timedelta(hours=8))


def _today_str() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d")


def _future_date(days: int = 30) -> str:
    return (datetime.now(CST) + timedelta(days=days)).strftime("%Y-%m-%d")


def _sample_plan_payload(name: str = "脾虚湿困调理方案") -> dict:
    return {
        "name": name,
        "description": "健脾祛湿，每日三次",
        "status": "active",
        "start_date": _today_str(),
        "items": [
            {
                "medicine_name": "参苓白术散",
                "dosage": "6g",
                "frequency": "daily",
                "times": ["07:00", "12:00", "19:00"],
                "notes": "饭前服用",
            },
            {
                "medicine_name": "Q10辅酶",
                "dosage": "1粒",
                "frequency": "daily",
                "times": ["08:00"],
                "notes": "早饭后",
            },
        ],
    }


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_plan_with_multiple_items(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/medication-plans",
        headers=auth_headers,
        json=_sample_plan_payload(),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "脾虚湿困调理方案"
    assert data["status"] == "active"
    assert len(data["items"]) == 2
    assert data["items"][0]["medicine_name"] == "参苓白术散"
    assert data["items"][1]["medicine_name"] == "Q10辅酶"
    assert data["items"][0]["times"] == ["07:00", "12:00", "19:00"]


@pytest.mark.asyncio
async def test_create_plan_auto_generates_reminders(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/medication-plans",
        headers=auth_headers,
        json=_sample_plan_payload(),
    )
    assert create_resp.status_code == 201
    plan_data = create_resp.json()

    for item in plan_data["items"]:
        assert item["reminder_id"] is not None
        reminder_resp = await client.get(
            f"/api/reminders/{item['reminder_id']}", headers=auth_headers
        )
        assert reminder_resp.status_code == 200
        reminder = reminder_resp.json()
        assert reminder["medicine_name"] == item["medicine_name"]
        assert reminder["dosage"] == item["dosage"]
        assert reminder["times"] == item["times"]
        assert reminder["enabled"] is True
        assert "脾虚湿困调理方案" in reminder["title"]


@pytest.mark.asyncio
async def test_create_plan_creates_correct_number_of_reminders(
    client: AsyncClient, auth_headers: dict
):
    before = await client.get("/api/reminders", headers=auth_headers)
    before_count = before.json()["total"]

    await client.post(
        "/api/medication-plans",
        headers=auth_headers,
        json=_sample_plan_payload(),
    )

    after = await client.get("/api/reminders", headers=auth_headers)
    assert after.json()["total"] == before_count + 2


@pytest.mark.asyncio
async def test_create_plan_requires_at_least_one_item(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/medication-plans",
        headers=auth_headers,
        json={
            "name": "空套餐",
            "start_date": _today_str(),
            "items": [],
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_plan_default_start_date_is_today(
    client: AsyncClient, auth_headers: dict
):
    response = await client.post(
        "/api/medication-plans",
        headers=auth_headers,
        json={
            "name": "无开始日期",
            "items": [
                {"medicine_name": "维生素D", "times": ["08:00"]},
            ],
        },
    )
    assert response.status_code == 201
    assert response.json()["start_date"] == _today_str()


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_plans(client: AsyncClient, auth_headers: dict):
    await client.post(
        "/api/medication-plans",
        headers=auth_headers,
        json=_sample_plan_payload("套餐一"),
    )
    await client.post(
        "/api/medication-plans",
        headers=auth_headers,
        json=_sample_plan_payload("套餐二"),
    )
    response = await client.get("/api/medication-plans", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    names = [p["name"] for p in data["items"]]
    assert "套餐一" in names
    assert "套餐二" in names


@pytest.mark.asyncio
async def test_list_plans_user_isolation(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    await client.post(
        "/api/medication-plans",
        headers=auth_headers,
        json=_sample_plan_payload("用户A的套餐"),
    )
    response = await client.get("/api/medication-plans", headers=second_user_headers)
    names = [p["name"] for p in response.json()["items"]]
    assert "用户A的套餐" not in names


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_plan_detail_with_items(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/medication-plans",
        headers=auth_headers,
        json=_sample_plan_payload(),
    )
    plan_id = create_resp.json()["id"]
    response = await client.get(
        f"/api/medication-plans/{plan_id}", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == plan_id
    assert len(data["items"]) == 2
    assert all("reminder_id" in item for item in data["items"])


@pytest.mark.asyncio
async def test_get_nonexistent_plan_404(client: AsyncClient, auth_headers: dict):
    response = await client.get(
        "/api/medication-plans/nonexistent-id", headers=auth_headers
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_plan_other_user_404(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    create_resp = await client.post(
        "/api/medication-plans",
        headers=auth_headers,
        json=_sample_plan_payload(),
    )
    plan_id = create_resp.json()["id"]
    response = await client.get(
        f"/api/medication-plans/{plan_id}", headers=second_user_headers
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_plan_name(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/medication-plans",
        headers=auth_headers,
        json=_sample_plan_payload("旧名称"),
    )
    plan_id = create_resp.json()["id"]
    response = await client.put(
        f"/api/medication-plans/{plan_id}",
        headers=auth_headers,
        json={"name": "新名称"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "新名称"


@pytest.mark.asyncio
async def test_update_plan_status(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/medication-plans",
        headers=auth_headers,
        json=_sample_plan_payload(),
    )
    plan_id = create_resp.json()["id"]
    response = await client.put(
        f"/api/medication-plans/{plan_id}",
        headers=auth_headers,
        json={"status": "completed"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_update_plan_invalid_status(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/medication-plans",
        headers=auth_headers,
        json=_sample_plan_payload(),
    )
    plan_id = create_resp.json()["id"]
    response = await client.put(
        f"/api/medication-plans/{plan_id}",
        headers=auth_headers,
        json={"status": "invalid"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_nonexistent_plan_404(client: AsyncClient, auth_headers: dict):
    response = await client.put(
        "/api/medication-plans/nonexistent-id",
        headers=auth_headers,
        json={"name": "更新"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Pause / Resume
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pause_plan_disables_all_reminders(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/medication-plans",
        headers=auth_headers,
        json=_sample_plan_payload(),
    )
    plan_id = create_resp.json()["id"]
    pause_resp = await client.post(
        f"/api/medication-plans/{plan_id}/pause", headers=auth_headers
    )
    assert pause_resp.status_code == 200
    assert pause_resp.json()["status"] == "paused"

    for item in create_resp.json()["items"]:
        reminder_resp = await client.get(
            f"/api/reminders/{item['reminder_id']}", headers=auth_headers
        )
        assert reminder_resp.json()["enabled"] is False


@pytest.mark.asyncio
async def test_resume_plan_reenables_all_reminders(
    client: AsyncClient, auth_headers: dict
):
    create_resp = await client.post(
        "/api/medication-plans",
        headers=auth_headers,
        json=_sample_plan_payload(),
    )
    plan_id = create_resp.json()["id"]
    await client.post(f"/api/medication-plans/{plan_id}/pause", headers=auth_headers)

    resume_resp = await client.post(
        f"/api/medication-plans/{plan_id}/resume", headers=auth_headers
    )
    assert resume_resp.status_code == 200
    assert resume_resp.json()["status"] == "active"

    for item in create_resp.json()["items"]:
        reminder_resp = await client.get(
            f"/api/reminders/{item['reminder_id']}", headers=auth_headers
        )
        assert reminder_resp.json()["enabled"] is True


@pytest.mark.asyncio
async def test_pause_then_resume_idempotent(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/medication-plans",
        headers=auth_headers,
        json=_sample_plan_payload(),
    )
    plan_id = create_resp.json()["id"]

    await client.post(f"/api/medication-plans/{plan_id}/pause", headers=auth_headers)
    await client.post(f"/api/medication-plans/{plan_id}/pause", headers=auth_headers)
    paused = await client.get(
        f"/api/medication-plans/{plan_id}", headers=auth_headers
    )
    assert paused.json()["status"] == "paused"

    await client.post(f"/api/medication-plans/{plan_id}/resume", headers=auth_headers)
    resumed = await client.get(
        f"/api/medication-plans/{plan_id}", headers=auth_headers
    )
    assert resumed.json()["status"] == "active"


@pytest.mark.asyncio
async def test_pause_nonexistent_404(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/medication-plans/nonexistent-id/pause", headers=auth_headers
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_resume_nonexistent_404(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/medication-plans/nonexistent-id/resume", headers=auth_headers
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_pause_plan_other_user_404(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    create_resp = await client.post(
        "/api/medication-plans",
        headers=auth_headers,
        json=_sample_plan_payload(),
    )
    plan_id = create_resp.json()["id"]
    response = await client.post(
        f"/api/medication-plans/{plan_id}/pause", headers=second_user_headers
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Delete (cascade)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_plan_cascades_items_and_reminders(
    client: AsyncClient, auth_headers: dict
):
    create_resp = await client.post(
        "/api/medication-plans",
        headers=auth_headers,
        json=_sample_plan_payload(),
    )
    plan_data = create_resp.json()
    plan_id = plan_data["id"]
    item_ids = [item["id"] for item in plan_data["items"]]
    reminder_ids = [item["reminder_id"] for item in plan_data["items"]]

    del_resp = await client.delete(
        f"/api/medication-plans/{plan_id}", headers=auth_headers
    )
    assert del_resp.status_code == 200

    get_resp = await client.get(
        f"/api/medication-plans/{plan_id}", headers=auth_headers
    )
    assert get_resp.status_code == 404

    for rid in reminder_ids:
        reminder_resp = await client.get(
            f"/api/reminders/{rid}", headers=auth_headers
        )
        assert reminder_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_404(client: AsyncClient, auth_headers: dict):
    response = await client.delete(
        "/api/medication-plans/nonexistent-id", headers=auth_headers
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_plan_other_user_404(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    create_resp = await client.post(
        "/api/medication-plans",
        headers=auth_headers,
        json=_sample_plan_payload(),
    )
    plan_id = create_resp.json()["id"]
    response = await client.delete(
        f"/api/medication-plans/{plan_id}", headers=second_user_headers
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unauthorized_access(raw_client: AsyncClient):
    response = await raw_client.get("/api/medication-plans")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_unauthorized_create(raw_client: AsyncClient):
    response = await raw_client.post("/api/medication-plans", json=_sample_plan_payload())
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_plan_invalid_status(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/medication-plans",
        headers=auth_headers,
        json={
            "name": "无效状态",
            "status": "archived",
            "start_date": _today_str(),
            "items": [{"medicine_name": "测试", "times": ["08:00"]}],
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_plan_end_date_before_start(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/medication-plans",
        headers=auth_headers,
        json={
            "name": "日期倒置",
            "start_date": _today_str(),
            "end_date": "2020-01-01",
            "items": [{"medicine_name": "测试", "times": ["08:00"]}],
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_plan_empty_name(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/medication-plans",
        headers=auth_headers,
        json={
            "name": "",
            "start_date": _today_str(),
            "items": [{"medicine_name": "测试", "times": ["08:00"]}],
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_plan_invalid_time_format(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/medication-plans",
        headers=auth_headers,
        json={
            "name": "无效时间",
            "start_date": _today_str(),
            "items": [{"medicine_name": "测试", "times": ["25:00"]}],
        },
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Full lifecycle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_lifecycle(client: AsyncClient, auth_headers: dict):
    # 1. Create
    create_resp = await client.post(
        "/api/medication-plans",
        headers=auth_headers,
        json=_sample_plan_payload("生命周期套餐"),
    )
    assert create_resp.status_code == 201
    plan_id = create_resp.json()["id"]
    assert len(create_resp.json()["items"]) == 2

    # 2. Verify reminders created
    reminders_before = await client.get("/api/reminders", headers=auth_headers)
    assert reminders_before.json()["total"] == 2

    # 3. Pause
    pause_resp = await client.post(
        f"/api/medication-plans/{plan_id}/pause", headers=auth_headers
    )
    assert pause_resp.json()["status"] == "paused"
    enabled_reminders = await client.get(
        "/api/reminders?enabled=true", headers=auth_headers
    )
    assert enabled_reminders.json()["total"] == 0

    # 4. Resume
    resume_resp = await client.post(
        f"/api/medication-plans/{plan_id}/resume", headers=auth_headers
    )
    assert resume_resp.json()["status"] == "active"
    enabled_after = await client.get(
        "/api/reminders?enabled=true", headers=auth_headers
    )
    assert enabled_after.json()["total"] == 2

    # 5. Delete
    del_resp = await client.delete(
        f"/api/medication-plans/{plan_id}", headers=auth_headers
    )
    assert del_resp.status_code == 200
    reminders_after = await client.get("/api/reminders", headers=auth_headers)
    assert reminders_after.json()["total"] == 0
