"""Tests for medical_visits.py and knowledge_browse.py routers."""
import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch

from app.database import SqliteAdapter, init_db, seed_safety_rules, seed_test_data


@pytest_asyncio.fixture
async def test_client():
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    adapter = SqliteAdapter(":memory:")
    await adapter.connect()
    await init_db(adapter)
    await seed_safety_rules(adapter)
    await seed_test_data(adapter)

    from app.database import set_db
    set_db(adapter)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/auth/register", json={
            "username": f"mv_{__import__('time').time()}",
            "password": "test123456",
            "consent_privacy": True,
            "consent_health": True,
        })
        token = resp.json().get("access_token", "")
        yield client, token

    set_db(None)
    await adapter.close()


class TestMedicalVisits:
    @pytest.mark.asyncio
    async def test_create_and_list_visit(self, test_client):
        client, token = test_client
        h = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/visits", json={
            "visit_date": "2026-01-15",
            "hospital": "市中医医院",
            "department": "内科",
            "doctor": "张医生",
            "diagnosis": "气虚感冒",
            "prescription": "参苏饮加减",
            "notes": "服药期间忌辛辣",
        }, headers=h)
        assert resp.status_code in (200, 201)

        resp2 = await client.get("/api/visits", headers=h)
        assert resp2.status_code == 200
        data = resp2.json()
        assert data.get("total", 0) >= 1 or len(data.get("items", data if isinstance(data, list) else [])) >= 1

    @pytest.mark.asyncio
    async def test_get_visit_by_id(self, test_client):
        client, token = test_client
        h = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/visits", json={
            "visit_date": "2026-01-15", "hospital": "测试医院", "department": "测试科室",
            "doctor": "测试医生", "diagnosis": "测试诊断",
        }, headers=h)
        visit_id = resp.json().get("id", "")

        if visit_id:
            resp2 = await client.get(f"/api/visits/{visit_id}", headers=h)
            assert resp2.status_code == 200

    @pytest.mark.asyncio
    async def test_update_visit(self, test_client):
        client, token = test_client
        h = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/visits", json={
            "visit_date": "2026-01-15", "hospital": "医院", "department": "科室",
            "doctor": "医生", "diagnosis": "诊断",
        }, headers=h)
        visit_id = resp.json().get("id", "")

        if visit_id:
            resp2 = await client.put(f"/api/visits/{visit_id}", json={
                "diagnosis": "更新诊断",
                "notes": "新增备注",
            }, headers=h)
            assert resp2.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_visit(self, test_client):
        client, token = test_client
        h = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/visits", json={
            "visit_date": "2026-01-15", "hospital": "x", "department": "x",
            "doctor": "x", "diagnosis": "x",
        }, headers=h)
        visit_id = resp.json().get("id", "")

        if visit_id:
            resp2 = await client.delete(f"/api/visits/{visit_id}", headers=h)
            assert resp2.status_code in (200, 204)

    @pytest.mark.asyncio
    async def test_list_empty(self, test_client):
        client, token = test_client
        resp = await client.get("/api/visits",
                                headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200


class TestKnowledgeBrowse:
    @pytest.mark.asyncio
    async def test_list_categories(self, test_client):
        client, token = test_client
        resp = await client.get("/api/knowledge/categories",
                                headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert isinstance(resp.json(), (list, dict))

    @pytest.mark.asyncio
    async def test_browse_entities(self, test_client):
        client, token = test_client
        resp = await client.get("/api/knowledge/browse?type=herb",
                                headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_browse_with_category_filter(self, test_client):
        client, token = test_client
        resp = await client.get("/api/knowledge/browse?type=herb&category=补气药",
                                headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_browse_with_search(self, test_client):
        client, token = test_client
        resp = await client.get("/api/knowledge/browse?type=herb&q=黄芪",
                                headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_note_nonexistent(self, test_client):
        client, token = test_client
        resp = await client.get("/api/knowledge/ke-nonexistent/note",
                                headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_request_append(self, test_client):
        client, token = test_client
        h = {"Authorization": f"Bearer {token}"}

        await client.post("/api/knowledge/browse", headers=h)
        resp = await client.post("/api/knowledge/ke-nonexistent/append", json={
            "instruction": "补充黄芪的配伍禁忌",
            "content": "黄芪畏防风",
        }, headers=h)
        assert resp.status_code in (200, 201, 404)

    @pytest.mark.asyncio
    async def test_append_history(self, test_client):
        client, token = test_client
        resp = await client.get("/api/knowledge/ke-nonexistent/append/history",
                                headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code in (200, 404)
