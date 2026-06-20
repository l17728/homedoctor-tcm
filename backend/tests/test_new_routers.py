"""Router tests for unified_knowledge, personal_knowledge, and rag_search endpoints."""

import pytest
import pytest_asyncio
from app.database import SqliteAdapter, init_db, seed_safety_rules, seed_test_data


@pytest_asyncio.fixture
async def seeded_client():
    """Client with knowledge_entities seeded for testing."""
    import app.database as db_mod
    import app.main as main_mod
    from httpx import ASGITransport, AsyncClient

    adapter = SqliteAdapter(":memory:")
    await adapter.connect()
    await init_db(adapter)
    await seed_safety_rules(adapter)
    await seed_test_data(adapter)
    await adapter.execute(
        """INSERT INTO knowledge_entities
           (id, entity_type, source_table, source_id, title, summary,
            keywords, tags, category, content_preview, properties, source_type, status, tenant_id)
           VALUES ('ke-test-herb-1', 'herb', 'test', 'th1', '黄芪',
                   '补气升阳', '[]', '[]', '补虚药', '气虚乏力',
                   '{"nature":"微温","flavor":"甘"}', 'system', 'active', NULL)"""
    )
    await adapter.execute(
        """INSERT INTO knowledge_entities
           (id, entity_type, source_table, source_id, title, summary,
            keywords, tags, category, content_preview, properties, source_type, status, tenant_id)
           VALUES ('ke-test-symptom-1', 'symptom', 'test', 'ts1', '气虚乏力',
                   '可由黄芪治疗', '[]', '[]', '气虚', '',
                   '{"treating_herbs":["黄芪"]}', 'system', 'active', NULL)"""
    )
    await adapter.execute(
        """INSERT INTO knowledge_entities
           (id, entity_type, source_table, source_id, title, summary,
            keywords, tags, category, content_preview, properties, source_type, status, tenant_id)
           VALUES ('ke-test-formula-1', 'formula', 'test', 'tf1', '四君子汤',
                   '益气健脾', '[]', '[]', '补益剂', '',
                   '{"composition":"人参,白术"}', 'system', 'active', NULL)"""
    )
    db_mod.set_db(adapter)

    transport = ASGITransport(app=main_mod.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Register user
        await ac.post("/api/auth/register", json={
            "username": "testuser", "password": "testpass123",
            "display_name": "测试", "consent_privacy": True, "consent_health_data": True,
        })
        login_resp = await ac.post("/api/auth/login", json={
            "username": "testuser", "password": "testpass123",
        })
        token = login_resp.json()["access_token"]
        ac.headers["Authorization"] = f"Bearer {token}"
        yield ac

    await adapter.close()


class TestUnifiedKnowledgeRoutes:

    @pytest.mark.asyncio
    async def test_list_herbs(self, seeded_client):
        resp = await seeded_client.get("/api/knowledge/herbs?page=1&page_size=5")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_list_herbs_search(self, seeded_client):
        resp = await seeded_client.get("/api/knowledge/herbs?q=黄芪")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert any("黄芪" in i["title"] for i in items)

    @pytest.mark.asyncio
    async def test_list_formulas(self, seeded_client):
        resp = await seeded_client.get("/api/knowledge/formulas")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    @pytest.mark.asyncio
    async def test_list_symptoms(self, seeded_client):
        resp = await seeded_client.get("/api/knowledge/symptoms?page=1&page_size=5")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_herb_detail(self, seeded_client):
        resp = await seeded_client.get("/api/knowledge/herbs/ke-test-herb-1")
        assert resp.status_code == 200
        assert resp.json()["title"] == "黄芪"

    @pytest.mark.asyncio
    async def test_get_herb_detail_404(self, seeded_client):
        resp = await seeded_client.get("/api/knowledge/herbs/nonexistent-id")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_formula_detail_404(self, seeded_client):
        resp = await seeded_client.get("/api/knowledge/formulas/nonexistent-id")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_unified_search(self, seeded_client):
        resp = await seeded_client.get("/api/knowledge/search?q=黄芪")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] > 0
        assert any(i["title"] == "黄芪" for i in data["items"])

    @pytest.mark.asyncio
    async def test_unified_search_empty(self, seeded_client):
        resp = await seeded_client.get("/api/knowledge/search?q=zzznonexistent")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    @pytest.mark.asyncio
    async def test_graph_404(self, seeded_client):
        resp = await seeded_client.get("/api/knowledge/graph/nonexistent?hops=2")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_graph_existing(self, seeded_client):
        resp = await seeded_client.get("/api/knowledge/graph/ke-test-herb-1?hops=2")
        assert resp.status_code == 200
        assert "entity" in resp.json()


class TestPersonalKnowledgeRoutes:

    @pytest.mark.asyncio
    async def test_log_symptom_success(self, seeded_client):
        resp = await seeded_client.post("/api/personal/symptoms", json={
            "symptom_name": "气虚乏力",
            "severity": "中度",
            "note": "工作疲劳",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "edge_id" in data
        assert data["symptom"] == "气虚乏力"

    @pytest.mark.asyncio
    async def test_log_symptom_not_found(self, seeded_client):
        resp = await seeded_client.post("/api/personal/symptoms", json={
            "symptom_name": "不存在的症状xyz",
        })
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_symptoms_empty(self, seeded_client):
        resp = await seeded_client.get("/api/personal/symptoms")
        assert resp.status_code == 200
        data = resp.json()
        assert "symptoms" in data
        assert data["total"] >= 0

    @pytest.mark.asyncio
    async def test_log_and_list_symptom(self, seeded_client):
        await seeded_client.post("/api/personal/symptoms", json={
            "symptom_name": "气虚乏力",
        })
        resp = await seeded_client.get("/api/personal/symptoms")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    @pytest.mark.asyncio
    async def test_create_edge_herb(self, seeded_client):
        resp = await seeded_client.post("/api/personal/edges", json={
            "target_title": "黄芪",
            "target_type": "herb",
            "relationship_type": "takes",
        })
        assert resp.status_code == 200
        assert resp.json()["target"] == "黄芪"

    @pytest.mark.asyncio
    async def test_list_edges(self, seeded_client):
        resp = await seeded_client.get("/api/personal/edges")
        assert resp.status_code == 200
        assert "edges" in resp.json()

    @pytest.mark.asyncio
    async def test_delete_edge(self, seeded_client):
        create = await seeded_client.post("/api/personal/edges", json={
            "target_title": "黄芪",
            "target_type": "herb",
            "relationship_type": "takes",
        })
        edge_id = create.json()["edge_id"]
        resp = await seeded_client.delete(f"/api/personal/edges/{edge_id}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_personal_graph(self, seeded_client):
        resp = await seeded_client.get("/api/personal/graph")
        assert resp.status_code == 200
        data = resp.json()
        assert "person_id" in data
        assert "groups" in data


class TestRagSearchRoutes:

    @pytest.mark.asyncio
    async def test_rag_search(self, seeded_client):
        resp = await seeded_client.get("/api/rag/search?q=黄芪&top_k=3")
        assert resp.status_code == 200
        data = resp.json()
        assert "intent" in data
        assert "strategies" in data
        assert "results" in data

    @pytest.mark.asyncio
    async def test_rag_search_short_query(self, seeded_client):
        resp = await seeded_client.get("/api/rag/search?q=x")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_rag_intent(self, seeded_client):
        resp = await seeded_client.get("/api/rag/intent?q=怎么补气")
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "CONCEPT"

    @pytest.mark.asyncio
    async def test_rag_index_status(self, seeded_client):
        resp = await seeded_client.get("/api/rag/index/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_entities" in data
        assert "coverage" in data
