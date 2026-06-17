"""Tests for child emergency triage system (spec §23.1 MVP P0).

Covers:
    - Age group determination (all 5 groups + edge cases)
    - Questionnaire correctness per age group
    - Red flag → emergency level (all 8 red flags)
    - Newborn fever ≥38°C → emergency
    - Infant/toddler fever ≥39°C → urgent
    - Fever duration > threshold → urgent
    - Mental status, feeding, urine, breathing → urgent
    - Normal symptoms → self_care/routine
    - Multiple red flags → still emergency
    - Disclaimer always attached
    - Invalid age → appropriate error
    - Full assess flow end-to-end
    - Safety keyword cross-reference
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.routers.triage import router as triage_router
from app.triage_data import (
    AGE_GROUP_ORDER,
    AGE_GROUPS,
    QUESTIONNAIRES,
    RED_FLAG_KEYWORD_MAP,
    RED_FLAG_MAP,
    RED_FLAG_SYMPTOMS,
    TRIAGE_DISCLAIMER,
    TRIAGE_LEVELS,
    URGENT_THRESHOLDS,
    answers_to_categories,
    determine_age_group,
    perform_triage,
)


# ---------------------------------------------------------------------------
# Test fixture: standalone triage app (main.py not modified)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def triage_client():
    """Create a test client with only the triage router.

    Triage endpoints are public (no auth, no DB) — they are pure
    computation for medical safety. We don't need the full app.
    """
    app = FastAPI()
    app.include_router(triage_router)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ===========================================================================
# Unit Tests: determine_age_group
# ===========================================================================

class TestDetermineAgeGroup:
    """Test age group determination for all pediatric ranges."""

    def test_newborn_zero_months(self):
        assert determine_age_group(0) == "新生儿"

    def test_newborn_with_days(self):
        assert determine_age_group(0, age_days=15) == "新生儿"

    def test_newborn_boundary_28_days(self):
        assert determine_age_group(0, age_days=28) == "新生儿"

    def test_infant_one_month(self):
        assert determine_age_group(1) == "婴儿"

    def test_infant_six_months(self):
        assert determine_age_group(6) == "婴儿"

    def test_infant_twelve_months(self):
        assert determine_age_group(12) == "婴儿"

    def test_toddler_thirteen_months(self):
        assert determine_age_group(13) == "幼儿"

    def test_toddler_twenty_four_months(self):
        assert determine_age_group(24) == "幼儿"

    def test_toddler_thirty_six_months(self):
        assert determine_age_group(36) == "幼儿"

    def test_preschool_thirty_seven_months(self):
        assert determine_age_group(37) == "学龄前"

    def test_preschool_sixty_months(self):
        assert determine_age_group(60) == "学龄前"

    def test_preschool_seventy_two_months(self):
        assert determine_age_group(72) == "学龄前"

    def test_school_age_seventy_three_months(self):
        assert determine_age_group(73) == "学龄"

    def test_school_age_one_hundred_twenty_months(self):
        assert determine_age_group(120) == "学龄"

    def test_school_age_max_168_months(self):
        assert determine_age_group(168) == "学龄"

    def test_negative_age_raises(self):
        with pytest.raises(ValueError, match="不能为负数"):
            determine_age_group(-1)

    def test_age_over_168_raises(self):
        with pytest.raises(ValueError, match="超出儿童分诊范围"):
            determine_age_group(200)

    def test_all_groups_covered(self):
        """Every month 0-168 maps to exactly one group."""
        for m in range(0, 169):
            group = determine_age_group(m)
            assert group in AGE_GROUP_ORDER


# ===========================================================================
# Unit Tests: perform_triage — Red Flag → Emergency
# ===========================================================================

class TestRedFlagEmergency:
    """ANY red flag symptom must trigger emergency level."""

    @pytest.mark.parametrize("rf_id", [rf["id"] for rf in RED_FLAG_SYMPTOMS])
    def test_each_red_flag_triggers_emergency(self, rf_id):
        """Each individual red flag ID → emergency."""
        result = perform_triage(
            age_months=24,
            answers_by_category={},
            red_flag_ids=[rf_id],
        )
        assert result["level_key"] == "emergency"
        assert result["level"] == "紧急"
        assert result["color"] == "red"

    def test_multiple_red_flags_still_emergency(self):
        """Multiple red flags → still emergency (not escalated beyond)."""
        result = perform_triage(
            age_months=12,
            answers_by_category={},
            red_flag_ids=["RF01", "RF02", "RF05"],
        )
        assert result["level_key"] == "emergency"
        assert len(result["triggered_red_flags"]) == 3
        assert len(result["warnings"]) == 3

    def test_seizure_rf01_emergency(self):
        """抽搐/惊厥 (seizures) → immediate emergency."""
        result = perform_triage(
            age_months=36,
            answers_by_category={},
            red_flag_ids=["RF01"],
        )
        assert result["level_key"] == "emergency"
        assert result["action"] == "立即拨打120或前往最近急诊"

    def test_breathing_difficulty_rf02_emergency(self):
        """呼吸困难 (breathing difficulty) → emergency."""
        result = perform_triage(
            age_months=48,
            answers_by_category={},
            red_flag_ids=["RF02"],
        )
        assert result["level_key"] == "emergency"

    def test_non_blanching_rash_rf05_emergency(self):
        """皮疹按压不褪色 (meningitis sign) → emergency."""
        result = perform_triage(
            age_months=24,
            answers_by_category={},
            red_flag_ids=["RF05"],
        )
        assert result["level_key"] == "emergency"

    def test_bulging_fontanelle_rf06_emergency(self):
        """囟门膨隆 (infant) → emergency."""
        result = perform_triage(
            age_months=6,
            answers_by_category={},
            red_flag_ids=["RF06"],
        )
        assert result["level_key"] == "emergency"

    def test_unknown_red_flag_id_ignored(self):
        """Unknown red flag IDs are silently ignored (not an error)."""
        result = perform_triage(
            age_months=24,
            answers_by_category={"temperature": 37.0},
            red_flag_ids=["RF99", "INVALID"],
        )
        # No known red flags triggered → not emergency
        assert result["level_key"] == "self_care"
        assert len(result["triggered_red_flags"]) == 0

    def test_red_flag_overrides_everything(self):
        """Red flag takes priority over any other answers."""
        result = perform_triage(
            age_months=60,
            answers_by_category={"temperature": 36.5},  # Normal temp
            red_flag_ids=["RF01"],  # But seizure present
        )
        assert result["level_key"] == "emergency"


# ===========================================================================
# Unit Tests: Newborn-specific rules
# ===========================================================================

class TestNewbornTriage:
    """Newborn (0-28 days) has the strictest thresholds."""

    def test_newborn_fever_38_emergency(self):
        """Newborn with ANY fever ≥38°C → emergency."""
        result = perform_triage(
            age_months=0,
            answers_by_category={"temperature": 38.0},
            red_flag_ids=[],
        )
        assert result["level_key"] == "emergency"
        assert "新生儿" in result["warnings"][0]

    def test_newborn_fever_38_5_emergency(self):
        """Newborn with 38.5°C → emergency."""
        result = perform_triage(
            age_months=0,
            answers_by_category={"temperature": 38.5},
            red_flag_ids=[],
        )
        assert result["level_key"] == "emergency"

    def test_newborn_fever_39_emergency(self):
        """Newborn with 39°C → emergency."""
        result = perform_triage(
            age_months=0,
            answers_by_category={"temperature": 39.0},
            red_flag_ids=[],
        )
        assert result["level_key"] == "emergency"

    def test_newborn_normal_temp_self_care(self):
        """Newborn with normal temp (37°C) → self_care."""
        result = perform_triage(
            age_months=0,
            answers_by_category={"temperature": 37.0},
            red_flag_ids=[],
        )
        assert result["level_key"] == "self_care"

    def test_newborn_low_fever_37_5_not_emergency(self):
        """Newborn with 37.5°C (below 38 threshold) → self_care."""
        result = perform_triage(
            age_months=0,
            answers_by_category={"temperature": 37.5},
            red_flag_ids=[],
        )
        assert result["level_key"] == "self_care"

    def test_newborn_not_crying_emergency(self):
        """Newborn not crying (不哭) → emergency."""
        result = perform_triage(
            age_months=0,
            answers_by_category={"cry": "不哭"},
            red_flag_ids=[],
        )
        assert result["level_key"] == "emergency"

    def test_newborn_refusing_milk_urgent(self):
        """Newborn refusing milk (拒奶) → urgent."""
        result = perform_triage(
            age_months=0,
            answers_by_category={"feeding": "拒奶"},
            red_flag_ids=[],
        )
        assert result["level_key"] == "urgent"

    def test_newborn_skin_blue_emergency(self):
        """Newborn with cyanosis (发紫) → emergency."""
        result = perform_triage(
            age_months=0,
            answers_by_category={"skin_color": "发紫"},
            red_flag_ids=[],
        )
        assert result["level_key"] == "emergency"


# ===========================================================================
# Unit Tests: Infant/Toddler/Child fever thresholds
# ===========================================================================

class TestFeverThresholds:
    """Test age-specific fever thresholds."""

    def test_infant_fever_39_urgent(self):
        """Infant (6 months) with fever ≥39°C → urgent."""
        result = perform_triage(
            age_months=6,
            answers_by_category={"temperature": 39.0},
            red_flag_ids=[],
        )
        assert result["level_key"] == "urgent"

    def test_infant_fever_39_5_urgent(self):
        """Infant with 39.5°C → urgent."""
        result = perform_triage(
            age_months=8,
            answers_by_category={"temperature": 39.5},
            red_flag_ids=[],
        )
        assert result["level_key"] == "urgent"

    def test_infant_fever_38_5_routine(self):
        """Infant with 38.5°C (below 39 threshold) → routine."""
        result = perform_triage(
            age_months=6,
            answers_by_category={"temperature": 38.5},
            red_flag_ids=[],
        )
        assert result["level_key"] == "routine"

    def test_toddler_fever_39_urgent(self):
        """Toddler (2 years) with fever ≥39°C → urgent."""
        result = perform_triage(
            age_months=24,
            answers_by_category={"temperature": 39.0},
            red_flag_ids=[],
        )
        assert result["level_key"] == "urgent"

    def test_preschool_fever_39_urgent(self):
        """Preschooler with fever ≥39°C → urgent."""
        result = perform_triage(
            age_months=48,
            answers_by_category={"temperature": 39.2},
            red_flag_ids=[],
        )
        assert result["level_key"] == "urgent"

    def test_school_age_fever_39_urgent(self):
        """School-age child with fever ≥39°C → urgent."""
        result = perform_triage(
            age_months=120,
            answers_by_category={"temperature": 39.5},
            red_flag_ids=[],
        )
        assert result["level_key"] == "urgent"

    def test_low_fever_38_routine(self):
        """Low-grade fever 38-38.9°C → routine for non-newborn."""
        result = perform_triage(
            age_months=36,
            answers_by_category={"temperature": 38.3},
            red_flag_ids=[],
        )
        assert result["level_key"] == "routine"

    def test_fever_boundary_exactly_39(self):
        """Exactly 39.0°C → urgent (>= threshold)."""
        result = perform_triage(
            age_months=24,
            answers_by_category={"temperature": 39.0},
            red_flag_ids=[],
        )
        assert result["level_key"] == "urgent"

    def test_fever_boundary_exactly_38(self):
        """Exactly 38.0°C → routine for non-newborn (low-grade)."""
        result = perform_triage(
            age_months=24,
            answers_by_category={"temperature": 38.0},
            red_flag_ids=[],
        )
        assert result["level_key"] == "routine"


# ===========================================================================
# Unit Tests: Fever duration
# ===========================================================================

class TestFeverDuration:
    """Test fever duration thresholds."""

    def test_toddler_fever_4_days_urgent(self):
        """Toddler fever >3 days → urgent even without high fever."""
        result = perform_triage(
            age_months=24,
            answers_by_category={
                "temperature": 38.5,  # Low fever
                "fever_duration": 4,  # > 3 days
            },
            red_flag_ids=[],
        )
        assert result["level_key"] == "urgent"

    def test_toddler_fever_3_days_routine(self):
        """Toddler fever exactly 3 days with low fever → routine (not > threshold)."""
        result = perform_triage(
            age_months=24,
            answers_by_category={
                "temperature": 38.5,
                "fever_duration": 3,  # = 3, not > 3
            },
            red_flag_ids=[],
        )
        assert result["level_key"] == "routine"

    def test_preschool_fever_5_days_urgent(self):
        """Preschooler fever 5 days → urgent."""
        result = perform_triage(
            age_months=48,
            answers_by_category={
                "temperature": 38.0,
                "fever_duration": 5,
            },
            red_flag_ids=[],
        )
        assert result["level_key"] == "urgent"

    def test_newborn_no_duration_threshold(self):
        """Newborns don't have duration threshold — any fever is emergency."""
        result = perform_triage(
            age_months=0,
            answers_by_category={
                "temperature": 37.5,  # Below fever threshold
                "fever_duration": 5,
            },
            red_flag_ids=[],
        )
        assert result["level_key"] == "self_care"


# ===========================================================================
# Unit Tests: Symptom-based urgent triggers
# ===========================================================================

class TestSymptomUrgentTriggers:
    """Test that specific symptom answers trigger urgent level."""

    def test_mental_status_lethargic_urgent(self):
        """嗜睡 (lethargy) → urgent."""
        result = perform_triage(
            age_months=24,
            answers_by_category={"mental_status": "嗜睡"},
            red_flag_ids=[],
        )
        assert result["level_key"] == "urgent"

    def test_mental_status_unconscious_urgent(self):
        """昏睡 (semiconscious) → urgent."""
        result = perform_triage(
            age_months=36,
            answers_by_category={"mental_status": "昏睡"},
            red_flag_ids=[],
        )
        assert result["level_key"] == "urgent"

    def test_mental_status_irritable_not_urgent(self):
        """烦躁 (irritable) alone → not urgent (only 嗜睡/昏睡 trigger)."""
        result = perform_triage(
            age_months=36,
            answers_by_category={"mental_status": "烦躁"},
            red_flag_ids=[],
        )
        assert result["level_key"] == "self_care"

    def test_feeding_refusal_urgent(self):
        """拒食 (refusing food) → urgent."""
        result = perform_triage(
            age_months=24,
            answers_by_category={"feeding": "拒食"},
            red_flag_ids=[],
        )
        assert result["level_key"] == "urgent"

    def test_urine_no_output_8h_urgent(self):
        """无尿>8小时 → urgent (dehydration risk)."""
        result = perform_triage(
            age_months=12,
            answers_by_category={"urine": "无尿>8小时"},
            red_flag_ids=[],
        )
        assert result["level_key"] == "urgent"

    def test_breathing_difficulty_urgent(self):
        """呼吸困难 → urgent (also a red flag if explicitly checked)."""
        result = perform_triage(
            age_months=24,
            answers_by_category={"breathing": "困难"},
            red_flag_ids=[],
        )
        assert result["level_key"] == "urgent"

    def test_breathing_laborious_urgent(self):
        """费力 (labored breathing) → urgent."""
        result = perform_triage(
            age_months=36,
            answers_by_category={"breathing": "费力"},
            red_flag_ids=[],
        )
        assert result["level_key"] == "urgent"


# ===========================================================================
# Unit Tests: Normal symptoms → self_care / routine
# ===========================================================================

class TestNormalTriage:
    """Test that normal/minor symptoms result in self_care or routine."""

    def test_all_normal_self_care(self):
        """All normal answers → self_care."""
        result = perform_triage(
            age_months=24,
            answers_by_category={
                "temperature": 36.8,
                "mental_status": "正常",
                "feeding": "正常",
                "urine": "正常",
                "breathing": "正常",
            },
            red_flag_ids=[],
        )
        assert result["level_key"] == "self_care"
        assert result["color"] == "blue"

    def test_no_answers_self_care(self):
        """No answers at all → self_care (conservative default)."""
        result = perform_triage(
            age_months=36,
            answers_by_category={},
            red_flag_ids=[],
        )
        assert result["level_key"] == "self_care"

    def test_low_fever_routine(self):
        """Low-grade fever → routine."""
        result = perform_triage(
            age_months=48,
            answers_by_category={"temperature": 38.2},
            red_flag_ids=[],
        )
        assert result["level_key"] == "routine"
        assert result["color"] == "green"
        assert len(result["recommendations"]) > 0

    def test_self_care_has_recommendations(self):
        """self_care level should include care recommendations."""
        result = perform_triage(
            age_months=60,
            answers_by_category={},
            red_flag_ids=[],
        )
        assert result["level_key"] == "self_care"
        assert len(result["recommendations"]) >= 2


# ===========================================================================
# Unit Tests: Disclaimer always present
# ===========================================================================

class TestDisclaimer:
    """Every triage result MUST include a disclaimer — non-negotiable."""

    def test_disclaimer_emergency(self):
        result = perform_triage(
            age_months=24,
            answers_by_category={},
            red_flag_ids=["RF01"],
        )
        assert result["disclaimer"] == TRIAGE_DISCLAIMER

    def test_disclaimer_urgent(self):
        result = perform_triage(
            age_months=24,
            answers_by_category={"temperature": 39.5},
            red_flag_ids=[],
        )
        assert result["disclaimer"] == TRIAGE_DISCLAIMER

    def test_disclaimer_routine(self):
        result = perform_triage(
            age_months=24,
            answers_by_category={"temperature": 38.2},
            red_flag_ids=[],
        )
        assert result["disclaimer"] == TRIAGE_DISCLAIMER

    def test_disclaimer_self_care(self):
        result = perform_triage(
            age_months=24,
            answers_by_category={},
            red_flag_ids=[],
        )
        assert result["disclaimer"] == TRIAGE_DISCLAIMER

    def test_disclaimer_non_empty(self):
        """Disclaimer must not be empty."""
        assert len(TRIAGE_DISCLAIMER) > 10
        assert "就医" in TRIAGE_DISCLAIMER or "诊断" in TRIAGE_DISCLAIMER


# ===========================================================================
# Unit Tests: answers_to_categories helper
# ===========================================================================

class TestAnswersToCategories:
    """Test the answer ID → category conversion."""

    def test_basic_conversion(self):
        """Q01 → temperature, Q03 → mental_status for 婴儿."""
        raw = [
            {"id": "Q01", "value": 38.5},
            {"id": "Q03", "value": "嗜睡"},
        ]
        result = answers_to_categories("婴儿", raw)
        assert result["temperature"] == 38.5
        assert result["mental_status"] == "嗜睡"

    def test_unknown_id_skipped(self):
        """Unknown question IDs are silently skipped."""
        raw = [
            {"id": "Q01", "value": 38.0},
            {"id": "Q99", "value": "unknown"},
        ]
        result = answers_to_categories("幼儿", raw)
        assert "temperature" in result
        assert len(result) == 1

    def test_empty_answers(self):
        """Empty answers list → empty dict."""
        result = answers_to_categories("婴儿", [])
        assert result == {}


# ===========================================================================
# Unit Tests: Safety keyword cross-reference
# ===========================================================================

class TestSafetyKeywordCrossReference:
    """Verify relationship between triage red flags and safety_keywords.py."""

    def test_keyword_map_exists(self):
        """RED_FLAG_KEYWORD_MAP should exist and be non-empty."""
        assert len(RED_FLAG_KEYWORD_MAP) > 0

    def test_rf01_maps_to_seizure_keywords(self):
        """RF01 (抽搐/惊厥) maps to 抽搐 and 惊厥 keywords."""
        assert "抽搐" in RED_FLAG_KEYWORD_MAP["RF01"]
        assert "惊厥" in RED_FLAG_KEYWORD_MAP["RF01"]

    def test_rf02_maps_to_breathing_keyword(self):
        """RF02 (呼吸困难) maps to 呼吸困难 keyword."""
        assert "呼吸困难" in RED_FLAG_KEYWORD_MAP["RF02"]

    def test_rf08_maps_to_fever_keywords(self):
        """RF08 (高热不退) maps to 高热 and 持续高烧 keywords."""
        assert "高热" in RED_FLAG_KEYWORD_MAP["RF08"]
        assert "持续高烧" in RED_FLAG_KEYWORD_MAP["RF08"]

    def test_all_mapped_ids_are_valid(self):
        """Every key in RED_FLAG_KEYWORD_MAP must be a valid red flag ID."""
        for rf_id in RED_FLAG_KEYWORD_MAP:
            assert rf_id in RED_FLAG_MAP


# ===========================================================================
# API Tests: GET /api/triage/age-groups
# ===========================================================================

class TestApiGetAgeGroups:
    """Test the age-groups endpoint."""

    @pytest.mark.asyncio
    async def test_returns_all_five_groups(self, triage_client: AsyncClient):
        response = await triage_client.get("/api/triage/age-groups")
        assert response.status_code == 200
        data = response.json()
        assert data["total_groups"] == 5
        names = [g["name"] for g in data["groups"]]
        assert names == AGE_GROUP_ORDER

    @pytest.mark.asyncio
    async def test_includes_triage_levels(self, triage_client: AsyncClient):
        response = await triage_client.get("/api/triage/age-groups")
        data = response.json()
        assert "triage_levels" in data
        assert "emergency" in data["triage_levels"]
        assert data["triage_levels"]["emergency"]["color"] == "red"

    @pytest.mark.asyncio
    async def test_newborn_has_days_criteria(self, triage_client: AsyncClient):
        response = await triage_client.get("/api/triage/age-groups")
        data = response.json()
        newborn = [g for g in data["groups"] if g["name"] == "新生儿"][0]
        assert newborn["min_days"] == 0
        assert newborn["max_days"] == 28

    @pytest.mark.asyncio
    async def test_no_auth_required(self, triage_client: AsyncClient):
        """Triage endpoints should work without auth (safety feature)."""
        response = await triage_client.get("/api/triage/age-groups")
        assert response.status_code == 200


# ===========================================================================
# API Tests: GET /api/triage/questionnaire
# ===========================================================================

class TestApiGetQuestionnaire:
    """Test the questionnaire endpoint."""

    @pytest.mark.asyncio
    async def test_newborn_questionnaire(self, triage_client: AsyncClient):
        """age_months=0 → 新生儿 questionnaire with 5 questions."""
        response = await triage_client.get(
            "/api/triage/questionnaire", params={"age_months": 0}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["age_group"] == "新生儿"
        assert data["question_count"] == 5
        assert data["questions"][0]["category"] == "temperature"

    @pytest.mark.asyncio
    async def test_infant_questionnaire(self, triage_client: AsyncClient):
        """age_months=6 → 婴儿 questionnaire with 6 questions."""
        response = await triage_client.get(
            "/api/triage/questionnaire", params={"age_months": 6}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["age_group"] == "婴儿"
        assert data["question_count"] == 6

    @pytest.mark.asyncio
    async def test_toddler_questionnaire(self, triage_client: AsyncClient):
        """age_months=24 → 幼儿 questionnaire with 7 questions."""
        response = await triage_client.get(
            "/api/triage/questionnaire", params={"age_months": 24}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["age_group"] == "幼儿"
        assert data["question_count"] == 7

    @pytest.mark.asyncio
    async def test_preschool_questionnaire(self, triage_client: AsyncClient):
        """age_months=48 → 学龄前 questionnaire with 8 questions."""
        response = await triage_client.get(
            "/api/triage/questionnaire", params={"age_months": 48}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["age_group"] == "学龄前"
        assert data["question_count"] == 8

    @pytest.mark.asyncio
    async def test_school_age_questionnaire(self, triage_client: AsyncClient):
        """age_months=120 → 学龄 questionnaire with 9 questions."""
        response = await triage_client.get(
            "/api/triage/questionnaire", params={"age_months": 120}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["age_group"] == "学龄"
        assert data["question_count"] == 9

    @pytest.mark.asyncio
    async def test_by_age_group_name(self, triage_client: AsyncClient):
        """Direct age_group param works."""
        response = await triage_client.get(
            "/api/triage/questionnaire", params={"age_group": "婴儿"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["age_group"] == "婴儿"

    @pytest.mark.asyncio
    async def test_includes_red_flags(self, triage_client: AsyncClient):
        """Questionnaire response includes red flag checklist."""
        response = await triage_client.get(
            "/api/triage/questionnaire", params={"age_months": 12}
        )
        data = response.json()
        assert "red_flags" in data
        assert len(data["red_flags"]) == 8

    @pytest.mark.asyncio
    async def test_includes_disclaimer(self, triage_client: AsyncClient):
        """Questionnaire response includes disclaimer."""
        response = await triage_client.get(
            "/api/triage/questionnaire", params={"age_months": 24}
        )
        data = response.json()
        assert data["disclaimer"] == TRIAGE_DISCLAIMER

    @pytest.mark.asyncio
    async def test_invalid_age_group_name(self, triage_client: AsyncClient):
        """Invalid age_group name → 422."""
        response = await triage_client.get(
            "/api/triage/questionnaire", params={"age_group": "青少年"}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_no_params_returns_422(self, triage_client: AsyncClient):
        """Neither age_months nor age_group → 422."""
        response = await triage_client.get("/api/triage/questionnaire")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_age_over_168_returns_422(self, triage_client: AsyncClient):
        """age_months > 168 → 422 (query param validation)."""
        response = await triage_client.get(
            "/api/triage/questionnaire", params={"age_months": 200}
        )
        assert response.status_code == 422


# ===========================================================================
# API Tests: GET /api/triage/red-flags
# ===========================================================================

class TestApiGetRedFlags:
    """Test the red-flags endpoint."""

    @pytest.mark.asyncio
    async def test_returns_all_red_flags(self, triage_client: AsyncClient):
        response = await triage_client.get("/api/triage/red-flags")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 8
        assert len(data["red_flags"]) == 8

    @pytest.mark.asyncio
    async def test_includes_keyword_cross_reference(
        self, triage_client: AsyncClient
    ):
        response = await triage_client.get("/api/triage/red-flags")
        data = response.json()
        assert "keyword_cross_reference" in data


# ===========================================================================
# API Tests: POST /api/triage/assess
# ===========================================================================

class TestApiAssess:
    """Test the assess endpoint end-to-end."""

    @pytest.mark.asyncio
    async def test_red_flag_assess_emergency(self, triage_client: AsyncClient):
        """POST assess with red flag → emergency."""
        response = await triage_client.post(
            "/api/triage/assess",
            json={
                "age_months": 24,
                "answers": [],
                "red_flags": ["RF01"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["level_key"] == "emergency"
        assert data["level"] == "紧急"
        assert data["color"] == "red"
        assert data["disclaimer"] == TRIAGE_DISCLAIMER

    @pytest.mark.asyncio
    async def test_newborn_fever_emergency(self, triage_client: AsyncClient):
        """POST assess: newborn with fever → emergency."""
        response = await triage_client.post(
            "/api/triage/assess",
            json={
                "age_months": 0,
                "answers": [{"id": "Q01", "value": 38.5}],
                "red_flags": [],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["level_key"] == "emergency"
        assert data["age_group"] == "新生儿"

    @pytest.mark.asyncio
    async def test_infant_high_fever_urgent(self, triage_client: AsyncClient):
        """POST assess: infant with high fever → urgent."""
        response = await triage_client.post(
            "/api/triage/assess",
            json={
                "age_months": 6,
                "answers": [{"id": "Q01", "value": 39.5}],
                "red_flags": [],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["level_key"] == "urgent"

    @pytest.mark.asyncio
    async def test_normal_self_care(self, triage_client: AsyncClient):
        """POST assess: normal symptoms → self_care."""
        response = await triage_client.post(
            "/api/triage/assess",
            json={
                "age_months": 36,
                "answers": [
                    {"id": "Q01", "value": 36.8},
                    {"id": "Q03", "value": "正常"},
                    {"id": "Q04", "value": "正常"},
                ],
                "red_flags": [],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["level_key"] == "self_care"

    @pytest.mark.asyncio
    async def test_missing_age_months_422(self, triage_client: AsyncClient):
        """Missing age_months → 422."""
        response = await triage_client.post(
            "/api/triage/assess",
            json={"answers": [], "red_flags": []},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_negative_age_422(self, triage_client: AsyncClient):
        """Negative age_months → 422."""
        response = await triage_client.post(
            "/api/triage/assess",
            json={"age_months": -1, "answers": [], "red_flags": []},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_age_over_168_422(self, triage_client: AsyncClient):
        """age_months > 168 → 422."""
        response = await triage_client.post(
            "/api/triage/assess",
            json={"age_months": 200, "answers": [], "red_flags": []},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_disclaimer_always_present(
        self, triage_client: AsyncClient
    ):
        """Every assess result has disclaimer."""
        for payload in [
            {"age_months": 0, "answers": [{"id": "Q01", "value": 39.0}], "red_flags": []},
            {"age_months": 24, "answers": [], "red_flags": ["RF01"]},
            {"age_months": 36, "answers": [{"id": "Q01", "value": 38.2}], "red_flags": []},
            {"age_months": 48, "answers": [], "red_flags": []},
        ]:
            response = await triage_client.post("/api/triage/assess", json=payload)
            assert response.status_code == 200
            assert response.json()["disclaimer"] == TRIAGE_DISCLAIMER

    @pytest.mark.asyncio
    async def test_full_flow_emergency(self, triage_client: AsyncClient):
        """Full emergency flow: red flag → emergency with all fields."""
        response = await triage_client.post(
            "/api/triage/assess",
            json={
                "age_months": 12,
                "answers": [{"id": "Q01", "value": 40.0}],
                "red_flags": ["RF01", "RF02"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["level_key"] == "emergency"
        assert data["level"] == "紧急"
        assert data["color"] == "red"
        assert data["action"] == "立即拨打120或前往最近急诊"
        assert data["time"] == "立即"
        assert len(data["triggered_red_flags"]) == 2
        assert len(data["warnings"]) == 2
        assert data["disclaimer"] == TRIAGE_DISCLAIMER
        assert data["age_group"] == "婴儿"

    @pytest.mark.asyncio
    async def test_full_flow_urgent(self, triage_client: AsyncClient):
        """Full urgent flow: high fever without red flags."""
        response = await triage_client.post(
            "/api/triage/assess",
            json={
                "age_months": 24,
                "answers": [
                    {"id": "Q01", "value": 39.5},
                    {"id": "Q02", "value": 2},
                    {"id": "Q03", "value": "嗜睡"},
                ],
                "red_flags": [],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["level_key"] == "urgent"
        assert data["color"] == "orange"
        assert data["time"] == "2小时内"
        assert len(data["warnings"]) >= 2  # fever + lethargy

    @pytest.mark.asyncio
    async def test_full_flow_routine(self, triage_client: AsyncClient):
        """Full routine flow: low-grade fever."""
        response = await triage_client.post(
            "/api/triage/assess",
            json={
                "age_months": 48,
                "answers": [{"id": "Q01", "value": 38.3}],
                "red_flags": [],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["level_key"] == "routine"
        assert data["color"] == "green"
        assert len(data["recommendations"]) >= 2

    @pytest.mark.asyncio
    async def test_full_flow_self_care(self, triage_client: AsyncClient):
        """Full self_care flow: normal symptoms."""
        response = await triage_client.post(
            "/api/triage/assess",
            json={
                "age_months": 60,
                "answers": [{"id": "Q01", "value": 36.5}],
                "red_flags": [],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["level_key"] == "self_care"
        assert data["color"] == "blue"
        assert len(data["recommendations"]) >= 2

    @pytest.mark.asyncio
    async def test_no_auth_required(self, triage_client: AsyncClient):
        """POST assess without auth token → 200 (safety feature)."""
        response = await triage_client.post(
            "/api/triage/assess",
            json={"age_months": 24, "answers": [], "red_flags": []},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_age_days_for_newborn_precision(
        self, triage_client: AsyncClient
    ):
        """age_days parameter works for newborn precision."""
        response = await triage_client.post(
            "/api/triage/assess",
            json={
                "age_months": 0,
                "age_days": 15,
                "answers": [{"id": "Q01", "value": 38.0}],
                "red_flags": [],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["age_group"] == "新生儿"
        assert data["level_key"] == "emergency"

    @pytest.mark.asyncio
    async def test_empty_answers_works(self, triage_client: AsyncClient):
        """Empty answers list → works (returns self_care)."""
        response = await triage_client.post(
            "/api/triage/assess",
            json={"age_months": 36, "answers": [], "red_flags": []},
        )
        assert response.status_code == 200
        assert response.json()["level_key"] == "self_care"

    @pytest.mark.asyncio
    async def test_string_age_months_422(self, triage_client: AsyncClient):
        """Non-integer age_months → 422."""
        response = await triage_client.post(
            "/api/triage/assess",
            json={"age_months": "abc", "answers": [], "red_flags": []},
        )
        assert response.status_code == 422


# ===========================================================================
# Data integrity tests
# ===========================================================================

class TestDataIntegrity:
    """Verify the triage data module is internally consistent."""

    def test_all_questionnaires_exist(self):
        """Every age group has a questionnaire."""
        for group in AGE_GROUP_ORDER:
            assert group in QUESTIONNAIRES, f"Missing questionnaire for {group}"
            assert len(QUESTIONNAIRES[group]) > 0

    def test_all_age_groups_have_thresholds(self):
        """Every age group has urgent thresholds defined."""
        for group in AGE_GROUP_ORDER:
            assert group in URGENT_THRESHOLDS
            assert "fever" in URGENT_THRESHOLDS[group]

    def test_newborn_fever_threshold_is_38(self):
        """Newborn fever threshold must be 38.0°C (strictest)."""
        assert URGENT_THRESHOLDS["新生儿"]["fever"] == 38.0

    def test_non_newborn_fever_threshold_is_39(self):
        """Non-newborn fever threshold must be 39.0°C."""
        for group in ["婴儿", "幼儿", "学龄前", "学龄"]:
            assert URGENT_THRESHOLDS[group]["fever"] == 39.0

    def test_all_red_flags_have_required_fields(self):
        """Every red flag has id, symptom, detail, action."""
        for rf in RED_FLAG_SYMPTOMS:
            assert "id" in rf
            assert "symptom" in rf
            assert "detail" in rf
            assert "action" in rf

    def test_triage_levels_complete(self):
        """All 4 triage levels are defined with required fields."""
        for key in ("emergency", "urgent", "routine", "self_care"):
            assert key in TRIAGE_LEVELS
            level = TRIAGE_LEVELS[key]
            assert "level" in level
            assert "color" in level
            assert "action" in level
            assert "time" in level

    def test_question_ids_unique_within_group(self):
        """Question IDs are unique within each age group."""
        for group, questions in QUESTIONNAIRES.items():
            ids = [q["id"] for q in questions]
            assert len(ids) == len(set(ids)), (
                f"Duplicate question IDs in {group}"
            )

    def test_temperature_question_in_all_groups(self):
        """Every age group has a temperature question."""
        for group, questions in QUESTIONNAIRES.items():
            categories = [q["category"] for q in questions]
            assert "temperature" in categories, (
                f"{group} missing temperature question"
            )
