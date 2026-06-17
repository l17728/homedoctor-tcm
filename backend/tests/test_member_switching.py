"""Tests for family member switching (US-8)."""

import pytest
from httpx import AsyncClient


async def _create_member(client: AsyncClient, headers: dict, name: str = "妈妈") -> str:
    resp = await client.post("/api/family-members", headers=headers, json={
        "name": name,
        "relation": "母亲",
        "gender": "女",
    })
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_medicine(client: AsyncClient, headers: dict, name: str = "阿司匹林") -> str:
    resp = await client.post("/api/medicines", headers=headers, json={
        "name": name,
        "type": "western",
    })
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_reminder(client: AsyncClient, headers: dict, title: str = "吃降压药") -> str:
    resp = await client.post("/api/reminders", headers=headers, json={
        "title": title,
        "times": ["08:00"],
        "start_date": "2026-01-01",
    })
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Switch endpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_switch_returns_member_info(client: AsyncClient, auth_headers: dict):
    member_id = await _create_member(client, auth_headers, "爸爸")
    resp = await client.post(
        f"/api/family-members/{member_id}/switch",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["member"]["id"] == member_id
    assert data["member"]["name"] == "爸爸"


@pytest.mark.asyncio
async def test_switch_nonexistent_returns_404(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/family-members/nonexistent-id/switch",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_switch_other_user_member_returns_404(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    member_id = await _create_member(client, auth_headers, "妈妈")
    resp = await client.post(
        f"/api/family-members/{member_id}/switch",
        headers=second_user_headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Current endpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_current_returns_null_without_header(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/family-members/current", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["member"] is None


@pytest.mark.asyncio
async def test_current_returns_member_with_header(client: AsyncClient, auth_headers: dict):
    member_id = await _create_member(client, auth_headers, "奶奶")
    resp = await client.get(
        "/api/family-members/current",
        headers={**auth_headers, "X-Member-Id": member_id},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["member"]["id"] == member_id
    assert data["member"]["name"] == "奶奶"


@pytest.mark.asyncio
async def test_current_invalid_member_id_returns_null(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        "/api/family-members/current",
        headers={**auth_headers, "X-Member-Id": "fake-id-123"},
    )
    assert resp.status_code == 200
    assert resp.json()["member"] is None


# ---------------------------------------------------------------------------
# Clear-switch endpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_clear_switch(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/api/family-members/clear-switch", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["member"] is None


# ---------------------------------------------------------------------------
# Medicines filtering
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_medicines_show_all_without_member(client: AsyncClient, auth_headers: dict):
    member_id = await _create_member(client, auth_headers, "妈妈")
    await _create_medicine(client, auth_headers, "药品A")

    member_headers = {**auth_headers, "X-Member-Id": member_id}
    await _create_medicine(client, member_headers, "药品B")

    resp = await client.get("/api/medicines", headers=auth_headers)
    assert resp.status_code == 200
    names = [m["name"] for m in resp.json()["items"]]
    assert "药品A" in names
    assert "药品B" in names


@pytest.mark.asyncio
async def test_medicines_filtered_by_member(client: AsyncClient, auth_headers: dict):
    member_id = await _create_member(client, auth_headers, "爸爸")

    await _create_medicine(client, auth_headers, "通用药品")

    member_headers = {**auth_headers, "X-Member-Id": member_id}
    scoped_id = await _create_medicine(client, member_headers, "爸爸专用药")

    resp = await client.get("/api/medicines", headers=member_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    names = [m["name"] for m in items]
    assert "爸爸专用药" in names
    assert "通用药品" not in names


@pytest.mark.asyncio
async def test_create_medicine_stores_member_id(client: AsyncClient, auth_headers: dict):
    member_id = await _create_member(client, auth_headers, "爷爷")

    member_headers = {**auth_headers, "X-Member-Id": member_id}
    medicine_id = await _create_medicine(client, member_headers, "爷爷的药")

    resp = await client.get(f"/api/medicines/{medicine_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["family_member_id"] == member_id


@pytest.mark.asyncio
async def test_create_medicine_without_member_has_null_member_id(
    client: AsyncClient, auth_headers: dict
):
    medicine_id = await _create_medicine(client, auth_headers, "无主药")

    resp = await client.get(f"/api/medicines/{medicine_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["family_member_id"] is None


# ---------------------------------------------------------------------------
# Reminders filtering
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reminders_show_all_without_member(client: AsyncClient, auth_headers: dict):
    member_id = await _create_member(client, auth_headers, "妈妈")
    await _create_reminder(client, auth_headers, "通用提醒")

    member_headers = {**auth_headers, "X-Member-Id": member_id}
    await _create_reminder(client, member_headers, "妈妈提醒")

    resp = await client.get("/api/reminders", headers=auth_headers)
    assert resp.status_code == 200
    titles = [r["title"] for r in resp.json()["items"]]
    assert "通用提醒" in titles
    assert "妈妈提醒" in titles


@pytest.mark.asyncio
async def test_reminders_filtered_by_member(client: AsyncClient, auth_headers: dict):
    member_id = await _create_member(client, auth_headers, "爸爸")

    await _create_reminder(client, auth_headers, "通用提醒")

    member_headers = {**auth_headers, "X-Member-Id": member_id}
    await _create_reminder(client, member_headers, "爸爸提醒")

    resp = await client.get("/api/reminders", headers=member_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    titles = [r["title"] for r in items]
    assert "爸爸提醒" in titles
    assert "通用提醒" not in titles


@pytest.mark.asyncio
async def test_create_reminder_stores_member_id(client: AsyncClient, auth_headers: dict):
    member_id = await _create_member(client, auth_headers, "奶奶")

    member_headers = {**auth_headers, "X-Member-Id": member_id}
    reminder_id = await _create_reminder(client, member_headers, "奶奶提醒")

    resp = await client.get(f"/api/reminders/{reminder_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["family_member_id"] == member_id
