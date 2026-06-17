"""Tests for auth endpoints: register, login, me."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    """POST /api/auth/register creates a new user and returns JWT."""
    response = await client.post("/api/auth/register", json={
        "username": "newuser",
        "password": "password123",
        "display_name": "新用户",
        "consent_privacy": True,
        "consent_health_data": True,
    })
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["username"] == "newuser"
    assert data["user"]["display_name"] == "新用户"
    assert data["user"]["family_id"] is not None


@pytest.mark.asyncio
async def test_register_duplicate(client: AsyncClient):
    """POST /api/auth/register with duplicate username returns 409."""
    await client.post("/api/auth/register", json={
        "username": "dupuser",
        "password": "password123",
        "consent_privacy": True,
    })
    response = await client.post("/api/auth/register", json={
        "username": "dupuser",
        "password": "password456",
        "consent_privacy": True,
    })
    assert response.status_code == 409
    assert "已存在" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    """POST /api/auth/login with correct credentials returns JWT."""
    # Register first
    await client.post("/api/auth/register", json={
        "username": "loginuser",
        "password": "mypassword",
        "consent_privacy": True,
    })
    # Login
    response = await client.post("/api/auth/login", json={
        "username": "loginuser",
        "password": "mypassword",
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["username"] == "loginuser"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    """POST /api/auth/login with wrong password returns 401."""
    await client.post("/api/auth/register", json={
        "username": "wrongpwuser",
        "password": "correctpass",
        "consent_privacy": True,
    })
    response = await client.post("/api/auth/login", json={
        "username": "wrongpwuser",
        "password": "wrongpass",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_with_valid_token(client: AsyncClient, auth_headers: dict):
    """GET /api/auth/me with valid token returns user info."""
    response = await client.get("/api/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "testuser"
    assert data["family_id"] is not None


@pytest.mark.asyncio
async def test_me_without_token(client: AsyncClient):
    """GET /api/auth/me without token returns 401."""
    response = await client.get("/api/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_with_invalid_token(client: AsyncClient):
    """GET /api/auth/me with invalid token returns 401."""
    response = await client.get("/api/auth/me", headers={
        "Authorization": "Bearer invalid.token.here",
    })
    assert response.status_code == 401
