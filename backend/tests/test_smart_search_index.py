"""Tests for smart search + index management — gap detection + deletion recommendations."""

import pytest
import pytest_asyncio
from app.database import SqliteAdapter, init_db, seed_safety_rules, seed_test_data


@pytest_asyncio.fixture
async def smart_db():
    adapter = SqliteAdapter(":memory:")
    await adapter.connect()
    await init_db(adapter)
    await seed_safety_rules(adapter)
    await seed_test_data(adapter)
    yield adapter
    await adapter.close()


class TestSmartSearch:
    @pytest.mark.asyncio
    async def test_internal_found(self, client):
        resp = await client.get("/api/smart-search?q=黄芪")
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] in ("internal", "external", "none")

    @pytest.mark.asyncio
    async def test_not_found_suggests_expand(self, client):
        resp = await client.get("/api/smart-search?q=zzznonexistent")
        assert resp.status_code == 200
        data = resp.json()
        if data["total"] == 0:
            assert data["source"] == "none"
            assert data["expandable"] is True
            assert "是否搜索互联网" in data.get("suggestion", "")

    @pytest.mark.asyncio
    async def test_expand_unauthorized(self, raw_client):
        resp = await raw_client.post("/api/smart-search/expand", json={"query": "test"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_import_unauthorized(self, raw_client):
        resp = await raw_client.post("/api/smart-search/import", json={"url": "https://test.com"})
        assert resp.status_code == 401


class TestIndexManagement:
    @pytest.mark.asyncio
    async def test_recommendations_empty(self, client):
        resp = await client.get("/api/admin/deletion-recommendations")
        assert resp.status_code == 200
        data = resp.json()
        assert "recommendations" in data

    @pytest.mark.asyncio
    async def test_recommendations_with_external(self, client, db):
        await db.execute(
            """INSERT INTO knowledge_chunks
               (id, entity_id, chunk_index, chunk_text, chunk_type, token_count,
                metadata, source_url, source_type, hit_count, created_at)
               VALUES ('rec-test-1', NULL, 0, '旧外部内容', 'external', 4,
                        '{}', 'https://old.com', 'external', 0, '2024-01-01 00:00:00')"""
        )
        resp = await client.get("/api/admin/deletion-recommendations?days_threshold=1")
        assert resp.status_code == 200
        recs = resp.json()["recommendations"]
        found = [r for r in recs if r["chunk_id"] == "rec-test-1"]
        assert len(found) == 1
        assert found[0]["priority"] > 0
        assert len(found[0]["reasons"]) >= 2

    @pytest.mark.asyncio
    async def test_exempt_and_list(self, client):
        resp = await client.post("/api/admin/deletion-exempt", json={
            "target_type": "chunk", "target_id": "test-chunk-1", "reason": "重要内容"
        })
        assert resp.status_code == 200
        resp2 = await client.get("/api/admin/deletion-exemptions")
        assert resp2.status_code == 200
        assert resp2.json()["total"] >= 1

    @pytest.mark.asyncio
    async def test_remove_exemption(self, client):
        await client.post("/api/admin/deletion-exempt", json={
            "target_type": "chunk", "target_id": "test-chunk-remove"
        })
        resp = await client.delete("/api/admin/deletion-exempt/test-chunk-remove")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_index_stats(self, client):
        resp = await client.get("/api/admin/index-stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_chunks" in data
        assert "external_chunks" in data
        assert "zero_hit_external" in data

    @pytest.mark.asyncio
    async def test_execute_deletion(self, client, db):
        await db.execute(
            """INSERT INTO knowledge_chunks
               (id, entity_id, chunk_index, chunk_text, chunk_type, token_count, metadata, source_type)
               VALUES ('del-test-1', NULL, 0, '删除测试', 'external', 4, '{}', 'external')"""
        )
        resp = await client.post("/api/admin/deletion-execute", json={"chunk_ids": ["del-test-1"]})
        assert resp.status_code == 200
        assert resp.json()["deleted"] >= 1

    @pytest.mark.asyncio
    async def test_exempted_not_in_recommendations(self, client, db):
        await db.execute(
            """INSERT INTO knowledge_chunks
               (id, entity_id, chunk_index, chunk_text, chunk_type, token_count,
                metadata, source_url, source_type, hit_count, created_at)
               VALUES ('exempt-rec-1', NULL, 0, '豁免测试', 'external', 4,
                        '{}', 'https://exempt.com', 'external', 0, '2024-01-01 00:00:00')"""
        )
        await client.post("/api/admin/deletion-exempt", json={
            "target_type": "chunk", "target_id": "exempt-rec-1"
        })
        resp = await client.get("/api/admin/deletion-recommendations?days_threshold=1")
        recs = resp.json()["recommendations"]
        assert not any(r["chunk_id"] == "exempt-rec-1" for r in recs)
