"""Tests for health check endpoint — DB probe + degraded states."""

import asyncio

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """GET /api/health returns 200 with status ok and database ok."""
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "ok"
    assert "version" in data
    assert data["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_health_degraded_on_db_error(raw_client: AsyncClient, db, monkeypatch):
    """DB probe raising → 503 {"status":"degraded","database":"error"}."""

    async def broken_query(sql, params=()):
        raise RuntimeError("db is broken")

    monkeypatch.setattr(db, "query", broken_query)
    response = await raw_client.get("/api/health")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert data["database"] == "error"


@pytest.mark.asyncio
async def test_health_degraded_on_db_timeout(raw_client: AsyncClient, db, monkeypatch):
    """DB probe slower than the 1s timeout → 503 degraded."""

    async def slow_query(sql, params=()):
        await asyncio.sleep(5)

    monkeypatch.setattr(db, "query", slow_query)
    response = await raw_client.get("/api/health")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert data["database"] == "error"
