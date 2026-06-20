"""Test fixtures: test client, test db, auth headers."""

from __future__ import annotations

import os

os.environ["HOMEDOCTOR_TESTING"] = "1"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.database import SqliteAdapter, init_db, seed_safety_rules, seed_test_data


@pytest_asyncio.fixture
async def db():
    """Create an in-memory database with schema and test data."""
    adapter = SqliteAdapter(":memory:")
    await adapter.connect()
    await init_db(adapter)
    await seed_safety_rules(adapter)
    await seed_test_data(adapter)
    yield adapter
    await adapter.close()


@pytest_asyncio.fixture
async def client(db: SqliteAdapter):
    """Create an async test client with the test database injected.

    The client is pre-authenticated with a test user so that the tightened
    AuthMiddleware (which rejects requests without a Bearer token) allows
    test requests through. Tests that explicitly need unauthenticated
    access should use a bare AsyncClient instead.
    """
    import app.database as db_mod
    import app.main as main_mod
    db_mod.set_db(db)

    transport = ASGITransport(app=main_mod.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/auth/register", json={
            "username": "_test_auto_user",
            "password": "_test_auto_pass123",
            "display_name": "测试",
            "consent_privacy": True,
            "consent_health_data": True,
        })
        if resp.status_code == 200:
            token = resp.json().get("access_token", "")
        else:
            login = await ac.post("/api/auth/login", json={
                "username": "_test_auto_user",
                "password": "_test_auto_pass123",
            })
            token = login.json().get("access_token", "")
        ac.headers["Authorization"] = f"Bearer {token}"
        yield ac


@pytest_asyncio.fixture
async def raw_client(db: SqliteAdapter):
    """Unauthenticated test client — for testing 401/403 behavior."""
    import app.database as db_mod
    import app.main as main_mod
    db_mod.set_db(db)
    transport = ASGITransport(app=main_mod.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient):
    """Register a test user and return auth headers."""
    response = await client.post("/api/auth/register", json={
        "username": "testuser",
        "password": "testpass123",
        "display_name": "测试用户",
        "consent_privacy": True,
        "consent_health_data": True,
    })
    data = response.json()
    token = data["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def second_user_headers(client: AsyncClient):
    """Register a second test user and return auth headers."""
    response = await client.post("/api/auth/register", json={
        "username": "testuser2",
        "password": "testpass456",
        "display_name": "第二用户",
        "consent_privacy": True,
        "consent_health_data": True,
    })
    data = response.json()
    token = data["access_token"]
    return {"Authorization": f"Bearer {token}"}
