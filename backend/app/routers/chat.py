"""AI Chat router — conversation with safety-first design.

Endpoints:
- POST /api/chat         — send a message, get AI response with safety check
- GET  /api/chat/history — list user's conversations
- POST /api/chat/conversations — save a conversation
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.database import DbAdapter, get_db
from app.safety_keywords import EMERGENCY_WARNING, check_emergency_keywords

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[dict[str, Any]] = Field(default_factory=list)


class ConversationCreate(BaseModel):
    title: str | None = None
    messages: list[dict[str, Any]] = Field(default_factory=list)
    reasoning_trace: list[dict[str, Any]] = Field(default_factory=list)
    model_id: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_mock_reply(message: str, matched_keywords: list[str]) -> dict[str, Any]:
    """Generate a mock AI response (MVP placeholder).

    In production, this would forward to an actual AI model.
    For MVP, returns a structured placeholder.
    """
    if matched_keywords:
        return {
            "reply": EMERGENCY_WARNING,
            "safety_warning": EMERGENCY_WARNING,
            "model_used": "safety-layer",
            "reasoning_trace": [
                {"step": "safety_keyword_check", "result": "emergency_detected",
                 "keywords": matched_keywords},
            ],
        }

    return {
        "reply": f"收到您的咨询：「{message}」。这是MVP版本的模拟回复，正式版将接入AI大模型提供专业中医药咨询服务。",
        "safety_warning": None,
        "model_used": "mock-v1",
        "reasoning_trace": [
            {"step": "safety_keyword_check", "result": "passed"},
            {"step": "ai_processing", "result": "mock_response"},
        ],
    }


def _parse_conversation(row: dict[str, Any]) -> dict[str, Any]:
    """Parse a conversation row, converting JSON strings to objects."""
    result = dict(row)
    for field in ("messages", "reasoning_trace"):
        if isinstance(result.get(field), str):
            try:
                result[field] = json.loads(result[field])
            except (json.JSONDecodeError, TypeError):
                result[field] = []
    return result


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("")
async def chat(
    body: ChatRequest,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Send a message and get an AI response.

    Safety-first: emergency keywords are checked before AI processing.
    If keywords are found, an immediate warning is returned without
    forwarding to the AI model.
    """
    # Layer 1: Safety keyword check (硬编码规则优先于 AI)
    matched_keywords = check_emergency_keywords(body.message)

    # Generate response (mock for MVP)
    response = _generate_mock_reply(body.message, matched_keywords)
    return response


@router.get("/history")
async def list_conversations(
    page: int = 1,
    pageSize: int = 20,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List the current user's conversations."""
    user_id = current_user["id"]

    count_row = await db.query_one(
        "SELECT COUNT(*) as cnt FROM conversations WHERE user_id = ?",
        (user_id,),
    )
    total = count_row["cnt"] if count_row else 0

    offset = (page - 1) * pageSize
    rows = await db.query(
        """SELECT * FROM conversations
           WHERE user_id = ?
           ORDER BY updated_at DESC
           LIMIT ? OFFSET ?""",
        (user_id, pageSize, offset),
    )

    conversations = [_parse_conversation(r) for r in rows]
    total_pages = (total + pageSize - 1) // pageSize
    return {
        "items": conversations,
        "total": total,
        "page": page,
        "pageSize": pageSize,
        "totalPages": total_pages,
    }


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
async def save_conversation(
    body: ConversationCreate,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Save a new conversation."""
    conversation_id = str(uuid.uuid4())
    user_id = current_user["id"]
    now = datetime.now(timezone.utc).isoformat()

    await db.execute(
        """INSERT INTO conversations
           (id, user_id, title, model_id, messages, reasoning_trace, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            conversation_id,
            user_id,
            body.title or "新对话",
            body.model_id or "mock-v1",
            json.dumps(body.messages, ensure_ascii=False),
            json.dumps(body.reasoning_trace, ensure_ascii=False),
            now,
            now,
        ),
    )

    row = await db.query_one(
        "SELECT * FROM conversations WHERE id = ?",
        (conversation_id,),
    )
    return _parse_conversation(row)
