"""Test fixtures: test client, test db, auth headers."""

from __future__ import annotations

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
    """Create an async test client with the test database injected."""
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
    })
    data = response.json()
    token = data["access_token"]
    return {"Authorization": f"Bearer {token}"}
