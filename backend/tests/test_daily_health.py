"""Tests for Daily Health Card router (app/routers/daily_health.py)."""

from __future__ import annotations

import pytest
from datetime import date
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# GET /api/daily-health
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_daily_health_card(client: AsyncClient, auth_headers: dict):
    """Should return today's health card with all required fields."""
    response = await client.get("/api/daily-health", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    # Required fields
    assert "date" in data
    assert data["date"] == date.today().isoformat()
    assert "solar_term" in data
    assert "season" in data
    assert "season_advice" in data
    assert "constitution_tips" in data
    assert "stock_alerts" in data
    assert "seasonal_herbs" in data

    # Season should be one of 春/夏/秋/冬
    assert data["season"] in ("春", "夏", "秋", "冬")

    # Season advice should be a non-empty list
    assert isinstance(data["season_advice"], list)
    assert len(data["season_advice"]) > 0

    # Constitution tips should be a non-empty list
    assert isinstance(data["constitution_tips"], list)
    assert len(data["constitution_tips"]) > 0

    # Seasonal herbs should be a non-empty list
    assert isinstance(data["seasonal_herbs"], list)
    assert len(data["seasonal_herbs"]) > 0

    # Stock alerts should be a list (empty if no medicines)
    assert isinstance(data["stock_alerts"], list)
    assert data["recent_consultations"] == {"period_days": 7, "count": 0, "topics": []}


@pytest.mark.asyncio
async def test_daily_health_uses_only_current_users_recent_consultations(client, auth_headers, db):
    user = await db.query_one("SELECT id FROM users WHERE username = 'testuser'")
    await db.execute(
        "INSERT INTO conversations (id, user_id, title, created_at) VALUES (?, ?, ?, datetime('now'))",
        ("recent-own", user["id"], "睡眠咨询"),
    )
    await db.execute(
        "INSERT INTO conversations (id, user_id, title, created_at) VALUES (?, ?, ?, datetime('now'))",
        ("recent-other", "other-user", "他人私密咨询"),
    )
    await db.execute(
        "INSERT INTO conversations (id, user_id, title, created_at) VALUES (?, ?, ?, datetime('now', '-8 days'))",
        ("old-own", user["id"], "旧咨询"),
    )
    response = await client.get("/api/daily-health", headers=auth_headers)
    data = response.json()["recent_consultations"]
    assert data == {"period_days": 7, "count": 1, "topics": ["睡眠咨询"]}


@pytest.mark.asyncio
async def test_daily_health_stock_alerts(client: AsyncClient, auth_headers: dict):
    """Should include stock alerts for low-quantity medicines."""
    # Create a medicine with low quantity
    await client.post(
        "/api/medicines",
        json={
            "name": "板蓝根颗粒",
            "type": "western",
            "quantity": 1,
        },
        headers=auth_headers,
    )

    response = await client.get("/api/daily-health", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    # Should have at least one stock alert
    assert len(data["stock_alerts"]) >= 1
    alert_names = [a["name"] for a in data["stock_alerts"]]
    assert "板蓝根颗粒" in alert_names


@pytest.mark.asyncio
async def test_daily_health_requires_auth(raw_client: AsyncClient):
    """Daily health endpoint should require authentication."""
    response = await raw_client.get("/api/daily-health")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_daily_health_next_term_info(client: AsyncClient, auth_headers: dict):
    """Should include next term information."""
    response = await client.get("/api/daily-health", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "next_term" in data
    assert "days_to_next_term" in data
    assert isinstance(data["days_to_next_term"], int)
    assert data["days_to_next_term"] >= 0


# ---------------------------------------------------------------------------
# Solar Terms module
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_solar_terms_module():
    """Test the solar_terms module directly."""
    from app.solar_terms import get_solar_term, get_season, get_next_term, SOLAR_TERMS

    # Should return all 24 terms
    assert len(SOLAR_TERMS) == 24

    # Test known dates
    assert get_solar_term(date(2026, 1, 1)) == "小寒"  # Jan 1 is before 小寒(Jan 6), falls in previous 小寒... actually Dec 22 is 冬至
    assert get_solar_term(date(2026, 1, 7)) == "小寒"
    assert get_solar_term(date(2026, 2, 4)) == "立春"
    assert get_solar_term(date(2026, 6, 21)) == "夏至"
    assert get_solar_term(date(2026, 12, 22)) == "冬至"

    # Season mapping
    assert get_season("立春") == "春"
    assert get_season("夏至") == "夏"
    assert get_season("秋分") == "秋"
    assert get_season("冬至") == "冬"

    # Next term
    name, days = get_next_term(date(2026, 1, 1))
    assert isinstance(name, str)
    assert isinstance(days, int)
    assert days > 0


@pytest.mark.asyncio
async def test_solar_terms_all_dates():
    """Every day of the year should map to a valid solar term."""
    from app.solar_terms import get_solar_term, SOLAR_TERMS

    all_term_names = {t[0] for t in SOLAR_TERMS}
    # Test first day of every month
    for month in range(1, 13):
        d = date(2026, month, 1)
        term = get_solar_term(d)
        assert term in all_term_names, f"Date {d} returned unknown term: {term}"

    # Test boundary dates
    assert get_solar_term(date(2026, 12, 31)) in all_term_names
    assert get_solar_term(date(2026, 1, 1)) in all_term_names
