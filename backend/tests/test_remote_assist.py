"""Tests for 子女远程协助 (remote family assistance, spec §22)."""

import json
from datetime import datetime, timezone, timedelta

import pytest
from httpx import AsyncClient

CST = timezone(timedelta(hours=8))


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

async def _get_user_id(client: AsyncClient, headers: dict) -> str:
    resp = await client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 200
    return resp.json()["id"]


async def _set_consent(client: AsyncClient, headers: dict) -> dict:
    return await client.put(
        "/api/remote-assist/consent",
        headers=headers,
        json={"share_consent": True},
    )


async def _create_medicine(client: AsyncClient, headers: dict, name: str = "阿司匹林", **kw) -> str:
    payload = {"name": name, "type": "western", "quantity": 10}
    payload.update(kw)
    resp = await client.post("/api/medicines", headers=headers, json=payload)
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_reminder(client: AsyncClient, headers: dict, title: str = "吃降压药") -> str:
    resp = await client.post("/api/reminders", headers=headers, json={
        "title": title,
        "times": ["08:00"],
        "start_date": "2020-01-01",
    })
    assert resp.status_code == 201
    return resp.json()["id"]


async def _check_in(client: AsyncClient, headers: dict, reminder_id: str, taken: bool = True) -> dict:
    return await client.post(
        f"/api/reminders/{reminder_id}/check-in",
        headers=headers,
        json={"taken": taken},
    )


async def _assess_constitution(client: AsyncClient, headers: dict) -> dict:
    answers = {f"q{i}": 3 for i in range(1, 67)}
    return await client.post(
        "/api/constitution/assess", headers=headers, json={"answers": answers}
    )


# ---------------------------------------------------------------------------
# 同意共享 (consent)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_consent_default_false(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/remote-assist/consent", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["share_consent"] is False
    assert data["role"] == "管理员"


@pytest.mark.asyncio
async def test_set_consent_true(client: AsyncClient, auth_headers: dict):
    resp = await _set_consent(client, auth_headers)
    assert resp.status_code == 200
    assert resp.json()["share_consent"] is True

    resp = await client.get("/api/remote-assist/consent", headers=auth_headers)
    assert resp.json()["share_consent"] is True


@pytest.mark.asyncio
async def test_consent_requires_auth(raw_client: AsyncClient):
    resp = await raw_client.get("/api/remote-assist/consent")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 邀请 (invite)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invite_without_consent_returns_403(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    resp = await client.post(
        "/api/remote-assist/invite",
        headers=auth_headers,
        json={"invitee_username": "testuser2", "role": "家属查看"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_invite_nonexistent_user_returns_404(
    client: AsyncClient, auth_headers: dict
):
    await _set_consent(client, auth_headers)
    resp = await client.post(
        "/api/remote-assist/invite",
        headers=auth_headers,
        json={"invitee_username": "nobody", "role": "家属查看"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_invite_self_returns_422(client: AsyncClient, auth_headers: dict):
    await _set_consent(client, auth_headers)
    resp = await client.post(
        "/api/remote-assist/invite",
        headers=auth_headers,
        json={"invitee_username": "testuser", "role": "家属查看"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_invite_creates_share(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    await _set_consent(client, auth_headers)
    resp = await client.post(
        "/api/remote-assist/invite",
        headers=auth_headers,
        json={"invitee_username": "testuser2", "role": "家属查看"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "active"
    assert data["role"] == "家属查看"


@pytest.mark.asyncio
async def test_invite_duplicate_returns_409(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    await _set_consent(client, auth_headers)
    await client.post(
        "/api/remote-assist/invite",
        headers=auth_headers,
        json={"invitee_username": "testuser2", "role": "家属查看"},
    )
    resp = await client.post(
        "/api/remote-assist/invite",
        headers=auth_headers,
        json={"invitee_username": "testuser2", "role": "家属查看"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_invite_invalid_role_returns_422(
    client: AsyncClient, auth_headers: dict
):
    await _set_consent(client, auth_headers)
    resp = await client.post(
        "/api/remote-assist/invite",
        headers=auth_headers,
        json={"invitee_username": "testuser2", "role": "超级管理员"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 撤销共享 (revoke)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_revoke_share_blocks_viewer(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    await _set_consent(client, auth_headers)
    invite = await client.post(
        "/api/remote-assist/invite",
        headers=auth_headers,
        json={"invitee_username": "testuser2", "role": "家属查看"},
    )
    share_id = invite.json()["id"]

    sharer_id = await _get_user_id(client, auth_headers)
    summary_before = await client.get(
        f"/api/remote-assist/{sharer_id}/summary", headers=second_user_headers
    )
    assert summary_before.status_code == 200

    revoke = await client.delete(
        f"/api/remote-assist/invite/{share_id}", headers=auth_headers
    )
    assert revoke.status_code == 200

    summary_after = await client.get(
        f"/api/remote-assist/{sharer_id}/summary", headers=second_user_headers
    )
    assert summary_after.status_code == 403


@pytest.mark.asyncio
async def test_revoke_by_non_sharer_returns_403(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    await _set_consent(client, auth_headers)
    invite = await client.post(
        "/api/remote-assist/invite",
        headers=auth_headers,
        json={"invitee_username": "testuser2", "role": "家属查看"},
    )
    share_id = invite.json()["id"]

    resp = await client.delete(
        f"/api/remote-assist/invite/{share_id}", headers=second_user_headers
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 共享给我的列表 (shared-with-me)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_shared_with_me_lists_sharers(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    await _set_consent(client, auth_headers)
    await client.post(
        "/api/remote-assist/invite",
        headers=auth_headers,
        json={"invitee_username": "testuser2", "role": "家属查看"},
    )

    resp = await client.get(
        "/api/remote-assist/shared-with-me", headers=second_user_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["sharer_name"] == "测试用户"
    assert data["items"][0]["role"] == "家属查看"


@pytest.mark.asyncio
async def test_shared_with_me_empty(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        "/api/remote-assist/shared-with-me", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# 隐私：无共享关系 → 403
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_summary_without_share_returns_403(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    sharer_id = await _get_user_id(client, auth_headers)
    resp = await client.get(
        f"/api/remote-assist/{sharer_id}/summary", headers=second_user_headers
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_weekly_report_without_share_returns_403(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    sharer_id = await _get_user_id(client, auth_headers)
    resp = await client.get(
        f"/api/remote-assist/{sharer_id}/weekly-report", headers=second_user_headers
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_alerts_without_share_returns_403(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    sharer_id = await _get_user_id(client, auth_headers)
    resp = await client.get(
        f"/api/remote-assist/{sharer_id}/alerts", headers=second_user_headers
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_set_alert_without_share_returns_403(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    sharer_id = await _get_user_id(client, auth_headers)
    resp = await client.post(
        f"/api/remote-assist/{sharer_id}/alert",
        headers=second_user_headers,
        json={"missed_reminder_threshold": 3},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 健康概要 (summary)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_summary_returns_adherence_and_alerts(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    await _set_consent(client, auth_headers)
    await client.post(
        "/api/remote-assist/invite",
        headers=auth_headers,
        json={"invitee_username": "testuser2", "role": "家属查看"},
    )

    rid = await _create_reminder(client, auth_headers, "早服降压药")
    await _check_in(client, auth_headers, rid, taken=True)
    rid2 = await _create_reminder(client, auth_headers, "晚服维生素")
    await _check_in(client, auth_headers, rid2, taken=False)
    await _create_medicine(client, auth_headers, "布洛芬", quantity=2)

    sharer_id = await _get_user_id(client, auth_headers)
    resp = await client.get(
        f"/api/remote-assist/{sharer_id}/summary", headers=second_user_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "medication_adherence" in data
    assert data["medication_adherence"]["taken_7d"] == 1
    assert data["medication_adherence"]["missed_7d"] == 1
    assert data["medication_adherence"]["total_7d"] == 2
    rate = data["medication_adherence"]["rate"]
    assert rate == 50.0
    assert isinstance(data["recent_alerts"], list)
    assert isinstance(data["missed_reminders"], int)


@pytest.mark.asyncio
async def test_summary_includes_constitution(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    await _set_consent(client, auth_headers)
    await client.post(
        "/api/remote-assist/invite",
        headers=auth_headers,
        json={"invitee_username": "testuser2", "role": "家属查看"},
    )
    await _assess_constitution(client, auth_headers)

    sharer_id = await _get_user_id(client, auth_headers)
    resp = await client.get(
        f"/api/remote-assist/{sharer_id}/summary", headers=second_user_headers
    )
    assert resp.status_code == 200
    cs = resp.json()["constitution_summary"]
    assert cs is not None
    assert "primary_type" in cs


@pytest.mark.asyncio
async def test_summary_empty_data(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    await _set_consent(client, auth_headers)
    await client.post(
        "/api/remote-assist/invite",
        headers=auth_headers,
        json={"invitee_username": "testuser2", "role": "家属查看"},
    )

    sharer_id = await _get_user_id(client, auth_headers)
    resp = await client.get(
        f"/api/remote-assist/{sharer_id}/summary", headers=second_user_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["medication_adherence"]["rate"] == 0.0
    assert data["medication_adherence"]["total_7d"] == 0
    assert data["constitution_summary"] is None


# ---------------------------------------------------------------------------
# 每周报告 (weekly-report)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_weekly_report_calculates_medication(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    await _set_consent(client, auth_headers)
    await client.post(
        "/api/remote-assist/invite",
        headers=auth_headers,
        json={"invitee_username": "testuser2", "role": "家属查看"},
    )

    rid = await _create_reminder(client, auth_headers, "早晨药")
    await _check_in(client, auth_headers, rid, taken=True)
    rid2 = await _create_reminder(client, auth_headers, "中午药")
    await _check_in(client, auth_headers, rid2, taken=True)
    rid3 = await _create_reminder(client, auth_headers, "晚上药")
    await _check_in(client, auth_headers, rid3, taken=False)

    sharer_id = await _get_user_id(client, auth_headers)
    resp = await client.get(
        f"/api/remote-assist/{sharer_id}/weekly-report", headers=second_user_headers
    )
    assert resp.status_code == 200
    med = resp.json()["medication"]
    assert med["taken"] == 2
    assert med["missed"] == 1
    assert med["adherence_rate"] == round(2 / 3 * 100, 1)


@pytest.mark.asyncio
async def test_weekly_report_includes_refills(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    await _set_consent(client, auth_headers)
    await client.post(
        "/api/remote-assist/invite",
        headers=auth_headers,
        json={"invitee_username": "testuser2", "role": "家属查看"},
    )
    await _create_medicine(client, auth_headers, "感冒灵", quantity=3)

    sharer_id = await _get_user_id(client, auth_headers)
    resp = await client.get(
        f"/api/remote-assist/{sharer_id}/weekly-report", headers=second_user_headers
    )
    assert resp.status_code == 200
    refills = resp.json()["upcoming_refills"]
    assert any(r["name"] == "感冒灵" for r in refills)


@pytest.mark.asyncio
async def test_weekly_report_period_keys(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    await _set_consent(client, auth_headers)
    await client.post(
        "/api/remote-assist/invite",
        headers=auth_headers,
        json={"invitee_username": "testuser2", "role": "家属查看"},
    )
    sharer_id = await _get_user_id(client, auth_headers)
    resp = await client.get(
        f"/api/remote-assist/{sharer_id}/weekly-report", headers=second_user_headers
    )
    data = resp.json()
    assert "from" in data["period"]
    assert "to" in data["period"]


# ---------------------------------------------------------------------------
# 预警阈值 (alert config)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_alert_thresholds(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    await _set_consent(client, auth_headers)
    await client.post(
        "/api/remote-assist/invite",
        headers=auth_headers,
        json={"invitee_username": "testuser2", "role": "家属查看"},
    )
    sharer_id = await _get_user_id(client, auth_headers)

    resp = await client.post(
        f"/api/remote-assist/{sharer_id}/alert",
        headers=second_user_headers,
        json={"missed_reminder_threshold": 3, "expired_medicine_alert": True},
    )
    assert resp.status_code == 200
    config = resp.json()["alert_config"]
    assert config["missed_reminder_threshold"] == 3
    assert config["expired_medicine_alert"] is True


@pytest.mark.asyncio
async def test_alerts_expired_medicine_breach(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    await _set_consent(client, auth_headers)
    await client.post(
        "/api/remote-assist/invite",
        headers=auth_headers,
        json={"invitee_username": "testuser2", "role": "家属查看"},
    )
    await _create_medicine(client, auth_headers, "过期阿司匹林", expiry_date="2020-01-01")
    sharer_id = await _get_user_id(client, auth_headers)

    await client.post(
        f"/api/remote-assist/{sharer_id}/alert",
        headers=second_user_headers,
        json={"expired_medicine_alert": True},
    )

    resp = await client.get(
        f"/api/remote-assist/{sharer_id}/alerts", headers=second_user_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["breach_count"] >= 1
    types = [b["type"] for b in data["breached"]]
    assert "过期药品" in types


@pytest.mark.asyncio
async def test_alerts_low_stock_breach(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    await _set_consent(client, auth_headers)
    await client.post(
        "/api/remote-assist/invite",
        headers=auth_headers,
        json={"invitee_username": "testuser2", "role": "家属查看"},
    )
    await _create_medicine(client, auth_headers, "低库存药", quantity=2)
    sharer_id = await _get_user_id(client, auth_headers)

    await client.post(
        f"/api/remote-assist/{sharer_id}/alert",
        headers=second_user_headers,
        json={"low_stock_threshold": 5},
    )

    resp = await client.get(
        f"/api/remote-assist/{sharer_id}/alerts", headers=second_user_headers
    )
    data = resp.json()
    types = [b["type"] for b in data["breached"]]
    assert "库存不足" in types


@pytest.mark.asyncio
async def test_alerts_no_config_no_breach(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    await _set_consent(client, auth_headers)
    await client.post(
        "/api/remote-assist/invite",
        headers=auth_headers,
        json={"invitee_username": "testuser2", "role": "家属查看"},
    )
    sharer_id = await _get_user_id(client, auth_headers)
    resp = await client.get(
        f"/api/remote-assist/{sharer_id}/alerts", headers=second_user_headers
    )
    assert resp.status_code == 200
    assert resp.json()["breach_count"] == 0


@pytest.mark.asyncio
async def test_alert_threshold_partial_update(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    await _set_consent(client, auth_headers)
    await client.post(
        "/api/remote-assist/invite",
        headers=auth_headers,
        json={"invitee_username": "testuser2", "role": "家属查看"},
    )
    sharer_id = await _get_user_id(client, auth_headers)

    await client.post(
        f"/api/remote-assist/{sharer_id}/alert",
        headers=second_user_headers,
        json={"missed_reminder_threshold": 5},
    )
    resp = await client.post(
        f"/api/remote-assist/{sharer_id}/alert",
        headers=second_user_headers,
        json={"expired_medicine_alert": True},
    )
    config = resp.json()["alert_config"]
    assert config["missed_reminder_threshold"] == 5
    assert config["expired_medicine_alert"] is True


# ---------------------------------------------------------------------------
# 跨用户隔离
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_viewer_cannot_access_unrelated_user(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    await _set_consent(client, auth_headers)
    await client.post(
        "/api/remote-assist/invite",
        headers=auth_headers,
        json={"invitee_username": "testuser2", "role": "家属查看"},
    )
    viewer_id = await _get_user_id(client, second_user_headers)
    resp = await client.get(
        f"/api/remote-assist/{viewer_id}/summary", headers=second_user_headers
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_missed_alerts_without_share_returns_403(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    sharer_id = await _get_user_id(client, auth_headers)
    resp = await client.get(
        f"/api/remote-assist/{sharer_id}/missed-alerts", headers=second_user_headers
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_missed_alerts_returns_structure(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    await _set_consent(client, auth_headers)
    await client.post(
        "/api/remote-assist/invite",
        headers=auth_headers,
        json={"invitee_username": "testuser2", "role": "家属查看"},
    )
    now_minus_5h = (datetime.now(CST) - timedelta(hours=5)).strftime("%H:%M")
    await _create_reminder(client, auth_headers, "漏服药")
    await client.post("/api/reminders", headers=auth_headers, json={
        "title": "漏服检测",
        "times": [now_minus_5h],
        "start_date": "2020-01-01",
    })

    sharer_id = await _get_user_id(client, auth_headers)
    resp = await client.get(
        f"/api/remote-assist/{sharer_id}/missed-alerts", headers=second_user_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "alerts" in data
    assert "total" in data
    assert "severity" in data
    assert "window_hours" in data
    assert data["window_hours"] == 48
    assert data["total"] >= 0
    if data["alerts"]:
        alert = data["alerts"][0]
        assert "reminder_title" in alert
        assert "medicine_name" in alert
        assert "missed_time" in alert
        assert "hours_ago" in alert


@pytest.mark.asyncio
async def test_missed_alerts_excludes_taken(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    await _set_consent(client, auth_headers)
    await client.post(
        "/api/remote-assist/invite",
        headers=auth_headers,
        json={"invitee_username": "testuser2", "role": "家属查看"},
    )
    now_minus_5h = (datetime.now(CST) - timedelta(hours=5)).strftime("%H:%M")
    rid = await _create_reminder(client, auth_headers, "已服药")
    await client.post("/api/reminders", headers=auth_headers, json={
        "title": "已服检测",
        "times": [now_minus_5h],
        "start_date": "2020-01-01",
    })
    today = datetime.now(CST).strftime("%Y-%m-%d")
    await client.post(
        f"/api/reminders/{rid}/check-in",
        headers=auth_headers,
        json={"taken": True, "date": today, "time": now_minus_5h},
    )

    sharer_id = await _get_user_id(client, auth_headers)
    resp = await client.get(
        f"/api/remote-assist/{sharer_id}/missed-alerts", headers=second_user_headers
    )
    data = resp.json()
    titles = [a["reminder_title"] for a in data["alerts"]]
    assert "已服药" not in titles


@pytest.mark.asyncio
async def test_missed_alerts_severity_critical_above_3(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    await _set_consent(client, auth_headers)
    await client.post(
        "/api/remote-assist/invite",
        headers=auth_headers,
        json={"invitee_username": "testuser2", "role": "家属查看"},
    )
    now_minus_5h = (datetime.now(CST) - timedelta(hours=5)).strftime("%H:%M")
    for i in range(4):
        await client.post("/api/reminders", headers=auth_headers, json={
            "title": f"多次漏服{i}",
            "times": [now_minus_5h],
            "start_date": "2020-01-01",
        })

    sharer_id = await _get_user_id(client, auth_headers)
    resp = await client.get(
        f"/api/remote-assist/{sharer_id}/missed-alerts", headers=second_user_headers
    )
    data = resp.json()
    assert data["total"] >= 4
    assert data["severity"] == "critical"
