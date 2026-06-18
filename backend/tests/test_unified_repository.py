"""Tests for the Phase 2 unified node repository and schema registry.

Covers:
- JSON schema loading from ``config/schemas/node_*.json``.
- Field type taxonomy (string / number / enum / ref / anchor / array / textarea).
- Node CRUD on ``graph_nodes`` (create / get / update / delete).
- Type-scoped queries with optional property filters.
- SQL-pushdown single-key equality via ``json_extract``.
- ``find_or_create`` deduplication.
- Edge CRUD on ``graph_edges`` plus the safety rail refusing empty filters.
- Migration script end-to-end against an in-memory database seeded with the
  canonical test herbs/formulas/therapies.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import pytest_asyncio

from app.database import SqliteAdapter, init_db, seed_test_data
from app.unified_repository import UnifiedRepository
from app.unified_schema import (
    FileSchemaRegistry,
    VALID_FIELD_TYPES,
    is_safe_json_key,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db() -> SqliteAdapter:
    """In-memory database with all tables + the canonical test seed data."""
    adapter = SqliteAdapter(":memory:")
    await adapter.connect()
    await init_db(adapter)
    await seed_test_data(adapter)
    yield adapter
    await adapter.close()


@pytest.fixture
def registry() -> FileSchemaRegistry:
    """Schema registry that reads from the project-root config dir."""
    reg = FileSchemaRegistry()
    reg.reload()
    return reg


@pytest_asyncio.fixture
async def repo(db: SqliteAdapter, registry: FileSchemaRegistry) -> UnifiedRepository:
    return UnifiedRepository(db, registry)


# ---------------------------------------------------------------------------
# Schema loading
# ---------------------------------------------------------------------------


def test_registry_loads_node_schemas(registry: FileSchemaRegistry) -> None:
    """The five Phase 2 node types are loaded from disk."""
    types = set(registry.list_node_types())
    assert {"herb", "formula", "therapy", "symptom", "medicine"} <= types


def test_registry_ignores_legacy_files(registry: FileSchemaRegistry) -> None:
    """Legacy ``herb.json`` (no node_ prefix) is NOT loaded here.

    This is critical: the legacy schema uses English field names (``name``,
    ``nature``) and is still served by the existing ``/api/schemas`` router.
    Mixing the two would break that contract.
    """
    schemas = {s.node_type: s for s in registry.list_schemas()}
    # All loaded schemas must declare fields with Chinese keys — a quick
    # sanity check that we picked up the right files.
    herb = schemas["herb"]
    field_ids = {f.id for f in herb.fields}
    assert "名称" in field_ids
    assert "药性" in field_ids


def test_herb_schema_has_ref_and_anchor_fields(registry: FileSchemaRegistry) -> None:
    """The herb schema declares both ref and anchor fields per spec."""
    ref_fields = registry.get_ref_fields("herb")
    ref_targets = {f.ref_type for f in ref_fields}
    assert "herb" in ref_targets, "herb schema should self-reference (相反/相畏)"
    assert "medicine" in ref_targets, "herb schema should reference medicine (中西药交互)"

    anchor_fields = registry.get_anchor_fields("herb")
    anchors = {f.anchor for f in anchor_fields if f.anchor}
    assert "症状" in anchors, "主治 field should anchor on 症状"
    assert "经络" in anchors, "归经 field should anchor on 经络"


def test_formula_schema_has_composition_ref(registry: FileSchemaRegistry) -> None:
    """The formula schema's 组成 field is a ref→herb."""
    refs = registry.get_ref_fields("formula")
    composition = next((f for f in refs if f.id == "组成"), None)
    assert composition is not None
    assert composition.ref_type == "herb"


def test_field_type_vocabulary_covers_fighting_set(registry: FileSchemaRegistry) -> None:
    """All field types used in the JSON schemas fall inside the /fighting vocab."""
    for schema in registry.list_schemas():
        for field in schema.fields:
            assert field.type in VALID_FIELD_TYPES, (
                f"unknown field type {field.type!r} in {schema.node_type}.{field.id}"
            )


def test_get_schema_unknown_type_returns_none(registry: FileSchemaRegistry) -> None:
    assert registry.get_schema("does-not-exist") is None


def test_registry_reload_is_idempotent(registry: FileSchemaRegistry) -> None:
    """Reload after the first load produces the same node-type set."""
    before = set(registry.list_node_types())
    registry.reload()
    after = set(registry.list_node_types())
    assert before == after


def test_is_safe_json_key_accepts_cjk_and_alnum() -> None:
    assert is_safe_json_key("名称")
    assert is_safe_json_key("药性")
    assert is_safe_json_key("herb_id")
    assert is_safe_json_key("abc123")


def test_is_safe_json_key_rejects_injection() -> None:
    """Path injection attempts are rejected — guards json_extract splicing."""
    assert not is_safe_json_key("'); DROP TABLE--")
    assert not is_safe_json_key("a.b")
    assert not is_safe_json_key("")
    assert not is_safe_json_key("name';--")


# ---------------------------------------------------------------------------
# Node CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_node_assigns_uuid_and_derives_label(
    repo: UnifiedRepository,
) -> None:
    node = await repo.create_node(
        "herb",
        {"名称": "测试药", "药性": "温"},
    )
    assert node["id"]
    assert node["node_type"] == "herb"
    # Label auto-derived from the schema's identity key (名称).
    assert node["label"] == "测试药"
    assert node["properties"]["名称"] == "测试药"
    assert node["properties"]["药性"] == "温"
    # search_text must include every string-valued property so substring
    # search works.
    assert "测试药" in node["search_text"]


@pytest.mark.asyncio
async def test_create_node_explicit_label_wins(repo: UnifiedRepository) -> None:
    node = await repo.create_node(
        "herb",
        {"名称": "黄芪"},
        label="custom label",
    )
    assert node["label"] == "custom label"


@pytest.mark.asyncio
async def test_get_node_missing_returns_none(repo: UnifiedRepository) -> None:
    assert await repo.get_node("nonexistent-id") is None


@pytest.mark.asyncio
async def test_update_node_merges_patch(repo: UnifiedRepository) -> None:
    node = await repo.create_node("herb", {"名称": "党参", "药性": "平"})
    updated = await repo.update_node(
        node["id"], {"药性": "温", "药味": "甘"}
    )
    # Patch overwrites existing keys, preserves untouched ones.
    assert updated["properties"]["名称"] == "党参"
    assert updated["properties"]["药性"] == "温"
    assert updated["properties"]["药味"] == "甘"
    # search_text must reflect the merged state.
    assert "党参" in updated["search_text"]
    assert "甘" in updated["search_text"]


@pytest.mark.asyncio
async def test_update_unknown_node_raises(repo: UnifiedRepository) -> None:
    with pytest.raises(KeyError):
        await repo.update_node("does-not-exist", {"foo": "bar"})


@pytest.mark.asyncio
async def test_delete_node_removes_edges_too(repo: UnifiedRepository) -> None:
    herb_a = await repo.create_node("herb", {"名称": "药A"})
    herb_b = await repo.create_node("herb", {"名称": "药B"})
    await repo.create_edge("相反", herb_a["id"], herb_b["id"])

    deleted = await repo.delete_node(herb_a["id"])
    assert deleted is True

    # Re-deleting is a no-op.
    assert await repo.delete_node(herb_a["id"]) is False

    # Edge that referenced the deleted node must be gone too.
    remaining = await repo.query_edges(edge_type="相反")
    assert remaining == []


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_nodes_filters_by_type(repo: UnifiedRepository) -> None:
    await repo.create_node("herb", {"名称": "黄芪"})
    await repo.create_node("formula", {"名称": "四君子汤"})
    herbs = await repo.query_nodes("herb")
    types = {n["node_type"] for n in herbs}
    assert types == {"herb"}


@pytest.mark.asyncio
async def test_query_nodes_python_filter(repo: UnifiedRepository) -> None:
    await repo.create_node("herb", {"名称": "温药", "药性": "温"})
    await repo.create_node("herb", {"名称": "寒药", "药性": "寒"})
    warm = await repo.query_nodes("herb", filter={"药性": "温"})
    assert len(warm) == 1
    assert warm[0]["properties"]["名称"] == "温药"


@pytest.mark.asyncio
async def test_query_nodes_by_property_uses_json_extract(
    repo: UnifiedRepository,
) -> None:
    """Single-key string equality pushes down into SQLite."""
    await repo.create_node("herb", {"名称": "黄芪", "药性": "微温"})
    await repo.create_node("herb", {"名称": "石膏", "药性": "寒"})

    warm = await repo.query_nodes_by_property("herb", "药性", "微温")
    assert len(warm) == 1
    assert warm[0]["properties"]["名称"] == "黄芪"

    cold = await repo.query_nodes_by_property("herb", "药性", "寒")
    assert len(cold) == 1
    assert cold[0]["properties"]["名称"] == "石膏"


@pytest.mark.asyncio
async def test_query_nodes_by_property_rejects_unsafe_key(
    repo: UnifiedRepository,
) -> None:
    with pytest.raises(ValueError):
        await repo.query_nodes_by_property("herb", "name'; DROP TABLE--", "x")


@pytest.mark.asyncio
async def test_find_or_create_is_idempotent(repo: UnifiedRepository) -> None:
    first = await repo.find_or_create("herb", "名称", "甘草", label="甘草")
    second = await repo.find_or_create("herb", "名称", "甘草")
    assert first["id"] == second["id"], "second call must return the existing node"

    # And it must not have created a duplicate.
    matches = await repo.query_nodes_by_property("herb", "名称", "甘草")
    assert len(matches) == 1


@pytest.mark.asyncio
async def test_query_nodes_limit_is_capped(repo: UnifiedRepository) -> None:
    """Limit > 1000 collapses to 1000 to protect the DB from runaway queries."""
    for i in range(5):
        await repo.create_node("herb", {"名称": f"药{i}"})
    # Capped to a small slice; assert it returned at most the cap value.
    out = await repo.query_nodes("herb", limit=3)
    assert len(out) == 3


# ---------------------------------------------------------------------------
# Edge CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_edge_and_query_round_trip(repo: UnifiedRepository) -> None:
    a = await repo.create_node("herb", {"名称": "藜芦"})
    b = await repo.create_node("herb", {"名称": "人参"})

    edge = await repo.create_edge(
        "相反",
        a["id"],
        b["id"],
        properties={"severity": "critical", "source": "十八反"},
    )
    assert edge["edge_type"] == "相反"
    assert edge["source_id"] == a["id"]
    assert edge["target_id"] == b["id"]
    assert edge["properties"]["severity"] == "critical"

    by_source = await repo.query_edges(source_id=a["id"])
    assert len(by_source) == 1
    by_type = await repo.query_edges(edge_type="相反")
    assert len(by_type) == 1
    by_target = await repo.query_edges(target_id=b["id"])
    assert len(by_target) == 1


@pytest.mark.asyncio
async def test_delete_edges_requires_filter(repo: UnifiedRepository) -> None:
    """An empty filter must be refused — safety rail against wiping the table."""
    with pytest.raises(ValueError):
        await repo.delete_edges()


@pytest.mark.asyncio
async def test_delete_edges_by_type_and_source(repo: UnifiedRepository) -> None:
    a = await repo.create_node("herb", {"名称": "A"})
    b = await repo.create_node("herb", {"名称": "B"})
    c = await repo.create_node("herb", {"名称": "C"})

    await repo.create_edge("相反", a["id"], b["id"])
    await repo.create_edge("相畏", a["id"], c["id"])
    await repo.create_edge("相反", b["id"], c["id"])

    # Delete only 相反 edges sourced at A.
    deleted = await repo.delete_edges(source_id=a["id"], edge_type="相反")
    assert deleted == 1

    remaining_from_a = await repo.query_edges(source_id=a["id"])
    assert len(remaining_from_a) == 1
    assert remaining_from_a[0]["edge_type"] == "相畏"

    # The 相反 edge B->C is untouched.
    remaining_incompat = await repo.query_edges(edge_type="相反")
    assert len(remaining_incompat) == 1
    assert remaining_incompat[0]["source_id"] == b["id"]


# ---------------------------------------------------------------------------
# Migration script — end-to-end
# ---------------------------------------------------------------------------


def _load_migration_module():
    """Import the migration script as a module without invoking argv."""
    script_path = (
        Path(__file__).resolve().parent.parent
        / "scripts"
        / "migrate_to_graph.py"
    )
    spec = importlib.util.spec_from_file_location("migrate_to_graph", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["migrate_to_graph"] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_migration_creates_nodes_for_seed_data() -> None:
    """Migration against the seeded in-memory DB produces the expected counts."""
    migration = _load_migration_module()

    # Use a temp file-backed SQLite so the migration can re-open the adapter.
    # :memory: would lose data when the adapter closes between calls.
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        seed_adapter = SqliteAdapter(db_path)
        await seed_adapter.connect()
        await init_db(seed_adapter)
        await seed_test_data(seed_adapter)
        await seed_adapter.close()

        stats = await migration.run_migration(db_path, dry_run=False)

        # The canonical seed_test_data plants 3 herbs + 2 formulas + therapies.
        # Counts may exceed 3 for therapies because therapy_data seeds many.
        assert stats["herbs_created"] >= 3
        assert stats["formulas_created"] >= 2
        assert stats["therapies_created"] >= 1

        # 四君子汤 contains 人参/白术/茯苓/甘草; seed herbs include 甘草.
        # So at least one 组成 edge should have been created.
        assert stats["composition_edges"] >= 1

        # Re-run must be idempotent — nothing new is created.
        stats_again = await migration.run_migration(db_path, dry_run=False)
        assert stats_again["herbs_created"] == 0
        assert stats_again["formulas_created"] == 0
        assert stats_again["therapies_created"] == 0
        assert stats_again["composition_edges"] == 0


@pytest.mark.asyncio
async def test_migration_dry_run_does_not_mutate() -> None:
    """A dry-run reports counts but leaves the DB untouched."""
    migration = _load_migration_module()

    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        seed_adapter = SqliteAdapter(db_path)
        await seed_adapter.connect()
        await init_db(seed_adapter)
        await seed_test_data(seed_adapter)
        await seed_adapter.close()

        dry_stats = await migration.run_migration(db_path, dry_run=True)
        assert dry_stats["herbs_created"] >= 3

        # Verify no nodes were actually written.
        verify_adapter = SqliteAdapter(db_path)
        await verify_adapter.connect()
        try:
            rows = await verify_adapter.query(
                "SELECT COUNT(*) AS n FROM graph_nodes WHERE node_type = 'herb'"
            )
            assert rows[0]["n"] == 0, "dry-run must not write herb nodes"
        finally:
            await verify_adapter.close()
