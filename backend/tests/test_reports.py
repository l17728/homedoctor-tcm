"""Tests for 报告中心 (Report Center) — spec §7 / §13.3 V3 P0.

Covers:
  - 体质报告 (constitution report): assessment + trends + recommendations + seasonal
  - 健康趋势报告 (health trend report): adherence + reminders + cabinet + chat + safety
  - 就诊准备报告 (pre-visit report): medications + allergies + constitution + questions
  - PDF generation for all report types
  - Auth enforcement (401 without token)
  - Input validation (invalid period / report type → 400)
  - Tenant isolation (cross-user data not leaked)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.audit import GENESIS_HASH, compute_hash


CST = timezone(timedelta(hours=8))


# ---------------------------------------------------------------------------
# Helpers — seed data via direct DB access
# ---------------------------------------------------------------------------

async def _seed_medication_log(
    db, user_id: str, *, medicine_id: str = "med-test",
    taken: bool = True, days_ago: int = 0,
) -> str:
    """Insert a medication_logs row directly."""
    log_id = str(uuid.uuid4())
    date_str = (datetime.now(CST) - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO medication_logs (id, family_member_id, date, medicine_id, taken, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (log_id, user_id, date_str, medicine_id, 1 if taken else 0, now),
    )
    return log_id


async def _seed_safety_audit(
    db, tenant_id: str, user_id: str, *,
    action: str = "safety_check",
    entity_type: str = "safety_check",
    changes: dict | None = None,
    days_ago: int = 0,
) -> str:
    """Insert an audit_log row (for safety_check / medicine create / delete)."""
    audit_id = str(uuid.uuid4())
    now = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    changes_str = json.dumps(changes or {}, ensure_ascii=False)
    h = compute_hash(GENESIS_HASH, action, entity_type, audit_id, changes_str, now)
    await db.execute(
        """INSERT INTO audit_log (id, tenant_id, user_id, action, entity_type, entity_id, changes, prev_hash, hash, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (audit_id, tenant_id, user_id, action, entity_type, audit_id, changes_str, GENESIS_HASH, h, now),
    )
    return audit_id


async def _seed_assessment(
    db, user_id: str, *, primary_type: str = "气虚质",
    secondary: list[str] | None = None, days_ago: int = 0,
    scores: dict | None = None,
) -> str:
    """Insert a constitution_assessments row directly."""
    aid = str(uuid.uuid4())
    assessed = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    default_scores = {
        "平和质": 30.0, "气虚质": 70.0, "阳虚质": 20.0, "阴虚质": 15.0,
        "痰湿质": 10.0, "湿热质": 10.0, "血瘀质": 10.0, "气郁质": 10.0, "特禀质": 10.0,
    }
    if scores:
        default_scores.update(scores)
    await db.execute(
        """INSERT INTO constitution_assessments (id, user_id, assessed_at, results, primary_type, secondary_types, raw_answers)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (aid, user_id, assessed,
         json.dumps(default_scores, ensure_ascii=False),
         primary_type,
         json.dumps(secondary or [], ensure_ascii=False),
         json.dumps({}, ensure_ascii=False)),
    )
    return aid


async def _seed_conversation(
    db, user_id: str, *, title: str = "咨询",
    messages: list[dict] | None = None, days_ago: int = 0,
) -> str:
    """Insert a conversations row directly."""
    cid = str(uuid.uuid4())
    now = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    msgs = messages or [{"role": "user", "content": "我最近总是咳嗽怎么办？"}]
    await db.execute(
        """INSERT INTO conversations (id, user_id, title, model_id, messages, reasoning_trace, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (cid, user_id, title, "mock-v1",
         json.dumps(msgs, ensure_ascii=False), "[]", now, now),
    )
    return cid


async def _get_user_id(client: AsyncClient, headers: dict) -> str:
    """Get current user id from /api/auth/me."""
    resp = await client.get("/api/auth/me", headers=headers)
    return resp.json()["id"]


# ===========================================================================
# Constitution Report (体质报告)
# ===========================================================================

@pytest.mark.asyncio
async def test_constitution_report_requires_auth(client: AsyncClient):
    """Without auth token → 401."""
    resp = await client.get("/api/reports/constitution")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_constitution_report_empty(client: AsyncClient, auth_headers: dict):
    """User with no assessment still gets a valid report structure."""
    resp = await client.get("/api/reports/constitution", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    # Common envelope
    assert data["report_type"] == "体质报告"
    assert "generated_at" in data
    assert "data_period" in data
    assert "disclaimer" in data
    assert "⚠" in data["disclaimer"]

    # Assessment section — no data
    assessment = data["assessment"]
    assert assessment["has_data"] is False
    assert assessment["primary_type"] is None
    assert assessment["latest_scores"] == {}

    # Trend — empty
    assert data["trend"]["total_assessments"] == 0
    assert data["trend"]["points"] == []

    # Recommendations — empty diet/exercise because no type
    recs = data["recommendations"]
    assert recs["diet"] == {"宜食": [], "忌食": []}
    assert recs["exercise"] == []


@pytest.mark.asyncio
async def test_constitution_report_with_assessment(
    client: AsyncClient, auth_headers: dict, db
):
    """Report reflects latest assessment + recommendations."""
    user_id = await _get_user_id(client, auth_headers)
    await _seed_assessment(db, user_id, primary_type="气虚质", secondary=["阳虚质"])

    resp = await client.get("/api/reports/constitution", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    assessment = data["assessment"]
    assert assessment["has_data"] is True
    assert assessment["primary_type"] == "气虚质"
    assert "阳虚质" in assessment["secondary_types"]
    assert assessment["description"]  # non-empty description
    assert "益气" in assessment["description"]  # 气虚质 → 需要益气健脾
    assert assessment["latest_scores"]["气虚质"] == 70.0

    # Recommendations specific to 气虚质
    recs = data["recommendations"]
    assert "黄芪" in "、".join(recs["diet"]["宜食"]) or "党参" in "、".join(recs["diet"]["宜食"])
    assert len(recs["exercise"]) > 0
    assert len(recs["lifestyle"]) > 0


@pytest.mark.asyncio
async def test_constitution_report_trend_multiple_assessments(
    client: AsyncClient, auth_headers: dict, db
):
    """Trend should list all assessments in chronological order."""
    user_id = await _get_user_id(client, auth_headers)
    await _seed_assessment(db, user_id, primary_type="气虚质", days_ago=60, scores={"气虚质": 50.0})
    await _seed_assessment(db, user_id, primary_type="气虚质", days_ago=30, scores={"气虚质": 65.0})
    await _seed_assessment(db, user_id, primary_type="气虚质", days_ago=0, scores={"气虚质": 70.0})

    resp = await client.get("/api/reports/constitution", headers=auth_headers)
    data = resp.json()
    trend = data["trend"]
    assert trend["total_assessments"] == 3
    points = trend["points"]
    assert len(points) == 3
    # Chronological order (oldest first)
    assert points[0]["primary_score"] == 50.0
    assert points[-1]["primary_score"] == 70.0
    # Each point has all 9 type scores
    assert len(points[0]["all_scores"]) == 9


@pytest.mark.asyncio
async def test_constitution_report_seasonal_advice(client: AsyncClient, auth_headers: dict):
    """Seasonal advice section always present with current solar term."""
    resp = await client.get("/api/reports/constitution", headers=auth_headers)
    data = resp.json()
    seasonal = data["seasonal_advice"]
    assert seasonal["current_term"]  # non-empty term name
    assert seasonal["season"] in ("春", "夏", "秋", "冬")


@pytest.mark.asyncio
async def test_constitution_report_all_nine_types_have_recommendations(
    client: AsyncClient, auth_headers: dict, db
):
    """Every constitution type should have diet + exercise recommendations."""
    from app.constitution_data import NINE_CONSTITUTION_TYPES
    from app.report_engine import CONSTITUTION_DIET, CONSTITUTION_EXERCISE

    for ctype in NINE_CONSTITUTION_TYPES:
        assert ctype in CONSTITUTION_DIET, f"Missing diet for {ctype}"
        assert "宜食" in CONSTITUTION_DIET[ctype]
        assert "忌食" in CONSTITUTION_DIET[ctype]
        assert ctype in CONSTITUTION_EXERCISE, f"Missing exercise for {ctype}"
        assert len(CONSTITUTION_EXERCISE[ctype]) > 0


# ===========================================================================
# Health Trend Report (健康趋势报告)
# ===========================================================================

@pytest.mark.asyncio
async def test_health_trend_requires_auth(client: AsyncClient):
    resp = await client.get("/api/reports/health-trend")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_health_trend_default_period(client: AsyncClient, auth_headers: dict):
    """Default period is 30d."""
    resp = await client.get("/api/reports/health-trend", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["report_type"] == "健康趋势报告"
    assert data["period"] == "30d"
    assert data["period_days"] == 30
    assert "近30天" in data["data_period"]


@pytest.mark.asyncio
async def test_health_trend_all_periods(client: AsyncClient, auth_headers: dict):
    for period in ("7d", "30d", "90d"):
        resp = await client.get(
            f"/api/reports/health-trend?period={period}", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["period"] == period


@pytest.mark.asyncio
async def test_health_trend_invalid_period(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        "/api/reports/health-trend?period=999d", headers=auth_headers
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_health_trend_adherence_calculation(
    client: AsyncClient, auth_headers: dict, db
):
    """Adherence rate = taken / total."""
    user_id = await _get_user_id(client, auth_headers)
    # 4 taken, 1 skipped → 80%
    await _seed_medication_log(db, user_id, taken=True, days_ago=1)
    await _seed_medication_log(db, user_id, taken=True, days_ago=2)
    await _seed_medication_log(db, user_id, taken=True, days_ago=3)
    await _seed_medication_log(db, user_id, taken=True, days_ago=4)
    await _seed_medication_log(db, user_id, taken=False, days_ago=5)

    resp = await client.get(
        "/api/reports/health-trend?period=7d", headers=auth_headers
    )
    data = resp.json()
    adherence = data["medication_adherence"]
    assert adherence["total_logs"] == 5
    assert adherence["taken_count"] == 4
    assert adherence["skipped_count"] == 1
    assert adherence["adherence_rate"] == 80.0


@pytest.mark.asyncio
async def test_health_trend_zero_adherence(client: AsyncClient, auth_headers: dict):
    """No logs → 0% adherence, no division error."""
    resp = await client.get(
        "/api/reports/health-trend?period=7d", headers=auth_headers
    )
    data = resp.json()
    assert data["medication_adherence"]["adherence_rate"] == 0.0
    assert data["medication_adherence"]["total_logs"] == 0


@pytest.mark.asyncio
async def test_health_trend_reminder_trends(
    client: AsyncClient, auth_headers: dict, db
):
    """Reminder trends reflect enabled/disabled counts."""
    user_id = await _get_user_id(client, auth_headers)
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    # Create 2 enabled + 1 disabled reminders
    for i in range(2):
        await db.execute(
            """INSERT INTO reminders (id, user_id, title, frequency, times, start_date, enabled, created_at, updated_at)
               VALUES (?, ?, ?, 'daily', '["08:00"]', ?, 1, ?, ?)""",
            (str(uuid.uuid4()), user_id, f"提醒{i}", now, now, now),
        )
    await db.execute(
        """INSERT INTO reminders (id, user_id, title, frequency, times, start_date, enabled, created_at, updated_at)
           VALUES (?, ?, ?, 'daily', '["20:00"]', ?, 0, ?, ?)""",
        (str(uuid.uuid4()), user_id, "停用提醒", now, now, now),
    )

    resp = await client.get(
        "/api/reports/health-trend?period=30d", headers=auth_headers
    )
    data = resp.json()
    trends = data["reminder_trends"]
    assert trends["total_reminders"] == 3
    assert trends["enabled_reminders"] == 2
    assert trends["disabled_reminders"] == 1


@pytest.mark.asyncio
async def test_health_trend_medicine_cabinet_changes(
    client: AsyncClient, auth_headers: dict, db
):
    """Cabinet changes reflect audit_log create/delete + expirations."""
    user_id = await _get_user_id(client, auth_headers)
    tenant_id = (await client.get("/api/auth/me", headers=auth_headers)).json().get("family_id", "default")

    # Seed audit entries for medicine create/delete
    await _seed_safety_audit(
        db, tenant_id, user_id,
        action="create", entity_type="medicine",
        changes={"name": "感冒灵"}, days_ago=5,
    )
    await _seed_safety_audit(
        db, tenant_id, user_id,
        action="delete", entity_type="medicine",
        changes={"name": "过期药"}, days_ago=3,
    )

    # Seed an expired medicine
    await db.execute(
        """INSERT INTO medicines (id, tenant_id, name, type, quantity, expiry_date)
           VALUES (?, ?, '板蓝根', '中成药', 2, ?)""",
        (str(uuid.uuid4()), tenant_id,
         (datetime.now(CST) - timedelta(days=10)).strftime("%Y-%m-%d")),
    )

    resp = await client.get(
        "/api/reports/health-trend?period=30d", headers=auth_headers
    )
    data = resp.json()
    cabinet = data["medicine_cabinet_changes"]
    assert cabinet["additions_count"] == 1
    assert cabinet["deletions_count"] == 1
    assert cabinet["expired_count"] >= 1


@pytest.mark.asyncio
async def test_health_trend_chat_frequency(
    client: AsyncClient, auth_headers: dict, db
):
    """Chat interaction reflects conversation count."""
    user_id = await _get_user_id(client, auth_headers)
    await _seed_conversation(db, user_id, title="咨询1", days_ago=1)
    await _seed_conversation(db, user_id, title="咨询2", days_ago=2)

    resp = await client.get(
        "/api/reports/health-trend?period=7d", headers=auth_headers
    )
    data = resp.json()
    chat = data["chat_interaction"]
    assert chat["total_conversations"] == 2
    assert chat["active_days"] >= 1


@pytest.mark.asyncio
async def test_health_trend_safety_history(
    client: AsyncClient, auth_headers: dict, db
):
    """Safety check history reflects audit_log entries."""
    user_id = await _get_user_id(client, auth_headers)
    tenant_id = (await client.get("/api/auth/me", headers=auth_headers)).json().get("family_id", "default")

    await _seed_safety_audit(
        db, tenant_id, user_id,
        changes={"safe": False, "warnings": [
            {"severity": "critical", "message": "十八反禁忌"},
            {"severity": "warning", "message": "剂量偏大"},
        ]},
        days_ago=1,
    )
    await _seed_safety_audit(
        db, tenant_id, user_id,
        changes={"safe": True, "warnings": []},
        days_ago=2,
    )

    resp = await client.get(
        "/api/reports/health-trend?period=30d", headers=auth_headers
    )
    data = resp.json()
    safety = data["safety_check_history"]
    assert safety["total_checks"] == 2
    assert safety["critical_count"] == 1
    assert safety["warning_count"] == 1


# ===========================================================================
# Pre-Visit Report (就诊准备报告)
# ===========================================================================

@pytest.mark.asyncio
async def test_pre_visit_requires_auth(client: AsyncClient):
    resp = await client.get("/api/reports/pre-visit")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_pre_visit_empty(client: AsyncClient, auth_headers: dict):
    """New user with no data still gets a valid report."""
    resp = await client.get("/api/reports/pre-visit", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["report_type"] == "就诊准备报告"
    assert data["medications"] == []
    assert data["medication_count"] == 0
    assert data["allergies"] == []
    assert data["health_conditions"] == []
    # Should always have baseline doctor questions
    assert len(data["questions_for_doctor"]) >= 2


@pytest.mark.asyncio
async def test_pre_visit_with_medicines_and_allergies(
    client: AsyncClient, auth_headers: dict
):
    """Report lists medications and allergies."""
    # Add medicines
    await client.post(
        "/api/medicines",
        json={"name": "感冒灵颗粒", "type": "中成药", "quantity": 10, "dosage_instructions": "一次1袋，一日3次"},
        headers=auth_headers,
    )
    await client.post(
        "/api/medicines",
        json={"name": "阿司匹林", "type": "西药", "quantity": 30, "dosage_instructions": "一次100mg，一日1次"},
        headers=auth_headers,
    )
    # Update profile with allergies
    await client.put(
        "/api/profile",
        json={"allergies": ["青霉素", "海鲜"], "health_conditions": ["高血压"]},
        headers=auth_headers,
    )

    resp = await client.get("/api/reports/pre-visit", headers=auth_headers)
    data = resp.json()
    assert data["medication_count"] == 2
    med_names = [m["name"] for m in data["medications"]]
    assert "感冒灵颗粒" in med_names
    assert "阿司匹林" in med_names
    assert "青霉素" in data["allergies"]
    assert "海鲜" in data["allergies"]
    assert "高血压" in data["health_conditions"]


@pytest.mark.asyncio
async def test_pre_visit_constitution_summary(
    client: AsyncClient, auth_headers: dict, db
):
    """Constitution summary reflects latest assessment."""
    user_id = await _get_user_id(client, auth_headers)
    await _seed_assessment(db, user_id, primary_type="阴虚质", secondary=["血瘀质"])

    resp = await client.get("/api/reports/pre-visit", headers=auth_headers)
    data = resp.json()
    const = data["constitution"]
    assert const["primary_type"] == "阴虚质"
    assert "血瘀质" in const["secondary_types"]
    assert const["description"]  # non-empty


@pytest.mark.asyncio
async def test_pre_visit_doctor_questions_from_chat(
    client: AsyncClient, auth_headers: dict, db
):
    """Auto-generated questions reflect recent chat symptom keywords."""
    user_id = await _get_user_id(client, auth_headers)
    await _seed_conversation(
        db, user_id,
        title="咳嗽咨询",
        messages=[
            {"role": "user", "content": "我最近一直咳嗽，有痰，头痛，怎么办？"},
            {"role": "assistant", "content": "咳嗽可能是风寒或风热..."},
        ],
        days_ago=1,
    )

    resp = await client.get("/api/reports/pre-visit", headers=auth_headers)
    data = resp.json()
    questions = data["questions_for_doctor"]
    questions_text = " ".join(questions)
    # Should mention detected symptoms
    assert "咳嗽" in questions_text
    assert "头痛" in questions_text


@pytest.mark.asyncio
async def test_pre_visit_recent_chat_topics(
    client: AsyncClient, auth_headers: dict, db
):
    """Recent chat topics extracted from conversations."""
    user_id = await _get_user_id(client, auth_headers)
    await _seed_conversation(
        db, user_id,
        messages=[{"role": "user", "content": "高血压吃什么中药好？"}],
        days_ago=1,
    )

    resp = await client.get("/api/reports/pre-visit", headers=auth_headers)
    data = resp.json()
    topics = data["recent_chat_topics"]
    assert len(topics) >= 1
    assert any("高血压" in t for t in topics)


@pytest.mark.asyncio
async def test_pre_visit_safety_check_results(
    client: AsyncClient, auth_headers: dict, db
):
    """Safety check results pulled from audit_log."""
    user_id = await _get_user_id(client, auth_headers)
    tenant_id = (await client.get("/api/auth/me", headers=auth_headers)).json().get("family_id", "default")

    await _seed_safety_audit(
        db, tenant_id, user_id,
        changes={"safe": False, "warnings": [
            {"severity": "critical", "message": "附子与半夏禁忌"},
        ]},
        days_ago=2,
    )

    resp = await client.get("/api/reports/pre-visit", headers=auth_headers)
    data = resp.json()
    results = data["safety_check_results"]
    assert len(results) >= 1
    assert any(not r["safe"] for r in results)


# ===========================================================================
# PDF Generation
# ===========================================================================

@pytest.mark.asyncio
async def test_generate_pdf_constitution(client: AsyncClient, auth_headers: dict):
    """PDF generation for constitution report returns valid PDF bytes."""
    resp = await client.post(
        "/api/reports/generate-pdf",
        json={"report_type": "constitution"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.headers["content-disposition"].startswith("attachment")
    # PDF magic bytes
    assert resp.content[:4] == b"%PDF"


@pytest.mark.asyncio
async def test_generate_pdf_health_trend(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/reports/generate-pdf",
        json={"report_type": "health-trend", "period": "7d"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"


@pytest.mark.asyncio
async def test_generate_pdf_pre_visit(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/reports/generate-pdf",
        json={"report_type": "pre-visit"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"


@pytest.mark.asyncio
async def test_generate_pdf_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/reports/generate-pdf",
        json={"report_type": "constitution"},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_generate_pdf_invalid_type(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/reports/generate-pdf",
        json={"report_type": "unknown"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_generate_pdf_invalid_period(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/reports/generate-pdf",
        json={"report_type": "health-trend", "period": "365d"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


# ===========================================================================
# Tenant isolation
# ===========================================================================

@pytest.mark.asyncio
async def test_tenant_isolation_medicines(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    """User A's medicines should NOT appear in User B's pre-visit report."""
    await client.post(
        "/api/medicines",
        json={"name": "用户A专用药", "type": "西药", "quantity": 1},
        headers=auth_headers,
    )

    # User B's report
    resp = await client.get("/api/reports/pre-visit", headers=second_user_headers)
    data = resp.json()
    med_names = [m["name"] for m in data["medications"]]
    assert "用户A专用药" not in med_names


@pytest.mark.asyncio
async def test_tenant_isolation_constitution(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict, db
):
    """User A's constitution assessment should NOT appear in User B's report."""
    user_a = await _get_user_id(client, auth_headers)
    await _seed_assessment(db, user_a, primary_type="痰湿质")

    resp = await client.get(
        "/api/reports/constitution", headers=second_user_headers
    )
    data = resp.json()
    assert data["assessment"]["primary_type"] != "痰湿质"
    assert data["assessment"]["has_data"] is False


# ===========================================================================
# Report engine unit tests (direct function calls)
# ===========================================================================

@pytest.mark.asyncio
async def test_engine_generate_report_dispatch(db, auth_headers, client):
    """generate_report() dispatches to correct generator."""
    from app.report_engine import generate_report

    user_id = await _get_user_id(client, auth_headers)
    tenant_id = user_id  # for test isolation, family_id may differ

    r1 = await generate_report(db, user_id, tenant_id, "constitution")
    assert r1["report_type"] == "体质报告"

    r2 = await generate_report(db, user_id, tenant_id, "health-trend", "7d")
    assert r2["report_type"] == "健康趋势报告"
    assert r2["period"] == "7d"

    r3 = await generate_report(db, user_id, tenant_id, "pre-visit")
    assert r3["report_type"] == "就诊准备报告"


@pytest.mark.asyncio
async def test_engine_generate_report_invalid_type(db, client, auth_headers):
    from app.report_engine import generate_report

    user_id = await _get_user_id(client, auth_headers)
    with pytest.raises(ValueError, match="未知的报告类型"):
        await generate_report(db, user_id, "default", "invalid-type")


@pytest.mark.asyncio
async def test_constitution_report_chinese_domain_language(
    client: AsyncClient, auth_headers: dict, db
):
    """Report uses Chinese domain language (spec §1.7)."""
    user_id = await _get_user_id(client, auth_headers)
    await _seed_assessment(db, user_id, primary_type="阳虚质")

    resp = await client.get("/api/reports/constitution", headers=auth_headers)
    data = resp.json()
    # Diet keys are Chinese
    assert "宜食" in data["recommendations"]["diet"]
    assert "忌食" in data["recommendations"]["diet"]
    # Report type is Chinese
    assert data["report_type"] == "体质报告"
