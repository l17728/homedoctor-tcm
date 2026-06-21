"""Tests for P3 features: interests, consensus, URL health, translation."""

import pytest


class TestUserInterests:
    @pytest.mark.asyncio
    async def test_empty_interests(self, client):
        resp = await client.get("/api/user/interests")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 0

    @pytest.mark.asyncio
    async def test_interest_classification(self):
        from app.routers.p3_features import _classify_search_domain
        assert _classify_search_domain("降压药有什么") == "老年慢性病"
        assert _classify_search_domain("小儿感冒怎么办") == "儿科调理"
        assert _classify_search_domain("太极拳怎么练") == "功法修炼"
        assert _classify_search_domain("黄芪补气") == "补益养生"
        assert _classify_search_domain("random text") == ""


class TestCommunityConsensus:
    @pytest.mark.asyncio
    async def test_consensus_scan_empty(self, client):
        resp = await client.post("/api/admin/community-consensus-scan")
        assert resp.status_code == 200
        assert "upgraded" in resp.json()

    @pytest.mark.asyncio
    async def test_consensus_triggers_upgrade(self, client, db):
        for i in range(3):
            await db.execute(
                """INSERT INTO knowledge_provenance (id, entity_id, source_type, trust_level, trust_score, imported_by)
                   VALUES (?, 'ke-consensus-test', 'url', 'B', 70.0, ?)""",
                (f"prov-cons-{i}", f"user-{i}"),
            )
        resp = await client.post("/api/admin/community-consensus-scan")
        assert resp.status_code == 200
        assert resp.json()["upgraded"] >= 1


class TestUrlHealth:
    @pytest.mark.asyncio
    async def test_url_stats_empty(self, client):
        resp = await client.get("/api/admin/url-health-stats")
        assert resp.status_code == 200
        assert "total_external_urls" in resp.json()

    @pytest.mark.asyncio
    async def test_url_stats_with_data(self, client, db):
        await db.execute(
            """INSERT INTO knowledge_chunks
               (id, entity_id, chunk_index, chunk_text, chunk_type, token_count, metadata, source_url, source_type)
               VALUES ('url-test-1', NULL, 0, 'test', 'external', 4, '{}', 'https://example.com', 'external')"""
        )
        resp = await client.get("/api/admin/url-health-stats")
        assert resp.json()["total_external_urls"] >= 1


class TestTranslateCheck:
    @pytest.mark.asyncio
    async def test_translate_check(self, client):
        resp = await client.post("/api/admin/translate-check")
        assert resp.status_code == 200
        assert "flagged_for_translation" in resp.json()

    @pytest.mark.asyncio
    async def test_translate_flags_english(self, client, db):
        await db.execute(
            """INSERT INTO knowledge_entities
               (id, entity_type, source_table, source_id, title, summary,
                keywords, tags, category, properties, source_type, status)
               VALUES ('ke-en-test', 'article', 'test', 'en1', 'Astragalus benefits',
                       'This herb boosts immune system function', '[]', '[]', 'en', '{}', 'system', 'active')"""
        )
        resp = await client.post("/api/admin/translate-check")
        assert resp.json()["flagged_for_translation"] >= 1
