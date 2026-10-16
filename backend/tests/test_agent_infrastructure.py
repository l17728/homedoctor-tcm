"""Tests for model registry, agent tools, and knowledge agent pipeline."""

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
           VALUES ('ke-agent-test', 'herb', 'test', 'at1', '测试中药',
                   '测试功效', '[]', '[]', '测试', '{"nature":"温"}', 'system', 'active')"""
    )
    yield adapter
    await adapter.close()


class TestModelRegistry:
    @pytest.mark.asyncio
    async def test_create_and_list_model(self, agent_db):
        from app.model_registry import create_model, list_models
        mid = await create_model(agent_db, name="测试模型", provider="test",
                                  model_id="test-1", api_endpoint="http://test",
                                  api_key="key123", capabilities=["text", "vision"])
        assert mid.startswith("model-")
        models = await list_models(agent_db)
        assert len(models) >= 1
        assert any(m["name"] == "测试模型" for m in models)

    @pytest.mark.asyncio
    async def test_update_model(self, agent_db):
        from app.model_registry import create_model, update_model, get_model
        mid = await create_model(agent_db, name="原模型", provider="test", model_id="m1")
        updated = await update_model(agent_db, mid, name="更新模型", enabled=False)
        assert updated is True
        model = await get_model(agent_db, mid)
        assert model["name"] == "更新模型"
        assert model["enabled"] is False

    @pytest.mark.asyncio
    async def test_delete_model(self, agent_db):
        from app.model_registry import create_model, delete_model, get_model
        mid = await create_model(agent_db, name="删除模型", provider="test", model_id="m2")
        assert await delete_model(agent_db, mid) is True
        assert await get_model(agent_db, mid) is None

    @pytest.mark.asyncio
    async def test_get_default_models(self, agent_db):
        from app.model_registry import create_model, get_default_models
        await create_model(agent_db, name="默认文本", provider="p1", model_id="d1",
                          capabilities=["text"], is_default=True)
        await create_model(agent_db, name="视觉模型", provider="p2", model_id="v1",
                          capabilities=["vision"], is_default=True)
        text_models = await get_default_models(agent_db, "text")
        vision_models = await get_default_models(agent_db, "vision")
        assert any(m["name"] == "默认文本" for m in text_models)
        assert any(m["name"] == "视觉模型" for m in vision_models)

    @pytest.mark.asyncio
    async def test_api_key_masked_in_list(self, agent_db):
        from app.model_registry import create_model, list_models
        await create_model(agent_db, name="密钥测试", provider="t", model_id="k1",
                          api_key="sk-1234567890abcdef")
        models = await list_models(agent_db)
        target = [m for m in models if m["name"] == "密钥测试"][0]
        assert "***" in target["api_key"]
        assert "1234567890abcdef" not in target["api_key"]

    @pytest.mark.asyncio
    async def test_legacy_plaintext_model_key_is_migrated(self, agent_db, monkeypatch):
        from app.model_registry import create_model, get_default_models, migrate_stored_api_keys

        mid = await create_model(agent_db, name="旧密钥模型", provider="test", model_id="legacy")
        await agent_db.execute("UPDATE ai_models SET api_key = ? WHERE id = ?", ("legacy-key-plain", mid))

        assert await migrate_stored_api_keys(agent_db) == 1
        stored = await agent_db.query_one("SELECT api_key FROM ai_models WHERE id = ?", (mid,))
        assert stored["api_key"].startswith("hde1:")
        model = next(item for item in await get_default_models(agent_db) if item["id"] == mid)
        assert model["api_key"] == "legacy-key-plain"

    @pytest.mark.asyncio
    async def test_model_key_reencrypted_during_secret_rotation(self, agent_db, monkeypatch):
        from app.config import settings
        from app.model_registry import create_model, get_default_models, migrate_stored_api_keys

        old_key = settings.SECRET_KEY
        new_key = "test-new-app-secret-key-for-model-rotation"
        monkeypatch.setattr(settings, "SECRET_KEY", "test-old-app-secret-key-for-model-rotation")
        mid = await create_model(
            agent_db, name="轮换密钥模型", provider="test", model_id="rotation",
            api_key="rotation-secret",
        )
        monkeypatch.setattr(settings, "SECRET_KEY", new_key)
        monkeypatch.setenv("HOMEDOCTOR_PREVIOUS_SECRET_KEY", "test-old-app-secret-key-for-model-rotation")

        assert await migrate_stored_api_keys(agent_db) == 1
        model = next(item for item in await get_default_models(agent_db) if item["id"] == mid)
        assert model["api_key"] == "rotation-secret"
        monkeypatch.setattr(settings, "SECRET_KEY", old_key)

    @pytest.mark.asyncio
    async def test_multi_model_vote_no_models(self, agent_db):
        from app.model_registry import multi_model_vote
        result = await multi_model_vote(agent_db, [{"role": "user", "content": "test"}])
        assert result["models_used"] == 0
        assert result["consensus"] == ""


class TestAgentTools:
    @pytest.mark.asyncio
    async def test_log_action(self, agent_db):
        from app.agent_tools import log_action
        log_id = await log_action(agent_db, "test_action", "text", "test_ref",
                                   "ke-agent-test", {"key": "val"}, "tested")
        assert log_id.startswith("log-")
        rows = await agent_db.query("SELECT * FROM agent_logs WHERE id = ?", (log_id,))
        assert len(rows) == 1
        assert rows[0]["action_type"] == "test_action"
        assert rows[0]["decision"] == "tested"

    @pytest.mark.asyncio
    async def test_tool_extract_text(self, agent_db):
        from app.agent_tools import tool_extract
        result = await tool_extract(agent_db, content="这是一段测试内容", source_type="text")
        assert result["text"] == "这是一段测试内容"
        assert result["decision"] == "extracted"

    @pytest.mark.asyncio
    async def test_tool_extract_empty(self, agent_db):
        from app.agent_tools import tool_extract
        result = await tool_extract(agent_db, content="", source_type="text")
        assert result["decision"] == "skipped_empty"

    @pytest.mark.asyncio
    async def test_tool_check_duplicates_exact(self, agent_db):
        from app.agent_tools import tool_check_duplicates
        dups = await tool_check_duplicates(agent_db, "测试中药", "测试内容")
        assert len(dups) >= 1
        assert any(d.get("title") == "测试中药" for d in dups)

    @pytest.mark.asyncio
    async def test_tool_check_duplicates_none(self, agent_db):
        from app.agent_tools import tool_check_duplicates
        dups = await tool_check_duplicates(agent_db, "不存在的中药xyz", "无匹配内容")
        assert len(dups) == 0 or all(d.get("title") != "不存在的中药xyz" for d in dups)

    @pytest.mark.asyncio
    async def test_tool_assess_quality_good(self, agent_db):
        from app.agent_tools import tool_assess_quality
        long_text = "这是一段很长的中医药知识内容。" * 50
        result = await tool_assess_quality(agent_db, long_text, "herb")
        assert result["score"] >= 50
        assert result["decision"] in ("auto_adopted", "pending_review")

    @pytest.mark.asyncio
    async def test_tool_assess_quality_empty(self, agent_db):
        from app.agent_tools import tool_assess_quality
        result = await tool_assess_quality(agent_db, "", "article")
        assert result["score"] == 0
        assert result["decision"] == "rejected"

    @pytest.mark.asyncio
    async def test_tool_create_entity(self, agent_db):
        from app.agent_tools import tool_create_or_update_entity
        result = await tool_create_or_update_entity(
            agent_db, entity_type="article", title="测试文章",
            summary="测试摘要", properties={"source": "test"},
        )
        assert result["entity_id"]
        assert result["decision"] == "created"

    @pytest.mark.asyncio
    async def test_tool_merge_entity(self, agent_db):
        from app.agent_tools import tool_create_or_update_entity
        duplicates = [{"id": "ke-agent-test", "title": "测试中药"}]
        result = await tool_create_or_update_entity(
            agent_db, entity_type="herb", title="测试中药",
            summary="更新后的更长摘要内容", properties={"new_field": "new_value"},
            duplicates=duplicates,
        )
        assert result["decision"] == "merged"
        assert result["entity_id"] == "ke-agent-test"

    @pytest.mark.asyncio
    async def test_tool_build_index(self, agent_db):
        from app.agent_tools import tool_build_index
        result = await tool_build_index(agent_db, "ke-agent-test")
        assert "chunks" in result
        assert "embedded" in result

    @pytest.mark.asyncio
    async def test_tool_push_to_modules(self, agent_db):
        from app.agent_tools import tool_push_to_modules
        pushed = await tool_push_to_modules(agent_db, "ke-agent-test", "herb")
        assert "safety_engine" in pushed
        assert "formulation_engine" in pushed


class TestKnowledgeAgent:
    @pytest.mark.asyncio
    async def test_process_text_input(self, agent_db):
        from app.knowledge_agent import process_input
        result = await process_input(
            agent_db,
            content="黄芪性甘微温，归脾肺经，具有补气升阳、固表止汗的功效。" * 10,
            title="黄芪功效详解",
            source_type="text",
        )
        assert result["decision"] in ("created", "merged", "auto_adopted", "pending_review")
        assert result["entity_id"]

    @pytest.mark.asyncio
    async def test_process_empty_input(self, agent_db):
        from app.knowledge_agent import process_input
        result = await process_input(agent_db, content="", source_type="text")
        assert result["decision"] == "skipped_empty"

    @pytest.mark.asyncio
    async def test_process_logs_to_agent_logs(self, agent_db):
        from app.knowledge_agent import process_input
        await process_input(
            agent_db,
            content="当归补血活血，调经止痛。" * 10,
            title="当归功效",
        )
        rows = await agent_db.query("SELECT * FROM agent_logs")
        assert len(rows) >= 3
        action_types = [r["action_type"] for r in rows]
        assert "pipeline_start" in action_types
        assert "pipeline_end" in action_types

    @pytest.mark.asyncio
    async def test_pipeline_never_raises(self, agent_db):
        from app.knowledge_agent import process_input
        result = await process_input(agent_db, content="x", url="http://nonexistent.invalid")
        assert "decision" in result
        assert "message" in result


class TestModelRegistryRouter:
    @pytest.mark.asyncio
    async def test_list_models_unauthorized(self, db):
        from httpx import ASGITransport, AsyncClient
        import app.database as db_mod
        import app.main as main_mod
        db_mod.set_db(db)
        transport = ASGITransport(app=main_mod.app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/models")
            assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_and_list_model(self, client):
        resp = await client.post("/api/models", json={
            "name": "Kimi-K2", "provider": "moonshot",
            "model_id": "moonshot/kimi-k2",
            "api_endpoint": "https://api.moonshot.cn/v1/chat/completions",
            "api_key": "test-key",
            "capabilities": ["text"],
        })
        assert resp.status_code == 200
        resp2 = await client.get("/api/models")
        assert resp2.status_code == 200
        assert any(m["name"] == "Kimi-K2" for m in resp2.json()["items"])

    @pytest.mark.asyncio
    async def test_agent_logs_empty(self, client):
        resp = await client.get("/api/agent/logs")
        assert resp.status_code == 200
        assert "items" in resp.json()

    @pytest.mark.asyncio
    async def test_agent_process_text(self, client):
        resp = await client.post("/api/agent/process", json={
            "content": "枸杞子性平味甘，归肝肾经，具有滋补肝肾、益精明目的功效。" * 10,
            "title": "枸杞子",
            "source_type": "text",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "decision" in data
        assert "entity_id" in data
