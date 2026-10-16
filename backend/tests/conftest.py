"""Test fixtures: test client, test db, auth headers."""

from __future__ import annotations

import hashlib
import os
os.environ["HOMEDOCTOR_TESTING"] = "1"

from pathlib import Path

import pytest
import pytest_asyncio

from httpx import ASGITransport, AsyncClient

from app.database import SqliteAdapter, init_db, seed_safety_rules, seed_test_data


@pytest.fixture(autouse=True)
def reset_agent_configs():
    from app.tools.config import _AGENT_CONFIGS
    original = {k: dict(v) for k, v in _AGENT_CONFIGS.items()}
    yield
    _AGENT_CONFIGS.clear()
    _AGENT_CONFIGS.update(original)


# --- 生产数据目录防泄漏守卫 -------------------------------------------------
# 背景：曾有一次针对真实 settings 的手工验证把 backup_*.db.enc 与
# .restore_pending 写进 backend/data/，随后服务重启时 _apply_pending_restore
# 把真实库换成了测试快照。此守卫确保：任何测试会话结束后，真实 data/
# 目录不得出现新文件（文件名对比；同名文件的 WAL/-shm 更新不触发）。
_REAL_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _snapshot_real_data_dir() -> dict[str, tuple[int, str]]:
    if not _REAL_DATA_DIR.is_dir():
        return {}
    snapshot = {}
    for path in _REAL_DATA_DIR.rglob("*"):
        if not path.is_file():
            continue
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        snapshot[str(path.relative_to(_REAL_DATA_DIR))] = (path.stat().st_size, digest.hexdigest())
    return snapshot


@pytest.fixture(autouse=True, scope="session")
def guard_real_data_dir():
    configured_db = os.environ.get("HOMEDOCTOR_DATABASE_URL")
    if configured_db:
        configured_path = Path(configured_db).resolve()
        real_dir = _REAL_DATA_DIR.resolve()
        if configured_path == real_dir or real_dir in configured_path.parents:
            raise AssertionError(
                f"Tests must not use the production data directory: {configured_path}"
            )

    before_snapshot = _snapshot_real_data_dir()
    before = set()
    if _REAL_DATA_DIR.is_dir():
        before = {p.name for p in _REAL_DATA_DIR.iterdir() if p.is_file()}
    yield
    after_snapshot = _snapshot_real_data_dir()
    changed = sorted(
        name
        for name in set(before_snapshot) | set(after_snapshot)
        if before_snapshot.get(name) != after_snapshot.get(name)
    )
    assert not changed, (
        f"Tests changed files in the real data directory {_REAL_DATA_DIR}: {changed}. "
        "Tests must isolate SQLite files with tmp_path or :memory:."
    )
    if _REAL_DATA_DIR.is_dir():
        leaked = sorted({p.name for p in _REAL_DATA_DIR.iterdir() if p.is_file()} - before)
        assert not leaked, (
            f"测试泄漏写入真实数据目录 {_REAL_DATA_DIR}: {leaked} —— "
            "测试必须使用 tmp_path/:memory: 隔离（参考 file_client fixture）"
        )


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
            "username": "admin",
            "password": "_test_auto_pass123",
            "display_name": "测试",
            "consent_privacy": True,
            "consent_health_data": True,
        })
        if resp.status_code == 200:
            token = resp.json().get("access_token", "")
        else:
            login = await ac.post("/api/auth/login", json={
                "username": "admin",
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
    if "access_token" not in data:
        login = await client.post("/api/auth/login", json={
            "username": "testuser",
            "password": "testpass123",
        })
        data = login.json()
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
    if "access_token" not in data:
        login = await client.post("/api/auth/login", json={
            "username": "testuser2",
            "password": "testpass456",
        })
        data = login.json()
    token = data["access_token"]
    return {"Authorization": f"Bearer {token}"}
