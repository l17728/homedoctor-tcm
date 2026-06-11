"""Tests for herbs endpoints: list, detail, search."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_herbs(client: AsyncClient):
    """GET /api/herbs returns paginated list."""
    response = await client.get("/api/herbs")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "pageSize" in data
    assert data["page"] == 1
    assert data["total"] >= 3  # We seeded 3 herbs


@pytest.mark.asyncio
async def test_list_herbs_pagination(client: AsyncClient):
    """GET /api/herbs?page=1&pageSize=2 returns correct pagination."""
    response = await client.get("/api/herbs", params={"page": 1, "pageSize": 2})
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) <= 2
    assert data["pageSize"] == 2
    assert data["totalPages"] >= 1


@pytest.mark.asyncio
async def test_list_herbs_by_category(client: AsyncClient):
    """GET /api/herbs?category=补虚药 filters by category."""
    response = await client.get("/api/herbs", params={"category": "补虚药"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 3  # All 3 test herbs are 补虚药
    for herb in data["items"]:
        assert herb["category"] == "补虚药"


@pytest.mark.asyncio
async def test_get_herb_detail(client: AsyncClient):
    """GET /api/herbs/{id} returns herb detail."""
    response = await client.get("/api/herbs/herb-001")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "黄芪"
    assert data["nature"] == "微温"
    assert data["category"] == "补虚药"
    assert data["toxicity"] == "无毒"
    assert isinstance(data["properties"], dict)


@pytest.mark.asyncio
async def test_get_herb_not_found(client: AsyncClient):
    """GET /api/herbs/{invalid_id} returns 404."""
    response = await client.get("/api/herbs/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_search_herbs(client: AsyncClient):
    """GET /api/herbs/search?q=黄芪 returns matching herbs."""
    response = await client.get("/api/herbs/search", params={"q": "黄芪"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    names = [h["name"] for h in data["items"]]
    assert "黄芪" in names


@pytest.mark.asyncio
async def test_search_herbs_by_alias(client: AsyncClient):
    """GET /api/herbs/search?q=绵芪 returns 黄芪 by alias."""
    response = await client.get("/api/herbs/search", params={"q": "绵芪"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    names = [h["name"] for h in data["items"]]
    assert "黄芪" in names
