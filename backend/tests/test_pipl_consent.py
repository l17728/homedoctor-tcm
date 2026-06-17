"""PIPL consent tests — spec §12.2 隐私同意 / 健康数据单独同意 / 未成年人保护."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_without_consent_privacy_returns_422(client: AsyncClient):
    """POST /api/auth/register without consent_privacy → 422 请同意隐私政策."""
    response = await client.post("/api/auth/register", json={
        "username": "noconsent",
        "password": "password123",
    })
    assert response.status_code == 422
    assert "隐私政策" in response.json()["detail"]


@pytest.mark.asyncio
async def test_register_with_consent_false_returns_422(client: AsyncClient):
    """POST /api/auth/register with consent_privacy=False → 422."""
    response = await client.post("/api/auth/register", json={
        "username": "falseconsent",
        "password": "password123",
        "consent_privacy": False,
    })
    assert response.status_code == 422
    assert "隐私政策" in response.json()["detail"]


@pytest.mark.asyncio
async def test_register_with_concept_success_stores_consent(client: AsyncClient):
    """POST /api/auth/register with full consent → 201, settings contain consent data."""
    response = await client.post("/api/auth/register", json={
        "username": "fullconsent",
        "password": "password123",
        "display_name": "完全同意用户",
        "consent_privacy": True,
        "consent_health_data": True,
        "birth_year": 1980,
    })
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["user"]["username"] == "fullconsent"

    token = data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    status_resp = await client.get("/api/auth/consent-status", headers=headers)
    assert status_resp.status_code == 200
    status = status_resp.json()
    assert status["consent_privacy"] is True
    assert status["consent_health_data"] is True
    assert status["consent_date"] is not None
    assert status["birth_year"] == 1980


@pytest.mark.asyncio
async def test_register_health_consent_false_still_succeeds(client: AsyncClient):
    """consent_health_data=False → register succeeds but consent_status shows False."""
    response = await client.post("/api/auth/register", json={
        "username": "nohealthconsent",
        "password": "password123",
        "consent_privacy": True,
        "consent_health_data": False,
    })
    assert response.status_code == 201
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    status_resp = await client.get("/api/auth/consent-status", headers=headers)
    assert status_resp.status_code == 200
    status = status_resp.json()
    assert status["consent_privacy"] is True
    assert status["consent_health_data"] is False


@pytest.mark.asyncio
async def test_register_under_14_returns_422(client: AsyncClient):
    """POST /api/auth/register with birth_year indicating under 14 → 422."""
    from datetime import datetime
    current_year = datetime.now().year
    young_year = current_year - 10

    response = await client.post("/api/auth/register", json={
        "username": "under14user",
        "password": "password123",
        "consent_privacy": True,
        "consent_health_data": True,
        "birth_year": young_year,
    })
    assert response.status_code == 422
    assert "未成年人" in response.json()["detail"]


@pytest.mark.asyncio
async def test_register_exactly_14_succeeds(client: AsyncClient):
    """POST /api/auth/register with birth_year = 14 years ago → 201 (boundary)."""
    from datetime import datetime
    current_year = datetime.now().year
    boundary_year = current_year - 14

    response = await client.post("/api/auth/register", json={
        "username": "age14user",
        "password": "password123",
        "consent_privacy": True,
        "consent_health_data": True,
        "birth_year": boundary_year,
    })
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_consent_status_without_token_returns_401(client: AsyncClient):
    """GET /api/auth/consent-status without token → 401."""
    response = await client.get("/api/auth/consent-status")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_consent_status_returns_stored_consent(client: AsyncClient, auth_headers: dict):
    """GET /api/auth/consent-status returns the consent record stored at registration."""
    response = await client.get("/api/auth/consent-status", headers=auth_headers)
    assert response.status_code == 200
    status = response.json()
    assert status["consent_privacy"] is True
    assert status["consent_health_data"] is True
    assert status["consent_date"] is not None
