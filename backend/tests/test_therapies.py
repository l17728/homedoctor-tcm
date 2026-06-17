"""Tests for therapies endpoints: list, search, detail, safety (spec §9.6)."""

import pytest
from httpx import AsyncClient

from app.therapy_data import THERAPIES, THERAPY_SAFETY_RULES, THERAPY_CATEGORIES


# ---------------------------------------------------------------------------
# GET /api/therapies — list with pagination
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_therapies(client: AsyncClient):
    response = await client.get("/api/therapies")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "pageSize" in data
    assert data["page"] == 1
    assert data["total"] >= 30


@pytest.mark.asyncio
async def test_list_therapies_returns_30_plus(client: AsyncClient):
    response = await client.get("/api/therapies", params={"pageSize": 100})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 30
    assert len(data["items"]) >= 30


@pytest.mark.asyncio
async def test_list_therapies_pagination(client: AsyncClient):
    response = await client.get("/api/therapies", params={"page": 1, "pageSize": 5})
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) <= 5
    assert data["pageSize"] == 5
    assert data["totalPages"] >= 6


@pytest.mark.asyncio
async def test_list_therapies_page2(client: AsyncClient):
    r1 = await client.get("/api/therapies", params={"page": 1, "pageSize": 10})
    r2 = await client.get("/api/therapies", params={"page": 2, "pageSize": 10})
    assert r1.status_code == 200
    assert r2.status_code == 200
    ids1 = {t["id"] for t in r1.json()["items"]}
    ids2 = {t["id"] for t in r2.json()["items"]}
    assert len(ids1 & ids2) == 0


# ---------------------------------------------------------------------------
# GET /api/therapies — category filter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_therapies_by_category_guasha(client: AsyncClient):
    response = await client.get("/api/therapies", params={"category": "刮痧"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 5
    for item in data["items"]:
        assert item["category"] == "刮痧"


@pytest.mark.asyncio
async def test_list_therapies_by_category_tuina(client: AsyncClient):
    response = await client.get("/api/therapies", params={"category": "推拿"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 5
    for item in data["items"]:
        assert item["category"] == "推拿"


@pytest.mark.asyncio
async def test_list_therapies_by_category_moxibustion(client: AsyncClient):
    response = await client.get("/api/therapies", params={"category": "艾灸"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 5
    for item in data["items"]:
        assert item["category"] == "艾灸"


@pytest.mark.asyncio
async def test_list_therapies_by_category_cupping(client: AsyncClient):
    response = await client.get("/api/therapies", params={"category": "拔罐"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 5


@pytest.mark.asyncio
async def test_list_therapies_by_category_acupuncture(client: AsyncClient):
    response = await client.get("/api/therapies", params={"category": "针刺"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 5
    for item in data["items"]:
        assert item["category"] == "针刺"


@pytest.mark.asyncio
async def test_list_therapies_by_category_pricking(client: AsyncClient):
    response = await client.get("/api/therapies", params={"category": "刺血"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 5
    for item in data["items"]:
        assert item["category"] == "刺血"


@pytest.mark.asyncio
async def test_list_therapies_invalid_category(client: AsyncClient):
    response = await client.get("/api/therapies", params={"category": "不存在的分类"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


# ---------------------------------------------------------------------------
# GET /api/therapies/categories
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_categories(client: AsyncClient):
    response = await client.get("/api/therapies/categories")
    assert response.status_code == 200
    data = response.json()
    assert "categories" in data
    cat_names = [c["name"] for c in data["categories"]]
    assert "刮痧" in cat_names
    assert "推拿" in cat_names
    assert "艾灸" in cat_names
    assert "拔罐" in cat_names
    assert "针刺" in cat_names
    assert "刺血" in cat_names
    for c in data["categories"]:
        assert c["count"] >= 5


# ---------------------------------------------------------------------------
# GET /api/therapies/search
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_therapies_by_name(client: AsyncClient):
    response = await client.get("/api/therapies/search", params={"q": "刮痧"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_search_therapies_by_indication(client: AsyncClient):
    response = await client.get("/api/therapies/search", params={"q": "感冒"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_search_therapies_by_acupoint(client: AsyncClient):
    response = await client.get("/api/therapies/search", params={"q": "足三里"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_search_therapies_with_category_filter(client: AsyncClient):
    response = await client.get(
        "/api/therapies/search",
        params={"q": "背部", "category": "刮痧"},
    )
    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        assert item["category"] == "刮痧"


@pytest.mark.asyncio
async def test_search_therapies_no_results(client: AsyncClient):
    response = await client.get("/api/therapies/search", params={"q": "完全不存在的疗法zzz"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0


# ---------------------------------------------------------------------------
# GET /api/therapies/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_therapy_detail(client: AsyncClient):
    response = await client.get("/api/therapies/therapy-guasha-001")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "感冒刮痧"
    assert data["category"] == "刮痧"
    assert data["risk_level"] == "medium"
    assert "description" in data
    assert "indications" in data
    assert "contraindications" in data
    assert "operation_steps" in data
    assert "duration" in data
    assert "precautions" in data
    assert isinstance(data.get("properties"), dict)
    assert "acupoints" in data
    assert len(data["acupoints"]) >= 1
    assert "safety_rules" in data
    assert len(data["safety_rules"]) >= 1


@pytest.mark.asyncio
async def test_get_therapy_detail_acupoints(client: AsyncClient):
    response = await client.get("/api/therapies/therapy-moxa-001")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "足三里艾灸"
    assert len(data["acupoints"]) >= 1
    ap = data["acupoints"][0]
    assert ap["acupoint_name"] == "足三里"
    assert "location" in ap
    assert "function" in ap
    assert "meridian" in ap


@pytest.mark.asyncio
async def test_get_therapy_not_found(client: AsyncClient):
    response = await client.get("/api/therapies/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_therapy_detail_includes_safety(client: AsyncClient):
    response = await client.get("/api/therapies/therapy-tuina-003")
    assert response.status_code == 200
    data = response.json()
    assert "safety_rules" in data
    assert len(data["safety_rules"]) >= 1
    severities = [r["severity"] for r in data["safety_rules"]]
    assert "critical" in severities or "high" in severities or "medium" in severities


# ---------------------------------------------------------------------------
# GET /api/therapies/{id}/safety
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_therapy_safety(client: AsyncClient):
    response = await client.get("/api/therapies/therapy-guasha-001/safety")
    assert response.status_code == 200
    data = response.json()
    assert data["therapy_id"] == "therapy-guasha-001"
    assert data["category"] == "刮痧"
    assert data["risk_level"] == "medium"
    assert "rules" in data
    assert data["total"] >= 1
    for rule in data["rules"]:
        assert "rule_type" in rule
        assert "condition_text" in rule
        assert "action" in rule
        assert "severity" in rule


@pytest.mark.asyncio
async def test_get_therapy_safety_includes_global_rules(client: AsyncClient):
    response = await client.get("/api/therapies/therapy-moxa-001/safety")
    assert response.status_code == 200
    data = response.json()
    categories_in_rules = {r["therapy_category"] for r in data["rules"]}
    assert "all" in categories_in_rules
    assert "艾灸" in categories_in_rules


@pytest.mark.asyncio
async def test_get_therapy_safety_not_found(client: AsyncClient):
    response = await client.get("/api/therapies/nonexistent/safety")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_therapy_safety_acupuncture_display_only(client: AsyncClient):
    response = await client.get("/api/therapies/therapy-acup-001/safety")
    assert response.status_code == 200
    data = response.json()
    assert data["display_only"] is True
    assert data["risk_level"] == "professional_only"


@pytest.mark.asyncio
async def test_get_therapy_safety_pricking_display_only(client: AsyncClient):
    response = await client.get("/api/therapies/therapy-pricking-001/safety")
    assert response.status_code == 200
    data = response.json()
    assert data["display_only"] is True
    assert data["risk_level"] == "high"


@pytest.mark.asyncio
async def test_get_therapy_safety_severity_ordering(client: AsyncClient):
    response = await client.get("/api/therapies/therapy-guasha-001/safety")
    assert response.status_code == 200
    rules = response.json()["rules"]
    if len(rules) >= 2:
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "warning": 4}
        for i in range(len(rules) - 1):
            s1 = severity_order.get(rules[i]["severity"], 5)
            s2 = severity_order.get(rules[i + 1]["severity"], 5)
            assert s1 <= s2


# ---------------------------------------------------------------------------
# Risk level & display_only verification (spec §9.6.1)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_acupuncture_is_display_only(client: AsyncClient):
    response = await client.get("/api/therapies", params={"category": "针刺"})
    data = response.json()
    for item in data["items"]:
        assert item["display_only"] is True
        assert item["risk_level"] == "professional_only"


@pytest.mark.asyncio
async def test_pricking_is_display_only(client: AsyncClient):
    response = await client.get("/api/therapies", params={"category": "刺血"})
    data = response.json()
    for item in data["items"]:
        assert item["display_only"] is True


@pytest.mark.asyncio
async def test_tuina_is_low_risk(client: AsyncClient):
    response = await client.get("/api/therapies", params={"category": "推拿"})
    data = response.json()
    for item in data["items"]:
        assert item["risk_level"] == "low"


@pytest.mark.asyncio
async def test_guasha_moxibustion_cupping_are_medium_risk(client: AsyncClient):
    for cat in ("刮痧", "艾灸", "拔罐"):
        response = await client.get("/api/therapies", params={"category": cat})
        data = response.json()
        assert data["total"] >= 5
        for item in data["items"]:
            assert item["risk_level"] == "medium"


# ---------------------------------------------------------------------------
# Data integrity — all 6 categories have ≥5 entries
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_categories_have_5_plus_entries(client: AsyncClient):
    for cat in THERAPY_CATEGORIES:
        response = await client.get("/api/therapies", params={"category": cat, "pageSize": 100})
        data = response.json()
        assert data["total"] >= 5, f"Category '{cat}' has only {data['total']} entries, expected ≥5"


# ---------------------------------------------------------------------------
# Seed script test — verify standalone script produces 30+
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_seed_therapy_data_count():
    assert len(THERAPIES) >= 30, f"Expected ≥30 therapies in THERAPIES, got {len(THERAPIES)}"


@pytest.mark.asyncio
async def test_seed_safety_rules_count():
    assert len(THERAPY_SAFETY_RULES) >= 20, (
        f"Expected ≥20 safety rules in THERAPY_SAFETY_RULES, got {len(THERAPY_SAFETY_RULES)}"
    )


@pytest.mark.asyncio
async def test_each_therapy_has_required_fields():
    for t in THERAPIES:
        for field in ("id", "name", "category", "risk_level", "description",
                       "indications", "contraindications", "operation_steps",
                       "duration", "frequency", "precautions"):
            assert field in t, f"Therapy {t.get('id', '?')} missing field '{field}'"


@pytest.mark.asyncio
async def test_each_therapy_category_is_valid():
    for t in THERAPIES:
        assert t["category"] in THERAPY_CATEGORIES, (
            f"Therapy {t['id']} has invalid category '{t['category']}'"
        )
