"""Tests for auth endpoints: register, login, me."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from jose import jwt

from app.config import settings
from app.auth import create_access_token
from fastapi import HTTPException


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
    assert data["user"]["role"] == "user"
    assert data["user"]["display_name"] == "新用户"
    assert data["user"]["family_id"] is not None


@pytest.mark.asyncio
async def test_admin_registration_requires_one_time_bootstrap_token(db, monkeypatch):
    import app.auth as auth_module

    monkeypatch.delenv("HOMEDOCTOR_TESTING", raising=False)
    monkeypatch.setattr(auth_module, "ADMIN_USERNAMES", {"admin", "root"})
    monkeypatch.setattr(settings, "ADMIN_BOOTSTRAP_TOKEN", "bootstrap-secret")

    with pytest.raises(HTTPException) as denied:
        await auth_module.register_user(db, "admin", "StrongPass123!")
    assert denied.value.status_code == 403

    result = await auth_module.register_user(
        db, "admin", "StrongPass123!", admin_bootstrap_token="bootstrap-secret"
    )
    assert result["role"] == "admin"
    payload = jwt.decode(
        result["access_token"], settings.SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
    assert payload["role"] == "admin"

    with pytest.raises(HTTPException) as second_admin:
        await auth_module.register_user(
            db, "root", "AnotherPass123!", admin_bootstrap_token="bootstrap-secret"
        )
    assert second_admin.value.status_code == 409


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
    assert data["user"]["role"] == "user"


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
    assert response.json()["detail"] == "用户名或密码错误"


@pytest.mark.asyncio
async def test_login_lockout_after_five_failures(client: AsyncClient, monkeypatch):
    import app.auth as auth_module

    auth_module._LOGIN_FAILURES_BY_KEY.clear()
    await client.post("/api/auth/register", json={
        "username": "lockoutuser", "password": "correct-password",
        "consent_privacy": True,
    })
    for _ in range(5):
        response = await client.post("/api/auth/login", json={
            "username": "lockoutuser", "password": "wrong-password",
        })
        assert response.status_code == 401
    blocked = await client.post("/api/auth/login", json={
        "username": "lockoutuser", "password": "correct-password",
    })
    assert blocked.status_code == 423
    assert "15分钟" in blocked.json()["detail"]

    monkeypatch.setattr(auth_module, "_monotonic", lambda: 1_000_000.0)
    recovered = await client.post("/api/auth/login", json={
        "username": "lockoutuser", "password": "correct-password",
    })
    assert recovered.status_code == 200
    auth_module._LOGIN_FAILURES_BY_KEY.clear()


@pytest.mark.asyncio
async def test_login_failure_budget_is_scoped_to_source_and_account(client: AsyncClient):
    await client.post("/api/auth/register", json={
        "username": "source-lockout", "password": "correct-password",
        "consent_privacy": True,
    })
    for _ in range(5):
        response = await client.post(
            "/api/auth/login", json={"username": "source-lockout", "password": "wrong"},
            headers={"X-Forwarded-For": "198.51.100.10"},
        )
        assert response.status_code == 401
    success = await client.post(
        "/api/auth/login", json={"username": "source-lockout", "password": "correct-password"},
        headers={"X-Forwarded-For": "198.51.100.11"},
    )
    assert success.status_code == 200


@pytest.mark.asyncio
async def test_logout_revokes_presented_token(client: AsyncClient):
    registered = await client.post("/api/auth/register", json={
        "username": "logoutuser", "password": "correct-password",
        "consent_privacy": True,
    })
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    assert (await client.get("/api/auth/me", headers=headers)).status_code == 200
    assert (await client.post("/api/auth/logout", headers=headers)).status_code == 204
    assert (await client.get("/api/auth/me", headers=headers)).status_code == 401


@pytest.mark.asyncio
async def test_request_reuses_middleware_auth_checks(client: AsyncClient, monkeypatch, db):
    """Middleware checks revocation and user once; dependency reuses request state."""
    import app.auth as auth_module
    import app.middleware.auth as middleware_module

    original = auth_module.is_access_token_revoked
    original_query_one = db.query_one
    calls = 0
    user_queries = 0

    async def counted(db, payload):
        nonlocal calls
        calls += 1
        return await original(db, payload)

    async def counted_query_one(sql, params=()):
        nonlocal user_queries
        if "FROM users WHERE id = ?" in sql:
            user_queries += 1
        return await original_query_one(sql, params)

    monkeypatch.setattr(auth_module, "is_access_token_revoked", counted)
    monkeypatch.setattr(middleware_module, "is_access_token_revoked", counted)
    monkeypatch.setattr(db, "query_one", counted_query_one)

    response = await client.get("/api/auth/me")

    assert response.status_code == 200
    assert calls == 1
    assert user_queries == 1


@pytest.mark.asyncio
async def test_auth_rejects_jwt_for_missing_user(client: AsyncClient):
    token = create_access_token({
        "sub": "deleted-account-id", "username": "deleted", "family_id": "old-family",
    })
    response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_rejects_token_after_account_family_changes(
    client: AsyncClient, auth_headers: dict, db
):
    """A stale family claim cannot keep access to the former tenant."""
    user = await db.query_one(
        "SELECT id, family_id FROM users WHERE username = 'testuser'"
    )
    assert user is not None
    old_family_id = user["family_id"]
    await db.execute(
        "UPDATE users SET family_id = ? WHERE id = ?",
        ("new-authoritative-family", user["id"]),
    )

    # This route relies on AuthMiddleware for authentication and tenant scope;
    # it does not call get_current_user itself.
    response = await client.get("/api/knowledge/categories", headers=auth_headers)

    assert response.status_code == 401
    assert await db.query_one(
        "SELECT id FROM users WHERE family_id = ?", (old_family_id,)
    ) is None

    herb = await db.query_one("SELECT id FROM herbs LIMIT 1")
    assert herb is not None
    # /api/herbs is middleware-public for read APIs, so the route dependency
    # itself must independently reject the stale family claim.
    dependency_response = await client.patch(
        f"/api/herbs/{herb['id']}/aliases",
        headers=auth_headers,
        json={"aliases": ["test-alias"], "source": "核验来源", "verified": True},
    )
    assert dependency_response.status_code == 401


@pytest.mark.asyncio
async def test_register_rejects_password_shorter_than_eight(client: AsyncClient):
    response = await client.post("/api/auth/register", json={
        "username": "shortpassword", "password": "1234567",
        "consent_privacy": True,
    })
    assert response.status_code == 422


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


# ---------------------------------------------------------------------------
# Register request validation — Pydantic model + birth_year 400 (spec §12.2)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_register_non_numeric_birth_year_400(client: AsyncClient):
    """birth_year 非数字 → 400 中文报错（而不是 500）。"""
    response = await client.post("/api/auth/register", json={
        "username": "birthyearbad",
        "password": "password123",
        "consent_privacy": True,
        "birth_year": "一九五八",
    })
    assert response.status_code == 400
    assert "出生年份" in response.json()["detail"]
    assert "数字" in response.json()["detail"]


@pytest.mark.asyncio
async def test_register_numeric_string_birth_year_ok(client: AsyncClient):
    """纯数字字符串 birth_year 应被接受（如 "1958"）。"""
    response = await client.post("/api/auth/register", json={
        "username": "birthyeardigit",
        "password": "password123",
        "consent_privacy": True,
        "birth_year": "1958",
    })
    assert response.status_code == 201
    token = response.json()["access_token"]
    consent = await client.get(
        "/api/auth/consent-status", headers={"Authorization": f"Bearer {token}"}
    )
    assert consent.status_code == 200
    assert consent.json()["birth_year"] == 1958


@pytest.mark.asyncio
async def test_register_minor_requires_guardian(client: AsyncClient):
    """未满 14 周岁 → 422 需监护人确认。"""
    from datetime import datetime, timezone
    minor_year = datetime.now(timezone.utc).year - 10
    response = await client.post("/api/auth/register", json={
        "username": "minoruser",
        "password": "password123",
        "consent_privacy": True,
        "birth_year": minor_year,
    })
    assert response.status_code == 422
    assert "监护人" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_missing_fields_422(client: AsyncClient):
    """login 缺少字段 → 422（Pydantic 校验）。"""
    response = await client.post("/api/auth/login", json={"username": "only-username"})
    assert response.status_code == 422
