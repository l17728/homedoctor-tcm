"""Personal knowledge layer — family-private edges to global entities.

Implements the tenant model: personal health data lives as EDGES from a
family-specific ``person`` entity to GLOBAL knowledge entities (symptoms,
herbs, formulas). No duplicate nodes are created.

Edge types:
  has_symptom       person → global symptom
  takes             person → global herb/medicine
  has_constitution  person → global constitution type (stored as property)
  prescribed        person → global formula

All edges carry ``tenant_id`` to scope them to a family.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from app.database import DbAdapter

logger = logging.getLogger(__name__)

PERSON_ENTITY_TYPE = "person"


async def ensure_person_entity(
    db: DbAdapter, user_id: str, tenant_id: str, name: str = ""
) -> str:
    """Get or create the person entity for a user within a tenant.

    Returns the entity_id. The entity is tenant-scoped (private to the family).
    """
    existing = await db.query(
        """SELECT id FROM knowledge_entities
            WHERE entity_type = ? AND source_id = ? AND tenant_id = ?""",
        (PERSON_ENTITY_TYPE, user_id, tenant_id),
    )
    if existing:
        return existing[0]["id"]

    entity_id = f"person-{tenant_id}-{user_id[:8]}"
    await db.execute(
        """INSERT INTO knowledge_entities
              (id, entity_type, source_table, source_id, title, summary,
               keywords, tags, category, properties, source_type, status, tenant_id)
           VALUES (?, ?, 'users', ?, ?, '用户健康档案', '[]', '[]', '个人',
                   '{}', 'user', 'active', ?)""",
        (entity_id, PERSON_ENTITY_TYPE, user_id, name or "家庭成员", tenant_id),
    )
    logger.info("personal_knowledge: created person entity %s for tenant %s", entity_id, tenant_id)
    return entity_id


async def add_personal_edge(
    db: DbAdapter,
    person_entity_id: str,
    target_entity_id: str,
    relationship_type: str,
    tenant_id: str,
    properties: dict[str, Any] | None = None,
) -> str:
    """Create a personal edge from person to a global entity. Idempotent."""
    existing = await db.query(
        """SELECT id FROM entity_relationships
            WHERE source_entity_id = ? AND target_entity_id = ?
              AND relationship_type = ? AND tenant_id = ?""",
        (person_entity_id, target_entity_id, relationship_type, tenant_id),
    )
    if existing:
        return existing[0]["id"]

    edge_id = f"edge-{uuid.uuid4()}"
    await db.execute(
        """INSERT INTO entity_relationships
              (id, source_entity_id, target_entity_id, relationship_type,
               properties, weight, tenant_id)
           VALUES (?, ?, ?, ?, ?, 1.0, ?)""",
        (
            edge_id, person_entity_id, target_entity_id, relationship_type,
            json.dumps(properties or {}, ensure_ascii=False), tenant_id,
        ),
    )
    return edge_id


async def remove_personal_edge(
    db: DbAdapter, edge_id: str, tenant_id: str
) -> bool:
    """Remove a personal edge. Returns True if deleted."""
    result = await db.execute(
        """DELETE FROM entity_relationships
            WHERE id = ? AND tenant_id = ?""",
        (edge_id, tenant_id),
    )
    return result > 0


async def list_personal_edges(
    db: DbAdapter, person_entity_id: str, tenant_id: str,
    relationship_type: str | None = None,
) -> list[dict[str, Any]]:
    """List personal edges for a person, with joined target entity data."""
    conditions = [
        "er.source_entity_id = ?",
        "er.tenant_id = ?",
    ]
    params: list[Any] = [person_entity_id, tenant_id]
    if relationship_type:
        conditions.append("er.relationship_type = ?")
        params.append(relationship_type)

    where = " AND ".join(conditions)
    rows = await db.query(
        f"""SELECT er.id, er.relationship_type, er.properties,
                  er.created_at,
                  ke.id AS target_id, ke.title AS target_title,
                  ke.entity_type AS target_type, ke.summary AS target_summary,
                  ke.properties AS target_properties, ke.category AS target_category
             FROM entity_relationships er
             JOIN knowledge_entities ke ON ke.id = er.target_entity_id
            WHERE {where}
            ORDER BY er.created_at DESC""",
        tuple(params),
    )
    result: list[dict[str, Any]] = []
    for r in rows:
        result.append({
            "edge_id": r["id"],
            "relationship_type": r["relationship_type"],
            "created_at": r.get("created_at", ""),
            "target": {
                "id": r.get("target_id", ""),
                "title": r.get("target_title", ""),
                "type": r.get("target_type", ""),
                "summary": r.get("target_summary", ""),
                "category": r.get("target_category", ""),
                "properties": _parse_json(r.get("target_properties"), {}),
            },
            "properties": _parse_json(r.get("properties"), {}),
        })
    return result


async def find_entity_by_title(
    db: DbAdapter, title: str, entity_type: str | None = None
) -> dict[str, Any] | None:
    """Find a global entity by exact title match."""
    conditions = ["title = ?", "status = 'active'", "tenant_id IS NULL"]
    params: list[Any] = [title]
    if entity_type:
        conditions.append("entity_type = ?")
        params.append(entity_type)
    rows = await db.query(
        f"""SELECT id, title, entity_type, summary, properties
             FROM knowledge_entities WHERE {' AND '.join(conditions)} LIMIT 1""",
        tuple(params),
    )
    return rows[0] if rows else None


def _parse_json(raw: Any, default: Any) -> Any:
    if isinstance(raw, (list, dict)):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return default
    return default
