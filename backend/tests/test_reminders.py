"""Tests for reminders CRUD + today endpoint."""

from datetime import datetime, timezone, timedelta

import pytest
from httpx import AsyncClient

CST = timezone(timedelta(hours=8))


def _today_str() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d")


def _future_date(days: int = 30) -> str:
    return (datetime.now(CST) + timedelta(days=days)).strftime("%Y-%m-%d")


def _past_date(days: int = 1) -> str:
    return (datetime.now(CST) - timedelta(days=days)).strftime("%Y-%m-%d")


@pytest.mark.asyncio
async def test_create_reminder_daily_two_times(client: AsyncClient, auth_headers: dict):
    response = await client.post("/api/reminders", headers=auth_headers, json={
        "title": "服用降压药",
        "frequency": "daily",
        "times": ["08:00", "20:00"],
        "start_date": _today_str(),
    })
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "服用降压药"
    assert data["frequency"] == "daily"
    assert data["times"] == ["08:00", "20:00"]
    assert data["enabled"] is True
    assert "id" in data


@pytest.mark.asyncio
async def test_create_reminder_with_herb_link(client: AsyncClient, auth_headers: dict):
    response = await client.post("/api/reminders", headers=auth_headers, json={
        "title": "煎服黄芪",
        "herb_name": "黄芪",
        "dosage": "15g煎服",
        "frequency": "daily",
        "times": ["09:00"],
        "start_date": _today_str(),
    })
    assert response.status_code == 201
    data = response.json()
    assert data["herb_name"] == "黄芪"
    assert data["dosage"] == "15g煎服"


@pytest.mark.asyncio
async def test_create_reminder_with_medicine_link(client: AsyncClient, auth_headers: dict):
    response = await client.post("/api/reminders", headers=auth_headers, json={
        "title": "服用阿司匹林",
        "medicine_name": "阿司匹林肠溶片",
        "dosage": "1片",
        "frequency": "daily",
        "times": ["07:30"],
        "start_date": _today_str(),
    })
    assert response.status_code == 201
    data = response.json()
    assert data["medicine_name"] == "阿司匹林肠溶片"


@pytest.mark.asyncio
async def test_create_reminder_with_formula_link(client: AsyncClient, auth_headers: dict):
    response = await client.post("/api/reminders", headers=auth_headers, json={
        "title": "服用四物汤",
        "formula_name": "四物汤",
        "dosage": "200ml温服",
        "frequency": "daily",
        "times": ["18:00"],
        "start_date": _today_str(),
    })
    assert response.status_code == 201
    data = response.json()
    assert data["formula_name"] == "四物汤"


@pytest.mark.asyncio
async def test_list_reminders_user_isolation(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    await client.post("/api/reminders", headers=auth_headers, json={
        "title": "用户A的提醒",
        "times": ["08:00"],
        "start_date": _today_str(),
    })
    response = await client.get("/api/reminders", headers=second_user_headers)
    assert response.status_code == 200
    data = response.json()
    titles = [r["title"] for r in data["items"]]
    assert "用户A的提醒" not in titles


@pytest.mark.asyncio
async def test_get_single_reminder(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/reminders", headers=auth_headers, json={
        "title": "维生素D",
        "times": ["12:00"],
        "start_date": _today_str(),
    })
    rid = create_resp.json()["id"]
    response = await client.get(f"/api/reminders/{rid}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["title"] == "维生素D"


@pytest.mark.asyncio
async def test_update_reminder_title(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/reminders", headers=auth_headers, json={
        "title": "旧标题",
        "times": ["08:00"],
        "start_date": _today_str(),
    })
    rid = create_resp.json()["id"]
    response = await client.put(
        f"/api/reminders/{rid}",
        headers=auth_headers,
        json={"title": "新标题"},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "新标题"


@pytest.mark.asyncio
async def test_update_reminder_times(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/reminders", headers=auth_headers, json={
        "title": "提醒",
        "times": ["08:00"],
        "start_date": _today_str(),
    })
    rid = create_resp.json()["id"]
    response = await client.put(
        f"/api/reminders/{rid}",
        headers=auth_headers,
        json={"times": ["07:00", "19:00", "23:00"]},
    )
    assert response.status_code == 200
    assert response.json()["times"] == ["07:00", "19:00", "23:00"]


@pytest.mark.asyncio
async def test_toggle_enable(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/reminders", headers=auth_headers, json={
        "title": "可切换",
        "times": ["08:00"],
        "start_date": _today_str(),
    })
    rid = create_resp.json()["id"]
    assert create_resp.json()["enabled"] is True

    off_resp = await client.put(f"/api/reminders/{rid}/toggle", headers=auth_headers)
    assert off_resp.status_code == 200
    assert off_resp.json()["enabled"] is False

    on_resp = await client.put(f"/api/reminders/{rid}/toggle", headers=auth_headers)
    assert on_resp.json()["enabled"] is True


@pytest.mark.asyncio
async def test_delete_reminder(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/reminders", headers=auth_headers, json={
        "title": "待删除",
        "times": ["08:00"],
        "start_date": _today_str(),
    })
    rid = create_resp.json()["id"]
    del_resp = await client.delete(f"/api/reminders/{rid}", headers=auth_headers)
    assert del_resp.status_code == 200
    get_resp = await client.get(f"/api/reminders/{rid}", headers=auth_headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_get_today_reminders_time_expansion(client: AsyncClient, auth_headers: dict):
    await client.post("/api/reminders", headers=auth_headers, json={
        "title": "每日三次",
        "times": ["08:00", "13:00", "20:00"],
        "start_date": _today_str(),
    })
    response = await client.get("/api/reminders/today", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    times = [s["time"] for s in data["items"]]
    assert times == ["08:00", "13:00", "20:00"]


@pytest.mark.asyncio
async def test_today_status_missed_and_pending(client: AsyncClient, auth_headers: dict):
    now = datetime.now(CST)
    past_time = (now - timedelta(hours=4)).strftime("%H:%M")
    future_time = (now + timedelta(hours=4)).strftime("%H:%M")
    await client.post("/api/reminders", headers=auth_headers, json={
        "title": "混合状态",
        "times": [past_time, future_time],
        "start_date": _today_str(),
    })
    response = await client.get("/api/reminders/today", headers=auth_headers)
    data = response.json()
    by_time = {s["time"]: s["status"] for s in data["items"]}
    assert by_time[past_time] == "漏服"
    assert by_time[future_time] == "待服"


@pytest.mark.asyncio
async def test_filter_enabled_only(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/reminders", headers=auth_headers, json={
        "title": "已停用",
        "times": ["08:00"],
        "start_date": _today_str(),
    })
    rid = create_resp.json()["id"]
    await client.put(f"/api/reminders/{rid}/toggle", headers=auth_headers)

    resp_all = await client.get("/api/reminders", headers=auth_headers)
    assert any(r["title"] == "已停用" for r in resp_all.json()["items"])

    resp_enabled = await client.get(
        "/api/reminders?enabled=true", headers=auth_headers
    )
    titles = [r["title"] for r in resp_enabled.json()["items"]]
    assert "已停用" not in titles


@pytest.mark.asyncio
async def test_unauthorized_access(client: AsyncClient):
    response = await client.get("/api/reminders")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_access_other_user_reminder_404(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    create_resp = await client.post("/api/reminders", headers=auth_headers, json={
        "title": "私有的",
        "times": ["08:00"],
        "start_date": _today_str(),
    })
    rid = create_resp.json()["id"]
    response = await client.get(f"/api/reminders/{rid}", headers=second_user_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_invalid_frequency(client: AsyncClient, auth_headers: dict):
    response = await client.post("/api/reminders", headers=auth_headers, json={
        "title": "无效频率",
        "frequency": "hourly",
        "times": ["08:00"],
        "start_date": _today_str(),
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_empty_times(client: AsyncClient, auth_headers: dict):
    response = await client.post("/api/reminders", headers=auth_headers, json={
        "title": "无时间",
        "times": [],
        "start_date": _today_str(),
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_end_date_before_start_date(client: AsyncClient, auth_headers: dict):
    response = await client.post("/api/reminders", headers=auth_headers, json={
        "title": "日期倒置",
        "times": ["08:00"],
        "start_date": _today_str(),
        "end_date": _past_date(1),
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_with_notes(client: AsyncClient, auth_headers: dict):
    response = await client.post("/api/reminders", headers=auth_headers, json={
        "title": "有备注",
        "times": ["08:00"],
        "start_date": _today_str(),
        "notes": "饭后半小时服用",
    })
    assert response.status_code == 201
    assert response.json()["notes"] == "饭后半小时服用"


@pytest.mark.asyncio
async def test_create_with_dosage(client: AsyncClient, auth_headers: dict):
    response = await client.post("/api/reminders", headers=auth_headers, json={
        "title": "有剂量",
        "times": ["08:00"],
        "start_date": _today_str(),
        "dosage": "2片",
    })
    assert response.status_code == 201
    assert response.json()["dosage"] == "2片"


@pytest.mark.asyncio
async def test_today_excludes_disabled(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/reminders", headers=auth_headers, json={
        "title": "已停用不在今天",
        "times": ["08:00"],
        "start_date": _today_str(),
    })
    rid = create_resp.json()["id"]
    await client.put(f"/api/reminders/{rid}/toggle", headers=auth_headers)

    resp = await client.get("/api/reminders/today", headers=auth_headers)
    titles = [s["title"] for s in resp.json()["items"]]
    assert "已停用不在今天" not in titles


@pytest.mark.asyncio
async def test_today_excludes_future_start(client: AsyncClient, auth_headers: dict):
    await client.post("/api/reminders", headers=auth_headers, json={
        "title": "未来开始",
        "times": ["08:00"],
        "start_date": _future_date(5),
    })
    resp = await client.get("/api/reminders/today", headers=auth_headers)
    titles = [s["title"] for s in resp.json()["items"]]
    assert "未来开始" not in titles


@pytest.mark.asyncio
async def test_today_excludes_expired(client: AsyncClient, auth_headers: dict):
    await client.post("/api/reminders", headers=auth_headers, json={
        "title": "已过期",
        "times": ["08:00"],
        "start_date": _past_date(10),
        "end_date": _past_date(1),
    })
    resp = await client.get("/api/reminders/today", headers=auth_headers)
    titles = [s["title"] for s in resp.json()["items"]]
    assert "已过期" not in titles


@pytest.mark.asyncio
async def test_today_excludes_other_user(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    await client.post("/api/reminders", headers=auth_headers, json={
        "title": "用户A今天",
        "times": ["08:00"],
        "start_date": _today_str(),
    })
    resp = await client.get("/api/reminders/today", headers=second_user_headers)
    titles = [s["title"] for s in resp.json()["items"]]
    assert "用户A今天" not in titles


@pytest.mark.asyncio
async def test_update_nonexistent_404(client: AsyncClient, auth_headers: dict):
    response = await client.put(
        "/api/reminders/nonexistent-id",
        headers=auth_headers,
        json={"title": "不存在"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_404(client: AsyncClient, auth_headers: dict):
    response = await client.delete(
        "/api/reminders/nonexistent-id", headers=auth_headers
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_toggle_nonexistent_404(client: AsyncClient, auth_headers: dict):
    response = await client.put(
        "/api/reminders/nonexistent-id/toggle", headers=auth_headers
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_with_no_end_date_indefinite(client: AsyncClient, auth_headers: dict):
    response = await client.post("/api/reminders", headers=auth_headers, json={
        "title": "无限期",
        "times": ["08:00"],
        "start_date": _today_str(),
    })
    assert response.status_code == 201
    assert response.json()["end_date"] is None


@pytest.mark.asyncio
async def test_check_in_with_past_date(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/reminders", headers=auth_headers, json={
        "title": "补打测试",
        "times": ["08:00"],
        "start_date": _past_date(5),
    })
    rid = create_resp.json()["id"]
    past = _past_date(1)
    resp = await client.post(
        f"/api/reminders/{rid}/check-in",
        headers=auth_headers,
        json={"taken": True, "date": past, "time": "08:00", "retroactive": True},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["date"] == past
    assert data["taken"] is True
    assert data["retroactive"] is True
    assert data["skipped_reason"] == "补打"


@pytest.mark.asyncio
async def test_check_in_today_not_retroactive(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/reminders", headers=auth_headers, json={
        "title": "今日打卡",
        "times": ["08:00"],
        "start_date": _today_str(),
    })
    rid = create_resp.json()["id"]
    resp = await client.post(
        f"/api/reminders/{rid}/check-in",
        headers=auth_headers,
        json={"taken": True, "time": "08:00"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["retroactive"] is False
    assert data["skipped_reason"] is None


@pytest.mark.asyncio
async def test_history_returns_slots_field(client: AsyncClient, auth_headers: dict):
    await client.post("/api/reminders", headers=auth_headers, json={
        "title": "历史时段",
        "times": ["08:00", "20:00"],
        "start_date": _past_date(10),
    })
    resp = await client.get("/api/reminders/history?days=7", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "slots" in data
    assert isinstance(data["slots"], list)
    assert len(data["slots"]) > 0
    slot = data["slots"][0]
    assert "reminder_id" in slot
    assert "title" in slot
    assert "date" in slot
    assert "time" in slot
    assert "status" in slot
    assert "can_retroactive" in slot
    assert "retroactive" in slot


@pytest.mark.asyncio
async def test_history_slots_missed_can_retroactive(client: AsyncClient, auth_headers: dict):
    await client.post("/api/reminders", headers=auth_headers, json={
        "title": "漏服可补打",
        "times": ["08:00"],
        "start_date": _past_date(10),
    })
    resp = await client.get("/api/reminders/history?days=3", headers=auth_headers)
    data = resp.json()
    missed_slots = [s for s in data["slots"] if s["status"] == "漏服"]
    assert len(missed_slots) > 0
    for s in missed_slots:
        assert s["can_retroactive"] is True
        assert s["retroactive"] is False


@pytest.mark.asyncio
async def test_history_slots_retroactive_after_checkin(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/reminders", headers=auth_headers, json={
        "title": "补打后验证",
        "times": ["08:00"],
        "start_date": _past_date(10),
    })
    rid = create_resp.json()["id"]
    past = _past_date(1)
    await client.post(
        f"/api/reminders/{rid}/check-in",
        headers=auth_headers,
        json={"taken": True, "date": past, "time": "08:00", "retroactive": True},
    )
    resp = await client.get("/api/reminders/history?days=3", headers=auth_headers)
    data = resp.json()
    retro_slots = [
        s for s in data["slots"]
        if s["reminder_id"] == rid and s["date"] == past and s["time"] == "08:00"
    ]
    assert len(retro_slots) == 1
    assert retro_slots[0]["status"] == "已服"
    assert retro_slots[0]["retroactive"] is True
