"""Tests for constitution injection into AI chat (spec §1.5 — 体质感知)."""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

from app.routers.chat import CONSTITUTION_ADVICE, _generate_mock_reply


# ---------------------------------------------------------------------------
# Helper to set user constitution via direct DB
# ---------------------------------------------------------------------------

async def _set_constitution(client: AsyncClient, headers: dict, db, constitution_type: str, secondary: list[str] | None = None):
    """Set the current user's constitution via direct DB insert."""
    me = await client.get("/api/auth/me", headers=headers)
    user_id = me.json()["id"]
    await db.execute(
        """INSERT INTO user_profiles (user_id, constitution_type, constitution_secondary, updated_at)
           VALUES (?, ?, ?, datetime('now'))
           ON CONFLICT(user_id) DO UPDATE SET
             constitution_type = excluded.constitution_type,
             constitution_secondary = excluded.constitution_secondary,
             updated_at = excluded.updated_at""",
        (user_id, constitution_type, json.dumps(secondary or [], ensure_ascii=False)),
    )


# ---------------------------------------------------------------------------
# Unit tests for _generate_mock_reply with constitution
# ---------------------------------------------------------------------------

def test_mock_reply_with_constitution_qixu():
    """Reply should contain constitution advice for 气虚质."""
    result = _generate_mock_reply(
        "我容易疲劳",
        [],
        constitution={"primary": "气虚质", "secondary": []},
    )
    assert result["safety_warning"] is None
    assert "气虚质" in result["reply"]
    assert "黄芪" in result["reply"] or "党参" in result["reply"]
    assert "体质档案" in result["reply"]


def test_mock_reply_with_constitution_yangxu():
    """Reply should contain constitution advice for 阳虚质."""
    result = _generate_mock_reply(
        "怕冷",
        [],
        constitution={"primary": "阳虚质", "secondary": []},
    )
    assert "阳虚质" in result["reply"]
    assert "肉桂" in result["reply"] or "附子" in result["reply"]


def test_mock_reply_without_constitution():
    """Reply without constitution should not mention constitution."""
    result = _generate_mock_reply("黄芪功效", [], constitution=None)
    assert "体质档案" not in result["reply"]
    assert "气虚质" not in result["reply"]


def test_mock_reply_emergency_overrides_constitution():
    """Emergency keywords should take priority — no constitution note."""
    result = _generate_mock_reply(
        "胸痛",
        ["胸痛"],
        constitution={"primary": "气虚质", "secondary": []},
    )
    assert result["safety_warning"] is not None
    assert "120" in result["safety_warning"]
    assert result["model_used"] == "safety-layer"
    assert "体质档案" not in result["reply"]


def test_mock_reply_constitution_with_secondary():
    """Reply with secondary types should mention them."""
    result = _generate_mock_reply(
        "调理建议",
        [],
        constitution={"primary": "气虚质", "secondary": ["血瘀质", "阴虚质"]},
    )
    assert "气虚质" in result["reply"]
    assert "血瘀质" in result["reply"]
    assert "阴虚质" in result["reply"]
    assert "兼夹体质" in result["reply"]


def test_mock_reply_constitution_reasoning_trace():
    """Reasoning trace should include constitution_context step."""
    result = _generate_mock_reply(
        "建议",
        [],
        constitution={"primary": "痰湿质", "secondary": []},
    )
    steps = [s["step"] for s in result["reasoning_trace"]]
    assert "constitution_context" in steps
    ctx_step = next(s for s in result["reasoning_trace"] if s["step"] == "constitution_context")
    assert ctx_step["primary_type"] == "痰湿质"


def test_constitution_advice_covers_all_nine_types():
    """CONSTITUTION_ADVICE should cover all nine constitution types."""
    nine_types = [
        "气虚质", "阳虚质", "阴虚质", "痰湿质", "湿热质",
        "血瘀质", "气郁质", "特禀质", "平和质",
    ]
    for t in nine_types:
        assert t in CONSTITUTION_ADVICE, f"Missing advice for {t}"
        assert len(CONSTITUTION_ADVICE[t]) > 0


# ---------------------------------------------------------------------------
# Integration tests via API
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_with_constitution_set(client: AsyncClient, auth_headers: dict, db):
    """User with constitution set → reply contains constitution info."""
    await _set_constitution(client, auth_headers, db, "气虚质")
    response = await client.post(
        "/api/chat",
        json={"message": "我容易疲劳怎么办", "history": []},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["safety_warning"] is None
    assert "气虚质" in data["reply"]
    assert "体质档案" in data["reply"]


@pytest.mark.asyncio
async def test_chat_without_constitution(client: AsyncClient, auth_headers: dict):
    """User without constitution → no constitution info in reply."""
    response = await client.post(
        "/api/chat",
        json={"message": "黄芪有什么功效", "history": []},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "体质档案" not in data["reply"]


@pytest.mark.asyncio
async def test_chat_constitution_yangxu_contains_warming_herbs(client: AsyncClient, auth_headers: dict, db):
    """User with 阳虚质 → reply mentions warming herbs."""
    await _set_constitution(client, auth_headers, db, "阳虚质")
    response = await client.post(
        "/api/chat",
        json={"message": "冬天怕冷", "history": []},
        headers=auth_headers,
    )
    assert response.status_code == 200
    reply = response.json()["reply"]
    assert "肉桂" in reply or "附子" in reply or "干姜" in reply


@pytest.mark.asyncio
async def test_chat_emergency_with_constitution(client: AsyncClient, auth_headers: dict, db):
    """Emergency + constitution → emergency warning takes priority."""
    await _set_constitution(client, auth_headers, db, "气虚质")
    response = await client.post(
        "/api/chat",
        json={"message": "我突然剧烈头痛", "history": []},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["safety_warning"] is not None
    assert "120" in data["safety_warning"]
    assert "体质档案" not in data["reply"]


@pytest.mark.asyncio
async def test_chat_constitution_with_secondary_types(client: AsyncClient, auth_headers: dict, db):
    """User with secondary constitution types → both shown in reply."""
    await _set_constitution(client, auth_headers, db, "湿热质", ["血瘀质"])
    response = await client.post(
        "/api/chat",
        json={"message": "皮肤问题", "history": []},
        headers=auth_headers,
    )
    assert response.status_code == 200
    reply = response.json()["reply"]
    assert "湿热质" in reply
    assert "血瘀质" in reply
    assert "兼夹体质" in reply
