"""Hybrid RAG search pipeline: BM25 + semantic + RRF fusion + optional rerank.

Orchestrates the four-stage search defined in the task spec:
  1. :func:`classify_query` picks the strategies (BM25 / semantic / both).
  2. Each strategy returns a ranked candidate list with entity metadata.
  3. :func:`rrf_fusion` merges multiple ranked lists via Reciprocal Rank Fusion.
  4. Optional :func:`rerank` re-scores the fused candidates with a
     cross-encoder; degrades gracefully to the fused order if unavailable.

Graceful degradation (AGENTS.md §F4): when the embedding model or reranker is
unavailable, the pipeline falls back to BM25-only and never raises.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.database import DbAdapter
from app.embedding import get_embedding_model
from app.query_router import COMPLEX, classify_query, strategies_for_intent
from app.vector_store import vector_search

logger = logging.getLogger(__name__)

RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"


# ---------------------------------------------------------------------------
# BM25-style lexical search on knowledge_entities
# ---------------------------------------------------------------------------

async def bm25_search(db: DbAdapter, query: str, top_k: int = 20) -> list[dict[str, Any]]:
    """IDF-weighted BM25-style lexical search over knowledge_entities.

    Upgraded from fixed-weight bigram matching to include IDF (Inverse
    Document Frequency): common terms (e.g. '中药') score lower, rare terms
    (e.g. '真气运行法') score higher. Formula: score = field_weight * IDF(term).
    IDF(term) = log(N / (1 + df(term))) where N=total docs, df=docs containing term.
    """
    import math

    if not query or not query.strip():
        return []

    q = query.strip()
    terms = _extract_terms(q)
    if not terms:
        return []

    cjk_terms = [t for t in terms if any(ord(c) > 0x2E00 for c in t)]
    prefilter_terms = cjk_terms[:8] if cjk_terms else terms[:3]

    like_conditions: list[str] = []
    like_params: list[str] = []
    for term in prefilter_terms:
        pat = f"%{term}%"
        like_conditions.append(
            "(title LIKE ? OR summary LIKE ? OR keywords LIKE ? OR tags LIKE ? OR content_preview LIKE ?)"
        )
        like_params.extend([pat] * 5)

    where_clause = " OR ".join(like_conditions) if like_conditions else "1=1"
    rows = await db.query(
        f"""SELECT id, entity_type, source_table, source_id, title, summary,
                  keywords, tags, category, content_preview, properties
             FROM knowledge_entities
            WHERE status = 'active' AND ({where_clause})""",
        tuple(like_params),
    )

    total_row = await db.query_one(
        "SELECT COUNT(*) AS c FROM knowledge_entities WHERE status = 'active'"
    )
    N = total_row["c"] if total_row else 0
    if N == 0:
        return []

    field_docs: dict[str, int] = {}
    for term in terms:
        df = sum(1 for r in rows if term in (r.get("title") or "") + (r.get("summary") or "")
                 + (r.get("keywords") or "") + (r.get("tags") or "") + (r.get("content_preview") or ""))
        field_docs[term] = max(df, 1)

    FIELD_WEIGHTS = {"title": 3.0, "summary": 2.0, "keywords": 1.0, "tags": 1.0, "preview": 0.5}

    scored: list[dict[str, Any]] = []
    for r in rows:
        title = r.get("title") or ""
        summary = r.get("summary") or ""
        keywords = r.get("keywords") or ""
        tags = r.get("tags") or ""
        preview = r.get("content_preview") or ""

        score = 0.0
        matched_terms: set[str] = set()
        for term in terms:
            idf = math.log(N / field_docs[term]) if field_docs[term] < N else 0.1
            if idf < 0.01:
                idf = 0.01

            if term in title:
                score += FIELD_WEIGHTS["title"] * idf
                matched_terms.add(term)
            if term in summary:
                score += FIELD_WEIGHTS["summary"] * idf
                matched_terms.add(term)
            if term in keywords:
                score += FIELD_WEIGHTS["keywords"] * idf
                matched_terms.add(term)
            if term in tags:
                score += FIELD_WEIGHTS["tags"] * idf
                matched_terms.add(term)
            if term in preview:
                score += FIELD_WEIGHTS["preview"] * idf
                matched_terms.add(term)

        if score <= 0:
            continue

        title_match = any(term in title for term in terms)
        if not title_match and score < 1.0:
            continue

        scored.append({
            "entity_id": r["id"],
            "entity_type": r.get("entity_type"),
            "source_table": r.get("source_table"),
            "source_id": r.get("source_id"),
            "title": title,
            "summary": summary,
            "category": r.get("category"),
            "bm25_score": score,
            "matched_terms": sorted(matched_terms),
            "source_type": "internal",
            "source_url": None,
        })

    scored.sort(key=lambda x: x["bm25_score"], reverse=True)
    scored = [s for s in scored if s["bm25_score"] > 0.001]

    ext_chunks = await db.query(
        """SELECT kc.id AS chunk_id, kc.entity_id, kc.chunk_text, kc.source_url,
                  ke.title, ke.entity_type, ke.summary, ke.category,
                  ke.source_table, ke.source_id
             FROM knowledge_chunks kc
             LEFT JOIN knowledge_entities ke ON ke.id = kc.entity_id
            WHERE kc.source_type = 'external'"""
    )
    for ec in ext_chunks:
        chunk_text = ec.get("chunk_text") or ""
        score = 0.0
        matched: set[str] = set()
        for term in terms:
            if term in chunk_text:
                score += 1.5
                matched.add(term)
        if score > 0:
            eid = ec.get("entity_id") or ec["chunk_id"]
            if not any(s["entity_id"] == eid for s in scored):
                scored.append({
                    "entity_id": eid,
                    "entity_type": ec.get("entity_type"),
                    "source_table": ec.get("source_table"),
                    "source_id": ec.get("source_id"),
                    "title": ec.get("title") or ec.get("source_url") or "外部内容",
                    "summary": ec.get("summary") or chunk_text[:80],
                    "category": ec.get("category"),
                    "bm25_score": score,
                    "matched_terms": sorted(matched),
                    "source_type": "external",
                    "source_url": ec.get("source_url"),
                })

    scored.sort(key=lambda x: x["bm25_score"], reverse=True)
    ranked = scored[:top_k]
    for i, item in enumerate(ranked):
        item["bm25_rank"] = i

    ext_eids = [item["entity_id"] for item in ranked
                if item.get("entity_id") and item.get("source_type") == "external"]
    if ext_eids:
        ext_placeholders = ",".join("?" * len(ext_eids))
        try:
            await db.execute(
                f"UPDATE knowledge_chunks SET hit_count = hit_count + 1, last_hit_at = datetime('now') "
                f"WHERE entity_id IN ({ext_placeholders}) AND source_type = 'external'",
                tuple(ext_eids),
            )
        except Exception as exc:
            logger.warning("hit_count batch update failed: %s", exc)

    return ranked


def _extract_terms(query: str) -> list[str]:
    """Extract search terms: the full query + all 2-char bigrams (Chinese-aware)."""
    q = query.strip()
    if not q:
        return []
    terms: list[str] = []
    seen: set[str] = set()
    if len(q) >= 2:
        if q not in seen:
            terms.append(q)
            seen.add(q)
    for i in range(len(q) - 1):
        bigram = q[i:i + 2]
        if bigram not in seen and _is_meaningful_bigram(bigram):
            terms.append(bigram)
            seen.add(bigram)
    return terms


def _is_meaningful_bigram(bigram: str) -> bool:
    """A bigram is meaningful for search if it contains CJK characters.

    ASCII bigrams (e.g. 'st', 'te', 'on') from English/URL queries produce
    false-positive matches with inflated IDF in a Chinese knowledge base.
    """
    return any(ord(c) > 0x2E00 for c in bigram)


# ---------------------------------------------------------------------------
# Semantic search
# ---------------------------------------------------------------------------

async def semantic_search(
    db: DbAdapter, query: str, top_k: int = 20
) -> list[dict[str, Any]] | None:
    """Embed the query and run vector search. Returns ``None`` if unavailable."""
    model = get_embedding_model()
    if not model.available:
        return None
    q_vec = model.embed_one(query)
    if q_vec is None:
        return None
    hits = await vector_search(db, q_vec, top_k=top_k)
    if not hits:
        return []

    entity_ids = [h["entity_id"] for h in hits if h.get("entity_id")]
    entity_map: dict[str, dict[str, Any]] = {}
    if entity_ids:
        placeholders = ",".join("?" * len(set(filter(None, entity_ids))))
        eids = list(set(filter(None, entity_ids)))
        rows = await db.query(
            f"""SELECT id, entity_type, source_table, source_id, title, summary,
                       category, properties
                  FROM knowledge_entities WHERE id IN ({placeholders})""",
            tuple(eids),
        )
        entity_map = {r["id"]: r for r in rows}

    results: list[dict[str, Any]] = []
    for rank, h in enumerate(hits):
        eid = h.get("entity_id")
        ent = entity_map.get(eid, {}) if eid else {}
        results.append({
            "entity_id": eid,
            "entity_type": ent.get("entity_type"),
            "source_table": ent.get("source_table"),
            "source_id": ent.get("source_id"),
            "title": ent.get("title", ""),
            "summary": ent.get("summary", ""),
            "category": ent.get("category"),
            "score": h.get("score", 0.0),
            "semantic_rank": rank,
            "chunk_text": h.get("chunk_text", ""),
            "source_type": h.get("source_type", "internal"),
            "source_url": h.get("source_url"),
        })
    return results


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------

def rrf_fusion(
    *ranked_lists: list[dict[str, Any]], k: int = 60
) -> list[dict[str, Any]]:
    """Merge multiple ranked lists by Reciprocal Rank Fusion.

    ``score = Σ 1/(k + rank)`` over all lists. Items are keyed on
    ``entity_id``. Each merged item keeps the best metadata from any list and
    records ``rrf_score`` + contributing ranks.
    """
    if not ranked_lists:
        return []

    fused: dict[str, dict[str, Any]] = {}
    for lst in ranked_lists:
        for rank, item in enumerate(lst):
            eid = item.get("entity_id")
            if not eid:
                continue
            contribution = 1.0 / (k + rank)
            if eid not in fused:
                merged_item = {key: val for key, val in item.items()
                               if key not in ("bm25_rank", "semantic_rank", "score", "bm25_score")}
                merged_item["rrf_score"] = contribution
                merged_item["ranks"] = {}
                fused[eid] = merged_item
            else:
                fused[eid]["rrf_score"] = fused[eid].get("rrf_score", 0.0) + contribution
            if "bm25_rank" in item:
                fused[eid]["ranks"]["bm25"] = item["bm25_rank"]
            if "semantic_rank" in item:
                fused[eid]["ranks"]["semantic"] = item["semantic_rank"]

    result = list(fused.values())
    result.sort(key=lambda x: x.get("rrf_score", 0.0), reverse=True)
    return result


# ---------------------------------------------------------------------------
# Optional reranker
# ---------------------------------------------------------------------------

_reranker: Any = None
_reranker_checked = False


def _get_reranker():
    """Lazy-load the cross-encoder reranker. Returns None if unavailable."""
    global _reranker, _reranker_checked
    if _reranker_checked:
        return _reranker
    _reranker_checked = True
    try:
        from sentence_transformers import CrossEncoder  # type: ignore[import-untyped]
        _reranker = CrossEncoder(RERANKER_MODEL)
        logger.info("reranker: %s loaded", RERANKER_MODEL)
    except Exception as exc:
        logger.info("reranker: %s unavailable (%s) — skipping rerank", RERANKER_MODEL, exc)
        _reranker = None
    return _reranker


def reset_reranker_cache() -> None:
    """Reset the reranker cache (tests)."""
    global _reranker, _reranker_checked
    _reranker = None
    _reranker_checked = False


async def rerank(
    query: str, candidates: list[dict[str, Any]], top_k: int = 10
) -> list[dict[str, Any]]:
    """Re-score ``candidates`` with a cross-encoder. Graceful no-op if unavailable."""
    if not candidates:
        return []
    model = _get_reranker()
    if model is None:
        return candidates[:top_k]
    try:
        pairs = []
        for c in candidates:
            text = c.get("summary") or c.get("title") or c.get("chunk_text") or ""
            pairs.append((query, text))
        scores = model.predict(pairs)
        scored = list(zip(candidates, [float(s) for s in scores]))
        scored.sort(key=lambda x: x[1], reverse=True)
        result = []
        for c, s in scored[:top_k]:
            item = dict(c)
            item["rerank_score"] = s
            result.append(item)
        return result
    except Exception as exc:
        logger.warning("rerank: failed (%s) — returning unfused order", exc)
        return candidates[:top_k]


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def search(
    db: DbAdapter,
    query: str,
    top_k: int = 10,
    enable_rerank: bool = True,
) -> dict[str, Any]:
    """Run the full hybrid search pipeline.

    Returns ``{intent, query, strategies, total, results, reranked, degraded}``.
    Degrades to BM25-only when the embedding model is unavailable.
    """
    intent = classify_query(query)
    strategies = strategies_for_intent(intent)
    ran: list[str] = []
    lists: list[list[dict[str, Any]]] = []
    degraded = False

    if "bm25" in strategies:
        bm25_res = await bm25_search(db, query, top_k=max(top_k * 2, 20))
        lists.append(bm25_res)
        ran.append("bm25")

    if "semantic" in strategies:
        sem_res = await semantic_search(db, query, top_k=max(top_k * 2, 20))
        if sem_res is None:
            degraded = True
            if not lists:  # semantic was the only strategy → fall back to bm25
                bm25_res = await bm25_search(db, query, top_k=max(top_k * 2, 20))
                lists.append(bm25_res)
                ran = ["bm25"]
        elif sem_res:
            lists.append(sem_res)
            ran.append("semantic")

    bm25_count = len(lists[0]) if (ran and ran[0] == "bm25") else 0

    if len(lists) > 1:
        fused = rrf_fusion(*lists)
    elif len(lists) == 1:
        fused = []
        for i, item in enumerate(lists[0]):
            new_item = dict(item)
            new_item["rrf_score"] = 1.0 / (60 + i)
            fused.append(new_item)
        fused.sort(key=lambda x: x.get("rrf_score", 0.0), reverse=True)
    else:
        fused = []

    if bm25_count == 0 and fused:
        fused = [
            item for item in fused
            if item.get("score", 0) >= 0.5
        ]

    reranked = False
    if enable_rerank and len(fused) > top_k:
        before = list(fused)
        fused = await rerank(query, before, top_k=top_k)
        if len(fused) == len(before) and fused and not fused[0].get("rerank_score"):
            reranked = False
        else:
            reranked = True
        if not reranked:
            fused = before[:top_k]
    else:
        fused = fused[:top_k]

    for i, item in enumerate(fused):
        item["final_rank"] = i

    return {
        "intent": intent,
        "query": query,
        "strategies": ran,
        "total": len(fused),
        "results": fused,
        "reranked": reranked,
        "degraded": degraded,
    }
