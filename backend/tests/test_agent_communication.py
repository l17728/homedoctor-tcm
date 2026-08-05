"""Tests for agent_communication.py — inter-agent messaging."""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch

from app.database import SqliteAdapter, init_db, seed_safety_rules, seed_test_data
from app.agent_communication import (
    agent_message,
    agent_ask,
    agent_propose,
    agent_debate,
    auto_apply_debate_results,
    get_conversation_history,
)


@pytest_asyncio.fixture
async def comm_db():
    adapter = SqliteAdapter(":memory:")
    await adapter.connect()
    await init_db(adapter)
    await seed_safety_rules(adapter)
    await seed_test_data(adapter)
    yield adapter
    await adapter.close()


class TestAgentMessage:
    @pytest.mark.asyncio
    async def test_insert_message(self, comm_db):
        result = await agent_message(comm_db, "agent_a", "agent_b", "你好", message_type="ask")
        assert result
        rows = await comm_db.query("SELECT * FROM agent_conversations WHERE id = ?", (result,))
        assert len(rows) == 1
        assert rows[0]["content"] == "你好"

    @pytest.mark.asyncio
    async def test_with_metadata(self, comm_db):
        result = await agent_message(comm_db, "a", "b", "建议", message_type="propose",
                                     metadata={"priority": "high"})
        assert result
        rows = await comm_db.query("SELECT metadata FROM agent_conversations WHERE id = ?", (result,))
        import json
        assert json.loads(rows[0]["metadata"])["priority"] == "high"


class TestAgentAsk:
    @pytest.mark.asyncio
    async def test_ask_and_reply(self, comm_db):
        with patch("app.llm_unified.llm_chat", new_callable=AsyncMock) as mock_llm, \
             patch("app.agent_memory.memory_search", new_callable=AsyncMock) as mock_ms:
            mock_ms.return_value = []
            mock_llm.return_value = "这是回复"
            result = await agent_ask(comm_db, "agent_a", "agent_b", "什么是黄芪？")
            assert "reply_id" in result
            assert result["reply"] == "这是回复"

    @pytest.mark.asyncio
    async def test_llm_empty_reply(self, comm_db):
        with patch("app.llm_unified.llm_chat", new_callable=AsyncMock) as mock_llm, \
             patch("app.agent_memory.memory_search", new_callable=AsyncMock) as mock_ms:
            mock_ms.return_value = []
            mock_llm.return_value = ""
            result = await agent_ask(comm_db, "a", "b", "test")
            assert "question_id" in result


class TestAgentPropose:
    @pytest.mark.asyncio
    async def test_propose_saved(self, comm_db):
        result = await agent_propose(comm_db, "a", "b", "增加巡检频率")
        assert result
        rows = await comm_db.query("SELECT message_type FROM agent_conversations WHERE id = ?", (result,))
        assert rows[0]["message_type"] == "propose"


class TestAgentDebate:
    @pytest.mark.asyncio
    async def test_debate_produces_summary(self, comm_db):
        with patch("app.llm_unified.llm_chat", new_callable=AsyncMock) as mock_llm, \
             patch("app.agent_memory.memory_search", new_callable=AsyncMock) as mock_mem, \
             patch("app.agent_memory.memory_save", new_callable=AsyncMock):
            mock_mem.return_value = []
            mock_llm.return_value = '{"consensus": "达成共识", "action_items": []}'
            result = await agent_debate(comm_db, "a", "b", "测试主题", rounds=1)
            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_debate_string_response(self, comm_db):
        with patch("app.llm_unified.llm_chat", new_callable=AsyncMock) as mock_llm, \
             patch("app.agent_memory.memory_search", new_callable=AsyncMock) as mock_mem:
            mock_mem.return_value = []
            mock_llm.return_value = "无法达成共识"
            result = await agent_debate(comm_db, "a", "b", "测试", rounds=1)
            assert isinstance(result, list)


class TestAutoApplyDebateResults:
    @pytest.mark.asyncio
    async def test_chinese_pattern(self, comm_db):
        with patch("app.tools.config.tool_set_config", new_callable=AsyncMock) as mock_set:
            mock_set.return_value = {"ok": True}
            result = await auto_apply_debate_results(comm_db, "建议将knowledge_agent的temperature设置为0.5。")
            assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_english_pattern(self, comm_db):
        with patch("app.tools.config.tool_set_config", new_callable=AsyncMock) as mock_set:
            mock_set.return_value = {"ok": True}
            result = await auto_apply_debate_results(comm_db, "config: knowledge_agent.temperature = 0.8\n")
            assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_no_suggestions(self, comm_db):
        assert await auto_apply_debate_results(comm_db, "讨论了天气") == []

    @pytest.mark.asyncio
    async def test_dict_summary(self, comm_db):
        with patch("app.tools.config.tool_set_config", new_callable=AsyncMock) as mock_set:
            mock_set.return_value = {"ok": True}
            result = await auto_apply_debate_results(comm_db, {"action_items": ["建议将knowledge_agent的max_tokens设置为4096。"]})
            assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_empty(self, comm_db):
        assert await auto_apply_debate_results(comm_db, "") == []

    @pytest.mark.asyncio
    async def test_none(self, comm_db):
        assert await auto_apply_debate_results(comm_db, None) == []


class TestGetConversationHistory:
    @pytest.mark.asyncio
    async def test_returns_all(self, comm_db):
        await agent_message(comm_db, "a", "b", "m1", message_type="ask")
        await agent_message(comm_db, "a", "b", "m2", message_type="ask")
        assert len(await get_conversation_history(comm_db)) >= 2

    @pytest.mark.asyncio
    async def test_filter_by_agent(self, comm_db):
        await agent_message(comm_db, "agent_x", "b", "msg", message_type="ask")
        result = await get_conversation_history(comm_db, agent_name="agent_x")
        assert len(result) >= 1
        assert all(r["from_agent"] == "agent_x" for r in result)

    @pytest.mark.asyncio
    async def test_limit(self, comm_db):
        for i in range(10):
            await agent_message(comm_db, "a", "b", f"m{i}", message_type="ask")
        assert len(await get_conversation_history(comm_db, limit=3)) <= 3
