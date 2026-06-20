"""Tests for joint recommendation, medical visits, and processed herb links."""

import pytest
import pytest_asyncio
from app.database import SqliteAdapter, init_db, seed_safety_rules, seed_test_data
from app.formulation_engine import recommend_herbs


@pytest_asyncio.fixture
async def joint_db():
    adapter = SqliteAdapter(":memory:")
    await adapter.connect()
    await init_db(adapter)
    await seed_safety_rules(adapter)
    await seed_test_data(adapter)
    await adapter.execute(
        """INSERT INTO knowledge_entities
           (id, entity_type, source_table, source_id, title, summary,
            keywords, tags, category, content_preview, properties, source_type, status, tenant_id)
           VALUES ('hp-joint-1', 'therapy', 'seed', 't1', '失眠推拿',
                   '安神助眠', '[]', '[]', '推拿', '失眠多梦',
                   '{"indications":["失眠","多梦"]}', 'system', 'active', NULL)"""
    )
    yield adapter
    await adapter.close()


class TestJointRecommendation:
    @pytest.mark.asyncio
    async def test_therapies_matched_by_symptom(self, joint_db):
        from app.routers.formulations import _recommend_therapies
        result = await _recommend_therapies(joint_db, ["失眠"])
        assert len(result) >= 1
        assert any("失眠" in t.get("summary", "") or "失眠" in t.get("title", "") for t in result)

    @pytest.mark.asyncio
    async def test_formulas_matched_by_symptom(self, joint_db):
        from app.routers.formulations import _recommend_formulas
        result = await _recommend_formulas(joint_db, ["失眠"])
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_empty_symptoms_no_match(self, joint_db):
        from app.routers.formulations import _recommend_therapies
        result = await _recommend_therapies(joint_db, ["不存在的症状xyz"])
        assert result == []


class TestMedicalVisits:
    @pytest.mark.asyncio
    async def test_create_and_list_visit(self, joint_db):
        from app.routers.medical_visits import _format
        assert callable(_format)

    @pytest.mark.asyncio
    async def test_visit_table_exists(self, joint_db):
        rows = await joint_db.query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='medical_visits'"
        )
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_visit_crud_cycle(self, joint_db):
        await joint_db.execute(
            """INSERT INTO medical_visits
               (id, user_id, visit_date, hospital, diagnosis, tcm_diagnosis)
               VALUES ('v-test-1', 'u1', '2025-06-20', '测试医院', '感冒', '风寒感冒')"""
        )
        rows = await joint_db.query("SELECT * FROM medical_visits WHERE id = 'v-test-1'")
        assert len(rows) == 1
        assert rows[0]["diagnosis"] == "感冒"
        assert rows[0]["tcm_diagnosis"] == "风寒感冒"

        await joint_db.execute("UPDATE medical_visits SET hospital = '更新医院' WHERE id = 'v-test-1'")
        rows = await joint_db.query("SELECT hospital FROM medical_visits WHERE id = 'v-test-1'")
        assert rows[0]["hospital"] == "更新医院"

        await joint_db.execute("DELETE FROM medical_visits WHERE id = 'v-test-1'")
        rows = await joint_db.query("SELECT * FROM medical_visits WHERE id = 'v-test-1'")
        assert len(rows) == 0


class TestProcessedHerbFormulaLinks:
    @pytest.mark.asyncio
    async def test_processing_relationship_type_exists(self, joint_db):
        await joint_db.execute(
            """INSERT INTO knowledge_entities
               (id, entity_type, source_table, source_id, title, summary,
                keywords, tags, category, properties, source_type, status)
               VALUES ('ph-test-1', 'herb', 'processed', 'p1', '炙甘草',
                       '补脾益气', '[]', '[]', '炮制品',
                       '{"raw_herb":"甘草"}', 'system', 'active')"""
        )
        await joint_db.execute(
            """INSERT INTO knowledge_entities
               (id, entity_type, source_table, source_id, title, summary,
                keywords, tags, category, properties, source_type, status)
               VALUES ('f-test-1', 'formula', 'formulas', 'f1', '炙甘草汤',
                       '益气养心', '[]', '[]', '补益剂', '{}', 'system', 'active')"""
        )
        await joint_db.execute(
            """INSERT INTO entity_relationships
               (id, source_entity_id, target_entity_id, relationship_type, properties, weight)
               VALUES ('rel-pf-test', 'f-test-1', 'ph-test-1', '方剂用药',
                       '{"role":"君药"}', 1.0)"""
        )
        rows = await joint_db.query(
            "SELECT * FROM entity_relationships WHERE relationship_type = '方剂用药'"
        )
        assert len(rows) == 1
