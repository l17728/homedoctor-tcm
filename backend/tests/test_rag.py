"""Tests for the RAG system: chunker, embedding, vector store, index manager,
query router, search pipeline, and the HTTP router.

Covers (task spec):
- chunker: splits text correctly, estimates tokens, hierarchy detection
- query_router: all 4 intents classified correctly
- bm25_search: returns relevant results
- rrf_fusion: correctly merges two ranked lists
- semantic_search: graceful None if model unavailable
- rerank: graceful skip if model unavailable
- full search pipeline: query → results
- index_manager: build for entity creates chunks
- HTTP endpoints: /api/rag/search, /api/rag/intent, /api/rag/index/*

Graceful degradation is enforced everywhere: the embedding model (BGE-M3) and
reranker require a multi-GB download which is NOT done in CI, so every
semantic/rerank path must succeed in BM25-only mode.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.chunker import (
    chunk_entity_content,
    chunk_text,
    estimate_tokens,
)
from app.database import DbAdapter
from app.embedding import EmbeddingModel, get_embedding_model
from app.index_manager import build_index_for_entity, get_index_status, rebuild_all
from app.query_router import (
    BROWSE,
    COMPLEX,
    CONCEPT,
    EXACT,
    classify_query,
    strategies_for_intent,
)
from app.search_pipeline import (
    bm25_search,
    rrf_fusion,
    rerank,
    reset_reranker_cache,
    search,
    semantic_search,
)
from app.vector_store import count_embeddings, store_embedding, vector_search


# ---------------------------------------------------------------------------
# Fixtures: insert knowledge_entities for RAG (seed_test_data only adds
# herbs/formulas, not knowledge_entities).
# ---------------------------------------------------------------------------

async def _seed_entities(db: DbAdapter) -> None:
    entities = [
        {
            "id": "ke-huangqi",
            "entity_type": "herb",
            "source_table": "herbs",
            "source_id": "herb-001",
            "title": "黄芪",
            "summary": "补气升阳，固表止汗，利水消肿。用于气虚乏力、食少便溏、表虚自汗。",
            "keywords": json.dumps(["补气", "固表", "气虚", "免疫力"], ensure_ascii=False),
            "tags": json.dumps(["补虚药"], ensure_ascii=False),
            "category": "补虚药",
            "content_preview": "黄芪是经典的补气中药，能增强免疫力。",
            "properties": json.dumps({"nature": "微温", "flavor": "甘"}, ensure_ascii=False),
        },
        {
            "id": "ke-danggui",
            "entity_type": "herb",
            "source_table": "herbs",
            "source_id": "herb-002",
            "title": "当归",
            "summary": "补血活血，调经止痛，润肠通便。用于血虚萎黄、月经不调、经闭痛经。",
            "keywords": json.dumps(["补血", "活血", "调经", "血虚"], ensure_ascii=False),
            "tags": json.dumps(["补虚药"], ensure_ascii=False),
            "category": "补虚药",
            "content_preview": "当归为补血要药，常用于妇科调经。",
            "properties": json.dumps({"nature": "温", "flavor": "甘,辛"}, ensure_ascii=False),
        },
        {
            "id": "ke-sijunzi",
            "entity_type": "formula",
            "source_table": "formulas",
            "source_id": "formula-001",
            "title": "四君子汤",
            "summary": "益气健脾。用于脾胃气虚证，面色萎白，语声低微，气短乏力，食少便溏。",
            "keywords": json.dumps(["益气", "健脾", "脾胃气虚"], ensure_ascii=False),
            "tags": json.dumps(["补益剂"], ensure_ascii=False),
            "category": "补益剂",
            "content_preview": "四君子汤由人参、白术、茯苓、甘草组成，是益气健脾的基础方。",
            "properties": json.dumps({}, ensure_ascii=False),
        },
    ]
    for e in entities:
        await db.execute(
            """INSERT OR REPLACE INTO knowledge_entities
                   (id, entity_type, source_table, source_id, title, summary,
                    keywords, tags, category, content_preview, properties,
                    status, view_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', 0)""",
            (e["id"], e["entity_type"], e["source_table"], e["source_id"],
             e["title"], e["summary"], e["keywords"], e["tags"], e["category"],
             e["content_preview"], e["properties"]),
        )


@pytest.fixture(autouse=True)
def _reset_ml_caches():
    """Reset embedding + reranker caches and block network model downloads.

    Forces the embedding model and reranker into "checked & unavailable" so no
    test ever triggers a multi-GB download. Tests that need mock embeddings or
    a mock reranker re-patch explicitly.
    """
    import app.search_pipeline as sp
    model = get_embedding_model()
    model.reset()
    model._available = False
    model._loaded = True
    sp._reranker = None
    sp._reranker_checked = True
    yield
    model = get_embedding_model()
    model.reset()
    model._available = False
    model._loaded = True
    sp._reranker = None
    sp._reranker_checked = True


# ---------------------------------------------------------------------------
# chunker
# ---------------------------------------------------------------------------

class TestChunker:
    def test_estimate_tokens_chinese(self):
        assert estimate_tokens("黄芪补气") == 2
        assert estimate_tokens("") == 0

    def test_chunk_short_text_returns_single_chunk(self):
        chunks = chunk_text("黄芪补气升阳。")
        assert len(chunks) == 1
        assert "黄芪" in chunks[0]["text"]
        assert chunks[0]["index"] == 0
        assert chunks[0]["token_count"] > 0

    def test_chunk_empty_text(self):
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_chunk_long_text_splits(self):
        text = "。" * 50 + "这是一个很长的段落，" * 200
        chunks = chunk_text(text, max_tokens=50, overlap=0)
        assert len(chunks) > 1
        for ch in chunks:
            assert ch["token_count"] > 0

    def test_chunk_detects_headers_hierarchy(self):
        text = "# 概述\n\n黄芪是补气药。\n\n# 功效\n\n补气升阳，固表止汗。"
        chunks = chunk_text(text, max_tokens=512, overlap=0)
        paths = [c["hierarchy_path"] for c in chunks]
        assert any("概述" in p for p in paths)
        assert any("功效" in p for p in paths)

    def test_chunk_entity_content_includes_title(self):
        chunks = chunk_entity_content(
            title="黄芪",
            summary="补气升阳",
            keywords=["补气", "固表"],
            content_preview="增强免疫力",
        )
        assert len(chunks) >= 1
        combined = " ".join(c["text"] for c in chunks)
        assert "黄芪" in combined
        assert "补气" in combined


# ---------------------------------------------------------------------------
# query_router
# ---------------------------------------------------------------------------

class TestQueryRouter:
    def test_browse_intent(self):
        assert classify_query("有哪些补气药") == BROWSE
        assert classify_query("中药分类") == BROWSE
        assert classify_query("列出所有方剂") == BROWSE

    def test_concept_intent(self):
        assert classify_query("怎么增强免疫力") == CONCEPT
        assert classify_query("为什么黄芪能补气") == CONCEPT
        assert classify_query("如何调理脾胃") == CONCEPT

    def test_exact_intent(self):
        assert classify_query("黄芪的功效") == EXACT
        assert classify_query("当归性味") == EXACT

    def test_complex_intent_default(self):
        assert classify_query("黄芪和当归") == COMPLEX
        assert classify_query("黄芪当归配伍") == COMPLEX
        assert classify_query("人参") == COMPLEX

    def test_empty_query(self):
        assert classify_query("") == COMPLEX

    def test_strategies_mapping(self):
        assert "bm25" in strategies_for_intent(BROWSE)
        assert "bm25" in strategies_for_intent(EXACT)
        assert "semantic" in strategies_for_intent(CONCEPT)
        assert "bm25" in strategies_for_intent(COMPLEX)
        assert "semantic" in strategies_for_intent(COMPLEX)


# ---------------------------------------------------------------------------
# embedding — graceful degradation
# ---------------------------------------------------------------------------

class TestEmbedding:
    def test_embed_returns_none_when_model_unavailable(self):
        model = EmbeddingModel("BAAI/nonexistent-model-xyz")
        # Force the load to fail fast by patching.
        with patch.dict("sys.modules", {"sentence_transformers": None}):
            result = model.embed(["test"])
        assert result is None

    def test_embed_one_returns_none_when_unavailable(self):
        model = EmbeddingModel("BAAI/nonexistent-model-xyz")
        with patch.dict("sys.modules", {"sentence_transformers": None}):
            result = model.embed_one("test")
        assert result is None

    def test_embed_empty_list(self):
        model = EmbeddingModel("BAAI/nonexistent-model-xyz")
        assert model.embed([]) == []

    def test_available_property_does_not_raise(self):
        model = EmbeddingModel("BAAI/nonexistent-model-xyz")
        with patch.dict("sys.modules", {"sentence_transformers": None}):
            assert model.available is False


# ---------------------------------------------------------------------------
# vector_store
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_vector_search_returns_empty_when_no_embeddings(db: DbAdapter):
    results = await vector_search(db, [0.1] * 1024, top_k=5)
    assert results == []


@pytest.mark.asyncio
async def test_store_and_search_embedding(db: DbAdapter):
    # Insert a chunk row first (FK-like expectation).
    await db.execute(
        """INSERT INTO knowledge_chunks (id, entity_id, chunk_index, chunk_text)
           VALUES ('kc-1', 'ke-huangqi', 0, '黄芪补气')"""
    )
    vec_a = [1.0] + [0.0] * 1023
    vec_b = [0.0, 1.0] + [0.0] * 1022
    await store_embedding(db, "kc-1", vec_a)
    await db.execute(
        """INSERT INTO knowledge_chunks (id, entity_id, chunk_index, chunk_text)
           VALUES ('kc-2', 'ke-danggui', 0, '当归补血')"""
    )
    await store_embedding(db, "kc-2", vec_b)
    assert await count_embeddings(db) == 2

    results = await vector_search(db, vec_a, top_k=2)
    assert len(results) == 2
    assert results[0]["chunk_id"] == "kc-1"
    assert results[0]["score"] > results[1]["score"]


@pytest.mark.asyncio
async def test_vector_search_handles_dimension_mismatch(db: DbAdapter):
    await db.execute(
        """INSERT INTO knowledge_chunks (id, entity_id, chunk_text)
           VALUES ('kc-x', 'ke-x', 'text')"""
    )
    await store_embedding(db, "kc-x", [0.1] * 512)
    # Query with different dim → mismatched embedding skipped, no crash.
    results = await vector_search(db, [0.1] * 1024, top_k=5)
    assert results == []


# ---------------------------------------------------------------------------
# index_manager
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_index_for_entity_creates_chunks(db: DbAdapter):
    await _seed_entities(db)
    res = await build_index_for_entity(db, "ke-huangqi")
    assert res["entity_id"] == "ke-huangqi"
    assert res["chunks"] >= 1
    rows = await db.query("SELECT * FROM knowledge_chunks WHERE entity_id = 'ke-huangqi'")
    assert len(rows) >= 1
    for r in rows:
        assert r["chunk_text"]
        assert r["token_count"] > 0


@pytest.mark.asyncio
async def test_build_index_missing_entity(db: DbAdapter):
    res = await build_index_for_entity(db, "ke-nonexistent")
    assert res["chunks"] == 0
    assert res["reason"] == "not_found"


@pytest.mark.asyncio
async def test_build_index_is_idempotent(db: DbAdapter):
    await _seed_entities(db)
    await build_index_for_entity(db, "ke-huangqi")
    first = await db.query("SELECT COUNT(*) AS c FROM knowledge_chunks WHERE entity_id = 'ke-huangqi'")
    await build_index_for_entity(db, "ke-huangqi")
    second = await db.query("SELECT COUNT(*) AS c FROM knowledge_chunks WHERE entity_id = 'ke-huangqi'")
    assert second[0]["c"] == first[0]["c"]


@pytest.mark.asyncio
async def test_rebuild_all(db: DbAdapter):
    await _seed_entities(db)
    res = await rebuild_all(db)
    assert res["entities"] == 3
    assert res["chunks"] >= 3
    assert res["errors"] == 0


@pytest.mark.asyncio
async def test_get_index_status(db: DbAdapter):
    await _seed_entities(db)
    await rebuild_all(db)
    status = await get_index_status(db)
    assert status["total_entities"] == 3
    assert status["total_chunks"] >= 3
    assert status["entities_indexed"] == 3
    assert 0.0 <= status["coverage"] <= 1.0


# ---------------------------------------------------------------------------
# search_pipeline
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bm25_search_returns_relevant(db: DbAdapter):
    await _seed_entities(db)
    results = await bm25_search(db, "黄芪", top_k=10)
    assert len(results) >= 1
    titles = [r["title"] for r in results]
    assert "黄芪" in titles
    top = results[0]
    assert top["bm25_rank"] == 0
    assert top["bm25_score"] > 0


@pytest.mark.asyncio
async def test_bm25_search_empty_query(db: DbAdapter):
    results = await bm25_search(db, "", top_k=10)
    assert results == []


@pytest.mark.asyncio
async def test_bm25_search_no_match(db: DbAdapter):
    await _seed_entities(db)
    results = await bm25_search(db, "不存在的稀有名词", top_k=10)
    assert results == []


def test_rrf_fusion_merges_two_lists():
    list_a = [
        {"entity_id": "A", "title": "A", "bm25_rank": 0},
        {"entity_id": "B", "title": "B", "bm25_rank": 1},
    ]
    list_b = [
        {"entity_id": "B", "title": "B", "semantic_rank": 0},
        {"entity_id": "C", "title": "C", "semantic_rank": 1},
    ]
    fused = rrf_fusion(list_a, list_b, k=60)
    ids = [f["entity_id"] for f in fused]
    assert set(ids) == {"A", "B", "C"}
    # B appears in both lists (rank 1 and rank 0) → highest RRF score.
    assert fused[0]["entity_id"] == "B"
    assert fused[0]["rrf_score"] > fused[1]["rrf_score"]


def test_rrf_fusion_empty():
    assert rrf_fusion() == []
    assert rrf_fusion([]) == []


@pytest.mark.asyncio
async def test_semantic_search_graceful_none_when_model_unavailable(db: DbAdapter):
    with patch.object(EmbeddingModel, "available", new_callable=lambda: property(lambda self: False)):
        result = await semantic_search(db, "怎么补气", top_k=5)
    assert result is None


@pytest.mark.asyncio
async def test_rerank_graceful_without_model():
    # Fixture marks reranker as checked & unavailable → rerank is a graceful no-op.
    candidates = [{"entity_id": "A", "title": "A"}, {"entity_id": "B", "title": "B"}]
    result = await rerank("query", candidates, top_k=5)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_rerank_empty_candidates():
    assert await rerank("q", [], top_k=5) == []


@pytest.mark.asyncio
async def test_full_search_bm25_fallback(db: DbAdapter):
    """Full pipeline works in BM25-only mode (model unavailable)."""
    await _seed_entities(db)
    # Force embedding unavailable → semantic degrades, bm25 runs.
    with patch.object(EmbeddingModel, "available", new_callable=lambda: property(lambda self: False)):
        result = await search(db, "黄芪的功效", top_k=5, enable_rerank=False)
    assert result["query"] == "黄芪的功效"
    assert result["intent"] == EXACT
    assert "bm25" in result["strategies"]
    assert result["total"] >= 1
    assert result["results"][0]["entity_id"] == "ke-huangqi"


@pytest.mark.asyncio
async def test_full_search_concept_intent_degrades(db: DbAdapter):
    """CONCEPT intent (semantic-only) degrades to BM25 when model unavailable."""
    await _seed_entities(db)
    with patch.object(EmbeddingModel, "available", new_callable=lambda: property(lambda self: False)):
        result = await search(db, "怎么增强免疫力", top_k=5, enable_rerank=False)
    assert result["intent"] == CONCEPT
    assert result["degraded"] is True
    assert "bm25" in result["strategies"]


@pytest.mark.asyncio
async def test_full_search_complex_intent(db: DbAdapter):
    await _seed_entities(db)
    with patch.object(EmbeddingModel, "available", new_callable=lambda: property(lambda self: False)):
        result = await search(db, "黄芪和当归", top_k=5, enable_rerank=False)
    assert result["intent"] == COMPLEX
    assert result["total"] >= 1


@pytest.mark.asyncio
async def test_full_search_with_mock_embeddings(db: DbAdapter):
    """Full pipeline with a mocked embedding model produces semantic results."""
    await _seed_entities(db)
    await rebuild_all(db)

    fake_vec = [0.1] * 1024
    fake_model = type("Fake", (), {"embed": lambda self, texts: [fake_vec for _ in texts]})()
    with patch.object(get_embedding_model().__class__, "available", new_callable=lambda: property(lambda self: True)), \
         patch.object(get_embedding_model().__class__, "embed", new_callable=lambda: lambda self, texts: [fake_vec for _ in texts]), \
         patch.object(get_embedding_model().__class__, "embed_one", new_callable=lambda: lambda self, text: fake_vec):
        result = await search(db, "黄芪", top_k=5, enable_rerank=False)
    assert result["query"] == "黄芪"
    assert result["total"] >= 1


# ---------------------------------------------------------------------------
# HTTP router (via the standard test client that uses main_mod.app)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_http_search_endpoint(client):
    """GET /api/rag/search returns results (registered in main.py)."""
    # Seed entities directly via the app's DB.
    import app.database as db_mod
    adb = db_mod.get_db()
    await _seed_entities(adb)

    resp = await client.get("/api/rag/search", params={"q": "黄芪", "rerank": "false"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "黄芪"
    assert data["total"] >= 1
    assert data["results"][0]["entity_id"] == "ke-huangqi"


@pytest.mark.asyncio
async def test_http_search_concept_endpoint(client):
    """GET /api/rag/search?q=怎么增强免疫力 returns results (BM25 fallback)."""
    import app.database as db_mod
    adb = db_mod.get_db()
    await _seed_entities(adb)

    resp = await client.get("/api/rag/search", params={"q": "怎么增强免疫力", "rerank": "false"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == CONCEPT
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_http_intent_endpoint(client):
    resp = await client.get("/api/rag/intent", params={"q": "有哪些补气药"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == BROWSE


@pytest.mark.asyncio
async def test_http_index_status_endpoint(client):
    import app.database as db_mod
    adb = db_mod.get_db()
    await _seed_entities(adb)

    resp = await client.get("/api/rag/index/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_entities"] == 3
    assert "coverage" in data


@pytest.mark.asyncio
async def test_http_index_rebuild_endpoint(client):
    import app.database as db_mod
    adb = db_mod.get_db()
    await _seed_entities(adb)

    resp = await client.post("/api/rag/index/rebuild")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["entities"] == 3
    assert data["chunks"] >= 3


@pytest.mark.asyncio
async def test_http_search_validation_error(client):
    """Missing q param → 422."""
    resp = await client.get("/api/rag/search")
    assert resp.status_code == 422
