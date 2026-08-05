"""Tests for tools/review.py — multi-model review + conflict detection."""
import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.database import SqliteAdapter, init_db, seed_safety_rules, seed_test_data
from app.tools.review import (
    tool_multi_model_review,
    tool_detect_conflicts,
    _parse_review_json,
    _resolve_conflict,
)


@pytest_asyncio.fixture
async def rev_db():
    adapter = SqliteAdapter(":memory:")
    await adapter.connect()
    await init_db(adapter)
    await seed_safety_rules(adapter)
    await seed_test_data(adapter)
    await adapter.execute(
        "INSERT INTO knowledge_entities (id, entity_type, source_table, source_id, title, summary, properties, status) "
        "VALUES ('ke-rev-test', 'herb', 'test', 's1', '测试药材', '摘要', "
        "'{\"dosage_min_g\":3.0,\"dosage_max_g\":10.0,\"nature\":\"温\",\"toxicity\":\"无毒\"}', 'active')"
    )
    yield adapter
    await adapter.close()


class TestParseReviewJson:
    def test_valid_json(self):
        result = _parse_review_json('{"medical_accuracy": 80, "recommendation": "adopt"}')
        assert result.get("medical_accuracy") == 80

    def test_empty_string(self):
        assert _parse_review_json("") == {}

    def test_none(self):
        assert _parse_review_json(None) == {}

    def test_embedded_json(self):
        result = _parse_review_json('评分结果：{"medical_accuracy": 70} 以上')
        assert result.get("medical_accuracy") == 70

    def test_non_json_returns_review(self):
        result = _parse_review_json("无法解析为JSON")
        assert result.get("recommendation") == "review"


class TestResolveConflict:
    def test_dosage_min_keeps_higher(self):
        result = _resolve_conflict("dosage_min_g", 3.0, 5.0)
        assert result["keep"] == 5.0
        assert "保守" in result["reason"]

    def test_dosage_max_keeps_lower(self):
        result = _resolve_conflict("dosage_max_g", 15.0, 10.0)
        assert result["keep"] == 10.0

    def test_non_numeric_dosage(self):
        result = _resolve_conflict("dosage_min_g", "高", "低")
        assert result["keep"] == "高"

    def test_nature_keeps_old(self):
        result = _resolve_conflict("nature", "温", "寒")
        assert result["keep"] == "温"
        assert "异说" in result["reason"]


class TestMultiModelReview:
    @pytest.mark.asyncio
    async def test_no_models(self, rev_db):
        with patch("app.model_registry.get_default_models", new_callable=AsyncMock) as mock:
            mock.return_value = []
            result = await tool_multi_model_review(rev_db, "测试", "内容")
            assert result["score"] == 50
            assert result["decision"] == "pending_review"

    @pytest.mark.asyncio
    async def test_with_mock_models(self, rev_db):
        mock_models = [{"name": "m1", "model_id": "m1", "api_key": "k"}]
        mock_review = '{"medical_accuracy": 80, "completeness": 70, "source_reliability": 75, "recommendation": "adopt"}'

        with patch("app.model_registry.get_default_models", new_callable=AsyncMock) as mock_md, \
             patch("app.model_registry.call_model_direct", new_callable=AsyncMock) as mock_call:
            mock_md.return_value = mock_models
            mock_call.return_value = mock_review
            result = await tool_multi_model_review(rev_db, "黄芪", "补气药")
            assert "score" in result
            assert "reviews" in result
            assert len(result["reviews"]) >= 1

    @pytest.mark.asyncio
    async def test_model_exception_handled(self, rev_db):
        with patch("app.model_registry.get_default_models", new_callable=AsyncMock) as mock_md, \
             patch("app.model_registry.call_model_direct", new_callable=AsyncMock) as mock_call:
            mock_md.return_value = [{"name": "m1", "model_id": "m1", "api_key": "k"}]
            mock_call.side_effect = RuntimeError("API error")
            result = await tool_multi_model_review(rev_db, "test", "content")
            assert isinstance(result, dict)
            assert result.get("reviews", []) == []


class TestDetectConflicts:
    @pytest.mark.asyncio
    async def test_no_conflicts_same_values(self, rev_db):
        result = await tool_detect_conflicts(rev_db, "ke-rev-test", {
            "dosage_min_g": 3.0, "dosage_max_g": 10.0, "nature": "温"
        })
        assert result == []

    @pytest.mark.asyncio
    async def test_dosage_conflict(self, rev_db):
        result = await tool_detect_conflicts(rev_db, "ke-rev-test", {
            "dosage_min_g": 5.0,
        })
        assert len(result) == 1
        assert result[0]["field"] == "dosage_min_g"
        assert result[0]["type"] == "数值冲突"

    @pytest.mark.asyncio
    async def test_nature_conflict(self, rev_db):
        result = await tool_detect_conflicts(rev_db, "ke-rev-test", {
            "nature": "寒",
        })
        assert len(result) == 1
        assert result[0]["type"] == "属性冲突"

    @pytest.mark.asyncio
    async def test_multiple_conflicts(self, rev_db):
        result = await tool_detect_conflicts(rev_db, "ke-rev-test", {
            "dosage_min_g": 1.0, "dosage_max_g": 20.0, "nature": "寒", "toxicity": "有毒"
        })
        assert len(result) >= 3

    @pytest.mark.asyncio
    async def test_nonexistent_entity(self, rev_db):
        result = await tool_detect_conflicts(rev_db, "ke-nonexistent", {"nature": "温"})
        assert result == []

    @pytest.mark.asyncio
    async def test_no_overlapping_fields(self, rev_db):
        result = await tool_detect_conflicts(rev_db, "ke-rev-test", {"category": "解表药"})
        assert result == []

    @pytest.mark.asyncio
    async def test_conflict_persisted_to_db(self, rev_db):
        await tool_detect_conflicts(rev_db, "ke-rev-test", {"nature": "寒"})
        rows = await rev_db.query("SELECT * FROM knowledge_conflicts WHERE entity_id = ?", ("ke-rev-test",))
        assert len(rows) >= 1
        assert rows[0]["field"] == "nature"
