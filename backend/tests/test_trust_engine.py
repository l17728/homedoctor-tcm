"""Tests for trust engine — SABC hierarchy, safety sandbox, provenance."""

import pytest
import pytest_asyncio
from app.database import SqliteAdapter, init_db, seed_safety_rules, seed_test_data
from app.trust_engine import (
    calculate_trust_score, can_enter_safety_check, can_reference_in_ai,
    get_domain_trust, record_provenance, get_trust_level, update_trust_level,
    get_provenance, LEVEL_S, LEVEL_A, LEVEL_B, LEVEL_C,
)


@pytest_asyncio.fixture
async def trust_db():
    adapter = SqliteAdapter(":memory:")
    await adapter.connect()
    await init_db(adapter)
    await seed_safety_rules(adapter)
    await seed_test_data(adapter)
    await adapter.execute(
        """INSERT INTO knowledge_entities
           (id, entity_type, source_table, source_id, title, summary,
            keywords, tags, category, properties, source_type, status)
           VALUES ('ke-trust-1', 'herb', 'test', 't1', '测试药材',
                   '测试功效', '[]', '[]', '测试', '{"nature":"温"}', 'system', 'active')"""
    )
    yield adapter
    await adapter.close()


class TestTrustScoring:
    def test_high_quality_adopted(self):
        reviews = [
            {"medical_accuracy": 90, "completeness": 85, "source_reliability": 88, "recommendation": "adopt"},
            {"medical_accuracy": 85, "completeness": 82, "source_reliability": 80, "recommendation": "adopt"},
            {"medical_accuracy": 88, "completeness": 86, "source_reliability": 84, "recommendation": "adopt"},
        ]
        result = calculate_trust_score(reviews)
        assert result["level"] == LEVEL_A
        assert result["decision"] == "adopted"
        assert result["score"] >= 80

    def test_low_quality_rejected(self):
        reviews = [
            {"medical_accuracy": 30, "completeness": 25, "source_reliability": 20, "recommendation": "reject"},
            {"medical_accuracy": 35, "completeness": 30, "source_reliability": 25, "recommendation": "reject"},
            {"medical_accuracy": 40, "completeness": 35, "source_reliability": 30, "recommendation": "reject"},
        ]
        result = calculate_trust_score(reviews)
        assert result["decision"] == "rejected"

    def test_mixed_reviews_pending(self):
        reviews = [
            {"medical_accuracy": 65, "completeness": 60, "source_reliability": 55, "recommendation": "adopt"},
            {"medical_accuracy": 45, "completeness": 40, "source_reliability": 35, "recommendation": "reject"},
            {"medical_accuracy": 55, "completeness": 50, "source_reliability": 45, "recommendation": "review"},
        ]
        result = calculate_trust_score(reviews)
        assert result["decision"] in ("pending_review", "rejected")

    def test_empty_reviews(self):
        result = calculate_trust_score([])
        assert result["score"] == 0
        assert result["decision"] == "rejected"


class TestSafetySandbox:
    def test_s_level_enters_safety(self):
        assert can_enter_safety_check(LEVEL_S) is True

    def test_a_level_enters_safety(self):
        assert can_enter_safety_check(LEVEL_A) is True

    def test_b_level_blocked_from_safety(self):
        assert can_enter_safety_check(LEVEL_B) is False

    def test_c_level_blocked_from_safety(self):
        assert can_enter_safety_check(LEVEL_C) is False

    def test_b_referenceable_in_ai(self):
        assert can_reference_in_ai(LEVEL_B) is True

    def test_c_not_referenceable_in_ai(self):
        assert can_reference_in_ai(LEVEL_C) is False


class TestDomainTrust:
    def test_cnki_is_a(self):
        assert get_domain_trust("https://cnki.net/article/123") == LEVEL_A

    def test_gov_is_s(self):
        assert get_domain_trust("https://satcm.gov.cn/page") == LEVEL_S

    def test_random_is_c(self):
        assert get_domain_trust("https://random-blog.com/post") == LEVEL_C

    def test_empty_url_is_c(self):
        assert get_domain_trust("") == LEVEL_C


class TestProvenance:
    @pytest.mark.asyncio
    async def test_record_and_get_provenance(self, trust_db):
        pid = await record_provenance(
            trust_db, "ke-trust-1", "url",
            source_url="https://cnki.net/article/123",
            source_title="测试文章",
            trust_level=LEVEL_A,
            trust_score=85.5,
        )
        assert pid.startswith("prov-")
        records = await get_provenance(trust_db, "ke-trust-1")
        assert len(records) >= 1
        assert records[0]["trust_level"] == LEVEL_A
        assert records[0]["trust_score"] == 85.5
        assert records[0]["source_domain"] == "cnki.net"

    @pytest.mark.asyncio
    async def test_get_trust_level(self, trust_db):
        await record_provenance(trust_db, "ke-trust-1", "seed", trust_level=LEVEL_S)
        await record_provenance(trust_db, "ke-trust-1", "url", trust_level=LEVEL_B)
        level = await get_trust_level(trust_db, "ke-trust-1")
        assert level == LEVEL_S

    @pytest.mark.asyncio
    async def test_no_provenance_defaults_c(self, trust_db):
        level = await get_trust_level(trust_db, "ke-trust-1")
        assert level == LEVEL_C

    @pytest.mark.asyncio
    async def test_update_trust_level(self, trust_db):
        await record_provenance(trust_db, "ke-trust-1", "url", trust_level=LEVEL_C)
        await update_trust_level(trust_db, "ke-trust-1", LEVEL_A, reason="expert_verified", verified_by="admin")
        level = await get_trust_level(trust_db, "ke-trust-1")
        assert level == LEVEL_A


class TestAgentToolsTrust:
    @pytest.mark.asyncio
    async def test_tool_detect_conflicts_no_conflict(self, trust_db):
        from app.agent_tools import tool_detect_conflicts
        conflicts = await tool_detect_conflicts(
            trust_db, "ke-trust-1", {"nature": "温"}
        )
        assert conflicts == []

    @pytest.mark.asyncio
    async def test_tool_detect_conflicts_found(self, trust_db):
        from app.agent_tools import tool_detect_conflicts
        conflicts = await tool_detect_conflicts(
            trust_db, "ke-trust-1", {"nature": "寒"}
        )
        assert len(conflicts) >= 1
        assert any(c["field"] == "nature" for c in conflicts)

    @pytest.mark.asyncio
    async def test_tool_record_provenance(self, trust_db):
        from app.agent_tools import tool_record_provenance
        pid = await tool_record_provenance(
            trust_db, "ke-trust-1", "url",
            source_url="https://test.com",
            trust_level=LEVEL_B,
            trust_score=72.3,
        )
        assert pid.startswith("prov-")

    def test_tool_generate_summary(self):
        from app.agent_tools import tool_generate_summary
        summary = tool_generate_summary("这是一段很长的文本内容" * 20)
        assert "这是一段很长的文本内容" in summary
        assert summary.endswith("...")
