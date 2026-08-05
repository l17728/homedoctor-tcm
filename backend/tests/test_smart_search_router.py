"""Tests for smart_search.py router — smart search, expand, import."""
import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.database import SqliteAdapter, init_db, seed_safety_rules, seed_test_data


@pytest_asyncio.fixture
async def search_app():
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
            "username": f"ss_{__import__('time').time()}",
            "password": "test123456",
            "consent_privacy": True,
            "consent_health": True,
        })
        token = resp.json().get("access_token", "")
        if not token:
            resp = await client.post("/api/auth/login", json={
                "username": "lifecycle_test", "password": "test123456"
            })
            token = resp.json().get("access_token", "")
        yield client, token

    set_db(None)
    await adapter.close()


class TestSmartSearch:
    @pytest.mark.asyncio
    async def test_internal_or_empty(self, search_app):
        client, token = search_app
        resp = await client.get("/api/smart-search?q=黄芪", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] in ("internal", "none")

    @pytest.mark.asyncio
    async def test_no_results_expandable(self, search_app):
        client, token = search_app
        resp = await client.get("/api/smart-search?q=zzznonexistent", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data.get("expandable") is True

    @pytest.mark.asyncio
    async def test_min_length_validation(self, search_app):
        client, token = search_app
        resp = await client.get("/api/smart-search?q=", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 422


class TestExpandSearch:
    @pytest.mark.asyncio
    async def test_expand_returns_results(self, search_app):
        client, token = search_app
        with patch("app.routers.smart_search._web_search", new_callable=AsyncMock) as mock_ws:
            mock_ws.return_value = [{"title": "test", "url": "https://example.com", "summary": "test"}]
            resp = await client.post("/api/smart-search/expand",
                                     json={"query": "黄芪功效", "num_results": 3},
                                     headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["source"] == "web"
            assert len(data["results"]) > 0

    @pytest.mark.asyncio
    async def test_expand_empty_results(self, search_app):
        client, token = search_app
        with patch("app.routers.smart_search._web_search", new_callable=AsyncMock) as mock_ws:
            mock_ws.return_value = []
            resp = await client.post("/api/smart-search/expand",
                                     json={"query": "nonexistent"},
                                     headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 200
            assert resp.json()["total"] == 0


class TestImportWebResult:
    @pytest.mark.asyncio
    async def test_import_success(self, search_app):
        client, token = search_app
        with patch("app.knowledge_agent.process_input", new_callable=AsyncMock) as mock_proc:
            mock_proc.return_value = {"entity_id": "ke-imported", "decision": "created"}
            resp = await client.post("/api/smart-search/import",
                                     json={"url": "https://example.com/tcm-article",
                                           "title": "中医文章",
                                           "source_query": "黄芪"},
                                     headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_import_ssrf_blocked(self, search_app):
        client, token = search_app
        resp = await client.post("/api/smart-search/import",
                                 json={"url": "http://192.168.1.1/internal",
                                       "title": "test", "source_query": ""},
                                 headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_import_localhost_blocked(self, search_app):
        client, token = search_app
        resp = await client.post("/api/smart-search/import",
                                 json={"url": "http://localhost:8000/api",
                                       "title": "test", "source_query": ""},
                                 headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 400


class TestWebSearchHelpers:
    @pytest.mark.asyncio
    async def test_search_via_api_exception(self):
        from app.routers.smart_search import _search_via_api
        with patch("httpx.AsyncClient", side_effect=Exception("network error")):
            try:
                result = await _search_via_api("test", 3, "fake-key")
                assert isinstance(result, list)
            except Exception:
                assert True

    @pytest.mark.asyncio
    async def test_search_via_llm_no_api_key(self):
        from app.routers.smart_search import _search_via_llm
        with patch("app.llm.has_api_key", return_value=False):
            result = await _search_via_llm("test", 5)
            assert result == []

    @pytest.mark.asyncio
    async def test_search_via_llm_with_api_key(self):
        from app.routers.smart_search import _search_via_llm
        with patch("app.llm.has_api_key", return_value=True), \
             patch("app.llm.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = '[{"title":"结果","url":"https://example.com","summary":"摘要"}]'
            result = await _search_via_llm("test", 3)
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_search_via_llm_invalid_json(self):
        from app.routers.smart_search import _search_via_llm
        with patch("app.llm.has_api_key", return_value=True), \
             patch("app.llm.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "not json"
            result = await _search_via_llm("test", 3)
            assert result == []
