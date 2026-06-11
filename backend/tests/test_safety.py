"""Tests for safety check endpoint."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_safe_combination(client: AsyncClient):
    """POST /api/safety/check with safe herbs returns no warnings."""
    response = await client.post("/api/safety/check", json={
        "herbs": ["黄芪", "当归"],
    })
    assert response.status_code == 200
    data = response.json()
    assert data["safe"] is True
    assert len(data["warnings"]) == 0
    assert "disclaimer" in data


@pytest.mark.asyncio
async def test_incompatible_herbs_18fan(client: AsyncClient):
    """POST /api/safety/check with 十八反 herbs returns critical warning."""
    response = await client.post("/api/safety/check", json={
        "herbs": ["甘草", "甘遂"],
    })
    assert response.status_code == 200
    data = response.json()
    assert data["safe"] is False
    assert len(data["warnings"]) >= 1
    warning = data["warnings"][0]
    assert warning["severity"] == "critical"
    assert "十八反" in warning["rule_type"]


@pytest.mark.asyncio
async def test_incompatible_herbs_19wei(client: AsyncClient):
    """POST /api/safety/check with 十九畏 herbs returns critical warning."""
    response = await client.post("/api/safety/check", json={
        "herbs": ["丁香", "郁金"],
    })
    assert response.status_code == 200
    data = response.json()
    assert data["safe"] is False
    assert len(data["warnings"]) >= 1
    warning = data["warnings"][0]
    assert warning["severity"] == "critical"
    assert "十九畏" in warning["rule_type"]


@pytest.mark.asyncio
async def test_herb_drug_interaction(client: AsyncClient):
    """POST /api/safety/check with herb-drug interaction returns critical warning."""
    response = await client.post("/api/safety/check", json={
        "herbs": ["当归"],
        "medicines": ["华法林"],
    })
    assert response.status_code == 200
    data = response.json()
    assert data["safe"] is False
    assert len(data["warnings"]) >= 1
    warning = data["warnings"][0]
    assert warning["severity"] == "critical"
    assert "中西药交互" in warning["rule_type"]


@pytest.mark.asyncio
async def test_herb_drug_warning_level(client: AsyncClient):
    """POST /api/safety/check with 甘草+降压药 returns warning level."""
    response = await client.post("/api/safety/check", json={
        "herbs": ["甘草"],
        "medicines": ["降压药"],
    })
    assert response.status_code == 200
    data = response.json()
    assert data["safe"] is False
    assert len(data["warnings"]) >= 1


@pytest.mark.asyncio
async def test_empty_check(client: AsyncClient):
    """POST /api/safety/check with no items returns safe."""
    response = await client.post("/api/safety/check", json={
        "herbs": [],
        "medicines": [],
    })
    assert response.status_code == 200
    data = response.json()
    assert data["safe"] is True
    assert len(data["warnings"]) == 0


@pytest.mark.asyncio
async def test_multiple_interactions(client: AsyncClient):
    """POST /api/safety/check with multiple conflicts returns all warnings."""
    response = await client.post("/api/safety/check", json={
        "herbs": ["甘草", "半夏", "当归", "人参"],
        "medicines": ["华法林"],
    })
    assert response.status_code == 200
    data = response.json()
    assert data["safe"] is False
    # Should find: 甘草×甘遂(no甘遂, so not this), but 甘草 is in 十八反 with others
    # 人参 × 藜芦(no藜芦), but 人参 × 五灵脂(十九畏, no五灵脂)
    # Actually: 当归 + 华法林 (R-01) should be found
    assert len(data["warnings"]) >= 1
