"""Tests for P2 features: conversation summary, feedback, freshness."""

import pytest
import pytest_asyncio
from app.database import SqliteAdapter, init_db, seed_safety_rules, seed_test_data


@pytest_asyncio.fixture
async def p2_db():
    adapter = SqliteAdapter(":memory:")
    await adapter.connect()
    await init_db(adapter)
    await seed_safety_rules(adapter)
    await seed_test_data(adapter)
    await adapter.execute(
        """INSERT INTO knowledge_entities
           (id, entity_type, source_table, source_id, title, summary,
            keywords, tags, category, properties, source_type, status)
           VALUES ('ke-p2-test', 'herb', 'test', 'p1', '测试药材',
                   '测试', '[]', '[]', '测试', '{}', 'system', 'active')"""
    )
    yield adapter
    await adapter.close()


class TestFeedback:
    @pytest.mark.asyncio
    async def test_submit_helpful(self, client):
        resp = await client.post("/api/knowledge/ke-p2-test/feedback", json={
            "rating": "helpful", "comment": "有用"
        })
        assert resp.status_code == 200
        assert resp.json()["rating"] == "helpful"

    @pytest.mark.asyncio
    async def test_submit_inaccurate(self, client):
        resp = await client.post("/api/knowledge/ke-p2-test/feedback", json={
            "rating": "inaccurate"
        })
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_invalid_rating(self, client):
        resp = await client.post("/api/knowledge/ke-p2-test/feedback", json={
            "rating": "invalid"
        })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_get_feedback(self, client):
        await client.post("/api/knowledge/ke-p2-test/feedback", json={"rating": "helpful"})
        resp = await client.get("/api/knowledge/ke-p2-test/feedback")
        assert resp.status_code == 200
        assert resp.json()["feedback"].get("helpful", 0) >= 1

    @pytest.mark.asyncio
    async def test_feedback_creates_review_request(self, p2_db):
        from app.routers.p2_features import submit_feedback
        from app.trust_engine import record_provenance, get_trust_level

        await record_provenance(p2_db, "ke-p2-test", "seed", trust_level="A", trust_score=85)

        for i in range(3):
            await p2_db.execute(
                """INSERT OR REPLACE INTO knowledge_feedback (id, entity_id, user_id, rating)
                   VALUES (?, ?, ?, 'inaccurate')""",
                (f"fb-{i}", "ke-p2-test", f"user-{i}"),
            )

        from app.routers.p2_features import FeedbackRequest
        req = FeedbackRequest(rating="inaccurate")
        await submit_feedback("ke-p2-test", req, p2_db, {"id": "user-4"})

        level = await get_trust_level(p2_db, "ke-p2-test")
        assert level == "A"

        log_rows = await p2_db.query(
            "SELECT * FROM agent_logs WHERE action_type='trust_downgrade_request' AND entity_id=?",
            ("ke-p2-test",),
        )
        assert len(log_rows) >= 1
        assert log_rows[0]["decision"] == "pending_admin_review"


class TestConversationSummary:
    @pytest.mark.asyncio
    async def test_summarize_nonexistent(self, client):
        resp = await client.post("/api/chat/nonexistent/summarize", json={"auto_import": False})
        assert resp.status_code in (404, 500)

    @pytest.mark.asyncio
    async def test_summarize_no_import(self, client, db):
        user_resp = await client.get("/api/auth/me")
        user_id = user_resp.json().get("id", "")
        await db.execute(
            """INSERT INTO conversations (id, user_id, title, messages)
               VALUES ('conv-test-1', ?, '测试',
               '[{"role":"user","content":"我最近总是口干口苦，尤其是早上起床的时候特别明显，已经持续了两周了，请问是什么原因？"},{"role":"assistant","content":"根据您描述的症状，口干口苦早上明显，可能是肝胆湿热或胃热。建议饮食清淡，避免辛辣油腻，可适当饮用菊花茶或决明子茶。"}]')""",
            (user_id,),
        )
        resp = await client.post("/api/chat/conv-test-1/summarize", json={"auto_import": False})
        assert resp.status_code == 200
        data = resp.json()
        assert "extracted" in data
        assert data["imported"] is False


class TestFreshness:
    @pytest.mark.asyncio
    async def test_freshness_check(self, client, db):
        await db.execute(
            """INSERT INTO knowledge_provenance (id, entity_id, source_type, content_date, freshness_status)
               VALUES ('prov-fresh-1', 'ke-p2-test', 'url', '2018-01-01', 'current')"""
        )
        resp = await client.post("/api/admin/freshness-check")
        assert resp.status_code == 200
        assert resp.json()["scanned"] >= 1

    @pytest.mark.asyncio
    async def test_freshness_stats(self, client):
        resp = await client.get("/api/admin/freshness-stats")
        assert resp.status_code == 200
        assert "distribution" in resp.json()

    @pytest.mark.asyncio
    async def test_unauthorized_freshness(self, raw_client):
        resp = await raw_client.post("/api/admin/freshness-check")
        assert resp.status_code == 401
