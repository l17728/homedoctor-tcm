"""Tests for AI classification management endpoints (spec §7.3 V2)."""

import pytest
from httpx import AsyncClient


# ===========================================================================
# POST /api/ai-classify/suggest
# ===========================================================================

@pytest.mark.asyncio
async def test_suggest_tags_returns_tags(client: AsyncClient, auth_headers: dict):
    """POST /api/ai-classify/suggest returns 1-3 suggested tags."""
    resp = await client.post("/api/ai-classify/suggest", json={
        "entry_type": "knowledge",
        "title": "黄芪补气升阳的功效与用法",
        "content": "黄芪是一味经典的补气中药，具有健脾益气、升阳举陷的功效，日常保健中常用于气虚体质的调理。",
    }, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "suggested_tags" in data
    assert isinstance(data["suggested_tags"], list)
    assert 1 <= len(data["suggested_tags"]) <= 3
    # Keyword fallback should find "补气" and "健脾"
    assert "补气" in data["suggested_tags"] or "健脾" in data["suggested_tags"]


@pytest.mark.asyncio
async def test_suggest_tags_health_content(client: AsyncClient, auth_headers: dict):
    """Suggest endpoint recognises health/养生 content."""
    resp = await client.post("/api/ai-classify/suggest", json={
        "entry_type": "knowledge",
        "title": "日常养生保健指南",
        "content": "日常保健养生建议，保持健康生活方式。",
    }, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["suggested_tags"]) >= 1


@pytest.mark.asyncio
async def test_suggest_tags_empty_body_rejected(client: AsyncClient, auth_headers: dict):
    """Empty title and content → 422."""
    resp = await client.post("/api/ai-classify/suggest", json={
        "entry_type": "knowledge",
        "title": "",
        "content": "",
    }, headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_suggest_tags_requires_auth(raw_client: AsyncClient):
    """No auth header → 401/403."""
    resp = await raw_client.post("/api/ai-classify/suggest", json={
        "title": "test",
        "content": "test",
    })
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_suggest_tags_constitution_content(client: AsyncClient, auth_headers: dict):
    """Suggest endpoint recognises constitution keywords."""
    resp = await client.post("/api/ai-classify/suggest", json={
        "entry_type": "knowledge",
        "title": "气虚体质的调理方法",
        "content": "气虚体质的人容易疲劳，需要补气调理。",
    }, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    # Should find 气虚体质 or 补气
    tags = data["suggested_tags"]
    assert len(tags) >= 1


# ===========================================================================
# POST /api/ai-classify/duplicates
# ===========================================================================

@pytest.mark.asyncio
async def test_detect_duplicates_finds_similar(client: AsyncClient, auth_headers: dict):
    """Detects duplicates with >80% character overlap."""
    resp = await client.post("/api/ai-classify/duplicates", json={
        "entries": [
            {"id": "a1", "title": "黄芪补气的功效", "content": "..."},
            {"id": "a2", "title": "黄芪补气功效", "content": "..."},  # very similar
            {"id": "a3", "title": "完全不同的标题", "content": "..."},
        ],
    }, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "duplicates" in data
    assert isinstance(data["duplicates"], list)
    # a1 and a2 should be flagged (high char overlap)
    found_pair = False
    for dup in data["duplicates"]:
        ids = {dup["id_a"], dup["id_b"]}
        if ids == {"a1", "a2"}:
            found_pair = True
            assert dup["similarity"] >= 0.80
            assert "reason" in dup
    assert found_pair, f"a1-a2 pair should be detected as duplicate: {data['duplicates']}"


@pytest.mark.asyncio
async def test_detect_duplicates_no_match(client: AsyncClient, auth_headers: dict):
    """Completely different titles → no duplicates."""
    resp = await client.post("/api/ai-classify/duplicates", json={
        "entries": [
            {"id": "x1", "title": "ABC", "content": ""},
            {"id": "x2", "title": "DEF", "content": ""},
        ],
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["duplicates"] == []


@pytest.mark.asyncio
async def test_detect_duplicates_empty_list(client: AsyncClient, auth_headers: dict):
    """Empty or single entry → no duplicates."""
    resp = await client.post("/api/ai-classify/duplicates", json={
        "entries": [{"id": "s1", "title": "唯一", "content": ""}],
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["duplicates"] == []


# ===========================================================================
# POST /api/ai-classify/merge
# ===========================================================================

@pytest.mark.asyncio
async def test_merge_entries_success(client: AsyncClient, auth_headers: dict):
    """Merge two knowledge entries — content combined, tags merged, source deleted."""
    import uuid

    # Get the actual user_id from the auth endpoint
    me_resp = await client.get("/api/auth/me", headers=auth_headers)
    assert me_resp.status_code == 200
    user_id = me_resp.json()["id"]

    source_id = f"test-src-{uuid.uuid4()}"
    target_id = f"test-tgt-{uuid.uuid4()}"

    from app.database import get_db
    db = get_db()

    await db.execute(
        """INSERT INTO knowledge_entries (id, user_id, entry_type, title, content, tags, source_type)
           VALUES (?, ?, 'knowledge_card', ?, ?, ?, 'manual')""",
        (source_id, user_id, "黄芪功效", "黄芪补气升阳", '["补气"]'),
    )
    await db.execute(
        """INSERT INTO knowledge_entries (id, user_id, entry_type, title, content, tags, source_type)
           VALUES (?, ?, 'knowledge_card', ?, ?, ?, 'manual')""",
        (target_id, user_id, "补气中药", "人参大补元气", '["补气", "元气"]'),
    )

    resp = await client.post("/api/ai-classify/merge", json={
        "source_id": source_id,
        "target_id": target_id,
    }, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["merged_id"] == target_id
    assert data["deleted_id"] == source_id

    # Verify source is deleted
    deleted_row = await db.query_one(
        "SELECT * FROM knowledge_entries WHERE id = ?", (source_id,)
    )
    assert deleted_row is None

    # Verify target has merged content
    target_row = await db.query_one(
        "SELECT * FROM knowledge_entries WHERE id = ?", (target_id,)
    )
    assert target_row is not None
    assert "黄芪补气升阳" in (target_row["content"] or "")
    assert "人参大补元气" in (target_row["content"] or "")


@pytest.mark.asyncio
async def test_merge_entries_missing_source(client: AsyncClient, auth_headers: dict):
    """Merge with non-existent source → 404."""
    resp = await client.post("/api/ai-classify/merge", json={
        "source_id": "nonexistent",
        "target_id": "also-nonexistent",
    }, headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_merge_entries_same_id(client: AsyncClient, auth_headers: dict):
    """Merge with source_id == target_id → 422."""
    resp = await client.post("/api/ai-classify/merge", json={
        "source_id": "same",
        "target_id": "same",
    }, headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_merge_entries_missing_fields(client: AsyncClient, auth_headers: dict):
    """Merge without IDs → 422."""
    resp = await client.post("/api/ai-classify/merge", json={}, headers=auth_headers)
    assert resp.status_code == 422


# ===========================================================================
# POST /api/ai-classify/auto-tag
# ===========================================================================

@pytest.mark.asyncio
async def test_auto_tag_bookmarks_success(client: AsyncClient, auth_headers: dict):
    """Auto-tag classifies untagged bookmarks."""
    # Create untagged bookmarks
    await client.post("/api/bookmarks", json={
        "entry_type": "knowledge",
        "title": "黄芪补气升阳",
        "content": "黄芪是补气要药",
        "tags": [],
    }, headers=auth_headers)
    await client.post("/api/bookmarks", json={
        "entry_type": "knowledge",
        "title": "日常养生",
        "content": "日常保健建议",
        "tags": [],
    }, headers=auth_headers)
    # Create a tagged bookmark (should be skipped)
    await client.post("/api/bookmarks", json={
        "entry_type": "knowledge",
        "title": "已标注",
        "content": "已有标签",
        "tags": ["已分类"],
    }, headers=auth_headers)

    resp = await client.post("/api/ai-classify/auto-tag", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "classified" in data
    assert "failed" in data
    assert data["classified"] >= 1


@pytest.mark.asyncio
async def test_auto_tag_no_untagged(client: AsyncClient, auth_headers: dict):
    """Auto-tag with no untagged bookmarks → classified=0."""
    # Create only tagged bookmarks
    await client.post("/api/bookmarks", json={
        "entry_type": "knowledge",
        "title": "已标注内容",
        "content": "内容",
        "tags": ["已分类"],
    }, headers=auth_headers)

    resp = await client.post("/api/ai-classify/auto-tag", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["classified"] == 0


# ===========================================================================
# Unit tests for helper functions
# ===========================================================================

class TestTitleSimilarity:
    def test_identical(self):
        from app.routers.ai_classify import _title_similarity
        assert _title_similarity("黄芪补气", "黄芪补气") == 1.0

    def test_completely_different(self):
        from app.routers.ai_classify import _title_similarity
        sim = _title_similarity("ABC", "XYZ")
        assert sim == 0.0

    def test_high_overlap(self):
        from app.routers.ai_classify import _title_similarity
        sim = _title_similarity("黄芪补气的功效", "黄芪补气功效")
        assert sim >= 0.80

    def test_empty_strings(self):
        from app.routers.ai_classify import _title_similarity
        assert _title_similarity("", "") == 0.0
        assert _title_similarity("test", "") == 0.0


class TestParseTagList:
    def test_json_array(self):
        from app.routers.ai_classify import _parse_tag_list
        result = _parse_tag_list('["补气", "健脾", "日常保健"]')
        assert result == ["补气", "健脾", "日常保健"]

    def test_markdown_code_block(self):
        from app.routers.ai_classify import _parse_tag_list
        result = _parse_tag_list('```json\n["补气", "健脾"]\n```')
        assert result == ["补气", "健脾"]

    def test_plain_text_comma(self):
        from app.routers.ai_classify import _parse_tag_list
        result = _parse_tag_list("补气, 健脾, 日常保健")
        assert "补气" in result
        assert "健脾" in result

    def test_empty(self):
        from app.routers.ai_classify import _parse_tag_list
        assert _parse_tag_list("") == []
        assert _parse_tag_list("   ") == []
