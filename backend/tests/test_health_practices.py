"""Tests for health practices, processed herbs, and practice relationships."""

import pytest
import pytest_asyncio
from app.database import SqliteAdapter, init_db, seed_safety_rules, seed_test_data


@pytest_asyncio.fixture
async def practice_db():
    adapter = SqliteAdapter(":memory:")
    await adapter.connect()
    await init_db(adapter)
    await seed_safety_rules(adapter)
    await seed_test_data(adapter)

    await adapter.execute(
        """INSERT INTO knowledge_entities
           (id, entity_type, source_table, source_id, title, summary,
            keywords, tags, category, content_preview, properties, source_type, status, tenant_id)
           VALUES ('hp-test', 'health_practice', 'seed', 'hp1', '八段锦',
                   '调理脏腑', '[]', '[]', '导引功法', '',
           '{"practice_type":"动功","difficulty":"入门","core_essence":"八式导引","breathing":"自然呼吸","mental_focus":"意气合一","key_points":["松静自然"],"indications":["强身健体"],"steps":[{"name":"双手托天","points":"上托"}]}',
                   'system', 'active', NULL)"""
    )
    await adapter.execute(
        """INSERT INTO knowledge_entities
           (id, entity_type, source_table, source_id, title, summary,
            keywords, tags, category, content_preview, properties, source_type, status, tenant_id)
           VALUES ('ps-test', 'practice_school', 'seed', 'ps1', '武当派',
                   '内家拳法', '[]', '[]', '门派', '',
           '{"founder":"张三丰","characteristics":"以柔克刚"}',
                   'system', 'active', NULL)"""
    )
    await adapter.execute(
        """INSERT INTO knowledge_entities
           (id, entity_type, source_table, source_id, title, summary,
            keywords, tags, category, content_preview, properties, source_type, status, tenant_id)
           VALUES ('ph-test', 'herb', 'processed', 'ph1', '炙甘草',
                   '补脾益气', '[]', '[]', '炮制品', '',
           '{"raw_herb":"甘草","processing_method":"蜜炙","nature":"温","is_processed":true}',
                   'system', 'active', NULL)"""
    )
    await adapter.execute(
        """INSERT INTO knowledge_entities
           (id, entity_type, source_table, source_id, title, summary,
            keywords, tags, category, content_preview, properties, source_type, status, tenant_id)
           VALUES ('ke-herb-raw', 'herb', 'herbs', 'h1', '甘草',
                   '清热解毒', '[]', '[]', '补虚药', '',
           '{"nature":"平","is_processed":false}',
                   'system', 'active', NULL)"""
    )
    await adapter.execute(
        """INSERT INTO entity_relationships
           (id, source_entity_id, target_entity_id, relationship_type, properties, weight)
           VALUES ('rel-processing', 'ph-test', 'ke-herb-raw', '炮制', '{"method":"蜜炙"}', 1.0)"""
    )
    await adapter.execute(
        """INSERT INTO entity_relationships
           (id, source_entity_id, target_entity_id, relationship_type, properties, weight)
           VALUES ('rel-school', 'hp-test', 'ps-test', 'belongs_to_school', '{}', 1.0)"""
    )
    yield adapter
    await adapter.close()


class TestHealthPracticeEntities:
    @pytest.mark.asyncio
    async def test_practice_has_properties(self, practice_db):
        from app.knowledge_reader import get_entity
        e = await get_entity(practice_db, "hp-test")
        assert e is not None
        props = e["properties"]
        assert props["practice_type"] == "动功"
        assert props["difficulty"] == "入门"
        assert "core_essence" in props
        assert "breathing" in props
        assert "mental_focus" in props

    @pytest.mark.asyncio
    async def test_practice_has_steps(self, practice_db):
        from app.knowledge_reader import get_entity
        e = await get_entity(practice_db, "hp-test")
        steps = e["properties"]["steps"]
        assert len(steps) >= 1
        assert steps[0]["name"] == "双手托天"

    @pytest.mark.asyncio
    async def test_practice_has_indications(self, practice_db):
        from app.knowledge_reader import get_entity
        e = await get_entity(practice_db, "hp-test")
        assert "强身健体" in e["properties"]["indications"]

    @pytest.mark.asyncio
    async def test_school_has_founder(self, practice_db):
        from app.knowledge_reader import get_entity
        e = await get_entity(practice_db, "ps-test")
        assert e["properties"]["founder"] == "张三丰"

    @pytest.mark.asyncio
    async def test_practice_belongs_to_school(self, practice_db):
        from app.knowledge_reader import get_entity_with_relations
        result = await get_entity_with_relations(practice_db, "hp-test")
        assert "belongs_to_school" in result["relationships"]

    @pytest.mark.asyncio
    async def test_list_practices(self, practice_db):
        from app.knowledge_reader import list_entities
        result = await list_entities(practice_db, "health_practice")
        assert result["total"] == 1
        assert result["items"][0]["title"] == "八段锦"

    @pytest.mark.asyncio
    async def test_list_schools(self, practice_db):
        from app.knowledge_reader import list_entities
        result = await list_entities(practice_db, "practice_school")
        assert result["total"] == 1


class TestProcessedHerbEntities:
    @pytest.mark.asyncio
    async def test_processed_herb_is_separate_node(self, practice_db):
        from app.knowledge_reader import get_entity
        processed = await get_entity(practice_db, "ph-test")
        raw = await get_entity(practice_db, "ke-herb-raw")
        assert processed["id"] != raw["id"]
        assert processed["title"] == "炙甘草"
        assert raw["title"] == "甘草"

    @pytest.mark.asyncio
    async def test_processed_has_different_nature(self, practice_db):
        from app.knowledge_reader import get_entity
        processed = await get_entity(practice_db, "ph-test")
        raw = await get_entity(practice_db, "ke-herb-raw")
        assert processed["properties"]["nature"] == "温"
        assert raw["properties"]["nature"] == "平"

    @pytest.mark.asyncio
    async def test_processing_relationship(self, practice_db):
        from app.knowledge_reader import get_entity_with_relations
        result = await get_entity_with_relations(practice_db, "ph-test")
        assert "炮制" in result["relationships"]
        rels = result["relationships"]["炮制"]
        assert any(r["title"] == "甘草" for r in rels)

    @pytest.mark.asyncio
    async def test_processed_has_method(self, practice_db):
        from app.knowledge_reader import get_entity
        e = await get_entity(practice_db, "ph-test")
        assert e["properties"]["processing_method"] == "蜜炙"
        assert e["properties"]["raw_herb"] == "甘草"

    @pytest.mark.asyncio
    async def test_processed_category(self, practice_db):
        from app.knowledge_reader import list_entities
        result = await list_entities(practice_db, "herb", category="炮制品")
        assert result["total"] >= 1
        assert all(i["category"] == "炮制品" for i in result["items"])

    @pytest.mark.asyncio
    async def test_raw_and_processed_both_queryable(self, practice_db):
        from app.knowledge_reader import list_entities
        all_herbs = await list_entities(practice_db, "herb")
        titles = [i["title"] for i in all_herbs["items"]]
        assert "甘草" in titles
        assert "炙甘草" in titles
