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
    """Sync herbs/formulas/symptoms full data into knowledge_entities.

    Called at startup to ensure knowledge_entities has complete data even
    after seed scripts re-create basic entities on container restart.
    """
    herbs_synced = await _enrich_herbs(db)
    formulas_synced = await _enrich_formulas(db)
    symptoms_synced = await _enrich_symptoms(db)
    logger.info(
        "knowledge_reader: enriched %d herbs + %d formulas + %d symptoms",
        herbs_synced, formulas_synced, symptoms_synced,
    )
    return {
        "herbs": herbs_synced,
        "formulas": formulas_synced,
        "symptoms": symptoms_synced,
    }


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


async def _enrich_symptoms(db: DbAdapter) -> int:
    """Reverse-fill symptom entities from treating herbs via relationships.

    For each symptom, finds all herbs with 主治/适用于 edges pointing to it,
    then populates ``properties`` with treating_herbs, herb_categories, and
    treatment_count. Also sets a human-readable ``summary``.
    """
    rows = await db.query(
        """SELECT ke.id AS symptom_id, ke.title AS symptom_name,
                  ke.properties AS existing_props,
                  GROUP_CONCAT(h.name, '、') AS herb_names,
                  GROUP_CONCAT(h.category, '、') AS herb_cats,
                  COUNT(DISTINCT h.id) AS herb_count
             FROM knowledge_entities ke
             JOIN entity_relationships er
               ON er.target_entity_id = ke.id
              AND er.relationship_type IN ('主治', '适用于')
             JOIN knowledge_entities ke_src
               ON ke_src.id = er.source_entity_id
              AND ke_src.entity_type = 'herb'
             JOIN herbs h ON h.id = ke_src.source_id
            WHERE ke.entity_type = 'symptom'
            GROUP BY ke.id"""
    )
    for row in rows:
        props = _parse_json(row.get("existing_props"), {})
        herb_names = (row.get("herb_names") or "").split("、")
        herb_names = [n for n in herb_names if n]
        herb_cats_raw = (row.get("herb_cats") or "").split("、")
        herb_cats = sorted(set(c for c in herb_cats_raw if c))

        props["treating_herbs"] = herb_names[:20]
        props["herb_categories"] = herb_cats[:8]
        props["treatment_count"] = row.get("herb_count", 0)

        summary = ""
        if herb_names:
            top = herb_names[:5]
            summary = f"可由{'、'.join(top)}等{row['herb_count']}味药治疗"
        content_preview = f"相关中药分类：{'、'.join(herb_cats[:5])}" if herb_cats else ""

        await db.execute(
            "UPDATE knowledge_entities SET properties = ?, summary = ?, "
            "content_preview = ?, updated_at = datetime('now') WHERE id = ?",
            (
                json.dumps(props, ensure_ascii=False),
                summary,
                content_preview,
                row["symptom_id"],
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


async def build_graph_context(
    db: DbAdapter, user_message: str, max_entities: int = 3
) -> str | None:
    """Build knowledge graph context for AI Q&A from a user's message.

    1. Scans the message for entity mentions (herbs, formulas, symptoms).
    2. For each top match, runs 2-hop traversal to find related entities.
    3. Formats results as a concise context string for the LLM system prompt.

    Returns ``None`` if no entities are found.
    """
    from app.entity_filter import get_entity_index

    index = await get_entity_index(db)
    mentions = index.scan(user_message)
    if not mentions:
        return None

    herb_formula_mentions = [
        m for m in mentions
        if m.get("type") in ("herb", "formula", "therapy") and m.get("entity_id")
    ][:max_entities]
    if not herb_formula_mentions:
        return None

    lines: list[str] = ["**知识图谱参考**（基于实体关系遍历，请结合用户问题参考使用）："]

    for m in herb_formula_mentions:
        entity_id = m["entity_id"]
        entity = await get_entity(db, entity_id)
        if not entity:
            continue

        props = entity.get("properties", {})
        parts: list[str] = []
        if props.get("nature"):
            parts.append(f"性{props['nature']}")
        if props.get("flavor"):
            parts.append(f"味{props['flavor']}")
        if props.get("meridians"):
            parts.append(f"归{props['meridians']}经")
        if props.get("efficacy"):
            parts.append(props["efficacy"])
        if props.get("indications"):
            parts.append(f"主治：{props['indications']}")
        if props.get("contraindications"):
            parts.append(f"禁忌：{props['contraindications']}")
        if props.get("dosage_min_g") and props.get("dosage_max_g"):
            parts.append(f"用量{props['dosage_min_g']}-{props['dosage_max_g']}g")

        lines.append(f"\n■ {m['name']}（{m['type']}）")
        if parts:
            lines.append(f"  {'，'.join(parts)}")

        rels = await db.query(
            """SELECT er.relationship_type, ke.title, ke.entity_type, ke.summary
                 FROM entity_relationships er
                 JOIN knowledge_entities ke ON ke.id = er.target_entity_id
                WHERE er.source_entity_id = ? AND ke.status = 'active'
                UNION ALL
               SELECT er.relationship_type, ke.title, ke.entity_type, ke.summary
                 FROM entity_relationships er
                 JOIN knowledge_entities ke ON ke.id = er.source_entity_id
                WHERE er.target_entity_id = ? AND ke.status = 'active'
                LIMIT 8""",
            (entity_id, entity_id),
        )
        for r in rels[:6]:
            rel_label = r["relationship_type"]
            target_title = r["title"]
            target_summary = (r.get("summary") or "")[:40]
            lines.append(f"  →[{rel_label}]→ {target_title}" + (f"（{target_summary}…）" if target_summary else ""))

    if len(lines) <= 1:
        return None

    return "\n".join(lines)
