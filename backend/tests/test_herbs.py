"""Tests for herbs endpoints: list, detail, search."""

import pytest


@pytest.mark.asyncio
async def test_alias_update_requires_admin_and_verified_source(client, auth_headers, db):
    denied = await client.patch("/api/herbs/herb-001/aliases", json={
        "aliases": ["绵芪"], "source": "药典", "verified": True,
    }, headers=auth_headers)
    assert denied.status_code == 403

    unverified = await client.patch("/api/herbs/herb-001/aliases", json={
        "aliases": ["未核验别名"], "source": "药典来源待确认", "verified": False,
    })
    assert unverified.status_code == 422

    saved = await client.patch("/api/herbs/herb-001/aliases", json={
        "aliases": ["绵芪", "黄芪", "绵芪"],
        "source": "中国药典 2020 年版",
        "verified": True,
    })
    assert saved.status_code == 200
    assert saved.json()["aliases"] == ["绵芪"]
    row = await db.query_one("SELECT aliases FROM herbs WHERE id = ?", ("herb-001",))
    assert row["aliases"] == "绵芪"
    audit = await db.query_one(
        "SELECT changes FROM audit_log WHERE entity_type = 'herb_aliases' AND entity_id = ?",
        ("herb-001",),
    )
    assert "中国药典 2020 年版" in audit["changes"]
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


@pytest.mark.asyncio
async def test_search_herbs_fts_operators_are_treated_as_text(client: AsyncClient):
    response = await client.get("/api/herbs/search", params={"q": '" OR *'})
    assert response.status_code == 200
