"""Tests for Dashboard Stats router (app/routers/dashboard.py)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# GET /api/dashboard/stats
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dashboard_stats_basic(client: AsyncClient, auth_headers: dict):
    """Should return all required stat fields."""
    response = await client.get("/api/dashboard/stats", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    assert "herb_count" in data
    assert "formula_count" in data
    assert "medicine_count" in data
    assert "safety_alert_count" in data
    assert "recent_searches" in data
    assert "stock_alerts" in data


@pytest.mark.asyncio
async def test_dashboard_stats_herb_count(client: AsyncClient, auth_headers: dict):
    """Herb count should reflect seed data (3 herbs)."""
    response = await client.get("/api/dashboard/stats", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["herb_count"] == 3  # seed_test_data inserts 3 herbs


@pytest.mark.asyncio
async def test_dashboard_stats_formula_count(client: AsyncClient, auth_headers: dict):
    """Formula count should reflect seed data (2 formulas)."""
    response = await client.get("/api/dashboard/stats", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["formula_count"] == 2  # seed_test_data inserts 2 formulas


@pytest.mark.asyncio
async def test_dashboard_stats_medicine_count_empty(client: AsyncClient, auth_headers: dict):
    """New user should have 0 medicines."""
    response = await client.get("/api/dashboard/stats", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["medicine_count"] == 0


@pytest.mark.asyncio
async def test_dashboard_stats_medicine_count_after_add(client: AsyncClient, auth_headers: dict):
    """Medicine count should increase after adding medicines."""
    # Add two medicines
    await client.post(
        "/api/medicines",
        json={"name": "感冒灵", "type": "western", "quantity": 10},
        headers=auth_headers,
    )
    await client.post(
        "/api/medicines",
        json={"name": "维生素C", "type": "supplement", "quantity": 5},
        headers=auth_headers,
    )

    response = await client.get("/api/dashboard/stats", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["medicine_count"] == 2


@pytest.mark.asyncio
async def test_dashboard_stats_safety_alert_count(client: AsyncClient, auth_headers: dict):
    """Safety alert count should reflect seeded safety rules (>0)."""
    response = await client.get("/api/dashboard/stats", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["safety_alert_count"] > 0


@pytest.mark.asyncio
async def test_dashboard_stats_stock_alerts_empty(client: AsyncClient, auth_headers: dict):
    """No medicines means no stock alerts."""
    response = await client.get("/api/dashboard/stats", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["stock_alerts"] == []


@pytest.mark.asyncio
async def test_dashboard_stats_stock_alerts_low_quantity(client: AsyncClient, auth_headers: dict):
    """Medicines with quantity <= 3 should trigger stock alerts."""
    # Add a medicine with low quantity
    await client.post(
        "/api/medicines",
        json={"name": "创可贴", "type": "western", "quantity": 1},
        headers=auth_headers,
    )

    response = await client.get("/api/dashboard/stats", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["stock_alerts"]) >= 1
    alert_names = [a["name"] for a in data["stock_alerts"]]
    assert "创可贴" in alert_names


@pytest.mark.asyncio
async def test_dashboard_stats_requires_auth(raw_client: AsyncClient):
    """Dashboard stats should require authentication."""
    response = await raw_client.get("/api/dashboard/stats")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_dashboard_stats_recent_searches_placeholder(client: AsyncClient, auth_headers: dict):
    """Recent searches should be an empty list for MVP."""
    response = await client.get("/api/dashboard/stats", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["recent_searches"], list)


@pytest.mark.asyncio
async def test_dashboard_stats_tenant_isolation(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    """Different users should see different medicine counts."""
    # User 1 adds a medicine
    await client.post(
        "/api/medicines",
        json={"name": "用户1的药", "type": "western", "quantity": 10},
        headers=auth_headers,
    )

    # User 2 has no medicines
    resp1 = await client.get("/api/dashboard/stats", headers=auth_headers)
    resp2 = await client.get("/api/dashboard/stats", headers=second_user_headers)

    data1 = resp1.json()
    data2 = resp2.json()

    assert data1["medicine_count"] >= 1
    assert data2["medicine_count"] == 0
