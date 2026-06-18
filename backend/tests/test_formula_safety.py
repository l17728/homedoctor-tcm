"""Tests for formula safety-check integration and TTS text endpoint.

Covers:
  - extract_herb_names() helper: composition list, properties.herbs array,
    properties.组成 free text, dosage stripping, dedup, mixed formats.
  - GET /api/formulas/{id}/safety-check: safe formula, 十八反 conflict,
    unknown formula 404, disclaimer, result structure, large formula, auth.
  - GET /api/formulas/{id}/safety-text: TTS plain-text output.
  - Integration: formula detail herb names == safety-check checked_herbs.
"""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

from app.database import DbAdapter
from app.routers.formulas import extract_herb_names


# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------

CONFLICT_FORMULA_ID = "formula-test-conflict"
LARGE_FORMULA_ID = "formula-test-large"
TEXT_FORMAT_ID = "formula-test-text"
ARRAY_FORMAT_ID = "formula-test-array"
EMPTY_FORMULA_ID = "formula-test-empty"


async def _seed_test_formulas(db: DbAdapter) -> None:
    """Insert formulas covering conflict, large, text-format, array-format."""
    formulas = [
        {
            "id": CONFLICT_FORMULA_ID,
            "name": "测试禁忌方",
            "composition": json.dumps(
                [
                    {"name": "附子", "dose": "9g", "role": "君"},
                    {"name": "半夏", "dose": "9g", "role": "臣"},
                    {"name": "甘草", "dose": "3g", "role": "使"},
                ],
                ensure_ascii=False,
            ),
            "properties": "{}",
        },
        {
            "id": LARGE_FORMULA_ID,
            "name": "测试大方",
            "composition": json.dumps(
                [
                    {"name": "黄芪", "dose": "30g", "role": "君"},
                    {"name": "当归", "dose": "10g", "role": "臣"},
                    {"name": "白术", "dose": "10g", "role": "佐"},
                    {"name": "茯苓", "dose": "10g", "role": "佐"},
                    {"name": "甘草", "dose": "6g", "role": "使"},
                    {"name": "人参", "dose": "6g", "role": "臣"},
                    {"name": "川芎", "dose": "6g", "role": "佐"},
                ],
                ensure_ascii=False,
            ),
            "properties": "{}",
        },
        {
            "id": TEXT_FORMAT_ID,
            "name": "测试文本格式方",
            "composition": "[]",
            "properties": json.dumps(
                {"组成": "黄芪30g 人参10g 甘草6g"}, ensure_ascii=False
            ),
        },
        {
            "id": ARRAY_FORMAT_ID,
            "name": "测试数组格式方",
            "composition": "[]",
            "properties": json.dumps(
                {"herbs": ["黄芪", "人参", "甘草"]}, ensure_ascii=False
            ),
        },
        {
            "id": EMPTY_FORMULA_ID,
            "name": "测试空方",
            "composition": "[]",
            "properties": "{}",
        },
    ]
    for f in formulas:
        await db.execute(
            """INSERT OR IGNORE INTO formulas
               (id, name, source, category, composition, efficacy, indications,
                modifications, modifications_structured, properties)
               VALUES (?, ?, '', '', ?, '', '', '[]', '[]', ?)""",
            (f["id"], f["name"], f["composition"], f["properties"]),
        )
    await db.execute("COMMIT")


# ---------------------------------------------------------------------------
# extract_herb_names unit tests
# ---------------------------------------------------------------------------

class TestExtractHerbNames:
    def test_from_composition_list_of_dicts(self):
        data = {
            "composition": [
                {"name": "黄芪", "dose": "30g", "role": "君"},
                {"name": "人参", "dose": "10g", "role": "臣"},
            ]
        }
        assert extract_herb_names(data) == ["黄芪", "人参"]

    def test_from_properties_herbs_array(self):
        data = {"composition": [], "properties": {"herbs": ["黄芪", "人参", "甘草"]}}
        assert extract_herb_names(data) == ["黄芪", "人参", "甘草"]

    def test_from_properties_text_format(self):
        data = {
            "composition": [],
            "properties": {"组成": "黄芪30g 人参10g 甘草6g"},
        }
        assert extract_herb_names(data) == ["黄芪", "人参", "甘草"]

    def test_text_with_chinese_dosage_units(self):
        data = {
            "composition": [],
            "properties": {"组成": "麻黄三钱 桂枝二钱 甘草一钱"},
        }
        result = extract_herb_names(data)
        assert "麻黄" in result
        assert "桂枝" in result
        assert "甘草" in result

    def test_text_with_mixed_numbers_and_chars(self):
        data = {
            "composition": [],
            "properties": {"组成": "熟地黄12g 当归9g 白芍9g 川芎6g"},
        }
        result = extract_herb_names(data)
        assert result == ["熟地黄", "当归", "白芍", "川芎"]

    def test_deduplication(self):
        data = {
            "composition": [
                {"name": "黄芪", "dose": "30g"},
                {"name": "黄芪", "dose": "15g"},
                {"name": "人参", "dose": "10g"},
            ]
        }
        assert extract_herb_names(data) == ["黄芪", "人参"]

    def test_empty_formula(self):
        assert extract_herb_names({"composition": [], "properties": {}}) == []

    def test_missing_all_fields(self):
        assert extract_herb_names({}) == []

    def test_composition_list_of_strings(self):
        data = {"composition": ["黄芪", "人参", "甘草"]}
        assert extract_herb_names(data) == ["黄芪", "人参", "甘草"]

    def test_composition_priority_over_properties(self):
        data = {
            "composition": [{"name": "黄芪"}],
            "properties": {"herbs": ["人参", "当归"]},
        }
        assert extract_herb_names(data) == ["黄芪"]

    def test_strips_whitespace(self):
        data = {"composition": [{"name": "  黄芪  "}]}
        assert extract_herb_names(data) == ["黄芪"]


# ---------------------------------------------------------------------------
# GET /api/formulas/{id}/safety-check
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_safety_check_safe_formula(client, auth_headers, db):
    await _seed_test_formulas(db)
    resp = await client.get(
        f"/api/formulas/{LARGE_FORMULA_ID}/safety-check", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "safe" in data
    assert "warnings" in data
    assert "disclaimer" in data
    assert "checked_herbs" in data
    assert isinstance(data["checked_herbs"], list)


@pytest.mark.asyncio
async def test_safety_check_conflict_formula_18fan(client, auth_headers, db):
    await _seed_test_formulas(db)
    resp = await client.get(
        f"/api/formulas/{CONFLICT_FORMULA_ID}/safety-check", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is False
    assert len(data["warnings"]) >= 1
    conflict = data["warnings"][0]
    assert conflict["severity"] == "critical"
    herbs_set = set(conflict["herbs"])
    assert "附子" in herbs_set
    assert "半夏" in herbs_set


@pytest.mark.asyncio
async def test_safety_check_unknown_formula_404(client, auth_headers):
    resp = await client.get(
        "/api/formulas/nonexistent-formula/safety-check", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_safety_check_returns_disclaimer(client, auth_headers, db):
    await _seed_test_formulas(db)
    resp = await client.get(
        f"/api/formulas/{LARGE_FORMULA_ID}/safety-check", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["disclaimer"]
    assert "咨询" in data["disclaimer"]


@pytest.mark.asyncio
async def test_safety_check_empty_formula_is_safe(client, auth_headers, db):
    await _seed_test_formulas(db)
    resp = await client.get(
        f"/api/formulas/{EMPTY_FORMULA_ID}/safety-check", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is True
    assert len(data["warnings"]) == 0


@pytest.mark.asyncio
async def test_safety_check_result_structure(client, auth_headers, db):
    await _seed_test_formulas(db)
    resp = await client.get(
        f"/api/formulas/{CONFLICT_FORMULA_ID}/safety-check", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    required_keys = {
        "safe", "warnings", "disclaimer",
        "checked_herbs", "checked_medicines",
        "unknown_herbs", "unknown_medicines",
    }
    assert required_keys.issubset(data.keys())
    for w in data["warnings"]:
        assert "layer" in w
        assert "severity" in w
        assert "title" in w
        assert "detail" in w
        assert "herbs" in w
        assert "action" in w
        assert "source" in w


@pytest.mark.asyncio
async def test_safety_check_large_formula_over_5_herbs(client, auth_headers, db):
    await _seed_test_formulas(db)
    resp = await client.get(
        f"/api/formulas/{LARGE_FORMULA_ID}/safety-check", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["checked_herbs"]) > 5


@pytest.mark.asyncio
async def test_safety_check_text_format_formula(client, auth_headers, db):
    await _seed_test_formulas(db)
    resp = await client.get(
        f"/api/formulas/{TEXT_FORMAT_ID}/safety-check", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "黄芪" in data["checked_herbs"]
    assert "人参" in data["checked_herbs"]
    assert "甘草" in data["checked_herbs"]


@pytest.mark.asyncio
async def test_safety_check_array_format_formula(client, auth_headers, db):
    await _seed_test_formulas(db)
    resp = await client.get(
        f"/api/formulas/{ARRAY_FORMAT_ID}/safety-check", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert set(data["checked_herbs"]) == {"黄芪", "人参", "甘草"}


@pytest.mark.asyncio
async def test_safety_check_requires_auth(client, db):
    await _seed_test_formulas(db)
    resp = await client.get(f"/api/formulas/{LARGE_FORMULA_ID}/safety-check")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_safety_check_two_users_same_result(client, auth_headers, second_user_headers, db):
    await _seed_test_formulas(db)
    resp1 = await client.get(
        f"/api/formulas/{LARGE_FORMULA_ID}/safety-check", headers=auth_headers
    )
    resp2 = await client.get(
        f"/api/formulas/{LARGE_FORMULA_ID}/safety-check", headers=second_user_headers
    )
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["safe"] == resp2.json()["safe"]
    assert resp1.json()["checked_herbs"] == resp2.json()["checked_herbs"]


@pytest.mark.asyncio
async def test_safety_check_multiple_formulas_different_profiles(client, auth_headers, db):
    await _seed_test_formulas(db)
    safe_resp = await client.get(
        f"/api/formulas/{LARGE_FORMULA_ID}/safety-check", headers=auth_headers
    )
    conflict_resp = await client.get(
        f"/api/formulas/{CONFLICT_FORMULA_ID}/safety-check", headers=auth_headers
    )
    assert safe_resp.status_code == 200
    assert conflict_resp.status_code == 200
    safe_data = safe_resp.json()
    conflict_data = conflict_resp.json()
    assert safe_data["safe"] != conflict_data["safe"] or \
           len(safe_data["warnings"]) != len(conflict_data["warnings"])


@pytest.mark.asyncio
async def test_safety_check_seeded_formula_safe(client, auth_headers):
    resp = await client.get(
        "/api/formulas/formula-001/safety-check", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is True
    blocking = [w for w in data["warnings"] if w["severity"] in ("critical", "high")]
    assert len(blocking) == 0


# ---------------------------------------------------------------------------
# GET /api/formulas/{id}/safety-text (TTS-ready)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_safety_text_returns_plain_text(client, auth_headers, db):
    await _seed_test_formulas(db)
    resp = await client.get(
        f"/api/formulas/{LARGE_FORMULA_ID}/safety-text", headers=auth_headers
    )
    assert resp.status_code == 200
    assert "text/plain" in resp.headers.get("content-type", "")
    assert "utf-8" in resp.headers.get("content-type", "").lower()


@pytest.mark.asyncio
async def test_safety_text_contains_formula_name(client, auth_headers, db):
    await _seed_test_formulas(db)
    resp = await client.get(
        f"/api/formulas/{LARGE_FORMULA_ID}/safety-text", headers=auth_headers
    )
    assert resp.status_code == 200
    assert "测试大方" in resp.text


@pytest.mark.asyncio
async def test_safety_text_contains_disclaimer(client, auth_headers, db):
    await _seed_test_formulas(db)
    resp = await client.get(
        f"/api/formulas/{LARGE_FORMULA_ID}/safety-text", headers=auth_headers
    )
    assert resp.status_code == 200
    assert "咨询" in resp.text


@pytest.mark.asyncio
async def test_safety_text_conflict_formula(client, auth_headers, db):
    await _seed_test_formulas(db)
    resp = await client.get(
        f"/api/formulas/{CONFLICT_FORMULA_ID}/safety-text", headers=auth_headers
    )
    assert resp.status_code == 200
    assert "禁忌" in resp.text or "禁止" in resp.text


@pytest.mark.asyncio
async def test_safety_text_unknown_formula_404(client, auth_headers):
    resp = await client.get(
        "/api/formulas/nonexistent/safety-text", headers=auth_headers
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Integration: formula detail ↔ safety-check consistency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_integration_detail_herbs_match_safety_check(client, auth_headers, db):
    await _seed_test_formulas(db)
    detail_resp = await client.get(
        f"/api/formulas/{LARGE_FORMULA_ID}", headers=auth_headers
    )
    safety_resp = await client.get(
        f"/api/formulas/{LARGE_FORMULA_ID}/safety-check", headers=auth_headers
    )
    assert detail_resp.status_code == 200
    assert safety_resp.status_code == 200
    detail_herbs = {c["name"] for c in detail_resp.json()["composition"]}
    checked_herbs = set(safety_resp.json()["checked_herbs"])
    assert detail_herbs == checked_herbs
