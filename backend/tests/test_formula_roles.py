"""Tests for formula herb role classification (spec §2.2 — 君臣佐使拆解)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.routers.formulas import (
    ENVOY_HERBS,
    _extract_herbs_with_dosage,
    _parse_dose_num,
    _parse_formula,
    classify_herb_roles,
)


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

def test_parse_dose_num_various_formats():
    """_parse_dose_num should extract numeric value from various dose strings."""
    assert _parse_dose_num("9g") == 9.0
    assert _parse_dose_num("12g") == 12.0
    assert _parse_dose_num("3枚") == 3.0
    assert _parse_dose_num("6克") == 6.0
    assert _parse_dose_num("") == 0.0
    assert _parse_dose_num(None) == 0.0
    assert _parse_dose_num(15) == 15.0


def test_classify_empty_herbs():
    """No herbs → empty result."""
    assert classify_herb_roles([]) == []


def test_classify_single_herb_is_jun():
    """Single herb should be 君药."""
    herbs = [{"name": "黄芪", "dosage": "30g", "dosage_num": 30}]
    roles = classify_herb_roles(herbs)
    assert len(roles) == 1
    assert roles[0]["name"] == "黄芪"
    assert roles[0]["role"] == "君药"
    assert "主药" in roles[0]["rationale"]


def test_classify_gancao_is_shi():
    """甘草 should always be 使药 regardless of dosage."""
    herbs = [
        {"name": "人参", "dosage": "9g", "dosage_num": 9},
        {"name": "白术", "dosage": "9g", "dosage_num": 9},
        {"name": "茯苓", "dosage": "9g", "dosage_num": 9},
        {"name": "甘草", "dosage": "6g", "dosage_num": 6},
    ]
    roles = classify_herb_roles(herbs)
    gancao = next(r for r in roles if r["name"] == "甘草")
    assert gancao["role"] == "使药"


def test_classify_dazao_is_shi():
    """大枣 should be 使药."""
    herbs = [
        {"name": "桂枝", "dosage": "9g", "dosage_num": 9},
        {"name": "大枣", "dosage": "3枚", "dosage_num": 3},
    ]
    roles = classify_herb_roles(herbs)
    dazao = next(r for r in roles if r["name"] == "大枣")
    assert dazao["role"] == "使药"


def test_classify_highest_dosage_is_jun():
    """Highest dosage herb (non-envoy) should be 君药."""
    herbs = [
        {"name": "熟地黄", "dosage": "12g", "dosage_num": 12},
        {"name": "当归", "dosage": "9g", "dosage_num": 9},
        {"name": "白芍", "dosage": "9g", "dosage_num": 9},
        {"name": "川芎", "dosage": "6g", "dosage_num": 6},
    ]
    roles = classify_herb_roles(herbs)
    assert roles[0]["name"] == "熟地黄"
    assert roles[0]["role"] == "君药"
    assert roles[0]["dosage"] == "12g"


def test_classify_envoy_herbs_set():
    """ENVOY_HERBS should contain common guide herbs."""
    assert "甘草" in ENVOY_HERBS
    assert "大枣" in ENVOY_HERBS
    assert "生姜" in ENVOY_HERBS
    assert "薄荷" in ENVOY_HERBS


def test_classify_result_structure():
    """Each role entry should have name, role, dosage, rationale."""
    herbs = [{"name": "人参", "dosage": "9g", "dosage_num": 9}]
    roles = classify_herb_roles(herbs)
    entry = roles[0]
    assert "name" in entry
    assert "role" in entry
    assert "dosage" in entry
    assert "rationale" in entry


# ---------------------------------------------------------------------------
# Integration tests via API — 四君子汤 (formula-001)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_formula_has_herb_roles(client: AsyncClient):
    """GET /api/formulas/{id} should include herb_roles field."""
    response = await client.get("/api/formulas/formula-001")
    assert response.status_code == 200
    data = response.json()
    assert "herb_roles" in data
    assert isinstance(data["herb_roles"], list)
    assert len(data["herb_roles"]) == 4


@pytest.mark.asyncio
async def test_formula_001_jun_is_renshen(client: AsyncClient):
    """四君子汤: 人参 (9g) should be 君药."""
    response = await client.get("/api/formulas/formula-001")
    roles = response.json()["herb_roles"]
    renshen = next(r for r in roles if r["name"] == "人参")
    assert renshen["role"] == "君药"


@pytest.mark.asyncio
async def test_formula_001_gancao_is_shi(client: AsyncClient):
    """四君子汤: 甘草 should be 使药."""
    response = await client.get("/api/formulas/formula-001")
    roles = response.json()["herb_roles"]
    gancao = next(r for r in roles if r["name"] == "甘草")
    assert gancao["role"] == "使药"


@pytest.mark.asyncio
async def test_get_formula_roles_endpoint(client: AsyncClient):
    """GET /api/formulas/{id}/roles should return just the roles."""
    response = await client.get("/api/formulas/formula-001/roles")
    assert response.status_code == 200
    data = response.json()
    assert data["formula_id"] == "formula-001"
    assert data["name"] == "四君子汤"
    assert isinstance(data["herb_roles"], list)
    assert len(data["herb_roles"]) == 4
    for role in data["herb_roles"]:
        assert "name" in role
        assert "role" in role
        assert "dosage" in role
        assert "rationale" in role


@pytest.mark.asyncio
async def test_formula_roles_not_found(client: AsyncClient):
    """GET /api/formulas/nonexistent/roles → 404."""
    response = await client.get("/api/formulas/nonexistent/roles")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_formula_002_si_wu_tang_distribution(client: AsyncClient):
    """四物汤 (formula-002): 熟地黄=君, 当归/白芍=臣, 川芎=佐."""
    response = await client.get("/api/formulas/formula-002/roles")
    assert response.status_code == 200
    roles = response.json()["herb_roles"]

    by_name = {r["name"]: r for r in roles}
    assert "熟地黄" in by_name
    assert by_name["熟地黄"]["role"] == "君药"

    assert "当归" in by_name
    assert by_name["当归"]["role"] in ("君药", "臣药")

    assert "川芎" in by_name
    assert by_name["川芎"]["role"] in ("佐药", "臣药")


@pytest.mark.asyncio
async def test_formula_roles_sorted_by_dosage(client: AsyncClient):
    """Herb roles should be sorted by dosage descending (non-envoy)."""
    response = await client.get("/api/formulas/formula-002/roles")
    roles = response.json()["herb_roles"]
    dosages = [r["dosage"] for r in roles if r["role"] != "使药"]
    assert len(dosages) >= 2
