"""Tests for 健康分享卡 & 月度家庭健康报告 — spec §13.3 V3.

Covers:
  - 分享卡生成 (summary / seasonal / constitution)
  - 卡片持久化 / 列表 / 详情 / 删除
  - 月度家庭健康报告聚合 (adherence, missed, expired, chat, safety)
  - 家庭级汇总 (total adherence, alerts, recommendations)
  - 成员不存在 → 404
  - 空数据优雅降级
  - 认证拦截 (401)
  - 输入校验 (无效 card_type → 400, 无效 month → 400)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

CST = timezone(timedelta(hours=8))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_user_id(client: AsyncClient, headers: dict) -> str:
    resp = await client.get("/api/auth/me", headers=headers)
    return resp.json()["id"]


async def _get_family_id(client: AsyncClient, headers: dict) -> str:
    resp = await client.get("/api/auth/me", headers=headers)
    return resp.json().get("family_id") or resp.json()["id"]


async def _create_member(
    client: AsyncClient, headers: dict, *, name: str = "王阿姨",
    relation: str = "母亲", gender: str = "女",
    birth_date: str = "1955-03-15",
) -> str:
    resp = await client.post(
        "/api/family-members",
        json={
            "name": name,
            "relation": relation,
            "gender": gender,
            "birth_date": birth_date,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _seed_med_log(
    db, member_id: str, *, medicine_id: str = "med-1",
    taken: bool = True, days_ago: int = 0,
) -> str:
    log_id = str(uuid.uuid4())
    today = datetime.now(CST)
    target = today - timedelta(days=days_ago)
    if target.year != today.year or target.month != today.month:
        first_of_month = today.replace(day=1)
        target = first_of_month
    date_str = target.strftime("%Y-%m-%d")
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO medication_logs (id, family_member_id, date, medicine_id, taken, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (log_id, member_id, date_str, medicine_id, 1 if taken else 0, now),
    )
    return log_id


async def _seed_assessment(
    db, user_id: str, *, primary_type: str = "气虚质",
    secondary: list[str] | None = None, days_ago: int = 0,
    scores: dict | None = None,
) -> str:
    aid = str(uuid.uuid4())
    assessed = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    default_scores = {
        "平和质": 30.0, "气虚质": 70.0, "阳虚质": 20.0, "阴虚质": 15.0,
        "痰湿质": 10.0, "湿热质": 10.0, "血瘀质": 10.0, "气郁质": 10.0, "特禀质": 10.0,
    }
    if scores:
        default_scores.update(scores)
    await db.execute(
        "INSERT INTO constitution_assessments (id, user_id, assessed_at, results, primary_type, secondary_types, raw_answers) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (aid, user_id, assessed, json.dumps(default_scores, ensure_ascii=False),
         primary_type, json.dumps(secondary or [], ensure_ascii=False), "{}"),
    )
    return aid


async def _seed_medicine(
    db, tenant_id: str, *, name: str = "感冒灵", member_id: str | None = None,
    expiry_date: str | None = None, quantity: int = 10,
) -> str:
    mid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO medicines (id, tenant_id, family_member_id, name, type, quantity, expiry_date, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (mid, tenant_id, member_id, name, "西药", quantity, expiry_date, now, now),
    )
    return mid


async def _seed_audit(
    db, tenant_id: str, user_id: str, *, action: str = "safety_check",
    entity_type: str = "safety_check", changes: dict | None = None,
    days_ago: int = 0,
) -> str:
    from app.audit import GENESIS_HASH, compute_hash

    aid = str(uuid.uuid4())
    today = datetime.now(CST)
    target = today - timedelta(days=days_ago)
    if target.year != today.year or target.month != today.month:
        target = today.replace(day=1)
    now = target.isoformat()
    changes_str = json.dumps(changes or {}, ensure_ascii=False)
    h = compute_hash(GENESIS_HASH, action, entity_type, aid, changes_str, now)
    await db.execute(
        "INSERT INTO audit_log (id, tenant_id, user_id, action, entity_type, entity_id, changes, prev_hash, hash, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (aid, tenant_id, user_id, action, entity_type, aid, changes_str, GENESIS_HASH, h, now),
    )
    return aid


async def _seed_conversation(
    db, user_id: str, *, days_ago: int = 0,
) -> str:
    cid = str(uuid.uuid4())
    today = datetime.now(CST)
    target = today - timedelta(days=days_ago)
    if target.year != today.year or target.month != today.month:
        target = today.replace(day=1)
    now = target.isoformat()
    await db.execute(
        "INSERT INTO conversations (id, user_id, title, model_id, messages, reasoning_trace, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (cid, user_id, "咨询", "mock", "[]", "[]", now, now),
    )
    return cid


async def _seed_reminder(
    db, user_id: str, *, member_id: str | None = None,
    title: str = "吃药", times: list | None = None,
    enabled: bool = True,
) -> str:
    rid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    today = datetime.now(CST).strftime("%Y-%m-%d")
    await db.execute(
        "INSERT INTO reminders (id, user_id, family_member_id, title, frequency, times, start_date, enabled, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (rid, user_id, member_id, title, "daily",
         json.dumps(times or ["08:00", "20:00"], ensure_ascii=False),
         today, 1 if enabled else 0, now, now),
    )
    return rid


# ===========================================================================
# Auth & Validation
# ===========================================================================

@pytest.mark.asyncio
async def test_generate_requires_auth(raw_client: AsyncClient):
    resp = await raw_client.post("/api/share-cards/generate", json={"card_type": "summary"})
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_generate_invalid_card_type(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/share-cards/generate",
        json={"card_type": "invalid"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "summary" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_list_requires_auth(raw_client: AsyncClient):
    resp = await raw_client.get("/api/share-cards/list")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_monthly_report_invalid_month(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/share-cards/monthly-report",
        json={"month": "not-a-month"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_monthly_report_invalid_member_ids_type(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/share-cards/monthly-report",
        json={"member_ids": "not-a-list"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


# ===========================================================================
# Summary Card
# ===========================================================================

@pytest.mark.asyncio
async def test_summary_card_empty_data(client: AsyncClient, auth_headers: dict):
    """User with no data still gets valid summary card."""
    resp = await client.post(
        "/api/share-cards/generate",
        json={"card_type": "summary"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    card = data["card_data"]

    assert card["card_type"] == "summary"
    assert card["member_name"]
    assert card["generated_at"]
    assert isinstance(card["sections"], list)
    assert len(card["sections"]) > 0
    assert card["quote"]
    assert card["disclaimer"]

    # Adherence section present even with no data
    adherence = next(s for s in card["sections"] if s["label"] == "用药依从性")
    assert "0" in adherence["value"]

    today_section = next(s for s in card["sections"] if s["label"] == "今日提醒")
    assert "0/0" in today_section["value"]


@pytest.mark.asyncio
async def test_summary_card_with_member(client: AsyncClient, auth_headers: dict, db):
    member_id = await _create_member(client, auth_headers, name="王阿姨", birth_date="1955-03-15")

    resp = await client.post(
        "/api/share-cards/generate",
        json={"member_id": member_id, "card_type": "summary"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    card = resp.json()["card_data"]

    assert card["member_name"] == "王阿姨"
    age_section = next(s for s in card["sections"] if s["label"] == "年龄")
    assert "岁" in age_section["value"]


@pytest.mark.asyncio
async def test_summary_card_with_adherence(client: AsyncClient, auth_headers: dict, db):
    user_id = await _get_user_id(client, auth_headers)
    # 8 taken, 2 missed out of 10
    for i in range(8):
        await _seed_med_log(db, user_id, taken=True, days_ago=i)
    for i in range(2):
        await _seed_med_log(db, user_id, taken=False, days_ago=8 + i)

    resp = await client.post(
        "/api/share-cards/generate",
        json={"card_type": "summary"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    card = resp.json()["card_data"]

    adherence = next(s for s in card["sections"] if s["label"] == "用药依从性")
    assert "80" in adherence["value"]
    assert adherence["color"] == "green"


@pytest.mark.asyncio
async def test_summary_card_member_not_found(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/share-cards/generate",
        json={"member_id": str(uuid.uuid4()), "card_type": "summary"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ===========================================================================
# Seasonal Card
# ===========================================================================

@pytest.mark.asyncio
async def test_seasonal_card_structure(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/share-cards/generate",
        json={"card_type": "seasonal"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    card = resp.json()["card_data"]

    assert card["card_type"] == "seasonal"
    term_section = next(s for s in card["sections"] if s["label"] == "当前节气")
    assert term_section["value"]

    season_section = next(s for s in card["sections"] if s["label"] == "时令")
    assert season_section["value"].startswith(("春", "夏", "秋", "冬"))


@pytest.mark.asyncio
async def test_seasonal_card_with_constitution(
    client: AsyncClient, auth_headers: dict, db
):
    user_id = await _get_user_id(client, auth_headers)
    await _seed_assessment(db, user_id, primary_type="阳虚质")

    resp = await client.post(
        "/api/share-cards/generate",
        json={"card_type": "seasonal"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    card = resp.json()["card_data"]

    const_section = next(s for s in card["sections"] if s["label"] == "体质")
    assert const_section["value"] == "阳虚质"


# ===========================================================================
# Constitution Card
# ===========================================================================

@pytest.mark.asyncio
async def test_constitution_card_no_data(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/share-cards/generate",
        json={"card_type": "constitution"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    card = resp.json()["card_data"]

    assert card["card_type"] == "constitution"
    section = next(s for s in card["sections"] if s["label"] == "体质")
    assert "尚未评估" in section["value"]


@pytest.mark.asyncio
async def test_constitution_card_with_assessment(
    client: AsyncClient, auth_headers: dict, db
):
    user_id = await _get_user_id(client, auth_headers)
    await _seed_assessment(db, user_id, primary_type="气虚质", secondary=["阳虚质"])

    resp = await client.post(
        "/api/share-cards/generate",
        json={"card_type": "constitution"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    card = resp.json()["card_data"]

    primary = next(s for s in card["sections"] if s["label"] == "主体质")
    assert primary["value"] == "气虚质"

    score = next(s for s in card["sections"] if s["label"] == "体质得分")
    assert "分" in score["value"]

    secondary = next(s for s in card["sections"] if s["label"] == "兼夹体质")
    assert "阳虚质" in secondary["value"]

    # Recommendations present
    diet = next((s for s in card["sections"] if s["label"] == "饮食宜"), None)
    assert diet is not None
    assert diet["value"]


# ===========================================================================
# Card CRUD (list / get / delete)
# ===========================================================================

@pytest.mark.asyncio
async def test_card_persist_and_list(client: AsyncClient, auth_headers: dict):
    # Generate 2 cards
    r1 = await client.post(
        "/api/share-cards/generate",
        json={"card_type": "summary"},
        headers=auth_headers,
    )
    r2 = await client.post(
        "/api/share-cards/generate",
        json={"card_type": "seasonal"},
        headers=auth_headers,
    )
    assert r1.status_code == 200
    assert r2.status_code == 200

    # List
    resp = await client.get("/api/share-cards/list", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    # Both have card_data
    for item in data["items"]:
        assert item["card_data"]["card_type"] in ("summary", "seasonal")
        assert item["is_monthly_report"] is False


@pytest.mark.asyncio
async def test_card_get_detail(client: AsyncClient, auth_headers: dict):
    gen = await client.post(
        "/api/share-cards/generate",
        json={"card_type": "constitution"},
        headers=auth_headers,
    )
    card_id = gen.json()["id"]

    resp = await client.get(f"/api/share-cards/{card_id}", headers=auth_headers)
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["id"] == card_id
    assert detail["card_data"]["card_type"] == "constitution"


@pytest.mark.asyncio
async def test_card_delete(client: AsyncClient, auth_headers: dict):
    gen = await client.post(
        "/api/share-cards/generate",
        json={"card_type": "summary"},
        headers=auth_headers,
    )
    card_id = gen.json()["id"]

    resp = await client.delete(f"/api/share-cards/{card_id}", headers=auth_headers)
    assert resp.status_code == 200

    # Verify deleted
    resp = await client.get(f"/api/share-cards/{card_id}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_card_get_not_found(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        f"/api/share-cards/{uuid.uuid4()}",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_card_delete_not_found(client: AsyncClient, auth_headers: dict):
    resp = await client.delete(
        f"/api/share-cards/{uuid.uuid4()}",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_card_isolation_between_users(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    """User A's cards are not visible to User B."""
    gen = await client.post(
        "/api/share-cards/generate",
        json={"card_type": "summary"},
        headers=auth_headers,
    )
    card_id = gen.json()["id"]

    # User B cannot access User A's card
    resp = await client.get(
        f"/api/share-cards/{card_id}",
        headers=second_user_headers,
    )
    assert resp.status_code == 404

    resp = await client.delete(
        f"/api/share-cards/{card_id}",
        headers=second_user_headers,
    )
    assert resp.status_code == 404


# ===========================================================================
# Monthly Family Health Report
# ===========================================================================

@pytest.mark.asyncio
async def test_monthly_report_empty(client: AsyncClient, auth_headers: dict):
    """No members, no data — still gets valid report structure."""
    resp = await client.post(
        "/api/share-cards/monthly-report",
        json={},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    report = data["report_data"]

    assert report["report_type"] == "月度家庭健康报告"
    assert "month" in report
    assert "data_period" in report
    assert "disclaimer" in report

    summary = report["family_summary"]
    assert summary["member_count"] >= 1
    assert summary["total_adherence_rate"] == 0.0

    assert isinstance(report["health_alerts"], list)
    assert isinstance(report["recommendations"], list)
    assert len(report["recommendations"]) > 0


@pytest.mark.asyncio
async def test_monthly_report_with_member_and_data(
    client: AsyncClient, auth_headers: dict, db
):
    user_id = await _get_user_id(client, auth_headers)
    family_id = await _get_family_id(client, auth_headers)
    member_id = await _create_member(client, auth_headers, name="李芳")

    # Seed adherence: 7 taken, 3 missed
    for i in range(7):
        await _seed_med_log(db, member_id, taken=True, days_ago=i)
    for i in range(3):
        await _seed_med_log(db, member_id, taken=False, days_ago=7 + i)

    # Seed expired medicine
    await _seed_medicine(db, family_id, name="过期药", member_id=member_id, expiry_date="2020-01-01")
    # Seed expiring medicine
    soon = (datetime.now(CST) + timedelta(days=10)).strftime("%Y-%m-%d")
    await _seed_medicine(db, family_id, name="即将过期药", member_id=member_id, expiry_date=soon)

    # Seed chat conversation
    await _seed_conversation(db, user_id, days_ago=5)

    # Seed safety check
    await _seed_audit(db, family_id, user_id, action="safety_check", days_ago=3)

    # Seed medicine creation audit
    await _seed_audit(
        db, family_id, user_id,
        action="create", entity_type="medicine", days_ago=10,
    )

    resp = await client.post(
        "/api/share-cards/monthly-report",
        json={"member_ids": [member_id]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    report = resp.json()["report_data"]

    members = report["members"]
    assert len(members) == 1
    m = members[0]
    assert m["member_name"] == "李芳"

    adherence = m["medication_adherence"]
    assert adherence["total"] == 10
    assert adherence["taken"] == 7
    assert adherence["rate"] == 70.0
    assert m["missed_reminders"] == 3

    assert len(m["expired_medicines"]) >= 1
    assert any(e["name"] == "过期药" for e in m["expired_medicines"])
    assert len(m["expiring_medicines"]) >= 1

    assert m["chat_interaction_count"] >= 1
    assert m["safety_check_count"] >= 1

    # Family summary
    summary = report["family_summary"]
    assert summary["member_count"] == 1
    assert summary["total_adherence_rate"] == 70.0
    assert summary["total_logs"] == 10

    # Alerts: expired medicine + missed > 3? missed is 3, not > 3, so only expired
    alerts = report["health_alerts"]
    assert any(a["type"] == "药品过期" for a in alerts)


@pytest.mark.asyncio
async def test_monthly_report_missed_alert_threshold(
    client: AsyncClient, auth_headers: dict, db
):
    """Missed > 3 triggers a warning alert."""
    user_id = await _get_user_id(client, auth_headers)
    member_id = await _create_member(client, auth_headers, name="张三")

    for i in range(5):
        await _seed_med_log(db, member_id, taken=False, days_ago=i)

    resp = await client.post(
        "/api/share-cards/monthly-report",
        json={"member_ids": [member_id]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    report = resp.json()["report_data"]

    alerts = report["health_alerts"]
    missed_alerts = [a for a in alerts if a["type"] == "漏服较多"]
    assert len(missed_alerts) == 1
    assert missed_alerts[0]["severity"] == "warning"


@pytest.mark.asyncio
async def test_monthly_report_specific_month(
    client: AsyncClient, auth_headers: dict, db
):
    """Report for a specific past month uses that month's range."""
    resp = await client.post(
        "/api/share-cards/monthly-report",
        json={"month": "2025-01"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    report = resp.json()["report_data"]
    assert report["month"] == "2025-01"
    assert "2025-01-01" in report["data_period"]


@pytest.mark.asyncio
async def test_monthly_report_all_members(
    client: AsyncClient, auth_headers: dict, db
):
    """No member_ids → all family members."""
    await _create_member(client, auth_headers, name="成员A")
    await _create_member(client, auth_headers, name="成员B", relation="儿子")

    resp = await client.post(
        "/api/share-cards/monthly-report",
        json={},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    report = resp.json()["report_data"]
    members = report["members"]
    names = [m["member_name"] for m in members]
    assert "成员A" in names
    assert "成员B" in names


@pytest.mark.asyncio
async def test_monthly_report_member_not_found(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.post(
        "/api/share-cards/monthly-report",
        json={"member_ids": [str(uuid.uuid4())]},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_monthly_report_latest(client: AsyncClient, auth_headers: dict):
    # No report yet → 404
    resp = await client.get(
        "/api/share-cards/monthly-report/latest",
        headers=auth_headers,
    )
    assert resp.status_code == 404

    # Generate one
    await client.post(
        "/api/share-cards/monthly-report",
        json={},
        headers=auth_headers,
    )

    resp = await client.get(
        "/api/share-cards/monthly-report/latest",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_monthly_report"] is True
    assert data["card_type"] == "monthly_report"
    assert data["card_data"]["report_type"] == "月度家庭健康报告"


@pytest.mark.asyncio
async def test_monthly_report_excluded_from_card_list(
    client: AsyncClient, auth_headers: dict
):
    """Monthly reports should NOT appear in /list (cards only)."""
    await client.post(
        "/api/share-cards/generate",
        json={"card_type": "summary"},
        headers=auth_headers,
    )
    await client.post(
        "/api/share-cards/monthly-report",
        json={},
        headers=auth_headers,
    )

    resp = await client.get("/api/share-cards/list", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    # Only the summary card, not the monthly report
    assert len(items) == 1
    assert items[0]["card_type"] == "summary"
