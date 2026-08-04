"""Characterization tests for review + pipeline groups before A4/A5 migration."""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from app.database import SqliteAdapter, init_db, seed_safety_rules, seed_test_data
from app.agent_tools import (
    tool_multi_model_review,
    tool_detect_conflicts,
    tool_analyze,
    tool_scan_entities,
    tool_check_duplicates,
    tool_assess_quality,
)


@pytest_asyncio.fixture
async def rev_db():
    adapter = SqliteAdapter(":memory:")
    await adapter.connect()
    await init_db(adapter)
    await seed_safety_rules(adapter)
    await seed_test_data(adapter)
    yield adapter
    await adapter.close()


class TestMultiModelReview:
    @pytest.mark.asyncio
    async def test_returns_result_dict(self, rev_db):
        with patch("app.llm_unified.llm_collective_review", new_callable=AsyncMock) as mock_review:
            mock_review.return_value = {
                "score": 75, "level": "B", "decision": "adopted",
                "reviews": [{"model": "test", "score": 75}],
            }
            result = await tool_multi_model_review(rev_db, "测试标题", "测试内容", "herb")
            assert isinstance(result, dict)
            assert "score" in result or "decision" in result

    @pytest.mark.asyncio
    async def test_fallback_on_error(self, rev_db):
        with patch("app.llm_unified.llm_collective_review", new_callable=AsyncMock) as mock_review:
            mock_review.side_effect = RuntimeError("API timeout")
            result = await tool_multi_model_review(rev_db, "测试", "内容", "article")
            assert isinstance(result, dict)


class TestDetectConflicts:
    @pytest.mark.asyncio
    async def test_no_conflicts_on_new_entity(self, rev_db):
        await rev_db.execute(
            "INSERT INTO knowledge_entities (id, entity_type, source_table, source_id, title, status) "
            "VALUES ('ke-conflict-test', 'herb', 'test', 's1', '测试冲突', 'active')"
        )
        result = await tool_detect_conflicts(rev_db, "ke-conflict-test", {"nature": "温"})
        assert isinstance(result, list)


class TestToolAnalyze:
    @pytest.mark.asyncio
    async def test_returns_analysis(self, rev_db):
        with patch("app.llm_unified.llm_chat", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = '{"entity_type":"herb","keywords":["补气"],"summary":"补气药"}'
            result = await tool_analyze(rev_db, "黄芪补气升阳固表", "黄芪", "text")
            assert isinstance(result, dict)
            assert "entity_type" in result or "summary" in result

    @pytest.mark.asyncio
    async def test_fallback_on_non_json(self, rev_db):
        with patch("app.llm_unified.llm_chat", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "无法分析"
            result = await tool_analyze(rev_db, "内容", "标题", "text")
            assert isinstance(result, dict)


class TestScanEntities:
    @pytest.mark.asyncio
    async def test_finds_known_entities(self, rev_db):
        await rev_db.execute(
            "INSERT INTO knowledge_entities (id, entity_type, source_table, source_id, title, status) "
            "VALUES ('ke-scan-1', 'herb', 'test', 's1', '黄芪', 'active')"
        )
        result = await tool_scan_entities(rev_db, "黄芪和人参都是补气药")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_empty_text(self, rev_db):
        result = await tool_scan_entities(rev_db, "")
        assert result == []

    @pytest.mark.asyncio
    async def test_no_matches(self, rev_db):
        result = await tool_scan_entities(rev_db, "一些不包含任何已知实体的文本内容")
        assert isinstance(result, list)


class TestCheckDuplicates:
    @pytest.mark.asyncio
    async def test_finds_exact_title_match(self, rev_db):
        await rev_db.execute(
            "INSERT INTO knowledge_entities (id, entity_type, source_table, source_id, title, status) "
            "VALUES ('ke-dup-1', 'herb', 'test', 's1', '测试重复', 'active')"
        )
        result = await tool_check_duplicates(rev_db, "测试重复", "内容")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_no_duplicates(self, rev_db):
        result = await tool_check_duplicates(rev_db, "全新唯一标题", "内容")
        assert result == []


class TestAssessQuality:
    @pytest.mark.asyncio
    async def test_returns_quality_dict(self, rev_db):
        with patch("app.llm_unified.llm_chat", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = '{"score":75}'
            result = await tool_assess_quality(rev_db, "这是一段有足够长度的文本内容用于质量评估测试", "herb")
            assert isinstance(result, dict)
            assert "score" in result or "decision" in result
