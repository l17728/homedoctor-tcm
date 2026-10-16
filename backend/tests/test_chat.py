"""Tests for AI Chat router (app/routers/chat.py)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# POST /api/chat
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_normal_message(client: AsyncClient, auth_headers: dict):
    """Normal message should return mock AI response without safety warning."""
    response = await client.post(
        "/api/chat",
        json={"message": "黄芪有什么功效？", "history": []},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert "safety_warning" in data
    assert data["safety_warning"] is None
    assert data["model_used"] == "mock-v1"
    assert isinstance(data["reasoning_trace"], list)
    assert len(data["reasoning_trace"]) >= 2


@pytest.mark.asyncio
async def test_chat_emergency_keyword_detected(client: AsyncClient, auth_headers: dict):
    """Message with emergency keyword should return safety warning."""
    response = await client.post(
        "/api/chat",
        json={"message": "我突然胸痛，呼吸困难", "history": []},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["safety_warning"] is not None
    assert "120" in data["safety_warning"]
    assert data["model_used"] == "safety-layer"
    # Check reasoning trace contains keyword detection
    trace = data["reasoning_trace"]
    assert any(t.get("step") == "safety_keyword_check" for t in trace)


@pytest.mark.asyncio
async def test_chat_multiple_emergency_keywords(client: AsyncClient, auth_headers: dict):
    """Multiple emergency keywords should all be detected."""
    response = await client.post(
        "/api/chat",
        json={"message": "患者出现昏迷和抽搐，疑似中毒", "history": []},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["safety_warning"] is not None
    trace = data["reasoning_trace"]
    keyword_step = next(t for t in trace if t.get("step") == "safety_keyword_check")
    keywords = keyword_step.get("keywords", [])
    assert "昏迷" in keywords
    assert "抽搐" in keywords
    assert "中毒" in keywords


@pytest.mark.asyncio
async def test_chat_with_history(client: AsyncClient, auth_headers: dict):
    """Chat with message history should work."""
    response = await client.post(
        "/api/chat",
        json={
            "message": "感冒了怎么办",
            "history": [
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "您好，请问有什么可以帮您的？"},
            ],
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["safety_warning"] is None
    assert "感冒" in data["reply"]


@pytest.mark.asyncio
async def test_chat_requires_auth(raw_client: AsyncClient):
    """Chat endpoint should require authentication."""
    response = await raw_client.post(
        "/api/chat",
        json={"message": "test", "history": []},
    )
    assert response.status_code == 403 or response.status_code == 401


@pytest.mark.asyncio
async def test_chat_empty_message_rejected(client: AsyncClient, auth_headers: dict):
    """Empty message should be rejected by validation."""
    response = await client.post(
        "/api/chat",
        json={"message": "", "history": []},
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_history_over_20_truncated(client: AsyncClient, auth_headers: dict):
    """History with 25 entries → truncated to the most recent 20, request still works."""
    long_history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"消息{i}"}
        for i in range(25)
    ]
    response = await client.post(
        "/api/chat",
        json={"message": "今天天气怎么样", "history": long_history},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["safety_warning"] is None
    assert "今天天气" in data["reply"]


@pytest.mark.asyncio
async def test_chat_history_pagination_bounds(client: AsyncClient, auth_headers: dict):
    """GET /api/chat/history 分页参数边界：page≥1、1≤pageSize≤100."""
    # page=0 → 422
    resp = await client.get(
        "/api/chat/history", params={"page": 0}, headers=auth_headers,
    )
    assert resp.status_code == 422
    # pageSize=101 → 422
    resp = await client.get(
        "/api/chat/history", params={"pageSize": 101}, headers=auth_headers,
    )
    assert resp.status_code == 422
    # 合法边界值 page=1 / pageSize=100 → 200
    resp = await client.get(
        "/api/chat/history", params={"page": 1, "pageSize": 100},
        headers=auth_headers,
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/chat/history
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_conversations_empty(client: AsyncClient, auth_headers: dict):
    """New user should have no conversations."""
    response = await client.get("/api/chat/history", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_list_conversations_after_save(client: AsyncClient, auth_headers: dict):
    """After saving a conversation, it should appear in history."""
    # Save a conversation
    await client.post(
        "/api/chat/conversations",
        json={
            "title": "感冒咨询",
            "messages": [
                {"role": "user", "content": "感冒了"},
                {"role": "assistant", "content": "请注意休息"},
            ],
        },
        headers=auth_headers,
    )

    # List history
    response = await client.get("/api/chat/history", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert any(c["title"] == "感冒咨询" for c in data["items"])


@pytest.mark.asyncio
async def test_search_by_message_content(client: AsyncClient, auth_headers: dict):
    """Search by keyword in message content (not in title) should find the conversation.

    Spec US-7: 搜索历史对话记录 — searches all conversations containing the keyword.
    """
    await client.post(
        "/api/chat/conversations",
        json={
            "title": "日常咨询",
            "messages": [
                {"role": "user", "content": "黄芪可以治疗气虚吗？"},
                {"role": "assistant", "content": "黄芪是补气要药，适合气虚体质。"},
            ],
        },
        headers=auth_headers,
    )

    response = await client.get(
        "/api/chat/history",
        params={"q": "气虚"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    matched = [c for c in data["items"] if c["title"] == "日常咨询"]
    assert len(matched) == 1


@pytest.mark.asyncio
async def test_search_by_title_still_works(client: AsyncClient, auth_headers: dict):
    """Search by keyword in title should still return matching conversations."""
    await client.post(
        "/api/chat/conversations",
        json={
            "title": "头痛治疗",
            "messages": [
                {"role": "user", "content": "怎么处理"},
                {"role": "assistant", "content": "建议休息"},
            ],
        },
        headers=auth_headers,
    )

    response = await client.get(
        "/api/chat/history",
        params={"q": "头痛"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert any(c["title"] == "头痛治疗" for c in data["items"])


@pytest.mark.asyncio
async def test_search_no_match_returns_empty(client: AsyncClient, auth_headers: dict):
    """Search with non-existent keyword should return empty results."""
    await client.post(
        "/api/chat/conversations",
        json={
            "title": "养生",
            "messages": [
                {"role": "user", "content": "枸杞泡水"},
            ],
        },
        headers=auth_headers,
    )

    response = await client.get(
        "/api/chat/history",
        params={"q": "不存在的罕见关键词XYZ"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_search_matches_assistant_reply(client: AsyncClient, auth_headers: dict):
    """Search should match keywords in assistant replies too, not just user messages."""
    await client.post(
        "/api/chat/conversations",
        json={
            "title": "提问",
            "messages": [
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "当归补血汤是经典方剂。"},
            ],
        },
        headers=auth_headers,
    )

    response = await client.get(
        "/api/chat/history",
        params={"q": "当归补血汤"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert any(c["title"] == "提问" for c in data["items"])


@pytest.mark.asyncio
async def test_search_isolates_by_user(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    """Search should not return conversations belonging to other users."""
    await client.post(
        "/api/chat/conversations",
        json={
            "title": "用户A的记录",
            "messages": [
                {"role": "user", "content": "独特关键词紫雪丹"},
            ],
        },
        headers=auth_headers,
    )

    response = await client.get(
        "/api/chat/history",
        params={"q": "紫雪丹"},
        headers=second_user_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0


# ---------------------------------------------------------------------------
# POST /api/chat/conversations
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_conversation(client: AsyncClient, auth_headers: dict):
    """Should save a conversation and return it."""
    response = await client.post(
        "/api/chat/conversations",
        json={
            "title": "养生咨询",
            "messages": [
                {"role": "user", "content": "冬天吃什么好"},
                {"role": "assistant", "content": "冬季宜温补"},
            ],
            "reasoning_trace": [
                {"step": "safety_check", "result": "passed"},
            ],
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "养生咨询"
    assert len(data["messages"]) == 2
    assert len(data["reasoning_trace"]) == 1
    assert "id" in data


@pytest.mark.asyncio
async def test_save_conversation_default_title(client: AsyncClient, auth_headers: dict):
    """Conversation without title should get default."""
    response = await client.post(
        "/api/chat/conversations",
        json={"messages": []},
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "新对话"


# ---------------------------------------------------------------------------
# Safety keywords module
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_safety_keywords_module():
    """Test the safety_keywords module directly."""
    from app.safety_keywords import check_emergency_keywords, EMERGENCY_KEYWORDS

    # All keywords should be in the list
    assert len(EMERGENCY_KEYWORDS) >= 29

    # Single keyword match
    result = check_emergency_keywords("我感到胸痛")
    assert "胸痛" in result

    # No match
    result = check_emergency_keywords("我想了解黄芪的功效")
    assert result == []

    # Multiple matches
    result = check_emergency_keywords("患者大出血，已休克")
    assert "大出血" in result
    assert "休克" in result


# ---------------------------------------------------------------------------
# Emergency synonym interception at the chat endpoint (audit gap P1.5).
# Synonyms (胸口疼↔胸痛, 喘不上气↔呼吸困难) must trigger the safety layer
# end-to-end through POST /api/chat, not only in the keyword module.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_synonym_chest_pain_intercepted(
    client: AsyncClient, auth_headers: dict
):
    """'我胸口疼得厉害' (synonym of 胸痛) triggers the emergency safety layer."""
    response = await client.post(
        "/api/chat",
        json={"message": "我胸口疼得厉害", "history": []},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["safety_warning"] is not None
    assert "120" in data["safety_warning"]
    assert data["model_used"] == "safety-layer"


@pytest.mark.asyncio
async def test_chat_synonym_breathing_difficulty_intercepted(
    client: AsyncClient, auth_headers: dict
):
    """'喘不上气' (synonym of 呼吸困难) triggers the emergency safety layer."""
    response = await client.post(
        "/api/chat",
        json={"message": "老人突然喘不上气了", "history": []},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["safety_warning"] is not None
    assert "120" in data["safety_warning"]
    assert data["model_used"] == "safety-layer"
