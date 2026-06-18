"""Tests for behaviour on an empty / freshly-initialised database (audit gap P2.6).

Verifies that read endpoints degrade gracefully (empty results, not errors)
when the knowledge base or safety rules contain no rows, and that an
authenticated dashboard loads for a brand-new user with zero personal data.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.database import DbAdapter


@pytest.mark.asyncio
async def test_herb_search_empty_db_returns_empty(
    client: AsyncClient, db: DbAdapter
):
    """With no herbs in the DB, search must return an empty list, not error."""
    await db.execute("DELETE FROM herbs")
    await db.execute("COMMIT")

    response = await client.get("/api/herbs/search", params={"q": "黄芪"})
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_safety_check_no_rules_returns_safe(
    client: AsyncClient, db: DbAdapter
):
    """With all safety rules removed, a check must report safe=True (no crash)."""
    await db.execute("DELETE FROM safety_rules")
    await db.execute("COMMIT")

    response = await client.post(
        "/api/safety/check-v2", json={"herbs": ["黄芪", "当归"]}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["safe"] is True
    assert isinstance(data["warnings"], list)


@pytest.mark.asyncio
async def test_dashboard_with_no_data(client: AsyncClient, auth_headers: dict):
    """A brand-new user (no medicines/logs) must load the dashboard without error."""
    response = await client.get("/api/dashboard/stats", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["medicine_count"] == 0
    assert data["stock_alerts"] == []
    assert data["adherence_rate"] == 0.0
