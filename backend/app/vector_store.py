"""Numpy cosine-similarity vector storage for RAG embeddings.

Embeddings are persisted as JSON strings in ``chunk_embeddings.embedding``.
Search loads all vectors into a numpy matrix and computes cosine similarity
against the query vector — O(N·D) which is fine for <10K chunks (AGENTS.md
spec note). Normalized embeddings make cosine == dot product.

Design (AGENTS.md §1.4 结构化是权威):
- ``knowledge_chunks`` is the authoritative chunk text source.
- ``chunk_embeddings`` is keyed by ``chunk_id`` (== ``knowledge_chunks.id``).
- Deletions of chunks cascade conceptually: stale embeddings are ignored
  during search (LEFT JOIN filters them out).
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from app.database import DbAdapter

logger = logging.getLogger(__name__)


async def store_embedding(
    db: DbAdapter, chunk_id: str, embedding: list[float], model_name: str = "bge-m3"
) -> None:
    """Upsert an embedding for a chunk (JSON string)."""
    dim = len(embedding)
    await db.execute(
        """INSERT INTO chunk_embeddings (chunk_id, embedding, model_name, dim, created_at)
           VALUES (?, ?, ?, ?, datetime('now'))
           ON CONFLICT(chunk_id) DO UPDATE SET
               embedding = excluded.embedding,
               dim = excluded.dim,
               model_name = excluded.model_name""",
        (chunk_id, json.dumps(embedding), model_name, dim),
    )


async def store_embeddings_batch(
    db: DbAdapter,
    items: list[tuple[str, list[float]]],
    model_name: str = "bge-m3",
) -> int:
    """Store many embeddings. ``items`` is a list of (chunk_id, vector)."""
    count = 0
    for chunk_id, embedding in items:
        await store_embedding(db, chunk_id, embedding, model_name)
        count += 1
    return count


async def delete_embedding(db: DbAdapter, chunk_id: str) -> None:
    await db.execute("DELETE FROM chunk_embeddings WHERE chunk_id = ?", (chunk_id,))


async def vector_search(
    db: DbAdapter, query_embedding: list[float], top_k: int = 20
) -> list[dict[str, Any]]:
    """Cosine-similarity search over all stored embeddings.

    Returns a list of ``{chunk_id, entity_id, score, chunk_text, ...}`` ranked
    by descending similarity. Returns ``[]`` if no embeddings are stored or
    numpy is unavailable.
    """
    try:
        import numpy as np
    except ImportError:
        logger.warning("vector_store: numpy not installed — vector search disabled")
        return []

    rows = await db.query(
        """SELECT ce.chunk_id, ce.embedding, kc.entity_id, kc.chunk_text,
                  kc.hierarchy_path, kc.chunk_index, kc.source_url, kc.source_type
             FROM chunk_embeddings ce
             LEFT JOIN knowledge_chunks kc ON kc.id = ce.chunk_id
          ORDER BY ce.chunk_id"""
    )
    if not rows:
        return []

    ids: list[str] = []
    matrix_rows: list[list[float]] = []
    meta: list[dict[str, Any]] = []
    for r in rows:
        try:
            vec = json.loads(r["embedding"])
        except (json.JSONDecodeError, TypeError):
            continue
        if not vec or len(vec) != len(query_embedding):
            continue
        ids.append(r["chunk_id"])
        matrix_rows.append(vec)
        meta.append({
            "chunk_id": r["chunk_id"],
            "entity_id": r.get("entity_id"),
            "chunk_text": r.get("chunk_text", ""),
            "hierarchy_path": r.get("hierarchy_path", ""),
            "chunk_index": r.get("chunk_index", 0),
            "source_url": r.get("source_url"),
            "source_type": r.get("source_type") or "internal",
        })

    if not matrix_rows:
        return []

    mat = np.array(matrix_rows, dtype=np.float32)
    query = np.array(query_embedding, dtype=np.float32)
    query_norm = query / (np.linalg.norm(query) + 1e-12)
    mat_norm = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-12)
    scores = mat_norm @ query_norm

    # Filter out noise: cosine similarity below 0.3 is essentially unrelated
    MIN_SIMILARITY = 0.3
    ranked_idx = [i for i in np.argsort(-scores) if scores[i] >= MIN_SIMILARITY][:top_k]
    results: list[dict[str, Any]] = []
    for rank, i in enumerate(ranked_idx):
        entry = dict(meta[i])
        entry["score"] = float(scores[i])
        entry["vector_rank"] = rank
        results.append(entry)
    return results


async def count_embeddings(db: DbAdapter) -> int:
    row = await db.query_one("SELECT COUNT(*) AS c FROM chunk_embeddings")
    return row["c"] if row else 0
