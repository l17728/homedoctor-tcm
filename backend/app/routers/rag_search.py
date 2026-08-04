"""RAG search router — hybrid retrieval API.

Endpoints
---------
- ``GET  /api/rag/search``         — hybrid search (BM25 + semantic + RRF + rerank)
- ``GET  /api/rag/intent``         — query intent classification
- ``POST /api/rag/index/rebuild``  — full index rebuild (chunk + embed all)
- ``GET  /api/rag/index/status``   — index coverage stats

Graceful degradation: when the embedding model is unavailable, search
degrades to BM25-only and reports ``degraded: true`` (AGENTS.md §F4).

Note: this router is registered in ``main.py`` alongside the other routers.
"""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.database import DbAdapter, get_db
from app.index_manager import get_index_status, rebuild_all
from app.query_router import classify_query, strategies_for_intent
from app.search_pipeline import search as run_search

router = APIRouter(prefix="/api/rag", tags=["rag"])


@router.get("/search")
async def rag_search(
    q: str = Query(..., min_length=1, description="搜索关键词或自然语言问题"),
    top_k: int = Query(10, ge=1, le=50),
    rerank: bool = Query(False, description="是否启用交叉编码器重排（默认关闭，首次加载~20s）"),
    db: DbAdapter = Depends(get_db),
) -> dict[str, Any]:
    """Hybrid RAG search: BM25 + semantic + RRF fusion + optional rerank."""
    result = await run_search(db, q, top_k=top_k, enable_rerank=rerank)
    return result


@router.get("/intent")
async def rag_intent(
    q: str = Query(..., min_length=1),
) -> dict[str, Any]:
    """Classify a query into a search intent and report planned strategies."""
    intent = classify_query(q)
    return {
        "query": q,
        "intent": intent,
        "strategies": strategies_for_intent(intent),
    }


@router.post("/index/rebuild")
async def rag_index_rebuild(
    db: DbAdapter = Depends(get_db),
) -> dict[str, Any]:
    """Rebuild the full RAG index (chunks + embeddings) for all active entities."""
    result = await rebuild_all(db)
    return {"status": "ok", **result}


@router.get("/index/status")
async def rag_index_status(
    db: DbAdapter = Depends(get_db),
) -> dict[str, Any]:
    """Return index coverage statistics."""
    return await get_index_status(db)
