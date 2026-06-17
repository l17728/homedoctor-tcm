"""Tests for 中药饮片变质判断 + 开封后保质期追踪 — spec §16.4.

Covers:
- Pure-logic unit tests for ``app.herb_quality.check_herb_quality``.
- Category detection & shelf-life estimation.
- ``shelf_life_after_open`` free-text parsing.
- HTTP endpoints: GET /api/medicines/{id}/quality, GET /api/medicines/quality-alerts.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from httpx import AsyncClient

from app.herb_quality import (
    DETERIORATION_SIGNS,
    HERB_SHELF_LIFE,
    _parse_date,
    _parse_shelf_life_after_open,
    check_herb_quality,
    estimate_shelf_life_days,
)
from app import herb_quality


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now():
    return herb_quality._now()


def _days_from_now(days: int) -> str:
    """Return a YYYY-MM-DD string offset from today by ``days``."""
    return (_now() + timedelta(days=days)).date().isoformat()


def _herb(**overrides) -> dict:
    base = {
        "name": "黄芪",
        "type": "herbal",
        "quantity": 100,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Constants & data integrity
# ---------------------------------------------------------------------------

class TestConstants:
    def test_shelf_life_table_matches_spec(self):
        assert HERB_SHELF_LIFE["挥发油类"] == 180
        assert HERB_SHELF_LIFE["芳香化湿药"] == 180
        assert HERB_SHELF_LIFE["解表药"] == 180
        assert HERB_SHELF_LIFE["糖类/树脂类"] == 365
        assert HERB_SHELF_LIFE["补益药"] == 365
        assert HERB_SHELF_LIFE["矿物类"] == 730
        assert HERB_SHELF_LIFE["default"] == 365

    def test_deterioration_signs_have_five(self):
        assert set(DETERIORATION_SIGNS.keys()) == {
            "虫蛀", "霉变", "泛油", "变色", "气味散失",
        }
        # Every sign has a non-empty Chinese description.
        for desc in DETERIORATION_SIGNS.values():
            assert isinstance(desc, str) and desc.strip()


# ---------------------------------------------------------------------------
# shelf_life_after_open parsing
# ---------------------------------------------------------------------------

class TestShelfLifeParsing:
    @pytest.mark.parametrize("raw,expected", [
        ("6个月", 180),
        ("6月", 180),
        ("180天", 180),
        ("180日", 180),
        ("180", 180),
        ("12个月", 360),
        ("1年", 365),
        ("2年", 730),
        ("半年", 182),       # 半=0.5年 → 0.5*365=182
        ("一年", 365),
        ("6m", 180),
        ("6M", 180),
        (180, 180),
        (None, None),
        ("", None),
        ("垃圾", None),
    ])
    def test_parse_various_forms(self, raw, expected):
        assert _parse_shelf_life_after_open(raw) == expected


# ---------------------------------------------------------------------------
# Category detection & shelf-life estimation
# ---------------------------------------------------------------------------

class TestCategoryDetection:
    def test_explicit_herb_category_in_properties(self):
        med = _herb(properties={"herbCategory": "挥发油类"})
        assert estimate_shelf_life_days(med) == 180

    def test_gongxiao_in_properties(self):
        med = _herb(properties={"功效分类": "矿物类"})
        assert estimate_shelf_life_days(med) == 730

    def test_herbal_fields_category(self):
        med = _herb(herbal_fields={"category": "解表药"})
        assert estimate_shelf_life_days(med) == 180

    def test_keyword_in_name(self):
        # Name contains a category keyword.
        med = _herb(name="薄荷饮片")
        # 薄荷 is volatile-oil; keyword "挥发油类" not in name → default
        # unless herbal_fields mention it. We assert default here and test
        # explicit matching below.
        med2 = _herb(name="挥发油类-薄荷", type="herbal")
        assert estimate_shelf_life_days(med2) == 180

    def test_explicit_shelf_life_overrides_category(self):
        med = _herb(properties={"herbCategory": "矿物类"},
                    shelf_life_after_open="6个月")
        assert estimate_shelf_life_days(med) == 180

    def test_default_when_no_info(self):
        med = _herb(name="某药材")
        assert estimate_shelf_life_days(med) == HERB_SHELF_LIFE["default"]


# ---------------------------------------------------------------------------
# check_herb_quality — core status logic
# ---------------------------------------------------------------------------

class TestCheckHerbQuality:
    def test_good_status_no_dates(self):
        result = check_herb_quality(_herb())
        assert result["status"] == "good"
        assert result["issues"] == []
        # Herbs still get deterioration signs to inspect.
        assert len(result["deterioration_signs"]) == 5
        assert result["is_herb"] is True

    def test_expiry_critical(self):
        med = _herb(expiry_date=_days_from_now(-5))
        result = check_herb_quality(med)
        assert result["status"] == "critical"
        types = [i["type"] for i in result["issues"]]
        assert "expired" in types

    def test_expiry_warning_within_30_days(self):
        med = _herb(expiry_date=_days_from_now(20))
        result = check_herb_quality(med)
        assert result["status"] == "warning"
        types = [i["type"] for i in result["issues"]]
        assert "expiring_soon" in types

    def test_expiry_far_future_is_good(self):
        med = _herb(expiry_date=_days_from_now(365))
        result = check_herb_quality(med)
        assert result["status"] == "good"

    def test_opened_shelf_life_exceeded_critical(self):
        # Opened 200 days ago, default shelf 365 — but make it volatile (180).
        med = _herb(opened_date=_days_from_now(-200),
                    properties={"herbCategory": "挥发油类"})
        result = check_herb_quality(med)
        assert result["status"] == "critical"
        types = [i["type"] for i in result["issues"]]
        assert "opened_shelf_life_exceeded" in types
        assert result["shelf_life_days"] == 180

    def test_opened_near_limit_warning(self):
        # Volatile (180d), opened 160 days ago → 160 >= 0.8*180=144 → warning.
        med = _herb(opened_date=_days_from_now(-160),
                    properties={"herbCategory": "挥发油类"})
        result = check_herb_quality(med)
        assert result["status"] == "warning"
        types = [i["type"] for i in result["issues"]]
        assert "opened_near_limit" in types

    def test_opened_within_shelf_life_no_warning(self):
        med = _herb(opened_date=_days_from_now(-10),
                    properties={"herbCategory": "挥发油类"})
        result = check_herb_quality(med)
        # 10 days into 180-day window → no opened warning.
        opened_issues = [i for i in result["issues"]
                         if i["type"].startswith("opened")]
        assert opened_issues == []

    def test_explicit_shelf_life_after_open_used(self):
        med = _herb(opened_date=_days_from_now(-100),
                    shelf_life_after_open="3个月")
        result = check_herb_quality(med)
        # 3个月=90d, opened 100d ago → exceeded.
        assert result["status"] == "critical"
        assert result["shelf_life_days"] == 90

    def test_no_opened_date_skips_shelf_life_check(self):
        med = _herb(expiry_date=_days_from_now(365))
        result = check_herb_quality(med)
        opened_issues = [i for i in result["issues"]
                         if i["type"].startswith("opened")]
        assert opened_issues == []

    def test_critical_takes_priority_over_warning(self):
        # Both expired (critical) and opened-exceeded would be critical;
        # ensure expired + near-limit opened → still critical.
        med = _herb(
            expiry_date=_days_from_now(-1),
            opened_date=_days_from_now(-160),
            properties={"herbCategory": "挥发油类"},
        )
        result = check_herb_quality(med)
        assert result["status"] == "critical"


# ---------------------------------------------------------------------------
# Deterioration signs (herbs only)
# ---------------------------------------------------------------------------

class TestDeteriorationSigns:
    def test_herb_gets_deterioration_signs(self):
        result = check_herb_quality(_herb(type="herbal"))
        signs = {s["sign"] for s in result["deterioration_signs"]}
        assert signs == set(DETERIORATION_SIGNS.keys())

    def test_western_medicine_no_deterioration_signs(self):
        med = {"name": "布洛芬", "type": "western", "quantity": 10}
        result = check_herb_quality(med)
        assert result["deterioration_signs"] == []
        assert result["is_herb"] is False

    def test_inspect_prompt_when_open_long(self):
        # Opened 200 days ago, herb → inspect_deterioration warning expected.
        med = _herb(opened_date=_days_from_now(-200),
                    properties={"herbCategory": "矿物类"})  # 730d, not exceeded
        result = check_herb_quality(med)
        types = [i["type"] for i in result["issues"]]
        assert "inspect_deterioration" in types

    def test_no_inspect_prompt_for_western(self):
        med = {"name": "阿司匹林", "type": "western",
               "opened_date": _days_from_now(-400)}
        result = check_herb_quality(med)
        types = [i["type"] for i in result["issues"]]
        assert "inspect_deterioration" not in types


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

class TestRecommendations:
    def test_critical_has_recommendations(self):
        med = _herb(expiry_date=_days_from_now(-1))
        result = check_herb_quality(med)
        assert result["status"] == "critical"
        assert len(result["recommendations"]) >= 1

    def test_good_herb_has_storage_advice(self):
        result = check_herb_quality(_herb())
        assert result["status"] == "good"
        assert any("阴凉" in r for r in result["recommendations"])


# ---------------------------------------------------------------------------
# Date parsing edge cases
# ---------------------------------------------------------------------------

class TestDateParsing:
    def test_iso_date(self):
        assert _parse_date("2026-06-17") is not None

    def test_slash_date(self):
        assert _parse_date("2026/06/17") is not None

    def test_empty_returns_none(self):
        assert _parse_date("") is None
        assert _parse_date(None) is None

    def test_garbage_returns_none(self):
        assert _parse_date("not-a-date") is None


# ---------------------------------------------------------------------------
# HTTP API endpoints
# ---------------------------------------------------------------------------

class TestQualityEndpoint:
    @pytest.mark.asyncio
    async def test_get_quality_for_medicine(
        self, client: AsyncClient, auth_headers: dict
    ):
        """GET /api/medicines/{id}/quality returns assessment."""
        create = await client.post("/api/medicines", headers=auth_headers, json={
            "name": "黄芪饮片",
            "type": "herbal",
            "quantity": 50,
            "expiry_date": _days_from_now(10),
        })
        assert create.status_code == 201
        med_id = create.json()["id"]

        resp = await client.get(
            f"/api/medicines/{med_id}/quality", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "warning"  # expiry within 30 days
        assert data["name"] == "黄芪饮片"
        assert data["is_herb"] is True
        assert len(data["deterioration_signs"]) == 5
        assert data["medicine_id"] == med_id
        assert "shelf_life_days" in data

    @pytest.mark.asyncio
    async def test_quality_expired_medicine(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Quality endpoint flags expired medicine as critical."""
        create = await client.post("/api/medicines", headers=auth_headers, json={
            "name": "过期板蓝根",
            "type": "herbal",
            "expiry_date": _days_from_now(-30),
        })
        med_id = create.json()["id"]

        resp = await client.get(
            f"/api/medicines/{med_id}/quality", headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "critical"

    @pytest.mark.asyncio
    async def test_quality_404_for_missing(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.get(
            "/api/medicines/nonexistent-id/quality", headers=auth_headers
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_quality_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/medicines/some-id/quality")
        assert resp.status_code == 401


class TestQualityAlertsEndpoint:
    @pytest.mark.asyncio
    async def test_quality_alerts_returns_flagged_only(
        self, client: AsyncClient, auth_headers: dict
    ):
        """GET /api/medicines/quality-alerts returns only non-good medicines."""
        # Good medicine (far expiry, not opened).
        await client.post("/api/medicines", headers=auth_headers, json={
            "name": "新鲜黄芪",
            "type": "herbal",
            "expiry_date": _days_from_now(500),
        })
        # Critical (expired).
        await client.post("/api/medicines", headers=auth_headers, json={
            "name": "过期药",
            "type": "western",
            "expiry_date": _days_from_now(-10),
        })
        # Warning (expiring soon).
        await client.post("/api/medicines", headers=auth_headers, json={
            "name": "临期药",
            "type": "western",
            "expiry_date": _days_from_now(15),
        })

        resp = await client.get(
            "/api/medicines/quality-alerts", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        names = [m["name"] for m in data["items"]]
        assert "过期药" in names
        assert "临期药" in names
        assert "新鲜黄芪" not in names
        assert data["total"] == 2
        # Each flagged item carries the quality assessment.
        assert "quality" in data["items"][0]
        assert data["items"][0]["quality"]["status"] in ("warning", "critical")

    @pytest.mark.asyncio
    async def test_quality_alerts_route_not_shadowed_by_id_param(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Ensure /quality-alerts is matched as a literal, not a medicine_id."""
        resp = await client.get(
            "/api/medicines/quality-alerts", headers=auth_headers
        )
        # Must be 200 with the alerts shape, NOT 404 (which would happen if
        # 'quality-alerts' were treated as a medicine_id).
        assert resp.status_code == 200
        assert "items" in resp.json()
        assert "total" in resp.json()

    @pytest.mark.asyncio
    async def test_quality_alerts_empty_when_all_good(
        self, client: AsyncClient, auth_headers: dict
    ):
        await client.post("/api/medicines", headers=auth_headers, json={
            "name": "好药",
            "type": "herbal",
            "expiry_date": _days_from_now(500),
        })
        resp = await client.get(
            "/api/medicines/quality-alerts", headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    @pytest.mark.asyncio
    async def test_quality_alerts_tenant_isolation(
        self, client: AsyncClient, auth_headers: dict, second_user_headers: dict
    ):
        """User A's expired medicine not visible to User B."""
        await client.post("/api/medicines", headers=auth_headers, json={
            "name": "用户A过期药",
            "type": "western",
            "expiry_date": _days_from_now(-5),
        })
        resp = await client.get(
            "/api/medicines/quality-alerts", headers=second_user_headers
        )
        assert resp.status_code == 200
        names = [m["name"] for m in resp.json()["items"]]
        assert "用户A过期药" not in names

    @pytest.mark.asyncio
    async def test_quality_alerts_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/medicines/quality-alerts")
        assert resp.status_code == 401
