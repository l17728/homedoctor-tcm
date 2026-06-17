"""Tests for AI Knowledge Extractor (app/extractor.py + app/routers/extractor.py).

Spec §8.4 — auto-extract health knowledge from chat conversations.

The LLM call is mocked via ``monkeypatch`` to ensure deterministic test results.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.database import DbAdapter


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_CONVERSATION = [
    {"role": "user", "content": "脾虚怎么调理？"},
    {"role": "assistant", "content": "脾虚建议用参苓白术散，补气健脾。也可以配合黄芪泡水，黄芪是补气要药，能升阳固表。饮食上可以多吃山药、薏苡仁，有健脾祛湿之效。穴位方面，经常按揉足三里穴有助于调理脾胃。"},
]

SAMPLE_EXTRACTION_RESULT = json.dumps([
    {
        "title": "参苓白术散健脾调理",
        "content": "脾虚可使用参苓白术散补气健脾，配合黄芪泡水升阳固表。",
        "category": "方剂推荐",
        "herbs_mentioned": ["黄芪"],
    },
    {
        "title": "健脾祛湿食疗",
        "content": "多吃山药、薏苡仁，有健脾祛湿之效。",
        "category": "食疗方法",
        "herbs_mentioned": [],
    },
    {
        "title": "足三里穴按摩",
        "content": "经常按揉足三里穴有助于调理脾胃功能。",
        "category": "穴位按摩",
        "herbs_mentioned": [],
    },
], ensure_ascii=False)

SAMPLE_EMPTY_RESULT = "[]"


# ---------------------------------------------------------------------------
# Helper: mock LLM
# ---------------------------------------------------------------------------

def _mock_llm_response(response_text: str):
    """Create an AsyncMock for _call_llm_for_extraction returning response_text."""
    mock = AsyncMock()
    mock.return_value = response_text
    return mock


async def _save_conversation(
    db: DbAdapter,
    user_id: str,
    messages: list[dict],
    conv_id: str = "conv-test-1",
    title: str = "测试对话",
) -> None:
    """Insert a conversation row directly into the DB for testing."""
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO conversations
           (id, user_id, title, model_id, messages, reasoning_trace, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            conv_id,
            user_id,
            title,
            "mock-v1",
            json.dumps(messages, ensure_ascii=False),
            "[]",
            now,
            now,
        ),
    )


# ---------------------------------------------------------------------------
# Unit tests: extract_knowledge (core logic)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_knowledge_returns_items(db: DbAdapter, monkeypatch):
    """extract_knowledge should return structured knowledge from a conversation."""
    monkeypatch.setattr(
        "app.extractor._call_llm_for_extraction",
        _mock_llm_response(SAMPLE_EXTRACTION_RESULT),
    )

    items = await _safe_import_extract_knowledge(SAMPLE_CONVERSATION, db)

    assert len(items) == 3
    assert items[0]["title"] == "参苓白术散健脾调理"
    assert items[0]["category"] == "方剂推荐"
    assert "黄芪" in items[0]["herbs_mentioned"]  # 黄芪 is in test seed data
    assert items[1]["category"] == "食疗方法"
    assert items[2]["category"] == "穴位按摩"


@pytest.mark.asyncio
async def test_extract_knowledge_empty_messages(db: DbAdapter):
    """extract_knowledge should return empty list for empty messages."""
    from app.extractor import extract_knowledge
    items = await extract_knowledge([], db)
    assert items == []


@pytest.mark.asyncio
async def test_extract_knowledge_llm_unavailable(db: DbAdapter, monkeypatch):
    """extract_knowledge should return empty list when LLM is unavailable."""
    monkeypatch.setattr(
        "app.extractor._call_llm_for_extraction",
        _mock_llm_response(None),
    )

    from app.extractor import extract_knowledge
    items = await extract_knowledge(SAMPLE_CONVERSATION, db)
    assert items == []


@pytest.mark.asyncio
async def test_extract_knowledge_no_valuable_content(db: DbAdapter, monkeypatch):
    """extract_knowledge should return empty list when no knowledge is found."""
    monkeypatch.setattr(
        "app.extractor._call_llm_for_extraction",
        _mock_llm_response(SAMPLE_EMPTY_RESULT),
    )

    from app.extractor import extract_knowledge
    items = await extract_knowledge(SAMPLE_CONVERSATION, db)
    assert items == []


@pytest.mark.asyncio
async def test_extract_knowledge_invalid_category_normalised(db: DbAdapter, monkeypatch):
    """Invalid category should be normalised to default."""
    bad_result = json.dumps([{
        "title": "测试",
        "content": "测试内容",
        "category": "无效分类",
        "herbs_mentioned": [],
    }], ensure_ascii=False)
    monkeypatch.setattr(
        "app.extractor._call_llm_for_extraction",
        _mock_llm_response(bad_result),
    )

    from app.extractor import extract_knowledge
    items = await extract_knowledge(SAMPLE_CONVERSATION, db)
    assert len(items) == 1
    assert items[0]["category"] == "养生建议"


@pytest.mark.asyncio
async def test_extract_knowledge_filters_unknown_herbs(db: DbAdapter, monkeypatch):
    """Herbs not in DB should be filtered out."""
    result = json.dumps([{
        "title": "测试",
        "content": "测试内容",
        "category": "药材功效",
        "herbs_mentioned": ["黄芪", "不存在的药材XYZ"],
    }], ensure_ascii=False)
    monkeypatch.setattr(
        "app.extractor._call_llm_for_extraction",
        _mock_llm_response(result),
    )

    from app.extractor import extract_knowledge
    items = await extract_knowledge(SAMPLE_CONVERSATION, db)
    assert len(items) == 1
    assert "黄芪" in items[0]["herbs_mentioned"]
    assert "不存在的药材XYZ" not in items[0]["herbs_mentioned"]


@pytest.mark.asyncio
async def test_extract_knowledge_handles_markdown_code_block(db: DbAdapter, monkeypatch):
    """LLM response wrapped in markdown code block should parse correctly."""
    wrapped = f"```json\n{SAMPLE_EXTRACTION_RESULT}\n```"
    monkeypatch.setattr(
        "app.extractor._call_llm_for_extraction",
        _mock_llm_response(wrapped),
    )

    from app.extractor import extract_knowledge
    items = await extract_knowledge(SAMPLE_CONVERSATION, db)
    assert len(items) == 3


@pytest.mark.asyncio
async def test_extract_knowledge_handles_prose_wrapped_json(db: DbAdapter, monkeypatch):
    """LLM response with surrounding prose should still parse."""
    prose_wrapped = f"好的，以下是提取的知识点：\n{SAMPLE_EXTRACTION_RESULT}\n以上是结果。"
    monkeypatch.setattr(
        "app.extractor._call_llm_for_extraction",
        _mock_llm_response(prose_wrapped),
    )

    from app.extractor import extract_knowledge
    items = await extract_knowledge(SAMPLE_CONVERSATION, db)
    assert len(items) == 3


@pytest.mark.asyncio
async def test_extract_knowledge_handles_single_dict(db: DbAdapter, monkeypatch):
    """LLM returning a single dict (not array) should still parse."""
    single = json.dumps({
        "title": "单一知识点",
        "content": "单一内容",
        "category": "养生建议",
        "herbs_mentioned": [],
    }, ensure_ascii=False)
    monkeypatch.setattr(
        "app.extractor._call_llm_for_extraction",
        _mock_llm_response(single),
    )

    from app.extractor import extract_knowledge
    items = await extract_knowledge(SAMPLE_CONVERSATION, db)
    assert len(items) == 1
    assert items[0]["title"] == "单一知识点"


@pytest.mark.asyncio
async def test_extract_knowledge_invalid_json(db: DbAdapter, monkeypatch):
    """Malformed JSON should return empty list, not crash."""
    monkeypatch.setattr(
        "app.extractor._call_llm_for_extraction",
        _mock_llm_response("this is not json at all"),
    )

    from app.extractor import extract_knowledge
    items = await extract_knowledge(SAMPLE_CONVERSATION, db)
    assert items == []


@pytest.mark.asyncio
async def test_extract_knowledge_skips_invalid_items(db: DbAdapter, monkeypatch):
    """Items missing title or content should be skipped."""
    result = json.dumps([
        {"title": "有标题", "content": "有内容", "category": "养生建议", "herbs_mentioned": []},
        {"title": "", "content": "空标题", "category": "养生建议", "herbs_mentioned": []},
        {"title": "空内容", "content": "", "category": "养生建议", "herbs_mentioned": []},
        {"content": "无标题", "category": "养生建议", "herbs_mentioned": []},
        {"title": "无内容", "category": "养生建议", "herbs_mentioned": []},
        "not a dict",
    ], ensure_ascii=False)
    monkeypatch.setattr(
        "app.extractor._call_llm_for_extraction",
        _mock_llm_response(result),
    )

    from app.extractor import extract_knowledge
    items = await extract_knowledge(SAMPLE_CONVERSATION, db)
    assert len(items) == 1
    assert items[0]["title"] == "有标题"


# ---------------------------------------------------------------------------
# Unit tests: auto_extract_for_user
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auto_extract_saves_entries(db: DbAdapter, monkeypatch):
    """auto_extract should process conversations and save knowledge entries."""
    user_id = "test-user-auto-1"
    await _save_conversation(db, user_id, SAMPLE_CONVERSATION)

    monkeypatch.setattr(
        "app.extractor._call_llm_for_extraction",
        _mock_llm_response(SAMPLE_EXTRACTION_RESULT),
    )

    from app.extractor import auto_extract_for_user
    count = await auto_extract_for_user(user_id, db)

    assert count == 3  # All 3 items are new

    # Verify entries saved
    rows = await db.query(
        "SELECT * FROM knowledge_entries WHERE user_id = ? AND source_type = 'extractor'",
        (user_id,),
    )
    assert len(rows) == 3
    titles = {r["title"] for r in rows}
    assert "参苓白术散健脾调理" in titles
    assert "健脾祛湿食疗" in titles
    assert "足三里穴按摩" in titles


@pytest.mark.asyncio
async def test_auto_extract_no_conversations(db: DbAdapter, monkeypatch):
    """auto_extract should return 0 if user has no conversations."""
    monkeypatch.setattr(
        "app.extractor._call_llm_for_extraction",
        _mock_llm_response(SAMPLE_EXTRACTION_RESULT),
    )

    from app.extractor import auto_extract_for_user
    count = await auto_extract_for_user("no-conv-user", db)
    assert count == 0


@pytest.mark.asyncio
async def test_auto_extract_dedup(db: DbAdapter, monkeypatch):
    """auto_extract should not create duplicate entries."""
    user_id = "test-user-dedup-1"
    await _save_conversation(db, user_id, SAMPLE_CONVERSATION)

    monkeypatch.setattr(
        "app.extractor._call_llm_for_extraction",
        _mock_llm_response(SAMPLE_EXTRACTION_RESULT),
    )

    from app.extractor import auto_extract_for_user

    # First run: should extract 3 items
    count1 = await auto_extract_for_user(user_id, db)
    assert count1 == 3

    # Manually reset rate limit by deleting recent entries timestamps
    # (Simulating a new hour window)
    await db.execute(
        "UPDATE knowledge_entries SET created_at = '2020-01-01T00:00:00' WHERE user_id = ?",
        (user_id,),
    )

    # Second run on the same conversation: should find all as duplicates
    count2 = await auto_extract_for_user(user_id, db)
    assert count2 == 0  # All already exist


@pytest.mark.asyncio
async def test_auto_extract_dedup_similar_title(db: DbAdapter, monkeypatch):
    """auto_extract should detect similar titles as duplicates."""
    user_id = "test-user-dedup-2"

    # Pre-insert an entry with a similar title
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO knowledge_entries
           (id, user_id, entry_type, title, content, tags, source_type, created_at, updated_at)
           VALUES (?, ?, 'knowledge_card', ?, ?, '[]', 'extractor', ?, ?)""",
        ("pre-existing-1", user_id, "黄芪功效详解", "已有内容", now, now),
    )

    await _save_conversation(db, user_id, SAMPLE_CONVERSATION)

    # LLM returns an item with similar title "黄芪的功效"
    result = json.dumps([{
        "title": "黄芪功效",
        "content": "黄芪是补气要药",
        "category": "药材功效",
        "herbs_mentioned": ["黄芪"],
    }], ensure_ascii=False)
    monkeypatch.setattr(
        "app.extractor._call_llm_for_extraction",
        _mock_llm_response(result),
    )

    from app.extractor import auto_extract_for_user
    count = await auto_extract_for_user(user_id, db)
    assert count == 0  # Should be detected as duplicate


@pytest.mark.asyncio
async def test_auto_extract_rate_limited(db: DbAdapter, monkeypatch):
    """auto_extract should be rate limited to 1 per hour."""
    user_id = "test-user-rate-1"
    await _save_conversation(db, user_id, SAMPLE_CONVERSATION)

    monkeypatch.setattr(
        "app.extractor._call_llm_for_extraction",
        _mock_llm_response(SAMPLE_EXTRACTION_RESULT),
    )

    from app.extractor import auto_extract_for_user

    # First run: extracts 3 items
    count1 = await auto_extract_for_user(user_id, db)
    assert count1 == 3

    # Second run immediately: rate limited
    count2 = await auto_extract_for_user(user_id, db)
    assert count2 == 0  # Rate limited


@pytest.mark.asyncio
async def test_auto_extract_multiple_conversations(db: DbAdapter, monkeypatch):
    """auto_extract should process multiple conversations."""
    user_id = "test-user-multi-1"
    await _save_conversation(db, user_id, SAMPLE_CONVERSATION, conv_id="conv-1")
    await _save_conversation(
        db, user_id,
        [
            {"role": "user", "content": "感冒怎么办？"},
            {"role": "assistant", "content": "风寒感冒可用荆防败毒散。"},
        ],
        conv_id="conv-2",
    )

    monkeypatch.setattr(
        "app.extractor._call_llm_for_extraction",
        _mock_llm_response(SAMPLE_EXTRACTION_RESULT),
    )

    from app.extractor import auto_extract_for_user
    count = await auto_extract_for_user(user_id, db)
    # Both conversations return the same 3 items, but conv-2 items are duplicates
    assert count == 3


# ---------------------------------------------------------------------------
# Dedup logic unit tests
# ---------------------------------------------------------------------------

def test_dedup_exact_match():
    from app.extractor import _is_duplicate
    assert _is_duplicate("黄芪功效", ["黄芪功效"]) is True


def test_dedup_normalized_match():
    from app.extractor import _is_duplicate
    assert _is_duplicate("黄芪，功效。", ["黄芪功效"]) is True


def test_dedup_substring_match():
    from app.extractor import _is_duplicate
    assert _is_duplicate("黄芪", ["黄芪的功效详解"]) is True


def test_dedup_different_titles():
    from app.extractor import _is_duplicate
    assert _is_duplicate("枸杞泡水", ["黄芪功效"]) is False


def test_dedup_empty_title():
    from app.extractor import _is_duplicate
    assert _is_duplicate("", ["黄芪功效"]) is False


# ---------------------------------------------------------------------------
# JSON parsing unit tests
# ---------------------------------------------------------------------------

def test_parse_raw_json_array():
    from app.extractor import _parse_extraction_response
    result = _parse_extraction_response('[{"title": "a", "content": "b"}]')
    assert len(result) == 1


def test_parse_markdown_wrapped():
    from app.extractor import _parse_extraction_response
    result = _parse_extraction_response('```json\n[{"title": "a", "content": "b"}]\n```')
    assert len(result) == 1


def test_parse_empty():
    from app.extractor import _parse_extraction_response
    assert _parse_extraction_response("") == []
    assert _parse_extraction_response("   ") == []


def test_parse_single_dict():
    from app.extractor import _parse_extraction_response
    result = _parse_extraction_response('{"title": "a", "content": "b"}')
    assert len(result) == 1


def test_parse_invalid():
    from app.extractor import _parse_extraction_response
    assert _parse_extraction_response("not json") == []


# ---------------------------------------------------------------------------
# Endpoint tests: POST /api/extractor/extract
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_endpoint_success(client: AsyncClient, auth_headers: dict, monkeypatch):
    """POST /api/extractor/extract should return extracted knowledge."""
    monkeypatch.setattr("app.config.settings.LLM_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.extractor._call_llm_for_extraction",
        _mock_llm_response(SAMPLE_EXTRACTION_RESULT),
    )

    response = await client.post(
        "/api/extractor/extract",
        json={"messages": SAMPLE_CONVERSATION},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 3
    assert len(data["items"]) == 3
    assert data["llm_available"] is True


@pytest.mark.asyncio
async def test_extract_endpoint_requires_auth(client: AsyncClient):
    """POST /api/extractor/extract should require authentication."""
    response = await client.post(
        "/api/extractor/extract",
        json={"messages": SAMPLE_CONVERSATION},
    )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_extract_endpoint_empty_messages_rejected(
    client: AsyncClient, auth_headers: dict
):
    """Empty messages should return 422."""
    response = await client.post(
        "/api/extractor/extract",
        json={"messages": []},
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_extract_endpoint_llm_unavailable(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    """When LLM is unavailable, should return empty items gracefully."""
    monkeypatch.setattr(
        "app.extractor._call_llm_for_extraction",
        _mock_llm_response(None),
    )

    response = await client.post(
        "/api/extractor/extract",
        json={"messages": SAMPLE_CONVERSATION},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["items"] == []


# ---------------------------------------------------------------------------
# Endpoint tests: POST /api/extractor/auto-extract
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auto_extract_endpoint_success(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    """POST /api/extractor/auto-extract should process conversations and save."""
    # First save a conversation
    await client.post(
        "/api/chat/conversations",
        json={
            "title": "脾虚调理",
            "messages": SAMPLE_CONVERSATION,
        },
        headers=auth_headers,
    )

    monkeypatch.setattr(
        "app.extractor._call_llm_for_extraction",
        _mock_llm_response(SAMPLE_EXTRACTION_RESULT),
    )

    response = await client.post(
        "/api/extractor/auto-extract",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["extracted"] == 3
    assert data["rate_limited"] is False


@pytest.mark.asyncio
async def test_auto_extract_endpoint_rate_limited(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    """Second auto-extract within an hour should be rate limited."""
    # Save a conversation
    await client.post(
        "/api/chat/conversations",
        json={"title": "测试", "messages": SAMPLE_CONVERSATION},
        headers=auth_headers,
    )

    monkeypatch.setattr(
        "app.extractor._call_llm_for_extraction",
        _mock_llm_response(SAMPLE_EXTRACTION_RESULT),
    )

    # First run
    response1 = await client.post("/api/extractor/auto-extract", headers=auth_headers)
    assert response1.status_code == 200
    assert response1.json()["extracted"] == 3

    # Second run — rate limited
    response2 = await client.post("/api/extractor/auto-extract", headers=auth_headers)
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["extracted"] == 0
    assert data2["rate_limited"] is True


@pytest.mark.asyncio
async def test_auto_extract_endpoint_no_conversations(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    """Auto-extract with no conversations should return 0."""
    monkeypatch.setattr(
        "app.extractor._call_llm_for_extraction",
        _mock_llm_response(SAMPLE_EXTRACTION_RESULT),
    )

    response = await client.post("/api/extractor/auto-extract", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["extracted"] == 0
    assert data["rate_limited"] is False


@pytest.mark.asyncio
async def test_auto_extract_endpoint_requires_auth(client: AsyncClient):
    """Auto-extract should require authentication."""
    response = await client.post("/api/extractor/auto-extract")
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Endpoint tests: GET /api/extractor/recent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recent_endpoint_empty(
    client: AsyncClient, auth_headers: dict
):
    """Recent endpoint should return empty for new user."""
    response = await client.get("/api/extractor/recent", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_recent_endpoint_after_extraction(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    """Recent endpoint should return auto-extracted entries."""
    # Save conversation
    await client.post(
        "/api/chat/conversations",
        json={"title": "测试", "messages": SAMPLE_CONVERSATION},
        headers=auth_headers,
    )

    monkeypatch.setattr(
        "app.extractor._call_llm_for_extraction",
        _mock_llm_response(SAMPLE_EXTRACTION_RESULT),
    )

    # Run auto-extract
    await client.post("/api/extractor/auto-extract", headers=auth_headers)

    # Get recent
    response = await client.get("/api/extractor/recent", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    titles = {item["title"] for item in data["items"]}
    assert "参苓白术散健脾调理" in titles


@pytest.mark.asyncio
async def test_recent_endpoint_requires_auth(client: AsyncClient):
    """Recent endpoint should require authentication."""
    response = await client.get("/api/extractor/recent")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_recent_endpoint_limit_param(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    """Recent endpoint should respect limit parameter."""
    # Save conversation and extract
    await client.post(
        "/api/chat/conversations",
        json={"title": "测试", "messages": SAMPLE_CONVERSATION},
        headers=auth_headers,
    )

    monkeypatch.setattr(
        "app.extractor._call_llm_for_extraction",
        _mock_llm_response(SAMPLE_EXTRACTION_RESULT),
    )

    await client.post("/api/extractor/auto-extract", headers=auth_headers)

    # Limit to 2
    response = await client.get(
        "/api/extractor/recent", params={"limit": 2}, headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2


# ---------------------------------------------------------------------------
# User isolation tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recent_isolates_by_user(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict, monkeypatch
):
    """User A's extracted knowledge should not be visible to user B."""
    # User A saves a conversation and extracts
    await client.post(
        "/api/chat/conversations",
        json={"title": "用户A对话", "messages": SAMPLE_CONVERSATION},
        headers=auth_headers,
    )

    monkeypatch.setattr(
        "app.extractor._call_llm_for_extraction",
        _mock_llm_response(SAMPLE_EXTRACTION_RESULT),
    )

    await client.post("/api/extractor/auto-extract", headers=auth_headers)

    # User B should see nothing
    response = await client.get("/api/extractor/recent", headers=second_user_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_auto_extract_isolates_by_user(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict, monkeypatch
):
    """Auto-extract should only process the current user's conversations."""
    # User A saves a conversation
    await client.post(
        "/api/chat/conversations",
        json={"title": "用户A对话", "messages": SAMPLE_CONVERSATION},
        headers=auth_headers,
    )

    monkeypatch.setattr(
        "app.extractor._call_llm_for_extraction",
        _mock_llm_response(SAMPLE_EXTRACTION_RESULT),
    )

    # User B runs auto-extract — should find 0 conversations
    response = await client.post("/api/extractor/auto-extract", headers=second_user_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["extracted"] == 0
    assert data["rate_limited"] is False


# ---------------------------------------------------------------------------
# Conversation text building
# ---------------------------------------------------------------------------

def test_build_conversation_text():
    from app.extractor import _build_conversation_text
    messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "您好"},
    ]
    text = _build_conversation_text(messages)
    assert "用户: 你好" in text
    assert "AI: 您好" in text


def test_build_conversation_text_multimodal():
    from app.extractor import _build_conversation_text
    messages = [
        {"role": "user", "content": [
            {"type": "text", "text": "这是什么药？"},
            {"type": "image_url", "image_url": {"url": "data:..."}},
        ]},
    ]
    text = _build_conversation_text(messages)
    assert "这是什么药？" in text


# ---------------------------------------------------------------------------
# Helper import (avoids issues if module not yet loaded)
# ---------------------------------------------------------------------------

async def _safe_import_extract_knowledge(messages, db):
    from app.extractor import extract_knowledge
    return await extract_knowledge(messages, db)
