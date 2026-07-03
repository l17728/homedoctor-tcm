"""Unit tests for RAG modules: vector_store, index_manager, query_router, search_pipeline, chunker."""

import pytest
import pytest_asyncio
import json
from app.database import SqliteAdapter, init_db
from app.chunker import chunk_text, chunk_entity_content, estimate_tokens
from app.query_router import classify_query, strategies_for_intent, BROWSE, EXACT, CONCEPT, COMPLEX
from app.vector_store import store_embedding, vector_search, count_embeddings, delete_embedding
from app.index_manager import build_index_for_entity, rebuild_all, get_index_status
from app.search_pipeline import bm25_search, rrf_fusion, search
from app.embedding import get_embedding_model


@pytest_asyncio.fixture
async def rag_db():
    adapter = SqliteAdapter(":memory:")
    await adapter.connect()
    await init_db(adapter)
    await adapter.execute(
        """INSERT INTO knowledge_entities
           (id, entity_type, source_table, source_id, title, summary,
            keywords, tags, category, content_preview, properties, source_type, status)
           VALUES ('ke-1', 'herb', 'seed', 's1', '黄芪',
                   '补气升阳，固表止汗', '["补气"]', '["温性"]', '补虚药',
                   '气虚乏力，食少便溏', '{"nature":"微温"}', 'system', 'active')"""
    )
    await adapter.execute(
        """INSERT INTO knowledge_entities
           (id, entity_type, source_table, source_id, title, summary,
            keywords, tags, category, content_preview, properties, source_type, status)
           VALUES ('ke-2', 'herb', 'seed', 's2', '人参',
                   '大补元气，复脉固脱', '["补气"]', '[]', '补虚药',
                   '气虚欲脱，肢冷脉微', '{"nature":"微温"}', 'system', 'active')"""
    )
    yield adapter
    await adapter.close()


# ========================= chunker =========================

class TestChunkText:
    def test_empty(self):
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_short_text_one_chunk(self):
        chunks = chunk_text("补气升阳")
        assert len(chunks) == 1
        assert chunks[0]["text"] == "补气升阳"

    def test_long_text_split(self):
        text = "段落一内容。" * 200
        chunks = chunk_text(text, max_tokens=50)
        assert len(chunks) > 1

    def test_header_detection(self):
        text = "# 黄芪\n\n补气升阳"
        chunks = chunk_text(text)
        assert any(c["hierarchy_path"] for c in chunks)

    def test_estimate_tokens(self):
        assert estimate_tokens("") == 0
        assert estimate_tokens("abcd") == 2
        assert estimate_tokens("中文测试") == 2


class TestChunkEntityContent:
    def test_full_entity(self):
        chunks = chunk_entity_content(
            title="黄芪",
            summary="补气升阳",
            keywords=["补气", "固表"],
            content_preview="气虚乏力",
            properties={"nature": "微温", "flavor": "甘"},
        )
        assert len(chunks) >= 1
        combined = " ".join(c["text"] for c in chunks)
        assert "黄芪" in combined
        assert "补气" in combined

    def test_title_only(self):
        chunks = chunk_entity_content(title="甘草")
        assert len(chunks) == 1
        assert "甘草" in chunks[0]["text"]

    def test_minimal_title(self):
        chunks = chunk_entity_content(title="甘草")
        assert len(chunks) >= 1
        assert "甘草" in chunks[0]["text"]


# ========================= query_router =========================

class TestClassifyQuery:
    def test_concept_keywords(self):
        assert classify_query("黄芪怎么用") == CONCEPT
        assert classify_query("为什么气虚") == CONCEPT
        assert classify_query("如何调理") == CONCEPT

    def test_browse_keywords(self):
        assert classify_query("有哪些补气药") == BROWSE
        assert classify_query("中药分类") == BROWSE

    def test_exact_property(self):
        assert classify_query("黄芪功效") == EXACT
        assert classify_query("当归性味") == EXACT

    def test_complex_relation(self):
        assert classify_query("黄芪和当归配伍") == COMPLEX
        assert classify_query("人参搭配白术") == COMPLEX

    def test_complex_default(self):
        assert classify_query("黄芪") == COMPLEX
        assert classify_query("") == COMPLEX

    def test_multi_entity(self):
        assert classify_query("黄芪、当归") == COMPLEX


class TestStrategiesForIntent:
    def test_browse_bm25_only(self):
        assert strategies_for_intent(BROWSE) == ["bm25"]

    def test_exact_bm25_only(self):
        assert strategies_for_intent(EXACT) == ["bm25"]

    def test_concept_semantic_only(self):
        assert strategies_for_intent(CONCEPT) == ["semantic"]

    def test_complex_both(self):
        assert strategies_for_intent(COMPLEX) == ["bm25", "semantic"]


# ========================= vector_store =========================

class TestVectorStore:
    @pytest.mark.asyncio
    async def test_store_and_count(self, rag_db):
        await store_embedding(rag_db, "chunk-1", [0.1, 0.2, 0.3])
        assert await count_embeddings(rag_db) == 1

    @pytest.mark.asyncio
    async def test_store_upsert(self, rag_db):
        await store_embedding(rag_db, "chunk-1", [0.1, 0.2])
        await store_embedding(rag_db, "chunk-1", [0.9, 0.8])
        assert await count_embeddings(rag_db) == 1

    @pytest.mark.asyncio
    async def test_delete(self, rag_db):
        await store_embedding(rag_db, "chunk-1", [0.1, 0.2])
        await delete_embedding(rag_db, "chunk-1")
        assert await count_embeddings(rag_db) == 0

    @pytest.mark.asyncio
    async def test_vector_search_empty(self, rag_db):
        results = await vector_search(rag_db, [0.1, 0.2], top_k=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_vector_search_returns_ranked(self, rag_db):
        await rag_db.execute(
            """INSERT INTO knowledge_chunks (id, entity_id, chunk_index, chunk_text, chunk_type, token_count, metadata)
               VALUES ('chunk-a', 'ke-1', 0, '黄芪补气', 'content', 4, '{}')"""
        )
        await rag_db.execute(
            """INSERT INTO knowledge_chunks (id, entity_id, chunk_index, chunk_text, chunk_type, token_count, metadata)
               VALUES ('chunk-b', 'ke-2', 0, '人参补气', 'content', 4, '{}')"""
        )
        await store_embedding(rag_db, "chunk-a", [1.0, 0.0, 0.0])
        await store_embedding(rag_db, "chunk-b", [0.0, 1.0, 0.0])
        results = await vector_search(rag_db, [0.8, 0.5, 0.3], top_k=2)
        assert len(results) == 2
        assert results[0]["score"] >= results[1]["score"]
        assert results[0]["chunk_id"] == "chunk-a"

    @pytest.mark.asyncio
    async def test_vector_search_dim_mismatch_skipped(self, rag_db):
        await store_embedding(rag_db, "chunk-x", [0.1, 0.2, 0.3])
        results = await vector_search(rag_db, [0.1, 0.2], top_k=5)
        assert results == []


# ========================= index_manager =========================

class TestIndexManager:
    @pytest.mark.asyncio
    async def test_build_index_for_entity(self, rag_db):
        result = await build_index_for_entity(rag_db, "ke-1")
        assert result["chunks"] >= 1
        assert "entity_id" in result

    @pytest.mark.asyncio
    async def test_build_nonexistent_entity(self, rag_db):
        result = await build_index_for_entity(rag_db, "nonexistent")
        assert result["chunks"] == 0

    @pytest.mark.asyncio
    async def test_rebuild_all(self, rag_db):
        result = await rebuild_all(rag_db)
        assert result["entities"] == 2
        assert result["chunks"] >= 2
        assert result["errors"] == 0

    @pytest.mark.asyncio
    async def test_get_index_status(self, rag_db):
        await rebuild_all(rag_db)
        status = await get_index_status(rag_db)
        assert status["total_entities"] == 2
        assert status["total_chunks"] >= 2
        assert 0 < status["coverage"] <= 1.0


# ========================= search_pipeline =========================

class TestBM25Search:
    @pytest.mark.asyncio
    async def test_search_finds_match(self, rag_db):
        results = await bm25_search(rag_db, "黄芪", top_k=5)
        assert len(results) >= 1
        assert any(r["title"] == "黄芪" for r in results)

    @pytest.mark.asyncio
    async def test_search_no_match(self, rag_db):
        results = await bm25_search(rag_db, "不存在的内容xyz", top_k=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_search_empty_query(self, rag_db):
        assert await bm25_search(rag_db, "", top_k=5) == []

    @pytest.mark.asyncio
    async def test_search_field_weighting(self, rag_db):
        title_results = await bm25_search(rag_db, "补气升阳", top_k=5)
        assert len(title_results) >= 1


class TestRRFFusion:
    def test_empty_lists(self):
        assert rrf_fusion() == []

    def test_single_list(self):
        lst = [{"entity_id": "a", "title": "A"}, {"entity_id": "b", "title": "B"}]
        result = rrf_fusion(lst)
        assert len(result) == 2
        assert result[0]["rrf_score"] > result[1]["rrf_score"]

    def test_merge_two_lists(self):
        l1 = [{"entity_id": "a"}, {"entity_id": "b"}]
        l2 = [{"entity_id": "b"}, {"entity_id": "c"}]
        result = rrf_fusion(l1, l2)
        ids = [r["entity_id"] for r in result]
        assert "a" in ids and "b" in ids and "c" in ids
        b_item = next(r for r in result if r["entity_id"] == "b")
        assert b_item["rrf_score"] > 0

    def test_item_in_both_lists_ranks_higher(self):
        l1 = [{"entity_id": "shared"}, {"entity_id": "only1"}]
        l2 = [{"entity_id": "shared"}, {"entity_id": "only2"}]
        result = rrf_fusion(l1, l2)
        assert result[0]["entity_id"] == "shared"


class TestSearchPipeline:
    @pytest.mark.asyncio
    async def test_search_returns_result(self, rag_db):
        result = await search(rag_db, "黄芪", top_k=3, enable_rerank=False)
        assert "intent" in result
        assert "strategies" in result
        assert "results" in result
        assert result["total"] >= 1

    @pytest.mark.asyncio
    async def test_search_empty_query(self, rag_db):
        result = await search(rag_db, "", top_k=3, enable_rerank=False)
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_search_concept_intent(self, rag_db):
        result = await search(rag_db, "怎么补气", top_k=3, enable_rerank=False)
        assert result["intent"] == CONCEPT

    @pytest.mark.asyncio
    async def test_search_browse_intent(self, rag_db):
        result = await search(rag_db, "有哪些中药", top_k=3, enable_rerank=False)
        assert result["intent"] == BROWSE
