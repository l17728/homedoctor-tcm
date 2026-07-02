"""Comprehensive tests for agent memory, communication, CRUD completion, config, and BM25 IDF."""

import pytest
import pytest_asyncio
from app.database import SqliteAdapter, init_db, seed_safety_rules, seed_test_data


@pytest_asyncio.fixture
async def agent_db():
    adapter = SqliteAdapter(":memory:")
    await adapter.connect()
    await init_db(adapter)
    await seed_safety_rules(adapter)
    await seed_test_data(adapter)
    await adapter.execute(
        """INSERT INTO knowledge_entities
           (id, entity_type, source_table, source_id, title, summary,
            keywords, tags, category, properties, source_type, status)
           VALUES ('ke-agent-full', 'herb', 'test', 'af1', '测试药材',
                   '补气升阳', '[]', '[]', '补虚药', '{"nature":"温"}', 'system', 'active')"""
    )
    await adapter.execute(
        """INSERT INTO knowledge_entities
           (id, entity_type, source_table, source_id, title, summary,
            keywords, tags, category, properties, source_type, status)
           VALUES ('ke-agent-full2', 'herb', 'test', 'af2', '当归',
                   '补血活血', '[]', '[]', '补虚药', '{"nature":"温"}', 'system', 'active')"""
    )
    yield adapter
    await adapter.close()


class TestAgentMemory:
    @pytest.mark.asyncio
    async def test_save_and_search(self, agent_db):
        from app.agent_memory import memory_save, memory_search
        mid = await memory_save(agent_db, "knowledge_agent", "处理气功类内容应先提取呼吸方法", "experience", ["气功", "呼吸"])
        assert mid.startswith("mem-")
        results = await memory_search(agent_db, "knowledge_agent", "气功")
        assert len(results) >= 1
        assert any("呼吸方法" in r["content"] for r in results)

    @pytest.mark.asyncio
    async def test_search_includes_shared(self, agent_db):
        from app.agent_memory import memory_save, memory_search
        await memory_save(agent_db, "shared", "全局规则：B级知识不进安全引擎", "rule")
        results = await memory_search(agent_db, "knowledge_agent", "安全引擎")
        assert len(results) >= 1
        assert results[0]["agent_name"] == "shared"

    @pytest.mark.asyncio
    async def test_search_by_type(self, agent_db):
        from app.agent_memory import memory_save, memory_search
        await memory_save(agent_db, "patrol_agent", "巡检发现穴位缺少刺法", "lesson")
        await memory_save(agent_db, "patrol_agent", "每次先搜索热门实体", "strategy")
        lessons = await memory_search(agent_db, "patrol_agent", memory_type="lesson")
        strategies = await memory_search(agent_db, "patrol_agent", memory_type="strategy")
        assert len(lessons) == 1
        assert len(strategies) == 1

    @pytest.mark.asyncio
    async def test_update_confidence(self, agent_db):
        from app.agent_memory import memory_save, memory_update, memory_search
        mid = await memory_save(agent_db, "knowledge_agent", "测试记忆更新", "experience", confidence=0.3)
        await memory_update(agent_db, mid, confidence=0.9)
        results = await memory_search(agent_db, "knowledge_agent", "测试记忆更新")
        assert results[0]["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_update_increment_used(self, agent_db):
        from app.agent_memory import memory_save, memory_update, memory_search
        mid = await memory_save(agent_db, "knowledge_agent", "使用计数测试", "experience")
        await memory_update(agent_db, mid, increment_used=True)
        await memory_update(agent_db, mid, increment_used=True)
        results = await memory_search(agent_db, "knowledge_agent", "使用计数")
        assert results[0]["times_used"] == 2

    @pytest.mark.asyncio
    async def test_update_increment_success(self, agent_db):
        from app.agent_memory import memory_save, memory_update, memory_search
        mid = await memory_save(agent_db, "knowledge_agent", "成功计数测试", "experience", confidence=0.5)
        await memory_update(agent_db, mid, increment_success=True)
        results = await memory_search(agent_db, "knowledge_agent", "成功计数")
        assert results[0]["success_count"] == 1
        assert results[0]["confidence"] > 0.5

    @pytest.mark.asyncio
    async def test_share_memory(self, agent_db):
        from app.agent_memory import memory_save, memory_share, memory_search
        mid = await memory_save(agent_db, "knowledge_agent", "值得分享的经验", "experience", confidence=0.8)
        shared_id = await memory_share(agent_db, mid, "shared")
        assert shared_id.startswith("mem-")
        shared_results = await memory_search(agent_db, "shared", "值得分享")
        assert len(shared_results) >= 1

    @pytest.mark.asyncio
    async def test_consolidate_duplicates(self, agent_db):
        from app.agent_memory import memory_save, memory_consolidate
        await memory_save(agent_db, "knowledge_agent", "处理气功类内容应先提取呼吸方法步骤", "experience")
        await memory_save(agent_db, "knowledge_agent", "处理气功类内容应先提取呼吸方法步骤", "experience")
        stats = await memory_consolidate(agent_db, "knowledge_agent", similarity_threshold=0.5)
        assert stats["total"] >= 2
        assert stats["merged"] >= 1

    def test_text_overlap_identical(self):
        from app.agent_memory import _text_overlap
        assert _text_overlap("相同的内容测试", "相同的内容测试") > 0.5

    def test_text_overlap_different(self):
        from app.agent_memory import _text_overlap
        assert _text_overlap("完全不同的内容", "毫不相关的文字") < 0.3

    def test_text_overlap_empty(self):
        from app.agent_memory import _text_overlap
        assert _text_overlap("", "内容") == 0.0
        assert _text_overlap("内容", "") == 0.0


class TestAgentCommunication:
    @pytest.mark.asyncio
    async def test_message_send(self, agent_db):
        from app.agent_communication import agent_message, get_conversation_history
        mid = await agent_message(agent_db, "patrol_agent", "knowledge_agent", "发现3个缺口")
        assert mid.startswith("conv-")
        history = await get_conversation_history(agent_db)
        assert len(history) >= 1
        assert history[0]["from_agent"] == "patrol_agent"

    @pytest.mark.asyncio
    async def test_message_with_reply(self, agent_db):
        from app.agent_communication import agent_message, get_conversation_history
        qid = await agent_message(agent_db, "patrol_agent", "knowledge_agent", "哪些缺字段？", "ask")
        rid = await agent_message(agent_db, "knowledge_agent", "patrol_agent", "3个穴位缺刺法", "reply", reply_to=qid)
        history = await get_conversation_history(agent_db, "patrol_agent")
        assert len(history) >= 2

    @pytest.mark.asyncio
    async def test_propose(self, agent_db):
        from app.agent_communication import agent_message, get_conversation_history
        pid = await agent_message(agent_db, "patrol_agent", "knowledge_agent", "建议优先补全足三里", "propose")
        history = await get_conversation_history(agent_db)
        msg = [h for h in history if h["id"] == pid]
        assert len(msg) == 1
        assert msg[0]["message_type"] == "propose"

    @pytest.mark.asyncio
    async def test_history_filter_by_agent(self, agent_db):
        from app.agent_communication import agent_message, get_conversation_history
        await agent_message(agent_db, "patrol_agent", "knowledge_agent", "消息1")
        await agent_message(agent_db, "knowledge_agent", "patrol_agent", "消息2")
        patrol_history = await get_conversation_history(agent_db, "patrol_agent")
        assert len(patrol_history) >= 2

    def test_dialogue_templates_exist(self):
        from app.agent_communication import DIALOGUE_TEMPLATES
        assert "open_ended" in DIALOGUE_TEMPLATES
        assert "reflective" in DIALOGUE_TEMPLATES
        assert "exploratory" in DIALOGUE_TEMPLATES
        assert "gap_filling" in DIALOGUE_TEMPLATES
        for category, templates in DIALOGUE_TEMPLATES.items():
            assert len(templates) >= 3, f"{category} needs >= 3 templates"


class TestCRUDCompletion:
    @pytest.mark.asyncio
    async def test_delete_entity_without_confirm(self, agent_db):
        from app.agent_tools import tool_delete_entity
        result = await tool_delete_entity(agent_db, "ke-agent-full")
        assert result["deleted"] is False

    @pytest.mark.asyncio
    async def test_delete_entity_with_confirm(self, agent_db):
        from app.agent_tools import tool_delete_entity
        result = await tool_delete_entity(agent_db, "ke-agent-full", confirm=True)
        assert result["deleted"] is True
        rows = await agent_db.query("SELECT * FROM knowledge_entities WHERE id = 'ke-agent-full'")
        assert len(rows) == 0

    @pytest.mark.asyncio
    async def test_create_relationship(self, agent_db):
        from app.agent_tools import tool_create_relationship
        rid = await tool_create_relationship(agent_db, "ke-agent-full", "ke-agent-full2", "配伍")
        assert rid.startswith("rel-")
        rows = await agent_db.query("SELECT * FROM entity_relationships WHERE id = ?", (rid,))
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_delete_relationship(self, agent_db):
        from app.agent_tools import tool_create_relationship, tool_delete_relationship
        rid = await tool_create_relationship(agent_db, "ke-agent-full", "ke-agent-full2", "test_rel")
        deleted = await tool_delete_relationship(agent_db, rid)
        assert deleted is True

    @pytest.mark.asyncio
    async def test_delete_nonexistent_relationship(self, agent_db):
        from app.agent_tools import tool_delete_relationship
        deleted = await tool_delete_relationship(agent_db, "nonexistent-rel")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_list_entity_types(self, agent_db):
        from app.agent_tools import tool_list_entity_types
        types = await tool_list_entity_types(agent_db)
        assert isinstance(types, list)
        assert len(types) > 0
        assert any(t["type"] == "herb" for t in types)

    @pytest.mark.asyncio
    async def test_list_categories(self, agent_db):
        from app.agent_tools import tool_list_categories
        cats = await tool_list_categories(agent_db, "herb")
        assert isinstance(cats, list)
        assert any(c["category"] == "补虚药" for c in cats)

    @pytest.mark.asyncio
    async def test_list_categories_all_types(self, agent_db):
        from app.agent_tools import tool_list_categories
        cats = await tool_list_categories(agent_db)
        assert isinstance(cats, list)
        assert len(cats) > 0

    @pytest.mark.asyncio
    async def test_query_logs(self, agent_db):
        from app.agent_tools import log_action, tool_query_logs
        await log_action(agent_db, "test_query", "test", "", "ke-agent-full", {"key": "val"}, "tested")
        logs = await tool_query_logs(agent_db, entity_id="ke-agent-full")
        assert len(logs) >= 1
        assert logs[0]["action_type"] == "test_query"

    @pytest.mark.asyncio
    async def test_query_logs_by_action(self, agent_db):
        from app.agent_tools import log_action, tool_query_logs
        await log_action(agent_db, "specific_action", "test", "", "", {}, "done")
        logs = await tool_query_logs(agent_db, action_type="specific_action")
        assert len(logs) >= 1
        assert all(l["action_type"] == "specific_action" for l in logs)


class TestConfigTools:
    @pytest.mark.asyncio
    async def test_get_config_all(self, agent_db):
        from app.agent_tools import tool_get_config
        result = await tool_get_config(agent_db, "knowledge_agent")
        assert "config" in result
        assert "temperature" in result["config"]

    @pytest.mark.asyncio
    async def test_get_config_specific_key(self, agent_db):
        from app.agent_tools import tool_get_config
        result = await tool_get_config(agent_db, "patrol_agent", "tcm_only")
        assert result["value"] is True

    @pytest.mark.asyncio
    async def test_set_config(self, agent_db):
        from app.agent_tools import tool_set_config, tool_get_config
        result = await tool_set_config(agent_db, "knowledge_agent", "temperature", 0.5)
        assert result["old_value"] == 0.3
        assert result["new_value"] == 0.5
        verify = await tool_get_config(agent_db, "knowledge_agent", "temperature")
        assert verify["value"] == 0.5

    @pytest.mark.asyncio
    async def test_set_config_new_agent(self, agent_db):
        from app.agent_tools import tool_set_config, tool_get_config
        await tool_set_config(agent_db, "new_agent", "custom_param", "value")
        result = await tool_get_config(agent_db, "new_agent")
        assert result["config"]["custom_param"] == "value"


class TestBM25IDF:
    @pytest.mark.asyncio
    async def test_idf_rare_term_scores_higher(self, agent_db):
        from app.search_pipeline import bm25_search
        await agent_db.execute(
            """INSERT INTO knowledge_entities
               (id, entity_type, source_table, source_id, title, summary,
                keywords, tags, category, properties, source_type, status)
               VALUES ('ke-rare-1', 'herb', 'test', 'r1', '珍稀药材',
                       '非常罕见的内容', '[]', '[]', '测试', '{}', 'system', 'active')"""
        )
        rare_results = await bm25_search(agent_db, "珍稀药材", top_k=5)
        common_results = await bm25_search(agent_db, "测试药材", top_k=5)
        if rare_results and common_results:
            rare_score = rare_results[0]["bm25_score"]
            common_score = common_results[0]["bm25_score"]
            assert rare_score > 0
            assert common_score > 0

    @pytest.mark.asyncio
    async def test_bm25_returns_matched_terms(self, agent_db):
        from app.search_pipeline import bm25_search
        results = await bm25_search(agent_db, "黄芪", top_k=3)
        for r in results:
            assert "matched_terms" in r
            assert isinstance(r["matched_terms"], list)

    @pytest.mark.asyncio
    async def test_bm25_empty_query(self, agent_db):
        from app.search_pipeline import bm25_search
        assert await bm25_search(agent_db, "", top_k=5) == []
        assert await bm25_search(agent_db, "   ", top_k=5) == []

    @pytest.mark.asyncio
    async def test_bm25_source_type_field(self, agent_db):
        from app.search_pipeline import bm25_search
        results = await bm25_search(agent_db, "药材", top_k=3)
        for r in results:
            assert r.get("source_type") == "internal"
            assert r.get("source_url") is None


class TestAgentAPIEndpoints:
    @pytest.mark.asyncio
    async def test_get_memories_unauthorized(self, raw_client):
        resp = await raw_client.get("/api/admin/agent/memories")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_memories_admin(self, client):
        resp = await client.get("/api/admin/agent/memories")
        assert resp.status_code == 200
        assert "items" in resp.json()

    @pytest.mark.asyncio
    async def test_save_memory_admin(self, client):
        resp = await client.post("/api/admin/agent/memories", json={
            "agent_name": "test_agent",
            "content": "测试API保存记忆",
            "memory_type": "experience",
        })
        assert resp.status_code == 200
        assert "id" in resp.json()

    @pytest.mark.asyncio
    async def test_get_conversations_admin(self, client):
        resp = await client.get("/api/admin/agent/conversations")
        assert resp.status_code == 200
        assert "items" in resp.json()

    @pytest.mark.asyncio
    async def test_get_config_admin(self, client):
        resp = await client.get("/api/admin/agent/config?agent_name=knowledge_agent")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_set_config_admin(self, client):
        resp = await client.put("/api/admin/agent/config", json={
            "agent_name": "knowledge_agent",
            "key": "temperature",
            "value": 0.7,
        })
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_memory_admin(self, client):
        create = await client.post("/api/admin/agent/memories", json={
            "agent_name": "test",
            "content": "待删除记忆",
        })
        mid = create.json()["id"]
        resp = await client.delete(f"/api/admin/agent/memories/{mid}")
        assert resp.status_code == 200
