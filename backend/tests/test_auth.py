"""Tests for auth endpoints: register, login, me."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from jose import jwt

from app.config import settings


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
async def test_me_without_token(raw_client: AsyncClient):
    """GET /api/auth/me without token returns 401."""
    response = await raw_client.get("/api/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_with_invalid_token(client: AsyncClient):
    """GET /api/auth/me with invalid token returns 401."""
    response = await client.get("/api/auth/me", headers={
        "Authorization": "Bearer invalid.token.here",
    })
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# JWT edge cases — expired, malformed, wrong-signature tokens (audit gap P1.1)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_expired_jwt_rejected(client: AsyncClient, auth_headers: dict):
    """A JWT with a past expiry must be rejected with 401 (not accepted)."""
    # Decode the user id from the valid token issued by the auth_headers fixture.
    valid_token = auth_headers["Authorization"].removeprefix("Bearer ")
    payload = jwt.decode(
        valid_token,
        settings.SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        options={"verify_exp": False},
    )
    # Re-sign a token whose expiry is already in the past.
    expired_payload = dict(payload)
    expired_payload["exp"] = datetime.now(timezone.utc) - timedelta(hours=1)
    expired_token = jwt.encode(
        expired_payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )

    response = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_malformed_token_rejected_without_500(client: AsyncClient):
    """A structurally malformed token must yield 401, never a 500 server error."""
    malformed_tokens = [
        "not.a.valid.jwt",
        "Bearer not.a.valid.jwt",
        "!!!garbage!!!",
        "a.b.c.d.e",
        "",
    ]
    for raw in malformed_tokens:
        response = await client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {raw}"}
        )
        assert response.status_code == 401, (
            f"malformed token {raw!r} returned {response.status_code}, expected 401"
        )
        assert response.status_code != 500, (
            f"malformed token {raw!r} caused a 500 server error (must be 401)"
        )


@pytest.mark.asyncio
async def test_wrong_signature_token_rejected(client: AsyncClient, auth_headers: dict):
    """A token signed with a different SECRET_KEY must be rejected with 401."""
    valid_token = auth_headers["Authorization"].removeprefix("Bearer ")
    payload = jwt.decode(
        valid_token,
        settings.SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        options={"verify_exp": False},
    )
    # Re-encode with a foreign secret — signature will not validate.
    forged_token = jwt.encode(
        payload, "a-completely-different-secret-key", algorithm=settings.JWT_ALGORITHM
    )

    response = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {forged_token}"}
    )
    assert response.status_code == 401
