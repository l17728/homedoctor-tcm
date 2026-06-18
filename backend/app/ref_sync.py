"""Edge derivation engine — port of /fighting refs.ts + anchors.ts.

When a node is created/updated, scan schema for ref-typed and anchor-typed
fields and create derived edges. This makes the knowledge graph DERIVED from
structured node properties (AGENTS.md §1.4 — 结构化是权威).

Edge types produced:
  - 分配 (ref edges):   source → referenced target node
  - 关联 (anchor edges): source → shared concept node

All herbs sharing 归经="脾,肺" are linked through the same concept nodes
(node_type="concept", label="脾"/"肺"), enabling graph traversal by property.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.database import DbAdapter
from app.schema.registry import FileSchemaRegistry

REF_EDGE_TYPE = "分配"
ANCHOR_EDGE_TYPE = "关联"


def _split_values(raw_value: Any) -> list[str]:
    """Normalize a property value into a list of non-empty trimmed strings.

    Handles: string (comma/Chinese-comma separated), list, single value.
    """
    if raw_value is None:
        return []
    if isinstance(raw_value, list):
        parts = raw_value
    else:
        s = str(raw_value).strip()
        if not s:
            return []
        parts = s.replace("，", ",").split(",")
    return [str(p).strip() for p in parts if str(p).strip()]


async def sync_ref_edges(
    db: DbAdapter,
    registry: FileSchemaRegistry,
    node: dict[str, Any],
    actor: str = "system",
) -> int:
    """Scan ref-typed schema fields and create 分配 edges to referenced nodes.

    Pattern from /fighting/refs.ts:
    1. Delete existing 分配 edges from this node (idempotent)
    2. For each ref-typed field: find or create target, create edge
    """
    schema = registry.get_schema(node["node_type"])
    if not schema:
        return 0

    await db.execute(
        "DELETE FROM graph_edges WHERE source_id = ? AND edge_type = ?",
        (node["id"], REF_EDGE_TYPE),
    )

    properties = node.get("properties")
    if isinstance(properties, str):
        properties = json.loads(properties or "{}")
    if not isinstance(properties, dict):
        properties = {}

    count = 0
    for field in registry.get_ref_fields(node["node_type"]):
        raw_value = properties.get(field.id, "")
        for v in _split_values(raw_value):
            target = await _find_or_create_by_name(db, field.ref_type, v)
            if target:
                await db.execute(
                    "INSERT INTO graph_edges (id, edge_type, source_id, target_id, properties, created_at) "
                    "VALUES (?, ?, ?, ?, ?, datetime('now'))",
                    (
                        str(uuid.uuid4()),
                        REF_EDGE_TYPE,
                        node["id"],
                        target["id"],
                        json.dumps(
                            {"field": field.id, "refType": field.ref_type},
                            ensure_ascii=False,
                        ),
                    ),
                )
                count += 1

    return count


async def sync_anchor_edges(
    db: DbAdapter,
    registry: FileSchemaRegistry,
    node: dict[str, Any],
    actor: str = "system",
) -> int:
    """Create concept-level cross-entity links via shared concept nodes.

    Pattern from /fighting/anchors.ts:
    For anchor-typed fields (e.g. meridians="脾,肺"):
    1. Find or create a concept node for each value
    2. Create edge: source → concept, type="关联"

    All herbs sharing the same anchor value link through the SAME concept node.
    """
    schema = registry.get_schema(node["node_type"])
    if not schema:
        return 0

    await db.execute(
        "DELETE FROM graph_edges WHERE source_id = ? AND edge_type = ?",
        (node["id"], ANCHOR_EDGE_TYPE),
    )

    properties = node.get("properties")
    if isinstance(properties, str):
        properties = json.loads(properties or "{}")
    if not isinstance(properties, dict):
        properties = {}

    count = 0
    for field in registry.get_anchor_fields(node["node_type"]):
        anchor_concept = field.anchor
        raw_value = properties.get(field.id, "")
        for v in _split_values(raw_value):
            concept = await _find_or_create_concept(db, anchor_concept, v)
            await db.execute(
                "INSERT INTO graph_edges (id, edge_type, source_id, target_id, properties, created_at) "
                "VALUES (?, ?, ?, ?, ?, datetime('now'))",
                (
                    str(uuid.uuid4()),
                    ANCHOR_EDGE_TYPE,
                    node["id"],
                    concept["id"],
                    json.dumps(
                        {"anchor": anchor_concept, "field": field.id},
                        ensure_ascii=False,
                    ),
                ),
            )
            count += 1

    return count


async def _find_or_create_by_name(
    db: DbAdapter, node_type: str, name: str
) -> dict[str, Any] | None:
    """Find a node by type + label (or name property), or create if not found."""
    row = await db.query_one(
        "SELECT * FROM graph_nodes WHERE node_type = ? AND label = ?",
        (node_type, name),
    )
    if row:
        return row

    row = await db.query_one(
        "SELECT * FROM graph_nodes WHERE node_type = ? "
        "AND json_extract(properties, '$.name') = ?",
        (node_type, name),
    )
    if row:
        return row

    node_id = str(uuid.uuid4())
    props = json.dumps({"name": name}, ensure_ascii=False)
    await db.execute(
        "INSERT INTO graph_nodes (id, node_type, label, properties, search_text, created_at) "
        "VALUES (?, ?, ?, ?, ?, datetime('now'))",
        (node_id, node_type, name, props, name),
    )
    return {"id": node_id, "node_type": node_type, "label": name, "properties": {"name": name}}


async def _find_or_create_concept(
    db: DbAdapter, concept_type: str, value: str
) -> dict[str, Any]:
    """Find or create a concept node for anchor linking.

    Concept nodes have node_type='concept', label=value, and properties
    containing the concept type (e.g. {"概念类型": "经络", "值": "脾"}).
    """
    row = await db.query_one(
        "SELECT * FROM graph_nodes WHERE node_type = 'concept' AND label = ? "
        "AND json_extract(properties, '$.概念类型') = ?",
        (value, concept_type),
    )
    if row:
        return row

    node_id = str(uuid.uuid4())
    props = json.dumps({"概念类型": concept_type, "值": value}, ensure_ascii=False)
    await db.execute(
        "INSERT INTO graph_nodes (id, node_type, label, properties, search_text, created_at) "
        "VALUES (?, 'concept', ?, ?, ?, datetime('now'))",
        (node_id, value, props, value),
    )
    return {
        "id": node_id,
        "node_type": "concept",
        "label": value,
        "properties": {"概念类型": concept_type, "值": value},
    }
