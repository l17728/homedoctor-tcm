"""RAG index builder — chunk knowledge_entities → embed → store.

Builds and maintains the ``knowledge_chunks`` + ``chunk_embeddings`` tables
that power semantic search. Idempotent and incremental.

Design (AGENTS.md §1.3 递归收敛, §1.4 结构化是权威):
- ``knowledge_entities`` is the authoritative source — chunks are derived.
- ``build_index_for_entity`` wipes that entity's chunks/embeddings then
  recreates them (idempotent rebuild per entity).
- ``rebuild_all`` wipes everything and rebuilds for all active entities.
- Embedding is skipped gracefully when the model is unavailable (BM25-only).
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from app.chunker import chunk_entity_content, estimate_tokens
from app.database import DbAdapter
from app.embedding import get_embedding_model
from app.vector_store import store_embedding

logger = logging.getLogger(__name__)


def _chunk_id() -> str:
    return f"chunk-{uuid.uuid4()}"


async def _delete_entity_chunks(db: DbAdapter, entity_id: str) -> None:
    rows = await db.query(
        "SELECT id FROM knowledge_chunks WHERE entity_id = ?", (entity_id,)
    )
    for r in rows:
        await db.execute("DELETE FROM chunk_embeddings WHERE chunk_id = ?", (r["id"],))
    await db.execute("DELETE FROM knowledge_chunks WHERE entity_id = ?", (entity_id,))


async def build_index_for_entity(
    db: DbAdapter, entity_id: str, max_tokens: int = 512
) -> dict[str, Any]:
    """Chunk + embed a single knowledge_entity. Returns a status dict.

    Skips gracefully (returns ``{"chunks": 0, "embedded": 0, "reason": ...}``)
    if the entity is missing or the embedding model is unavailable.
    """
    entity = await db.query_one(
        "SELECT * FROM knowledge_entities WHERE id = ?", (entity_id,)
    )
    if not entity:
        return {"entity_id": entity_id, "chunks": 0, "embedded": 0, "reason": "not_found"}

    await _delete_entity_chunks(db, entity_id)

    keywords = _safe_json(entity.get("keywords"), [])
    properties = _safe_json(entity.get("properties"), {})
    chunk_dicts = chunk_entity_content(
        title=entity.get("title", ""),
        summary=entity.get("summary", ""),
        keywords=keywords,
        content_preview=entity.get("content_preview", ""),
        properties=properties,
        max_tokens=max_tokens,
    )

    if not chunk_dicts:
        return {"entity_id": entity_id, "chunks": 0, "embedded": 0, "reason": "no_content"}

    chunk_ids: list[str] = []
    chunk_texts: list[str] = []
    for cd in chunk_dicts:
        cid = _chunk_id()
        chunk_ids.append(cid)
        chunk_texts.append(cd["text"])
        await db.execute(
            """INSERT INTO knowledge_chunks
                   (id, entity_id, chunk_index, chunk_text, chunk_type,
                    hierarchy_path, hierarchy_level, token_count, metadata)
               VALUES (?, ?, ?, ?, 'content', ?, ?, ?, '{}')""",
            (
                cid, entity_id, cd["index"], cd["text"],
                cd.get("hierarchy_path", ""), cd.get("hierarchy_level", 0),
                cd.get("token_count", estimate_tokens(cd["text"])),
            ),
        )

    embedded = 0
    model = get_embedding_model()
    if model.available:
        vectors = model.embed(chunk_texts)
        if vectors:
            for cid, vec in zip(chunk_ids, vectors):
                await store_embedding(db, cid, vec)
            embedded = len(vectors)

    return {
        "entity_id": entity_id,
        "chunks": len(chunk_dicts),
        "embedded": embedded,
        "embedding_available": model.available,
    }


async def rebuild_all(db: DbAdapter, max_tokens: int = 512) -> dict[str, Any]:
    """Wipe all chunks/embeddings and rebuild for every active entity."""
    await db.execute("DELETE FROM chunk_embeddings")
    await db.execute("DELETE FROM knowledge_chunks")

    entities = await db.query(
        "SELECT id FROM knowledge_entities WHERE status = 'active'"
    )
    total_chunks = 0
    total_embedded = 0
    errors = 0
    for e in entities:
        try:
            res = await build_index_for_entity(db, e["id"], max_tokens=max_tokens)
            total_chunks += res.get("chunks", 0)
            total_embedded += res.get("embedded", 0)
        except Exception as exc:
            logger.warning("index_manager: build for %s failed: %s", e["id"], exc)
            errors += 1

    return {
        "entities": len(entities),
        "chunks": total_chunks,
        "embedded": total_embedded,
        "errors": errors,
    }


async def get_index_status(db: DbAdapter) -> dict[str, Any]:
    """Return coverage stats: entity/chunk/embedding counts + coverage ratio."""
    entity_count_row = await db.query_one(
        "SELECT COUNT(*) AS c FROM knowledge_entities WHERE status = 'active'"
    )
    chunk_count_row = await db.query_one("SELECT COUNT(*) AS c FROM knowledge_chunks")
    emb_count_row = await db.query_one("SELECT COUNT(*) AS c FROM chunk_embeddings")
    covered_row = await db.query_one(
        "SELECT COUNT(DISTINCT entity_id) AS c FROM knowledge_chunks WHERE entity_id IS NOT NULL"
    )

    total_entities = entity_count_row["c"] if entity_count_row else 0
    chunks = chunk_count_row["c"] if chunk_count_row else 0
    embeddings = emb_count_row["c"] if emb_count_row else 0
    covered = covered_row["c"] if covered_row else 0

    return {
        "total_entities": total_entities,
        "total_chunks": chunks,
        "total_embeddings": embeddings,
        "entities_indexed": covered,
        "coverage": (covered / total_entities) if total_entities > 0 else 0.0,
        "embedding_available": get_embedding_model().available,
    }


def _safe_json(raw: Any, default: Any) -> Any:
    if isinstance(raw, (list, dict)):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return default
    return default
