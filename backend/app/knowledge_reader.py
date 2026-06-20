"""Unified knowledge reader — single read API over knowledge_entities.

All knowledge consumers (herbs list, formula detail, AI Q&A context, safety
check) call this module instead of querying the legacy herbs/formulas tables
directly. This is the "one data source, many views" principle (Phase 2).

Entity data lives in knowledge_entities:
  - Dedicated columns: title, summary, content_preview, category, keywords, tags
  - Flexible fields: properties JSON (nature, flavor, meridians, dosage, etc.)
  - tenant_id: NULL = global shared, non-NULL = family-private

Functions mirror the existing router shapes so routers can delegate here with
minimal changes.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.database import DbAdapter

logger = logging.getLogger(__name__)

_HERB_FIELDS = [
    "aliases", "nature", "flavor", "meridians", "efficacy", "indications",
    "contraindications", "dosage_min_g", "dosage_max_g", "toxicity",
    "category", "processing_method", "origin", "source_ref",
]
_FORMULA_FIELDS = [
    "source", "category", "composition", "efficacy", "indications",
    "modifications", "modifications_structured", "derived_from_id",
]


async def enrich_from_legacy_tables(db: DbAdapter) -> dict[str, int]:
    """Sync herbs/formulas full data into knowledge_entities.properties.

    Called at startup to ensure knowledge_entities has complete data even
    after seed scripts re-create basic entities on container restart.
    Returns ``{"herbs": N, "formulas": M}``.
    """
    herbs_synced = await _enrich_herbs(db)
    formulas_synced = await _enrich_formulas(db)
    logger.info(
        "knowledge_reader: enriched %d herbs + %d formulas from legacy tables",
        herbs_synced, formulas_synced,
    )
    return {"herbs": herbs_synced, "formulas": formulas_synced}


async def _enrich_herbs(db: DbAdapter) -> int:
    rows = await db.query(
        "SELECT ke.id AS eid, ke.properties AS ep, h.* FROM knowledge_entities ke "
        "JOIN herbs h ON h.id = ke.source_id "
        "WHERE ke.source_table = 'herbs' AND ke.entity_type = 'herb'"
    )
    for row in rows:
        props = _parse_json(row.get("ep"), {})
        for col in _HERB_FIELDS:
            val = row.get(col)
            if val is not None and val != "":
                if isinstance(val, float) and val.is_integer():
                    val = int(val)
                props[col] = val
        legacy = _parse_json(row.get("properties"), {})
        for k, v in legacy.items():
            if k not in props:
                props[k] = v
        await db.execute(
            "UPDATE knowledge_entities SET properties = ?, summary = ?, "
            "content_preview = ?, category = ?, updated_at = datetime('now') WHERE id = ?",
            (
                json.dumps(props, ensure_ascii=False),
                row.get("efficacy") or "",
                row.get("indications") or "",
                row.get("category") or "",
                row["eid"],
            ),
        )
    return len(rows)


async def _enrich_formulas(db: DbAdapter) -> int:
    rows = await db.query(
        "SELECT ke.id AS eid, ke.properties AS ep, f.* FROM knowledge_entities ke "
        "JOIN formulas f ON f.id = ke.source_id "
        "WHERE ke.source_table = 'formulas' AND ke.entity_type = 'formula'"
    )
    for row in rows:
        props = _parse_json(row.get("ep"), {})
        for col in _FORMULA_FIELDS:
            val = row.get(col)
            if val is not None and val != "":
                props[col] = val
        legacy = _parse_json(row.get("properties"), {})
        for k, v in legacy.items():
            if k not in props:
                props[k] = v
        await db.execute(
            "UPDATE knowledge_entities SET properties = ?, summary = ?, "
            "content_preview = ?, category = ?, updated_at = datetime('now') WHERE id = ?",
            (
                json.dumps(props, ensure_ascii=False),
                row.get("efficacy") or "",
                row.get("indications") or "",
                row.get("category") or "",
                row["eid"],
            ),
        )
    return len(rows)


def _parse_json(raw: Any, default: Any) -> Any:
    if isinstance(raw, (list, dict)):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return default
    return default


async def list_entities(
    db: DbAdapter,
    entity_type: str,
    *,
    category: str | None = None,
    search: str | None = None,
    tenant_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """Paginated list of knowledge entities of a given type.

    Returns ``{"items": [...], "total": N, "page": P, "page_size": S}``.
    """
    conditions = ["entity_type = ?", "status = 'active'"]
    params: list[Any] = [entity_type]

    if tenant_id is not None:
        conditions.append("(tenant_id IS NULL OR tenant_id = ?)")
        params.append(tenant_id)

    if category:
        conditions.append("category = ?")
        params.append(category)

    if search:
        conditions.append("(title LIKE ? OR summary LIKE ? OR keywords LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like, like])

    where = " AND ".join(conditions)
    offset = (page - 1) * page_size

    count_row = await db.query_one(
        f"SELECT COUNT(*) AS c FROM knowledge_entities WHERE {where}", tuple(params)
    )
    total = count_row["c"] if count_row else 0

    rows = await db.query(
        f"""SELECT id, title, summary, content_preview, category, keywords, tags,
                  properties, view_count, source_table, source_id
             FROM knowledge_entities
            WHERE {where}
            ORDER BY view_count DESC, title ASC
            LIMIT ? OFFSET ?""",
        tuple(params + [page_size, offset]),
    )

    return {
        "items": [_format_entity(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_entity(db: DbAdapter, entity_id: str) -> dict[str, Any] | None:
    """Fetch a single entity with all properties."""
    rows = await db.query(
        """SELECT id, entity_type, title, summary, content_preview, category,
                  keywords, tags, properties, view_count, source_table, source_id,
                  tenant_id, created_at, updated_at
             FROM knowledge_entities WHERE id = ?""",
        (entity_id,),
    )
    if not rows:
        return None
    return _format_entity(rows[0], include_meta=True)


async def get_entity_with_relations(
    db: DbAdapter, entity_id: str
) -> dict[str, Any] | None:
    """Fetch entity + grouped relationships (for detail views)."""
    entity = await get_entity(db, entity_id)
    if not entity:
        return None

    rels = await db.query(
        """SELECT er.relationship_type, er.properties,
                  ke_target.id AS target_id,
                  ke_target.title AS target_title,
                  ke_target.entity_type AS target_type
             FROM entity_relationships er
             JOIN knowledge_entities ke_target ON ke_target.id = er.target_entity_id
            WHERE er.source_entity_id = ?
            UNION ALL
           SELECT er.relationship_type, er.properties,
                  ke_source.id AS target_id,
                  ke_source.title AS target_title,
                  ke_source.entity_type AS target_type
             FROM entity_relationships er
             JOIN knowledge_entities ke_source ON ke_source.id = er.source_entity_id
            WHERE er.target_entity_id = ?""",
        (entity_id, entity_id),
    )

    grouped: dict[str, list[dict[str, Any]]] = {}
    for r in rels:
        rel_type = r["relationship_type"]
        if rel_type not in grouped:
            grouped[rel_type] = []
        grouped[rel_type].append({
            "id": r["target_id"],
            "title": r["target_title"],
            "type": r["target_type"],
        })

    entity["relationships"] = grouped
    return entity


async def multi_hop_traverse(
    db: DbAdapter,
    start_entity_id: str,
    max_hops: int = 3,
    max_depth: int = 20,
) -> list[dict[str, Any]]:
    """BFS traversal from a start entity, returning paths up to max_hops deep.

    Each path is ``{"path": [entity_dict, ...], "edges": [rel_type, ...]}``.
    Used by AI Q&A to build context like:
      黄芪 →(主治)→ 气虚 →(组成方剂)→ 补中益气汤 →(组成)→ 人参
    """
    visited: set[str] = {start_entity_id}
    results: list[dict[str, Any]] = []

    start = await get_entity(db, start_entity_id)
    if not start:
        return results

    frontier: list[tuple[dict[str, Any], list[str], list[str]]] = [
        (start, [start_entity_id], [])
    ]

    for hop in range(max_hops):
        if not frontier:
            break
        next_frontier: list[tuple[dict[str, Any], list[str], list[str]]] = []
        for entity, path_ids, path_edges in frontier:
            rels = await db.query(
                """SELECT er.relationship_type, er.target_entity_id,
                          ke.id, ke.title, ke.entity_type, ke.summary,
                          ke.properties, ke.category
                     FROM entity_relationships er
                     JOIN knowledge_entities ke ON ke.id = er.target_entity_id
                    WHERE er.source_entity_id = ? AND ke.status = 'active'
                    LIMIT 10
                    UNION ALL
                   SELECT er.relationship_type, er.source_entity_id,
                          ke.id, ke.title, ke.entity_type, ke.summary,
                          ke.properties, ke.category
                     FROM entity_relationships er
                     JOIN knowledge_entities ke ON ke.id = er.source_entity_id
                    WHERE er.target_entity_id = ? AND ke.status = 'active'
                    LIMIT 10""",
                (entity["id"], entity["id"]),
            )
            for r in rels[:5]:
                tid = r["id"]
                if tid in visited or len(visited) >= max_depth:
                    continue
                visited.add(tid)
                target_entity = _format_entity(r)
                new_path = path_ids + [tid]
                new_edges = path_edges + [r["relationship_type"]]
                results.append({
                    "path": new_path,
                    "edges": new_edges,
                    "entities": [_format_entity({"id": pid, "title": "", "entity_type": ""}) for pid in new_path],
                })
                next_frontier.append((target_entity, new_path, new_edges))
        frontier = next_frontier

    return results


def _format_entity(row: dict[str, Any], include_meta: bool = False) -> dict[str, Any]:
    """Convert a raw DB row to a clean entity dict."""
    properties = _parse_json(row.get("properties"), {})
    keywords = _parse_json(row.get("keywords"), [])
    tags = _parse_json(row.get("tags"), [])

    result: dict[str, Any] = {
        "id": row.get("id", ""),
        "type": row.get("entity_type") or row.get("type") or "",
        "title": row.get("title", ""),
        "summary": row.get("summary") or "",
        "content_preview": row.get("content_preview") or "",
        "category": row.get("category") or "",
        "keywords": keywords if isinstance(keywords, list) else [],
        "tags": tags if isinstance(tags, list) else [],
        "properties": properties if isinstance(properties, dict) else {},
    }

    if include_meta:
        result["source_table"] = row.get("source_table", "")
        result["source_id"] = row.get("source_id", "")
        result["view_count"] = row.get("view_count", 0)
        result["tenant_id"] = row.get("tenant_id")
        result["created_at"] = row.get("created_at", "")
        result["updated_at"] = row.get("updated_at", "")

    return result
