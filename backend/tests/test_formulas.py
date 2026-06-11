"""Tests for formulas endpoints: list, detail."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_formulas(client: AsyncClient):
    """GET /api/formulas returns paginated list."""
    response = await client.get("/api/formulas")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert data["total"] >= 2  # We seeded 2 formulas
    assert data["page"] == 1


@pytest.mark.asyncio
async def test_list_formulas_pagination(client: AsyncClient):
    """GET /api/formulas?page=1&pageSize=1 returns correct pagination."""
    response = await client.get("/api/formulas", params={"page": 1, "pageSize": 1})
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) <= 1
    assert data["totalPages"] >= 2


@pytest.mark.asyncio
async def test_get_formula_detail(client: AsyncClient):
    """GET /api/formulas/{id} returns formula detail."""
    response = await client.get("/api/formulas/formula-001")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "四君子汤"
    assert data["category"] == "补益剂"
    assert data["source"] == "《太平惠民和剂局方》"
    assert isinstance(data["composition"], list)
    assert len(data["composition"]) == 4  # 人参, 白术, 茯苓, 甘草
    # Check composition structure
    for comp in data["composition"]:
        assert "name" in comp
        assert "dose" in comp
        assert "role" in comp


@pytest.mark.asyncio
async def test_get_formula_not_found(client: AsyncClient):
    """GET /api/formulas/{invalid_id} returns 404."""
    response = await client.get("/api/formulas/nonexistent")
    assert response.status_code == 404
