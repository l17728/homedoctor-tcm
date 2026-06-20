"""Unit tests for knowledge_reader.py — unified read layer over knowledge_entities."""

import pytest
import pytest_asyncio
import json
from app.database import SqliteAdapter, init_db
from app.knowledge_reader import (
    list_entities,
    get_entity,
    get_entity_with_relations,
    multi_hop_traverse,
    build_graph_context,
    enrich_from_legacy_tables,
)


async def _seed_test_entities(db):
    """Insert a small knowledge graph for testing."""
    entities = [
        ("ke-herb-1", "herb", "herbs", "h1", "黄芪", "补气升阳", "补虚药",
         '{"nature":"微温","flavor":"甘","meridians":"脾,肺","dosage_min_g":9,"dosage_max_g":30}'),
        ("ke-herb-2", "herb", "herbs", "h2", "人参", "大补元气", "补虚药",
         '{"nature":"微温","flavor":"甘,微苦","meridians":"脾,肺,心"}'),
        ("ke-formula-1", "formula", "formulas", "f1", "四君子汤", "益气健脾", "补益剂",
         '{"composition":"人参,白术,茯苓,甘草"}'),
        ("ke-symptom-1", "symptom", "symptoms", "s1", "气虚乏力", "可由黄芪等药治疗", "气虚",
         '{"treating_herbs":["黄芪","人参"]}'),
        ("ke-symptom-2", "symptom", "symptoms", "s2", "食少便溏", "可由黄芪治疗", "气虚",
         '{"treating_herbs":["黄芪"]}'),
        ("ke-acupoint-1", "acupoint", "seed", "a1", "足三里", "健脾和胃", "足阳明胃经",
         '{"code":"ST36","location":"犊鼻下3寸","needling":"直刺1~2寸"}'),
        ("ke-meridian-1", "meridian", "seed", "m1", "足阳明胃经", "循行腹部", "正经",
         '{"code":"ST","point_count":45}'),
    ]
    for eid, etype, stable, sid, title, summary, cat, props in entities:
        await db.execute(
            """INSERT OR REPLACE INTO knowledge_entities
               (id, entity_type, source_table, source_id, title, summary,
                keywords, tags, category, content_preview, properties,
                source_type, status, tenant_id)
               VALUES (?, ?, ?, ?, ?, ?, '[]', '[]', ?, '', ?, 'system', 'active', NULL)""",
            (eid, etype, stable, sid, title, summary, cat, props),
        )
    rels = [
        ("rel-1", "ke-herb-1", "ke-symptom-1", "主治"),
        ("rel-2", "ke-herb-1", "ke-symptom-2", "主治"),
        ("rel-3", "ke-herb-2", "ke-symptom-1", "主治"),
        ("rel-4", "ke-acupoint-1", "ke-meridian-1", "belongs_to_meridian"),
        ("rel-5", "ke-formula-1", "ke-herb-1", "组成"),
        ("rel-6", "ke-formula-1", "ke-herb-2", "组成"),
    ]
    for rid, src, tgt, rtype in rels:
        await db.execute(
            """INSERT OR REPLACE INTO entity_relationships
               (id, source_entity_id, target_entity_id, relationship_type,
                properties, weight, tenant_id)
               VALUES (?, ?, ?, ?, '{}', 1.0, NULL)""",
            (rid, src, tgt, rtype),
        )


@pytest_asyncio.fixture
async def reader_db():
    adapter = SqliteAdapter(":memory:")
    await adapter.connect()
    await init_db(adapter)
    await _seed_test_entities(adapter)
    yield adapter
    await adapter.close()


class TestListEntities:
    @pytest.mark.asyncio
    async def test_list_herbs(self, reader_db):
        result = await list_entities(reader_db, "herb", page=1, page_size=10)
        assert result["total"] == 2
        titles = [i["title"] for i in result["items"]]
        assert "黄芪" in titles
        assert "人参" in titles

    @pytest.mark.asyncio
    async def test_list_with_search(self, reader_db):
        result = await list_entities(reader_db, "herb", search="黄芪")
        assert result["total"] == 1
        assert result["items"][0]["title"] == "黄芪"

    @pytest.mark.asyncio
    async def test_list_with_category(self, reader_db):
        result = await list_entities(reader_db, "herb", category="补虚药")
        assert result["total"] == 2

    @pytest.mark.asyncio
    async def test_list_pagination(self, reader_db):
        p1 = await list_entities(reader_db, "symptom", page=1, page_size=1)
        assert len(p1["items"]) == 1
        assert p1["total"] == 2
        p2 = await list_entities(reader_db, "symptom", page=2, page_size=1)
        assert len(p2["items"]) == 1

    @pytest.mark.asyncio
    async def test_list_properties_parsed(self, reader_db):
        result = await list_entities(reader_db, "herb", search="黄芪")
        props = result["items"][0]["properties"]
        assert props["nature"] == "微温"
        assert props["dosage_min_g"] == 9

    @pytest.mark.asyncio
    async def test_list_empty_type(self, reader_db):
        result = await list_entities(reader_db, "nonexistent")
        assert result["total"] == 0
        assert result["items"] == []


class TestGetEntity:
    @pytest.mark.asyncio
    async def test_get_existing(self, reader_db):
        entity = await get_entity(reader_db, "ke-herb-1")
        assert entity is not None
        assert entity["title"] == "黄芪"
        assert entity["type"] == "herb"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, reader_db):
        entity = await get_entity(reader_db, "does-not-exist")
        assert entity is None

    @pytest.mark.asyncio
    async def test_get_with_meta(self, reader_db):
        entity = await get_entity(reader_db, "ke-acupoint-1")
        assert entity["source_table"] == "seed"
        assert entity["properties"]["code"] == "ST36"


class TestGetEntityWithRelations:
    @pytest.mark.asyncio
    async def test_herb_has_symptoms(self, reader_db):
        result = await get_entity_with_relations(reader_db, "ke-herb-1")
        assert result is not None
        assert "主治" in result["relationships"]
        symptoms = result["relationships"]["主治"]
        assert len(symptoms) == 2
        titles = [s["title"] for s in symptoms]
        assert "气虚乏力" in titles

    @pytest.mark.asyncio
    async def test_formula_has_composition(self, reader_db):
        result = await get_entity_with_relations(reader_db, "ke-formula-1")
        assert "组成" in result["relationships"]
        herbs = result["relationships"]["组成"]
        assert len(herbs) == 2

    @pytest.mark.asyncio
    async def test_acupoint_has_meridian(self, reader_db):
        result = await get_entity_with_relations(reader_db, "ke-acupoint-1")
        assert "belongs_to_meridian" in result["relationships"]

    @pytest.mark.asyncio
    async def test_nonexistent_returns_none(self, reader_db):
        result = await get_entity_with_relations(reader_db, "nope")
        assert result is None


class TestMultiHopTraverse:
    @pytest.mark.asyncio
    async def test_2hop_from_herb(self, reader_db):
        paths = await multi_hop_traverse(reader_db, "ke-herb-1", max_hops=2)
        assert len(paths) > 0
        all_ids = []
        for p in paths:
            all_ids.extend(p["path"])
        assert "ke-symptom-1" in all_ids or "ke-symptom-2" in all_ids

    @pytest.mark.asyncio
    async def test_no_orphans(self, reader_db):
        paths = await multi_hop_traverse(reader_db, "ke-meridian-1", max_hops=2)
        assert isinstance(paths, list)

    @pytest.mark.asyncio
    async def test_nonexistent_entity(self, reader_db):
        paths = await multi_hop_traverse(reader_db, "nope", max_hops=3)
        assert paths == []


class TestBuildGraphContext:
    @pytest.mark.asyncio
    async def test_context_for_herb_question(self, reader_db):
        from app.entity_filter import get_entity_index, reset_index
        reset_index()
        await get_entity_index(reader_db)
        ctx = await build_graph_context(reader_db, "黄芪补气怎么用？")
        if ctx is not None:
            assert "黄芪" in ctx
            assert "微温" in ctx or "甘" in ctx

    @pytest.mark.asyncio
    async def test_context_no_match(self, reader_db):
        from app.entity_filter import get_entity_index, reset_index
        reset_index()
        await get_entity_index(reader_db)
        ctx = await build_graph_context(reader_db, "今天天气怎么样")
        assert ctx is None

    @pytest.mark.asyncio
    async def test_context_includes_relationships(self, reader_db):
        from app.entity_filter import get_entity_index, reset_index
        reset_index()
        await get_entity_index(reader_db)
        ctx = await build_graph_context(reader_db, "人参的功效")
        if ctx:
            assert "人参" in ctx


class TestEnrichFromLegacyTables:
    @pytest.mark.asyncio
    async def test_enrich_idempotent(self, reader_db):
        result1 = await enrich_from_legacy_tables(reader_db)
        result2 = await enrich_from_legacy_tables(reader_db)
        assert result1 == result2
