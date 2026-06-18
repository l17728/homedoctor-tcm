"""Tests for ref_sync edge derivation engine (port of /fighting refs.ts + anchors.ts).

Covers:
  - sync_ref_edges creates 分配 edges for ref-typed fields
  - sync_anchor_edges creates concept nodes + 关联 edges
  - rebuild_all_edges wipes and regenerates all derived edges
  - safety edges created from rules table
  - idempotency (running twice produces same result)
  - node with no ref/anchor fields produces no edges
"""

import json
import uuid

import pytest

from app.database import DbAdapter, SqliteAdapter, init_db, seed_safety_rules, seed_test_data
from app.kg_rebuild import rebuild_all_edges
from app.ref_sync import (
    sync_ref_edges,
    sync_anchor_edges,
    REF_EDGE_TYPE,
    ANCHOR_EDGE_TYPE,
)
from app.schema.registry import FileSchemaRegistry, SchemaDefinition, SchemaField


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_registry_with_ref():
    """Build an in-memory registry with a node type that has ref + anchor fields."""
    registry = FileSchemaRegistry.__new__(FileSchemaRegistry)
    registry._config_dir = None
    registry._loaded = True
    registry._schemas = {}

    test_schema = SchemaDefinition({
        "nodeType": "test_herb",
        "label": "测试中药",
        "fields": [
            {"id": "name", "type": "string", "label": "名称", "required": True},
            {"id": "related_herb", "type": "ref", "label": "相关中药",
             "refType": "herb"},
            {"id": "meridians", "type": "string", "label": "归经",
             "anchor": "经络"},
            {"id": "nature", "type": "string", "label": "药性",
             "anchor": "药性"},
        ],
    })
    registry._schemas["test_herb"] = test_schema
    return registry


def _make_registry_no_special():
    """Registry with a node type that has NO ref or anchor fields."""
    registry = FileSchemaRegistry.__new__(FileSchemaRegistry)
    registry._config_dir = None
    registry._loaded = True
    registry._schemas = {}

    plain_schema = SchemaDefinition({
        "nodeType": "plain",
        "label": "普通节点",
        "fields": [
            {"id": "name", "type": "string", "label": "名称", "required": True},
            {"id": "description", "type": "text", "label": "描述"},
        ],
    })
    registry._schemas["plain"] = plain_schema
    return registry


async def _insert_node(db, node_id, node_type, label, properties):
    await db.execute(
        "INSERT INTO graph_nodes (id, node_type, label, properties, search_text, created_at) "
        "VALUES (?, ?, ?, ?, ?, datetime('now'))",
        (node_id, node_type, label,
         json.dumps(properties, ensure_ascii=False), label),
    )


# ---------------------------------------------------------------------------
# sync_ref_edges
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_ref_edges_creates_edges_for_ref_fields(db: DbAdapter):
    """sync_ref_edges creates 分配 edges when a node has ref-typed properties."""
    registry = _make_registry_with_ref()
    await _insert_node(db, "th-1", "test_herb", "测试药A", {
        "name": "测试药A",
        "related_herb": "甘草",
    })
    await _insert_node(db, "herb-target", "herb", "甘草", {"name": "甘草"})

    node = await db.query_one("SELECT * FROM graph_nodes WHERE id = 'th-1'")
    count = await sync_ref_edges(db, registry, node)

    assert count == 1
    edges = await db.query(
        "SELECT * FROM graph_edges WHERE source_id = 'th-1' AND edge_type = ?",
        (REF_EDGE_TYPE,),
    )
    assert len(edges) == 1
    assert edges[0]["target_id"] == "herb-target"


@pytest.mark.asyncio
async def test_sync_ref_edges_creates_target_if_missing(db: DbAdapter):
    """sync_ref_edges creates the target node if it doesn't exist yet."""
    registry = _make_registry_with_ref()
    await _insert_node(db, "th-2", "test_herb", "测试药B", {
        "name": "测试药B",
        "related_herb": "新中药",
    })

    node = await db.query_one("SELECT * FROM graph_nodes WHERE id = 'th-2'")
    count = await sync_ref_edges(db, registry, node)

    assert count == 1
    target = await db.query_one(
        "SELECT * FROM graph_nodes WHERE node_type = 'herb' AND label = '新中药'"
    )
    assert target is not None
    edge = await db.query_one(
        "SELECT * FROM graph_edges WHERE source_id = 'th-2' AND edge_type = ?",
        (REF_EDGE_TYPE,),
    )
    assert edge["target_id"] == target["id"]


@pytest.mark.asyncio
async def test_sync_ref_edges_handles_multi_value(db: DbAdapter):
    """sync_ref_edges handles comma-separated multi-ref values."""
    registry = _make_registry_with_ref()
    await _insert_node(db, "herb-a", "herb", "药A", {"name": "药A"})
    await _insert_node(db, "herb-b", "herb", "药B", {"name": "药B"})
    await _insert_node(db, "th-3", "test_herb", "测试药C", {
        "name": "测试药C",
        "related_herb": "药A,药B",
    })

    node = await db.query_one("SELECT * FROM graph_nodes WHERE id = 'th-3'")
    count = await sync_ref_edges(db, registry, node)

    assert count == 2


@pytest.mark.asyncio
async def test_sync_ref_edges_no_schema_returns_zero(db: DbAdapter):
    """sync_ref_edges returns 0 when node type has no schema."""
    registry = _make_registry_with_ref()
    await _insert_node(db, "unknown-1", "unknown_type", "未知", {})

    node = await db.query_one("SELECT * FROM graph_nodes WHERE id = 'unknown-1'")
    count = await sync_ref_edges(db, registry, node)
    assert count == 0


@pytest.mark.asyncio
async def test_sync_ref_edges_no_ref_fields_returns_zero(db: DbAdapter):
    """sync_ref_edges returns 0 when schema has no ref fields."""
    registry = _make_registry_no_special()
    await _insert_node(db, "p-1", "plain", "普通", {"name": "普通"})

    node = await db.query_one("SELECT * FROM graph_nodes WHERE id = 'p-1'")
    count = await sync_ref_edges(db, registry, node)
    assert count == 0


# ---------------------------------------------------------------------------
# sync_anchor_edges
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_anchor_edges_creates_concept_and_edges(db: DbAdapter):
    """sync_anchor_edges creates concept nodes + 关联 edges."""
    registry = _make_registry_with_ref()
    await _insert_node(db, "th-anc-1", "test_herb", "药X", {
        "name": "药X",
        "meridians": "脾,肺",
    })

    node = await db.query_one("SELECT * FROM graph_nodes WHERE id = 'th-anc-1'")
    count = await sync_anchor_edges(db, registry, node)

    assert count == 2
    edges = await db.query(
        "SELECT * FROM graph_edges WHERE source_id = 'th-anc-1' AND edge_type = ?",
        (ANCHOR_EDGE_TYPE,),
    )
    assert len(edges) == 2
    for e in edges:
        concept = await db.query_one(
            "SELECT * FROM graph_nodes WHERE id = ?", (e["target_id"],)
        )
        assert concept["node_type"] == "concept"
        props = json.loads(concept["properties"])
        assert props["概念类型"] == "经络"
        assert concept["label"] in ("脾", "肺")


@pytest.mark.asyncio
async def test_sync_anchor_edges_shares_concept_nodes(db: DbAdapter):
    """Two herbs with the same meridian share the SAME concept node."""
    registry = _make_registry_with_ref()
    await _insert_node(db, "h-share-1", "test_herb", "药甲", {
        "name": "药甲", "meridians": "肝",
    })
    await _insert_node(db, "h-share-2", "test_herb", "药乙", {
        "name": "药乙", "meridians": "肝",
    })

    node1 = await db.query_one("SELECT * FROM graph_nodes WHERE id = 'h-share-1'")
    node2 = await db.query_one("SELECT * FROM graph_nodes WHERE id = 'h-share-2'")
    await sync_anchor_edges(db, registry, node1)
    await sync_anchor_edges(db, registry, node2)

    concepts = await db.query(
        "SELECT * FROM graph_nodes WHERE node_type = 'concept' AND label = '肝'"
    )
    assert len(concepts) == 1, "Both herbs should share the same concept node"


@pytest.mark.asyncio
async def test_sync_anchor_edges_no_anchor_fields(db: DbAdapter):
    """sync_anchor_edges returns 0 when schema has no anchor fields."""
    registry = _make_registry_no_special()
    await _insert_node(db, "p-2", "plain", "普通2", {"name": "普通2"})

    node = await db.query_one("SELECT * FROM graph_nodes WHERE id = 'p-2'")
    count = await sync_anchor_edges(db, registry, node)
    assert count == 0


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_ref_edges_idempotent(db: DbAdapter):
    """Running sync_ref_edges twice produces the same edge count (no duplicates)."""
    registry = _make_registry_with_ref()
    await _insert_node(db, "herb-target-i", "herb", "靶药", {"name": "靶药"})
    await _insert_node(db, "th-idem", "test_herb", "药幂等", {
        "name": "药幂等", "related_herb": "靶药",
    })

    node = await db.query_one("SELECT * FROM graph_nodes WHERE id = 'th-idem'")
    c1 = await sync_ref_edges(db, registry, node)
    c2 = await sync_ref_edges(db, registry, node)

    assert c1 == 1
    assert c2 == 1
    edges = await db.query(
        "SELECT * FROM graph_edges WHERE source_id = 'th-idem' AND edge_type = ?",
        (REF_EDGE_TYPE,),
    )
    assert len(edges) == 1


@pytest.mark.asyncio
async def test_sync_anchor_edges_idempotent(db: DbAdapter):
    """Running sync_anchor_edges twice doesn't duplicate concept nodes or edges."""
    registry = _make_registry_with_ref()
    await _insert_node(db, "th-aidem", "test_herb", "药锚等", {
        "name": "药锚等", "meridians": "心",
    })

    node = await db.query_one("SELECT * FROM graph_nodes WHERE id = 'th-aidem'")
    c1 = await sync_anchor_edges(db, registry, node)
    c2 = await sync_anchor_edges(db, registry, node)

    assert c1 == 1
    assert c2 == 1
    concepts = await db.query(
        "SELECT * FROM graph_nodes WHERE node_type = 'concept' AND label = '心'"
    )
    assert len(concepts) == 1


# ---------------------------------------------------------------------------
# Full rebuild
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rebuild_all_edges_creates_all_types(db: DbAdapter):
    """rebuild_all_edges creates 组成/主治/配伍禁忌/中西药交互 + 分配/关联 edges."""
    counts = await rebuild_all_edges(db)

    assert "组成" in counts
    assert counts["组成"] >= 2
    assert counts["主治"] >= 1
    assert "配伍禁忌" in counts
    assert "中西药交互" in counts
    assert "分配" in counts
    assert "关联" in counts
    assert counts["关联"] > 0, "Should have anchor edges from herb schemas"


@pytest.mark.asyncio
async def test_rebuild_all_edges_idempotent(db: DbAdapter):
    """Running rebuild twice produces the same edge counts."""
    c1 = await rebuild_all_edges(db)
    c2 = await rebuild_all_edges(db)

    for key in c1:
        assert c1[key] == c2[key], f"Edge count mismatch for {key}: {c1[key]} vs {c2[key]}"


@pytest.mark.asyncio
async def test_rebuild_no_orphan_edges(db: DbAdapter):
    """After rebuild, every edge's source_id and target_id exist in graph_nodes."""
    await rebuild_all_edges(db)

    edges = await db.query("SELECT edge_type, source_id, target_id FROM graph_edges")
    assert len(edges) > 0

    node_ids = {
        row["id"] for row in await db.query("SELECT id FROM graph_nodes")
    }

    orphans = [
        (e["edge_type"], e["source_id"], e["target_id"])
        for e in edges
        if e["source_id"] not in node_ids or e["target_id"] not in node_ids
    ]
    assert orphans == [], f"{len(orphans)} orphan edges: {orphans[:3]}"


@pytest.mark.asyncio
async def test_rebuild_safety_edges_from_rules(db: DbAdapter):
    """Safety rules (十八反/十九畏) produce 配伍禁忌 edges when herbs exist."""
    await db.execute(
        "INSERT OR IGNORE INTO herbs (id, name, nature, flavor, meridians, "
        "efficacy, indications, category, properties) VALUES "
        "('herb-fuzi', '附子', '热', '辛', '心,肾,脾', '回阳救逆', '亡阳证', '温里药', '{}'),"
        "('herb-banxia', '半夏', '温', '辛', '脾,胃', '燥湿化痰', '湿痰寒痰', '化痰止咳平喘药', '{}')"
    )

    counts = await rebuild_all_edges(db)

    conflict_edges = await db.query(
        "SELECT * FROM graph_edges WHERE edge_type = '配伍禁忌'"
    )
    assert len(conflict_edges) > 0, "Should have 配伍禁忌 edges from 十八反 (附子×半夏)"

    for e in conflict_edges:
        props = json.loads(e["properties"])
        assert "severity" in props


@pytest.mark.asyncio
async def test_rebuild_anchor_edges_link_herbs_by_meridian(db: DbAdapter):
    """Herbs sharing the same meridian are linked through the same concept node."""
    await rebuild_all_edges(db)

    herb_nodes = await db.query(
        "SELECT * FROM graph_nodes WHERE node_type = 'herb'"
    )
    assert len(herb_nodes) >= 3

    anchor_edges = await db.query(
        "SELECT * FROM graph_edges WHERE edge_type = ?", (ANCHOR_EDGE_TYPE,)
    )
    assert len(anchor_edges) > 0

    concept_targets = {e["target_id"] for e in anchor_edges}
    for cid in concept_targets:
        concept = await db.query_one(
            "SELECT * FROM graph_nodes WHERE id = ?", (cid,)
        )
        assert concept is not None
        assert concept["node_type"] == "concept"


# ---------------------------------------------------------------------------
# Schema registry extensions
# ---------------------------------------------------------------------------

def test_schema_field_reads_ref_type():
    """SchemaField reads refType from JSON data."""
    field = SchemaField({"id": "ref1", "type": "ref", "refType": "herb"})
    assert field.ref_type == "herb"
    assert field.type == "ref"


def test_schema_field_reads_anchor():
    """SchemaField reads anchor from JSON data."""
    field = SchemaField({"id": "m", "type": "string", "anchor": "经络"})
    assert field.anchor == "经络"


def test_schema_field_defaults_no_ref_no_anchor():
    """SchemaField defaults ref_type and anchor to None."""
    field = SchemaField({"id": "x", "type": "string"})
    assert field.ref_type is None
    assert field.anchor is None


def test_registry_get_ref_fields():
    """FileSchemaRegistry.get_ref_fields returns only ref-typed fields."""
    registry = _make_registry_with_ref()
    refs = registry.get_ref_fields("test_herb")
    assert len(refs) == 1
    assert refs[0].id == "related_herb"
    assert refs[0].ref_type == "herb"


def test_registry_get_anchor_fields():
    """FileSchemaRegistry.get_anchor_fields returns only anchor-typed fields."""
    registry = _make_registry_with_ref()
    anchors = registry.get_anchor_fields("test_herb")
    anchor_ids = {a.id for a in anchors}
    assert "meridians" in anchor_ids
    assert "nature" in anchor_ids


def test_registry_get_ref_fields_unknown_type():
    """get_ref_fields returns empty list for unknown node type."""
    registry = _make_registry_with_ref()
    assert registry.get_ref_fields("nonexistent") == []


def test_registry_get_anchor_fields_unknown_type():
    """get_anchor_fields returns empty list for unknown node type."""
    registry = _make_registry_with_ref()
    assert registry.get_anchor_fields("nonexistent") == []


def test_herb_schema_has_anchor_fields():
    """Production herb.json schema has anchor metadata on meridians/nature/category."""
    from app.schema.registry import schema_registry
    anchors = schema_registry.get_anchor_fields("herb")
    anchor_map = {a.id: a.anchor for a in anchors}
    assert "meridians" in anchor_map
    assert anchor_map["meridians"] == "经络"
    assert "nature" in anchor_map
    assert "category" in anchor_map
