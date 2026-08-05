"""Step A1 tests: config/evolution group — 6 untested functions.

These tests are written BEFORE the refactoring to serve as characterization tests.
They must pass before AND after the code moves to tools/config.py.

Coverage:
- tool_optimize_prompt: happy path + LLM mock + empty lessons
- tool_apply_prompt_optimization: modifications + additions + empty suggestions
- tool_optimize_and_apply: combined flow + no actionable items
- tool_generalize_experience: happy path + LLM returns non-JSON
- memory_save_tool: saves to agent_memories table
- _load_configs_from_db: loads from agent_configs + merges into defaults + handles corrupt JSON
"""
import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.database import SqliteAdapter, init_db, seed_safety_rules, seed_test_data
from app.agent_tools import (
    tool_optimize_prompt,
    tool_apply_prompt_optimization,
    tool_optimize_and_apply,
    tool_generalize_experience,
    memory_save_tool,
    _load_configs_from_db,
    tool_get_config,
    tool_set_config,
    _AGENT_CONFIGS,
)


@pytest_asyncio.fixture
async def cfg_db():
    from app.tools.config import _AGENT_CONFIGS
    original = {k: dict(v) for k, v in _AGENT_CONFIGS.items()}
    adapter = SqliteAdapter(":memory:")
    await adapter.connect()
    await init_db(adapter)
    await seed_safety_rules(adapter)
    await seed_test_data(adapter)
    yield adapter
    _AGENT_CONFIGS.clear()
    _AGENT_CONFIGS.update(original)
    await adapter.close()


# ========================= _load_configs_from_db =========================

class TestLoadConfigsFromDb:
    @pytest.mark.asyncio
    async def test_loads_from_db_and_merges(self, cfg_db):
        await cfg_db.execute(
            "INSERT INTO agent_configs (agent_name, config_key, config_value, updated_at) VALUES (?, ?, ?, datetime('now'))",
            ("knowledge_agent", "custom_key", json.dumps(42)),
        )
        original = _AGENT_CONFIGS.get("knowledge_agent", {}).get("temperature")
        await _load_configs_from_db(cfg_db)
        assert _AGENT_CONFIGS["knowledge_agent"]["custom_key"] == 42
        assert _AGENT_CONFIGS["knowledge_agent"]["temperature"] == original

    @pytest.mark.asyncio
    async def test_loads_new_agent(self, cfg_db):
        await cfg_db.execute(
            "INSERT INTO agent_configs (agent_name, config_key, config_value, updated_at) VALUES (?, ?, ?, datetime('now'))",
            ("new_agent", "enabled", json.dumps(True)),
        )
        await _load_configs_from_db(cfg_db)
        assert _AGENT_CONFIGS.get("new_agent", {}).get("enabled") is True

    @pytest.mark.asyncio
    async def test_skips_corrupt_json(self, cfg_db):
        await cfg_db.execute(
            "INSERT INTO agent_configs (agent_name, config_key, config_value, updated_at) VALUES (?, ?, ?, datetime('now'))",
            ("knowledge_agent", "bad_key", "not_json{"),
        )
        await _load_configs_from_db(cfg_db)
        assert "bad_key" not in _AGENT_CONFIGS.get("knowledge_agent", {})

    @pytest.mark.asyncio
    async def test_empty_table_no_crash(self, cfg_db):
        await _load_configs_from_db(cfg_db)
        assert "knowledge_agent" in _AGENT_CONFIGS


# ========================= memory_save_tool =========================

class TestMemorySaveTool:
    @pytest.mark.asyncio
    async def test_saves_to_agent_memories(self, cfg_db):
        result = await memory_save_tool(cfg_db, "test_agent", "测试经验", "experience", 0.8)
        assert result  # returns memory ID

        rows = await cfg_db.query(
            "SELECT * FROM agent_memories WHERE agent_name = ? AND content = ?",
            ("test_agent", "测试经验"),
        )
        assert len(rows) == 1
        assert rows[0]["memory_type"] == "experience"
        assert rows[0]["confidence"] == 0.8

    @pytest.mark.asyncio
    async def test_default_confidence(self, cfg_db):
        result = await memory_save_tool(cfg_db, "test_agent", "默认置信度")
        assert result
        rows = await cfg_db.query("SELECT confidence FROM agent_memories WHERE id = ?", (result,))
        assert rows[0]["confidence"] == 0.5

    @pytest.mark.asyncio
    async def test_empty_content(self, cfg_db):
        result = await memory_save_tool(cfg_db, "test_agent", "", "experience", 0.1)
        assert result  # still saves


# ========================= tool_optimize_prompt =========================

class TestToolOptimizePrompt:
    @pytest.mark.asyncio
    async def test_returns_suggestions_dict(self, cfg_db):
        mock_response = '{"additions": ["新规则1"], "deletions": [], "modifications": [{"field": "temp", "old": 0.3, "new": 0.5}]}'
        with patch("app.llm_unified.llm_chat", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_response
            result = await tool_optimize_prompt(cfg_db, "knowledge_agent", "你是一个知识提取Agent")
            assert isinstance(result, dict)
            assert "additions" in result or "raw_suggestions" in result

    @pytest.mark.asyncio
    async def test_returns_raw_on_non_json(self, cfg_db):
        with patch("app.llm_unified.llm_chat", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "这不是JSON格式"
            result = await tool_optimize_prompt(cfg_db, "knowledge_agent", "test prompt")
            assert "raw_suggestions" in result
            assert isinstance(result["raw_suggestions"], str)

    @pytest.mark.asyncio
    async def test_saves_memory_after_optimize(self, cfg_db):
        with patch("app.llm_unified.llm_chat", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = '{"additions": []}'
            await tool_optimize_prompt(cfg_db, "knowledge_agent", "test")
            rows = await cfg_db.query(
                "SELECT * FROM agent_memories WHERE agent_name = ? AND content LIKE ?",
                ("knowledge_agent", "%提示词优化%"),
            )
            assert len(rows) >= 1


# ========================= tool_apply_prompt_optimization =========================

class TestToolApplyPromptOptimization:
    @pytest.mark.asyncio
    async def test_applies_modifications(self, cfg_db):
        suggestions = {
            "modifications": [
                {"field": "temperature", "new_value": 0.7},
                {"field": "max_tokens", "new": 4096},
            ],
            "additions": [],
        }
        result = await tool_apply_prompt_optimization(cfg_db, "knowledge_agent", suggestions)
        assert result["applied_count"] == 2
        assert result["agent"] == "knowledge_agent"

        config = await tool_get_config(cfg_db, "knowledge_agent")
        assert config["config"]["prompt_temperature"] == 0.7
        assert config["config"]["prompt_max_tokens"] == 4096

    @pytest.mark.asyncio
    async def test_applies_additions(self, cfg_db):
        suggestions = {
            "modifications": [],
            "additions": ["注意处理特殊字符", "总是返回中文"],
        }
        result = await tool_apply_prompt_optimization(cfg_db, "knowledge_agent", suggestions)
        assert result["applied_count"] == 2

        config = await tool_get_config(cfg_db, "knowledge_agent")
        assert config["config"]["prompt_addition_0"] == "注意处理特殊字符"
        assert config["config"]["prompt_addition_1"] == "总是返回中文"

    @pytest.mark.asyncio
    async def test_empty_suggestions(self, cfg_db):
        result = await tool_apply_prompt_optimization(cfg_db, "test_agent", {})
        assert result["applied_count"] == 0

    @pytest.mark.asyncio
    async def test_skips_null_values(self, cfg_db):
        suggestions = {
            "modifications": [{"field": None, "new_value": 1}],
            "additions": [],
        }
        result = await tool_apply_prompt_optimization(cfg_db, "test_agent", suggestions)
        assert result["applied_count"] == 0


# ========================= tool_optimize_and_apply =========================

class TestToolOptimizeAndApply:
    @pytest.mark.asyncio
    async def test_combines_optimize_and_apply(self, cfg_db):
        mock_response = '{"additions": ["规则A"], "modifications": [{"field": "temp", "new": 0.5}]}'
        with patch("app.llm_unified.llm_chat", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_response
            result = await tool_optimize_and_apply(cfg_db, "knowledge_agent", "test prompt")
            assert "suggestions" in result
            assert "applied" in result
            assert result["applied"]["applied_count"] == 2

    @pytest.mark.asyncio
    async def test_no_actionable_items(self, cfg_db):
        with patch("app.llm_unified.llm_chat", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = '{"additions": [], "modifications": []}'
            result = await tool_optimize_and_apply(cfg_db, "knowledge_agent", "test")
            assert result["applied"] == {}


# ========================= tool_generalize_experience =========================

class TestToolGeneralizeExperience:
    @pytest.mark.asyncio
    async def test_returns_pattern_dict(self, cfg_db):
        mock_response = '{"problem_type": "数据格式", "pattern": "非标准JSON", "strategy": "使用平衡括号提取"}'
        with patch("app.llm_unified.llm_chat", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_response
            result = await tool_generalize_experience(cfg_db, "test_agent", "处理JSON解析失败")
            assert result.get("problem_type") == "数据格式"
            assert "strategy" in result

    @pytest.mark.asyncio
    async def test_returns_raw_on_non_json(self, cfg_db):
        with patch("app.llm_unified.llm_chat", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "无法提取模式"
            result = await tool_generalize_experience(cfg_db, "test_agent", "模糊案例")
            assert "raw" in result

    @pytest.mark.asyncio
    async def test_saves_pattern_memory(self, cfg_db):
        mock_response = '{"problem_type": "超时", "pattern": "LLM调用", "strategy": "增加retry"}'
        with patch("app.llm_unified.llm_chat", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_response
            await tool_generalize_experience(cfg_db, "test_agent", "LLM超时处理")
            rows = await cfg_db.query(
                "SELECT * FROM agent_memories WHERE agent_name = ? AND memory_type = 'pattern'",
                ("test_agent",),
            )
            assert len(rows) >= 1
            assert "超时" in rows[0]["content"]


# ========================= tool_get_config / tool_set_config (already tested but verify) =========================

class TestConfigGetSet:
    @pytest.mark.asyncio
    async def test_get_config_returns_defaults(self, cfg_db):
        result = await tool_get_config(cfg_db, "knowledge_agent")
        assert "temperature" in result["config"]
        assert result["config"]["temperature"] == 0.3

    @pytest.mark.asyncio
    async def test_get_specific_key(self, cfg_db):
        result = await tool_get_config(cfg_db, "knowledge_agent", "temperature")
        assert result["value"] == 0.3

    @pytest.mark.asyncio
    async def test_get_nonexistent_agent(self, cfg_db):
        result = await tool_get_config(cfg_db, "nonexistent_agent")
        assert result["config"] == {}

    @pytest.mark.asyncio
    async def test_set_config_persists_to_db(self, cfg_db):
        result = await tool_set_config(cfg_db, "knowledge_agent", "test_key", "test_value")
        assert result["old_value"] != "test_value"
        assert result["new_value"] == "test_value"

        rows = await cfg_db.query(
            "SELECT config_value FROM agent_configs WHERE agent_name = ? AND config_key = ?",
            ("knowledge_agent", "test_key"),
        )
        assert len(rows) == 1
        assert json.loads(rows[0]["config_value"]) == "test_value"

    @pytest.mark.asyncio
    async def test_set_config_creates_audit_log(self, cfg_db):
        await tool_set_config(cfg_db, "knowledge_agent", "audited_key", 123)
        rows = await cfg_db.query(
            "SELECT * FROM agent_logs WHERE action_type = 'config_change'",
        )
        assert len(rows) >= 1
        details = json.loads(rows[0]["details"])
        assert details["key"] == "audited_key"
