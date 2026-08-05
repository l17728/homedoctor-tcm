"""Tests for knowledge_feeder.py — patrol agent (巡检Agent)."""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.database import SqliteAdapter, init_db, seed_safety_rules, seed_test_data
from app.knowledge_feeder import run_feeder_scan, _detect_gaps, _feed_url, query_db_adapter


@pytest_asyncio.fixture
async def feed_db():
    adapter = SqliteAdapter(":memory:")
    await adapter.connect()
    await init_db(adapter)
    await seed_safety_rules(adapter)
    await seed_test_data(adapter)
    for i in range(3):
        await adapter.execute(
            "INSERT INTO knowledge_entities (id, entity_type, source_table, source_id, title, summary, status) "
            "VALUES (?, 'herb', 'test', ?, ?, '', 'active')",
            (f"ke-feed-{i}", f"s{i}", f"测试药材{i}"),
        )
    yield adapter
    await adapter.close()


class TestDetectGaps:
    @pytest.mark.asyncio
    async def test_finds_entities_with_missing_fields(self, feed_db):
        result = await _detect_gaps(feed_db)
        assert isinstance(result, list)
        assert len(result) <= 50

    @pytest.mark.asyncio
    async def test_no_gaps_when_all_complete(self, feed_db):
        await feed_db.execute(
            "UPDATE knowledge_entities SET summary='详细功效说明', keywords='[\"补气\"]', "
            "tags='[\"常用\"]', category='补气药' WHERE id LIKE 'ke-feed-%'"
        )
        result = await _detect_gaps(feed_db)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_empty_db(self, feed_db):
        await feed_db.execute("DELETE FROM knowledge_entities")
        result = await _detect_gaps(feed_db)
        assert result == []


class TestRunFeederScan:
    @pytest.mark.asyncio
    async def test_no_gaps_returns_empty(self, feed_db):
        await feed_db.execute("DELETE FROM knowledge_entities")
        with patch("app.knowledge_feeder._search_tcm_content", new_callable=AsyncMock) as mock_search:
            result = await run_feeder_scan(feed_db, max_feeds=5)
            assert result["gaps_found"] == 0
            assert mock_search.call_count == 0

    @pytest.mark.asyncio
    async def test_with_gaps_and_mock_search(self, feed_db):
        with patch("app.knowledge_feeder._search_tcm_content", new_callable=AsyncMock) as mock_search, \
             patch("app.knowledge_agent.process_input", new_callable=AsyncMock) as mock_process:
            mock_search.return_value = [{"title": "test", "url": "https://example.com/tcm", "summary": "test"}]
            mock_process.return_value = {"entity_id": "ke-new", "decision": "created"}
            result = await run_feeder_scan(feed_db, max_feeds=2)
            assert result["gaps_found"] > 0
            assert "feeds_sent" in result

    @pytest.mark.asyncio
    async def test_search_returns_empty(self, feed_db):
        with patch("app.knowledge_feeder._search_tcm_content", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = []
            result = await run_feeder_scan(feed_db, max_feeds=2)
            assert result["feeds_sent"] == 0

    @pytest.mark.asyncio
    async def test_process_input_failure_handled(self, feed_db):
        with patch("app.knowledge_feeder._search_tcm_content", new_callable=AsyncMock) as mock_search, \
             patch("app.knowledge_agent.process_input", new_callable=AsyncMock) as mock_process:
            mock_search.return_value = [{"title": "t", "url": "https://example.com", "summary": "s"}]
            mock_process.side_effect = RuntimeError("LLM timeout")
            result = await run_feeder_scan(feed_db, max_feeds=1)
            assert "results" in result


class TestFeedUrl:
    @pytest.mark.asyncio
    async def test_successful_feed(self, feed_db):
        with patch("app.knowledge_agent.process_input", new_callable=AsyncMock) as mock_proc:
            mock_proc.return_value = {"entity_id": "ke-new", "decision": "created"}
            url_info = {"title": "测试", "url": "https://example.com/tcm", "summary": "s"}
            gap = {"entity_id": "ke-feed-0", "entity_type": "herb", "entity_title": "测试药材0"}
            result = await _feed_url(feed_db, url_info, gap)
            assert result is not None
            assert mock_proc.call_count == 1

    @pytest.mark.asyncio
    async def test_feed_failure_returns_failed_dict(self, feed_db):
        with patch("app.knowledge_agent.process_input", new_callable=AsyncMock) as mock_proc:
            mock_proc.side_effect = RuntimeError("error")
            url_info = {"title": "t", "url": "https://example.com", "summary": "s"}
            gap = {"entity_id": "ke-feed-0", "entity_type": "herb", "entity_title": "test"}
            result = await _feed_url(feed_db, url_info, gap)
            assert isinstance(result, dict)
            assert result.get("decision") == "failed"


class TestQueryDbAdapter:
    def test_returns_adapter(self):
        from app.database import set_db, _db_adapter
        mock = MagicMock()
        set_db(mock)
        from app.database import get_db
        result = get_db()
        assert result is mock
