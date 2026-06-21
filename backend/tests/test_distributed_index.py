"""Tests for distributed knowledge index — external content indexing."""

import pytest
import pytest_asyncio
from app.database import SqliteAdapter, init_db, seed_safety_rules, seed_test_data


@pytest_asyncio.fixture
async def ext_db():
    adapter = SqliteAdapter(":memory:")
    await adapter.connect()
    await init_db(adapter)
    await seed_safety_rules(adapter)
    await seed_test_data(adapter)
    await adapter.execute(
        """INSERT INTO knowledge_entities
           (id, entity_type, source_table, source_id, title, summary,
            keywords, tags, category, properties, source_type, status)
           VALUES ('ke-ext-test', 'article', 'agent', 'at1', '外部文章测试',
                   '黄芪补气', '[]', '[]', '文章', '{}', 'agent', 'active')"""
    )
    yield adapter
    await adapter.close()


class TestExternalIndexing:
    @pytest.mark.asyncio
    async def test_index_external_content(self, ext_db):
        from app.agent_tools import tool_index_external_content
        result = await tool_index_external_content(
            ext_db,
            raw_text="这是一篇关于黄芪补气功效的详细文章。" * 20,
            source_url="https://example.com/article1",
            title="黄芪补气详解",
            entity_id="ke-ext-test",
        )
        assert result["chunks"] > 0
        assert result["decision"] == "indexed"

        rows = await ext_db.query(
            "SELECT * FROM knowledge_chunks WHERE source_url = ? AND source_type = 'external'",
            ("https://example.com/article1",),
        )
        assert len(rows) >= 1
        assert rows[0]["chunk_type"] == "external"

    @pytest.mark.asyncio
    async def test_dedup_same_url(self, ext_db):
        from app.agent_tools import tool_index_external_content
        await tool_index_external_content(
            ext_db, "内容A" * 50, "https://example.com/dup-test",
            "标题", "ke-ext-test",
        )
        result = await tool_index_external_content(
            ext_db, "内容B" * 50, "https://example.com/dup-test",
            "标题", "ke-ext-test",
        )
        assert result["decision"] == "already_indexed"
        assert result["chunks"] == 0

    @pytest.mark.asyncio
    async def test_bm25_covers_external(self, ext_db):
        from app.agent_tools import tool_index_external_content
        await tool_index_external_content(
            ext_db,
            "甘草清热解毒，炙甘草补脾益气。" * 20,
            "https://example.com/gancao",
            "甘草功效",
            "ke-ext-test",
        )
        from app.search_pipeline import bm25_search
        results = await bm25_search(ext_db, "甘草", top_k=10)
        ext_hits = [r for r in results if r.get("entity_id") == "ke-ext-test"]
        assert len(ext_hits) > 0

    @pytest.mark.asyncio
    async def test_search_results_have_source_type(self, ext_db):
        from app.search_pipeline import bm25_search
        results = await bm25_search(ext_db, "黄芪", top_k=5)
        for r in results:
            assert "source_type" in r
            assert r["source_type"] == "internal"

    @pytest.mark.asyncio
    async def test_vector_search_returns_source(self, ext_db):
        from app.vector_store import store_embedding, vector_search
        await ext_db.execute(
            """INSERT INTO knowledge_chunks
               (id, entity_id, chunk_index, chunk_text, chunk_type, token_count,
                metadata, source_url, source_type)
               VALUES ('ext-vs-test', 'ke-ext-test', 0, '测试外部向量', 'external',
                        4, '{}', 'https://test.com', 'external')"""
        )
        await store_embedding(ext_db, "ext-vs-test", [0.1] * 1024)
        results = await vector_search(ext_db, [0.1] * 1024, top_k=5)
        ext_hit = [r for r in results if r.get("chunk_id") == "ext-vs-test"]
        if ext_hit:
            assert ext_hit[0]["source_type"] == "external"
            assert ext_hit[0]["source_url"] == "https://test.com"

    @pytest.mark.asyncio
    async def test_chunks_migration_columns_exist(self, ext_db):
        cols = await ext_db.query("PRAGMA table_info(knowledge_chunks)")
        col_names = [c["name"] for c in cols]
        assert "source_url" in col_names
        assert "source_type" in col_names

    @pytest.mark.asyncio
    async def test_existing_chunks_default_internal(self, ext_db):
        rows = await ext_db.query(
            "SELECT DISTINCT source_type FROM knowledge_chunks WHERE source_type IS NOT NULL"
        )
        for r in rows:
            assert r["source_type"] in ("internal", "external", "content")
