"""Characterization tests for entities+relationships group before A3 migration.

Covers: tool_auto_relate (previously untested), tool_create_relationship,
tool_delete_relationship, tool_record_provenance, tool_generate_summary,
tool_delete_entity, tool_list_entity_types, tool_list_categories.
"""
import pytest
import pytest_asyncio
from app.database import SqliteAdapter, init_db, seed_safety_rules, seed_test_data
from app.agent_tools import (
    tool_auto_relate,
    tool_create_relationship,
    tool_delete_relationship,
    tool_record_provenance,
    tool_generate_summary,
    tool_delete_entity,
    tool_list_entity_types,
    tool_list_categories,
)


@pytest_asyncio.fixture
async def ent_db():
    adapter = SqliteAdapter(":memory:")
    await adapter.connect()
    await init_db(adapter)
    await seed_safety_rules(adapter)
    await seed_test_data(adapter)
    for i, name in enumerate(["黄芪", "人参", "白术", "当归", "甘草"]):
        await adapter.execute(
            "INSERT INTO knowledge_entities (id, entity_type, source_table, source_id, title, summary, category, status) "
            "VALUES (?, 'herb', 'test', ?, ?, ?, '补气药', 'active')",
            (f"ke-herb-{i}", f"src-{i}", name, f"{name}的功效与作用"),
        )
    yield adapter
    await adapter.close()


class TestAutoRelate:
    @pytest.mark.asyncio
    async def test_creates_relations_to_similar_entities(self, ent_db):
        result = await tool_auto_relate(
            ent_db, "ke-herb-0", "herb", "黄芪", "补气升阳",
        )
        assert isinstance(result, list)
        assert len(result) <= 5

    @pytest.mark.asyncio
    async def test_no_relations_when_only_self(self, ent_db):
        await ent_db.execute("DELETE FROM knowledge_entities WHERE id != 'ke-herb-0'")
        result = await tool_auto_relate(
            ent_db, "ke-herb-0", "herb", "黄芪", "补气",
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_respects_max_relations(self, ent_db):
        result = await tool_auto_relate(
            ent_db, "ke-herb-0", "herb", "黄芪", "补气",
            max_relations=2,
        )
        assert len(result) <= 2

    @pytest.mark.asyncio
    async def test_with_content_text(self, ent_db):
        result = await tool_auto_relate(
            ent_db, "ke-herb-0", "herb", "黄芪", "补气",
            content="黄芪补气升阳，固表止汗，用于气虚乏力",
        )
        assert isinstance(result, list)


class TestRelationships:
    @pytest.mark.asyncio
    async def test_create_and_delete_relationship(self, ent_db):
        rel_id = await tool_create_relationship(
            ent_db, "ke-herb-0", "ke-herb-1", "配伍", {"reason": "相须为用"},
        )
        assert rel_id
        assert isinstance(rel_id, str)

        deleted = await tool_delete_relationship(ent_db, rel_id)
        assert deleted is True


class TestProvenance:
    @pytest.mark.asyncio
    async def test_record_provenance(self, ent_db):
        result = await tool_record_provenance(
            ent_db, "ke-herb-0", "system", "", "黄芪",
            trust_level="S", trust_score=95,
        )
        assert result  # returns provenance ID

    @pytest.mark.asyncio
    async def test_record_provenance_with_details(self, ent_db):
        result = await tool_record_provenance(
            ent_db, "ke-herb-0", "web", "https://example.com", "测试",
            trust_level="B", trust_score=60,
            review_details={"reviews": [], "conflicts": 0},
        )
        assert result


class TestGenerateSummary:
    def test_short_text(self):
        result = tool_generate_summary("短文本")
        assert isinstance(result, str)

    def test_long_text_truncated(self):
        long_text = "这是一段很长的文本。" * 100
        result = tool_generate_summary(long_text)
        assert len(result) <= 200

    def test_empty_text(self):
        result = tool_generate_summary("")
        assert isinstance(result, str)


class TestDeleteEntity:
    @pytest.mark.asyncio
    async def test_delete_without_confirm_raises(self, ent_db):
        result = await tool_delete_entity(ent_db, "ke-herb-0", confirm=False)
        assert "error" in result or "confirm" in str(result).lower()

    @pytest.mark.asyncio
    async def test_delete_with_confirm(self, ent_db):
        result = await tool_delete_entity(ent_db, "ke-herb-1", confirm=True)
        assert result.get("deleted") is True or "deleted" in str(result).lower()

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, ent_db):
        result = await tool_delete_entity(ent_db, "ke-nonexistent", confirm=True)
        assert result.get("deleted") is False or "error" in result


class TestListTypes:
    @pytest.mark.asyncio
    async def test_list_entity_types(self, ent_db):
        result = await tool_list_entity_types(ent_db)
        assert isinstance(result, list)
        assert len(result) > 0


class TestListCategories:
    @pytest.mark.asyncio
    async def test_list_all_categories(self, ent_db):
        result = await tool_list_categories(ent_db)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_list_by_type(self, ent_db):
        result = await tool_list_categories(ent_db, entity_type="herb")
        assert isinstance(result, list)
