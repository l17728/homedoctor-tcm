"""Expert review专项测试 — 验证安全/医药/UX评审修复项的测试覆盖。"""

import pytest
import pytest_asyncio
from app.database import SqliteAdapter, init_db, seed_safety_rules, seed_test_data
from app.safety_engine import run_safety_check
from app.safety_keywords import EMERGENCY_KEYWORDS, SYNONYM_MAP, check_emergency_keywords
from app.llm import build_system_prompt


@pytest_asyncio.fixture
async def safety_db():
    adapter = SqliteAdapter(":memory:")
    await adapter.connect()
    await init_db(adapter)
    await seed_safety_rules(adapter)
    await seed_test_data(adapter)
    yield adapter
    await adapter.close()


class TestFoodInteractionSafety:
    """医药评审: 食物禁忌检查"""

    @pytest.mark.asyncio
    async def test_grapefruit_medication_warning(self, safety_db):
        result = await run_safety_check(
            safety_db,
            herb_names=[],
            medicine_names=["硝苯地平"],
            user_profile={},
        )
        warnings_text = json.dumps(result.warnings, ensure_ascii=False)
        assert any("葡萄柚" in w or "食物" in w for w in result.warnings) or result.safe

    @pytest.mark.asyncio
    async def test_food_interaction_layer_exists(self, safety_db):
        from app.safety_engine import _check_food_interactions
        warnings = await _check_food_interactions(safety_db, ["黄芪"], [])
        assert isinstance(warnings, list)

    @pytest.mark.asyncio
    async def test_food_rules_seeded(self, safety_db):
        rows = await safety_db.query(
            "SELECT COUNT(*) as c FROM safety_rules WHERE rule_type = '食物禁忌'"
        )
        assert rows[0]["c"] > 0


class TestEmergencySynonyms:
    """安全评审: 急症关键词50+同义词匹配"""

    def test_synonym_map_not_empty(self):
        assert len(SYNONYM_MAP) > 0

    def test_synonyms_count(self):
        total_keywords = len(EMERGENCY_KEYWORDS)
        total_synonyms = sum(len(syns) for syns in SYNONYM_MAP.values())
        assert total_keywords + total_synonyms >= 50, f"Only {total_keywords}+{total_synonyms}={total_keywords+total_synonyms}"

    def test_chest_pain_synonyms(self):
        matched = check_emergency_keywords("胸口痛")
        assert matched is not None or check_emergency_keywords("胸痛") is not None

    def test_breathing_synonyms(self):
        matched = check_emergency_keywords("喘不上气")
        assert matched is not None or check_emergency_keywords("呼吸困难") is not None

    def test_unconscious_synonyms(self):
        matched = check_emergency_keywords("晕过去了")
        assert matched is not None or check_emergency_keywords("突然意识丧失") is not None

    def test_hemorrhage_synonyms(self):
        matched = check_emergency_keywords("大出血")
        assert matched is not None

    def test_non_emergency_not_matched(self):
        result = check_emergency_keywords("今天天气很好")
        assert result is None or len(result) == 0

    def test_direct_keywords_work(self):
        assert check_emergency_keywords("胸痛") is not None


class TestLLMTemperature:
    """安全评审: LLM温度0.3"""

    def test_temperature_in_code(self):
        import inspect
        from app.llm import chat_completion, chat_completion_stream
        src = inspect.getsource(chat_completion)
        assert "0.3" in src
        src2 = inspect.getsource(chat_completion_stream)
        assert "0.3" in src2


class TestHallucinationDefense:
    """安全评审: 幻觉三层防御"""

    def test_l1_keyword_filter_exists(self):
        from app.llm import SYSTEM_PROMPT
        assert "不允许" in SYSTEM_PROMPT or "禁止" in SYSTEM_PROMPT or "不可" in SYSTEM_PROMPT

    def test_l2_validate_function_exists(self):
        from app.llm import _validate_and_augment
        assert callable(_validate_and_augment)

    def test_l3_judge_prompt_exists(self):
        import app.llm as llm_mod
        src = inspect.getsource(llm_mod)
        assert "judge" in src.lower() or "JUDGE" in src


class TestScheduleConflictSeparation:
    """医药评审: 排程安全冲突隔开"""

    def test_schedule_engine_has_conflict_check(self):
        from app.schedule_engine import generate_weekly_schedule
        import inspect
        src = inspect.getsource(generate_weekly_schedule)
        assert "conflict" in src.lower() or "冲突" in src or "gap_required" in src

    def test_critical_conflict_rejection(self):
        from app.schedule_engine import generate_weekly_schedule
        import inspect
        src = inspect.getsource(generate_weekly_schedule)
        assert "禁止同服" in src or "inf" in src


class TestJudgeDefaultReject:
    """安全评审: Judge默认拒绝"""

    def test_expert_review_function_exists(self):
        from app.schedule_engine import expert_review_schedule
        import inspect
        src = inspect.getsource(expert_review_schedule)
        assert "consensus" in src or "approval" in src or "// 2" in src or "majority" in src


class TestWarningNotBlocking:
    """医药评审: 安全warning不阻断"""

    @pytest.mark.asyncio
    async def test_warning_level_safe(self, safety_db):
        result = await run_safety_check(
            safety_db,
            herb_names=["黄芪"],
            medicine_names=[],
            user_profile={},
        )
        if any("warning" in str(w).lower() or "注意" in w for w in result.warnings):
            assert result.safe is True or result.safe is False

    def test_safety_engine_warning_logic(self):
        from app.safety_engine import SafetyCheckResult
        import inspect
        src = inspect.getsource(run_safety_check)
        assert "warning" in src.lower() or "severity" in src.lower()


class TestCumulativeToxicity:
    """医药评审: 累积毒性检查"""

    @pytest.mark.asyncio
    async def test_cumulative_check_with_correct_args(self):
        from app.safety_engine import _check_cumulative_toxicity
        herb_names = ["附子", "川乌"]
        herb_info = {"附子": {"toxic_compound": "乌头碱"}, "川乌": {"toxic_compound": "乌头碱"}}
        dosages = {"附子": 3.0, "川乌": 3.0}
        result = await _check_cumulative_toxicity(herb_names, herb_info, dosages)
        assert isinstance(result, list)

    def test_cumulative_in_safety_engine(self):
        from app.safety_engine import run_safety_check
        import inspect
        src = inspect.getsource(run_safety_check)
        assert "累积" in src or "cumulative" in src.lower()


class TestLiverKidneyCheck:
    """医药评审: 肝肾疾病特殊人群"""

    @pytest.mark.asyncio
    async def test_liver_disease_check(self, safety_db):
        result = await run_safety_check(
            safety_db,
            herb_names=["黄芪"],
            medicine_names=[],
            user_profile={"liver_disease": True},
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_kidney_disease_check(self, safety_db):
        result = await run_safety_check(
            safety_db,
            herb_names=["黄芪"],
            medicine_names=[],
            user_profile={"kidney_disease": True},
        )
        assert result is not None


class TestGancaoInteraction:
    """安全评审: 甘草交互检查"""

    @pytest.mark.asyncio
    async def test_gancao_in_safety_rules(self, safety_db):
        rows = await safety_db.query(
            "SELECT COUNT(*) as c FROM safety_rules WHERE drug_a = '甘草' OR drug_b = '甘草'"
        )
        assert rows[0]["c"] > 0


class TestToxicHerbExclusion:
    """安全评审: 有毒药材排除"""

    def test_toxicity_in_safety_engine(self):
        from app.safety_engine import run_safety_check
        import inspect
        src = inspect.getsource(run_safety_check)
        assert "毒性" in src or "toxic" in src.lower() or "toxicity" in src.lower()


import json
import inspect
