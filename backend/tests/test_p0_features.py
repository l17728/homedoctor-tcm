"""P0 feature tests: Favorites, Knowledge Cards, Check-in, Medicine Alerts."""

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


# ===========================================================================
# Favorites (12 tests)
# ===========================================================================


@pytest.mark.asyncio
async def test_create_herb_favorite(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/api/favorites", headers=auth_headers, json={
        "entry_type": "herb",
        "title": "黄芪",
        "content": '{"nature": "微温", "flavor": "甘"}',
        "source_type": "herb",
        "source_url": "herb-001",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["entry_type"] == "herb"
    assert data["title"] == "黄芪"
    assert data["source_url"] == "herb-001"
    assert data["is_starred"] is False


@pytest.mark.asyncio
async def test_create_formula_favorite(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/api/favorites", headers=auth_headers, json={
        "entry_type": "formula",
        "title": "四物汤",
        "content": '{"efficacy": "补血调血"}',
        "source_type": "formula",
        "source_url": "formula-002",
    })
    assert resp.status_code == 201
    assert resp.json()["entry_type"] == "formula"


@pytest.mark.asyncio
async def test_create_knowledge_card_favorite(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/api/favorites", headers=auth_headers, json={
        "entry_type": "knowledge_card",
        "title": "黄芪养生笔记",
        "content": "黄芪适合气虚体质，可搭配党参增强补气效果",
        "summary": "黄芪补气搭配",
        "tags": ["补气", "气虚"],
        "source_type": "chat",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["tags"] == ["补气", "气虚"]
    assert data["summary"] == "黄芪补气搭配"


@pytest.mark.asyncio
async def test_list_all_favorites(client: AsyncClient, auth_headers: dict):
    await client.post("/api/favorites", headers=auth_headers, json={
        "entry_type": "herb", "title": "当归", "source_url": "herb-002",
    })
    await client.post("/api/favorites", headers=auth_headers, json={
        "entry_type": "formula", "title": "四君子汤", "source_url": "formula-001",
    })
    resp = await client.get("/api/favorites", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2


@pytest.mark.asyncio
async def test_list_favorites_by_type(client: AsyncClient, auth_headers: dict):
    await client.post("/api/favorites", headers=auth_headers, json={
        "entry_type": "herb", "title": "甘草", "source_url": "herb-003",
    })
    await client.post("/api/favorites", headers=auth_headers, json={
        "entry_type": "formula", "title": "四物汤2", "source_url": "formula-002x",
    })
    resp = await client.get("/api/favorites?entry_type=herb", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert all(f["entry_type"] == "herb" for f in data["items"])


@pytest.mark.asyncio
async def test_star_unstar_favorite(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/favorites", headers=auth_headers, json={
        "entry_type": "herb", "title": "黄芪star", "source_url": "herb-001s",
    })
    fid = create_resp.json()["id"]

    star_resp = await client.put(f"/api/favorites/{fid}", headers=auth_headers, json={
        "is_starred": True,
    })
    assert star_resp.status_code == 200
    assert star_resp.json()["is_starred"] is True

    unstar_resp = await client.put(f"/api/favorites/{fid}", headers=auth_headers, json={
        "is_starred": False,
    })
    assert unstar_resp.json()["is_starred"] is False


@pytest.mark.asyncio
async def test_update_favorite_tags(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/favorites", headers=auth_headers, json={
        "entry_type": "herb", "title": "当归tag", "source_url": "herb-002t",
    })
    fid = create_resp.json()["id"]

    resp = await client.put(f"/api/favorites/{fid}", headers=auth_headers, json={
        "tags": ["补血", "妇科"],
    })
    assert resp.status_code == 200
    assert resp.json()["tags"] == ["补血", "妇科"]


@pytest.mark.asyncio
async def test_delete_favorite(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/favorites", headers=auth_headers, json={
        "entry_type": "herb", "title": "待删除", "source_url": "herb-del",
    })
    fid = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/favorites/{fid}", headers=auth_headers)
    assert del_resp.status_code == 200

    get_resp = await client.get(f"/api/favorites/{fid}", headers=auth_headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_check_existing_favorite(client: AsyncClient, auth_headers: dict):
    await client.post("/api/favorites", headers=auth_headers, json={
        "entry_type": "herb", "title": "甘草check", "source_type": "herb",
        "source_url": "herb-003c",
    })
    resp = await client.post("/api/favorites/check", headers=auth_headers, json={
        "entry_type": "herb",
        "source_id": "herb-003c",
    })
    assert resp.status_code == 200
    assert resp.json()["is_favorited"] is True


@pytest.mark.asyncio
async def test_check_nonexistent_favorite(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/api/favorites/check", headers=auth_headers, json={
        "entry_type": "herb",
        "source_id": "nonexistent-herb",
    })
    assert resp.status_code == 200
    assert resp.json()["is_favorited"] is False


@pytest.mark.asyncio
async def test_favorites_user_isolation(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    await client.post("/api/favorites", headers=auth_headers, json={
        "entry_type": "herb", "title": "用户A的收藏", "source_url": "herb-private",
    })
    resp = await client.get("/api/favorites", headers=second_user_headers)
    assert resp.status_code == 200
    titles = [f["title"] for f in resp.json()["items"]]
    assert "用户A的收藏" not in titles


@pytest.mark.asyncio
async def test_favorites_unauthorized(raw_client: AsyncClient):
    resp = await raw_client.get("/api/favorites")
    assert resp.status_code == 401


# ===========================================================================
# Knowledge Card from Chat (4 tests)
# ===========================================================================


@pytest.mark.asyncio
async def test_save_knowledge_card_from_chat(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/api/chat/save-card", headers=auth_headers, json={
        "title": "关于黄芪的对话",
        "content": "黄芪适合气虚体质，每日9-30g煎服，可与党参配伍增强补气。",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["entry_type"] == "knowledge_card"
    assert data["title"] == "关于黄芪的对话"
    assert data["source_type"] == "chat"


@pytest.mark.asyncio
async def test_save_knowledge_card_with_tags(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/api/chat/save-card", headers=auth_headers, json={
        "title": "当归使用心得",
        "content": "当归补血活血，6-12g常用量。",
        "tags": ["补血", "妇科常用药"],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["tags"] == ["补血", "妇科常用药"]


@pytest.mark.asyncio
async def test_get_saved_knowledge_card(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/chat/save-card", headers=auth_headers, json={
        "title": "甘草知识卡",
        "content": "甘草调和诸药，2-10g常用量。",
    })
    card_id = create_resp.json()["id"]

    get_resp = await client.get(f"/api/favorites/{card_id}", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["title"] == "甘草知识卡"


@pytest.mark.asyncio
async def test_list_knowledge_cards(client: AsyncClient, auth_headers: dict):
    await client.post("/api/chat/save-card", headers=auth_headers, json={
        "title": "卡片1",
        "content": "内容1",
    })
    await client.post("/api/chat/save-card", headers=auth_headers, json={
        "title": "卡片2",
        "content": "内容2",
    })
    resp = await client.get("/api/favorites?entry_type=knowledge_card", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2
    assert all(f["entry_type"] == "knowledge_card" for f in data["items"])


# ===========================================================================
# Reminder Check-in (8 tests)
# ===========================================================================


@pytest.mark.asyncio
async def test_check_in_mark_taken(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/reminders", headers=auth_headers, json={
        "title": "打卡测试",
        "times": ["08:00"],
        "start_date": _today_str(),
    })
    rid = create_resp.json()["id"]

    resp = await client.post(f"/api/reminders/{rid}/check-in", headers=auth_headers, json={
        "time": "08:00",
        "taken": True,
    })
    assert resp.status_code == 201
    assert resp.json()["taken"] is True


@pytest.mark.asyncio
async def test_check_in_mark_skipped(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/reminders", headers=auth_headers, json={
        "title": "跳过测试",
        "times": ["08:00"],
        "start_date": _today_str(),
    })
    rid = create_resp.json()["id"]

    resp = await client.post(f"/api/reminders/{rid}/check-in", headers=auth_headers, json={
        "time": "08:00",
        "taken": False,
        "skipped_reason": "忘了",
    })
    assert resp.status_code == 201
    assert resp.json()["taken"] is False


@pytest.mark.asyncio
async def test_check_in_double_same_day(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/reminders", headers=auth_headers, json={
        "title": "双打卡",
        "times": ["08:00"],
        "start_date": _today_str(),
    })
    rid = create_resp.json()["id"]

    first = await client.post(f"/api/reminders/{rid}/check-in", headers=auth_headers, json={
        "time": "08:00", "taken": True,
    })
    assert first.status_code == 201

    second = await client.post(f"/api/reminders/{rid}/check-in", headers=auth_headers, json={
        "time": "08:00", "taken": True,
    })
    assert second.status_code == 201


@pytest.mark.asyncio
async def test_check_in_then_today_shows_taken(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/reminders", headers=auth_headers, json={
        "title": "今日已服",
        "times": ["08:00"],
        "start_date": _today_str(),
    })
    rid = create_resp.json()["id"]

    await client.post(f"/api/reminders/{rid}/check-in", headers=auth_headers, json={
        "time": "08:00", "taken": True,
    })

    today_resp = await client.get("/api/reminders/today", headers=auth_headers)
    slots = today_resp.json()["items"]
    match = [s for s in slots if s["reminder_id"] == rid]
    assert len(match) == 1
    assert match[0]["status"] == "已服"


@pytest.mark.asyncio
async def test_check_in_different_reminder(client: AsyncClient, auth_headers: dict):
    r1 = await client.post("/api/reminders", headers=auth_headers, json={
        "title": "提醒A", "times": ["08:00"], "start_date": _today_str(),
    })
    r2 = await client.post("/api/reminders", headers=auth_headers, json={
        "title": "提醒B", "times": ["12:00"], "start_date": _today_str(),
    })
    rid1 = r1.json()["id"]
    rid2 = r2.json()["id"]

    await client.post(f"/api/reminders/{rid1}/check-in", headers=auth_headers, json={
        "time": "08:00", "taken": True,
    })

    today_resp = await client.get("/api/reminders/today", headers=auth_headers)
    slots = today_resp.json()["items"]
    by_id = {s["reminder_id"]: s for s in slots}
    assert by_id[rid1]["status"] == "已服"
    assert by_id[rid2]["status"] != "已服"


@pytest.mark.asyncio
async def test_check_in_user_isolation(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    create_resp = await client.post("/api/reminders", headers=auth_headers, json={
        "title": "用户A的打卡", "times": ["08:00"], "start_date": _today_str(),
    })
    rid = create_resp.json()["id"]

    resp = await client.post(f"/api/reminders/{rid}/check-in", headers=second_user_headers, json={
        "time": "08:00", "taken": True,
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_check_in_unauthorized(client: AsyncClient, raw_client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/reminders", headers=auth_headers, json={
        "title": "未授权打卡", "times": ["08:00"], "start_date": _today_str(),
    })
    rid = create_resp.json()["id"]

    resp = await raw_client.post(f"/api/reminders/{rid}/check-in", json={
        "time": "08:00", "taken": True,
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_check_in_nonexistent_reminder(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/api/reminders/nonexistent-id/check-in", headers=auth_headers, json={
        "time": "08:00", "taken": True,
    })
    assert resp.status_code == 404


# ===========================================================================
# Medicine Expiry Alerts (8 tests)
# ===========================================================================


@pytest.mark.asyncio
async def test_alert_expired_medicine(client: AsyncClient, auth_headers: dict):
    await client.post("/api/medicines", headers=auth_headers, json={
        "name": "过期药",
        "type": "western",
        "quantity": 10,
        "expiry_date": _past_date(10),
    })
    resp = await client.get("/api/medicines/alerts/expiring", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    names = [m["name"] for m in data["expired"]]
    assert "过期药" in names


@pytest.mark.asyncio
async def test_alert_expiring_soon(client: AsyncClient, auth_headers: dict):
    await client.post("/api/medicines", headers=auth_headers, json={
        "name": "即将过期",
        "type": "western",
        "quantity": 10,
        "expiry_date": _future_date(15),
    })
    resp = await client.get("/api/medicines/alerts/expiring", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    names = [m["name"] for m in data["expiring_soon"]]
    assert "即将过期" in names


@pytest.mark.asyncio
async def test_alert_safe_medicine_not_in_alerts(client: AsyncClient, auth_headers: dict):
    await client.post("/api/medicines", headers=auth_headers, json={
        "name": "安全药品",
        "type": "western",
        "quantity": 20,
        "expiry_date": _future_date(60),
    })
    resp = await client.get("/api/medicines/alerts/expiring", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    all_names = (
        [m["name"] for m in data["expired"]]
        + [m["name"] for m in data["expiring_soon"]]
        + [m["name"] for m in data["low_stock"]]
    )
    assert "安全药品" not in all_names


@pytest.mark.asyncio
async def test_alert_low_stock(client: AsyncClient, auth_headers: dict):
    await client.post("/api/medicines", headers=auth_headers, json={
        "name": "低库存药",
        "type": "western",
        "quantity": 3,
        "expiry_date": _future_date(90),
    })
    resp = await client.get("/api/medicines/alerts/expiring", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    names = [m["name"] for m in data["low_stock"]]
    assert "低库存药" in names


@pytest.mark.asyncio
async def test_alert_zero_stock(client: AsyncClient, auth_headers: dict):
    await client.post("/api/medicines", headers=auth_headers, json={
        "name": "零库存药",
        "type": "western",
        "quantity": 0,
        "expiry_date": _future_date(90),
    })
    resp = await client.get("/api/medicines/alerts/expiring", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    names = [m["name"] for m in data["low_stock"]]
    assert "零库存药" in names


@pytest.mark.asyncio
async def test_alert_multiple_categories(client: AsyncClient, auth_headers: dict):
    await client.post("/api/medicines", headers=auth_headers, json={
        "name": "过期低库存",
        "type": "western",
        "quantity": 2,
        "expiry_date": _past_date(5),
    })
    resp = await client.get("/api/medicines/alerts/expiring", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    expired_names = [m["name"] for m in data["expired"]]
    low_names = [m["name"] for m in data["low_stock"]]
    assert "过期低库存" in expired_names
    assert "过期低库存" in low_names


@pytest.mark.asyncio
async def test_alert_no_medicines(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/medicines/alerts/expiring", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["expired"] == []
    assert data["expiring_soon"] == []
    assert data["low_stock"] == []


@pytest.mark.asyncio
async def test_alert_user_isolation(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    await client.post("/api/medicines", headers=auth_headers, json={
        "name": "用户A过期药",
        "type": "western",
        "quantity": 1,
        "expiry_date": _past_date(5),
    })
    resp = await client.get("/api/medicines/alerts/expiring", headers=second_user_headers)
    assert resp.status_code == 200
    data = resp.json()
    all_names = (
        [m["name"] for m in data["expired"]]
        + [m["name"] for m in data["expiring_soon"]]
        + [m["name"] for m in data["low_stock"]]
    )
    assert "用户A过期药" not in all_names
