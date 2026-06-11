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
        json={"message": "患者出现昏迷和抽搐，疑似中毒"},
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
async def test_chat_requires_auth(client: AsyncClient):
    """Chat endpoint should require authentication."""
    response = await client.post(
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
