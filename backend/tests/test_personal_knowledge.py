"""Unit tests for personal_knowledge.py — tenant-scoped personal health edges."""

import pytest
import pytest_asyncio
import json
from app.database import SqliteAdapter, init_db
from app.personal_knowledge import (
    ensure_person_entity,
    add_personal_edge,
    remove_personal_edge,
    list_personal_edges,
    find_entity_by_title,
    PERSON_ENTITY_TYPE,
)


async def _seed_globals(db):
    await db.execute(
        """INSERT INTO knowledge_entities
           (id, entity_type, source_table, source_id, title, summary,
            keywords, tags, category, properties, source_type, status, tenant_id)
           VALUES ('ke-symptom-test', 'symptom', 'seed', 's1', '气虚乏力',
                   '可由黄芪治疗', '[]', '[]', '气虚', '{}', 'system', 'active', NULL)"""
    )
    await db.execute(
        """INSERT INTO knowledge_entities
           (id, entity_type, source_table, source_id, title, summary,
            keywords, tags, category, properties, source_type, status, tenant_id)
           VALUES ('ke-herb-test', 'herb', 'seed', 'h1', '黄芪',
                   '补气升阳', '[]', '[]', '补虚药', '{}', 'system', 'active', NULL)"""
    )


@pytest_asyncio.fixture
async def pdb():
    adapter = SqliteAdapter(":memory:")
    await adapter.connect()
    await init_db(adapter)
    await _seed_globals(adapter)
    yield adapter
    await adapter.close()


class TestEnsurePersonEntity:
    @pytest.mark.asyncio
    async def test_creates_new_person(self, pdb):
        eid = await ensure_person_entity(pdb, "user-1", "tenant-A", "张三")
        assert eid == "person-tenant-A-user-1"
        rows = await pdb.query(
            "SELECT * FROM knowledge_entities WHERE id = ?", (eid,)
        )
        assert len(rows) == 1
        assert rows[0]["entity_type"] == PERSON_ENTITY_TYPE
        assert rows[0]["tenant_id"] == "tenant-A"
        assert rows[0]["title"] == "张三"

    @pytest.mark.asyncio
    async def test_idempotent(self, pdb):
        eid1 = await ensure_person_entity(pdb, "user-1", "tenant-A", "张三")
        eid2 = await ensure_person_entity(pdb, "user-1", "tenant-A", "张三")
        assert eid1 == eid2
        rows = await pdb.query(
            "SELECT COUNT(*) as c FROM knowledge_entities WHERE entity_type = 'person'"
        )
        assert rows[0]["c"] == 1

    @pytest.mark.asyncio
    async def test_different_tenants_separate(self, pdb):
        eid_a = await ensure_person_entity(pdb, "user-1", "tenant-A")
        eid_b = await ensure_person_entity(pdb, "user-1", "tenant-B")
        assert eid_a != eid_b


class TestAddPersonalEdge:
    @pytest.mark.asyncio
    async def test_create_edge(self, pdb):
        person_id = await ensure_person_entity(pdb, "u1", "t1")
        edge_id = await add_personal_edge(
            pdb, person_id, "ke-symptom-test", "has_symptom", "t1",
            properties={"severity": "中度"},
        )
        assert edge_id.startswith("edge-")
        rows = await pdb.query(
            "SELECT * FROM entity_relationships WHERE id = ?", (edge_id,)
        )
        assert len(rows) == 1
        assert rows[0]["tenant_id"] == "t1"
        assert rows[0]["relationship_type"] == "has_symptom"

    @pytest.mark.asyncio
    async def test_idempotent_edge(self, pdb):
        person_id = await ensure_person_entity(pdb, "u1", "t1")
        e1 = await add_personal_edge(pdb, person_id, "ke-symptom-test", "has_symptom", "t1")
        e2 = await add_personal_edge(pdb, person_id, "ke-symptom-test", "has_symptom", "t1")
        assert e1 == e2

    @pytest.mark.asyncio
    async def test_different_relationships_not_merged(self, pdb):
        person_id = await ensure_person_entity(pdb, "u1", "t1")
        e1 = await add_personal_edge(pdb, person_id, "ke-symptom-test", "has_symptom", "t1")
        e2 = await add_personal_edge(pdb, person_id, "ke-herb-test", "takes", "t1")
        assert e1 != e2


class TestRemovePersonalEdge:
    @pytest.mark.asyncio
    async def test_remove_existing(self, pdb):
        person_id = await ensure_person_entity(pdb, "u1", "t1")
        edge_id = await add_personal_edge(pdb, person_id, "ke-symptom-test", "has_symptom", "t1")
        deleted = await remove_personal_edge(pdb, edge_id, "t1")
        assert deleted is True

    @pytest.mark.asyncio
    async def test_remove_wrong_tenant_fails(self, pdb):
        person_id = await ensure_person_entity(pdb, "u1", "t1")
        edge_id = await add_personal_edge(pdb, person_id, "ke-symptom-test", "has_symptom", "t1")
        deleted = await remove_personal_edge(pdb, edge_id, "t2")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_remove_nonexistent(self, pdb):
        deleted = await remove_personal_edge(pdb, "fake-edge", "t1")
        assert deleted is False


class TestListPersonalEdges:
    @pytest.mark.asyncio
    async def test_list_with_joined_data(self, pdb):
        person_id = await ensure_person_entity(pdb, "u1", "t1")
        await add_personal_edge(pdb, person_id, "ke-symptom-test", "has_symptom", "t1",
                                properties={"severity": "重度"})
        edges = await list_personal_edges(pdb, person_id, "t1")
        assert len(edges) == 1
        assert edges[0]["target"]["title"] == "气虚乏力"
        assert edges[0]["target"]["type"] == "symptom"
        assert edges[0]["properties"]["severity"] == "重度"

    @pytest.mark.asyncio
    async def test_filter_by_relationship(self, pdb):
        person_id = await ensure_person_entity(pdb, "u1", "t1")
        await add_personal_edge(pdb, person_id, "ke-symptom-test", "has_symptom", "t1")
        await add_personal_edge(pdb, person_id, "ke-herb-test", "takes", "t1")
        symptoms = await list_personal_edges(pdb, person_id, "t1", relationship_type="has_symptom")
        assert len(symptoms) == 1
        meds = await list_personal_edges(pdb, person_id, "t1", relationship_type="takes")
        assert len(meds) == 1

    @pytest.mark.asyncio
    async def test_cross_tenant_isolation(self, pdb):
        p1 = await ensure_person_entity(pdb, "u1", "t1")
        p2 = await ensure_person_entity(pdb, "u2", "t2")
        await add_personal_edge(pdb, p1, "ke-symptom-test", "has_symptom", "t1")
        await add_personal_edge(pdb, p2, "ke-herb-test", "takes", "t2")
        e1 = await list_personal_edges(pdb, p1, "t1")
        e2 = await list_personal_edges(pdb, p2, "t2")
        assert len(e1) == 1
        assert e1[0]["relationship_type"] == "has_symptom"
        assert len(e2) == 1
        assert e2[0]["relationship_type"] == "takes"

    @pytest.mark.asyncio
    async def test_empty_list(self, pdb):
        person_id = await ensure_person_entity(pdb, "u1", "t1")
        edges = await list_personal_edges(pdb, person_id, "t1")
        assert edges == []


class TestFindEntityByTitle:
    @pytest.mark.asyncio
    async def test_exact_match(self, pdb):
        result = await find_entity_by_title(pdb, "气虚乏力", "symptom")
        assert result is not None
        assert result["title"] == "气虚乏力"

    @pytest.mark.asyncio
    async def test_no_match(self, pdb):
        result = await find_entity_by_title(pdb, "不存在的症状")
        assert result is None

    @pytest.mark.asyncio
    async def test_wrong_type(self, pdb):
        result = await find_entity_by_title(pdb, "气虚乏力", "herb")
        assert result is None
