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
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.config import settings
from app.database import DbAdapter, get_db
from app.llm import chat_completion, chat_completion_stream, DISCLAIMER, has_api_key
from app.safety_keywords import EMERGENCY_WARNING, check_emergency_keywords

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ---------------------------------------------------------------------------
# Constitution advice (spec §1.5 — 体质感知)
# ---------------------------------------------------------------------------

CONSTITUTION_ADVICE: dict[str, str] = {
    "气虚质": "宜益气健脾，推荐黄芪、党参、白术等补气药材。避免过度劳累。",
    "阳虚质": "宜温阳补火，推荐肉桂、附子、干姜等温阳药材。注意保暖。",
    "阴虚质": "宜滋阴润燥，推荐沙参、麦冬、石斛等养阴药材。避免辛辣。",
    "痰湿质": "宜化痰祛湿，推荐陈皮、半夏、茯苓等化湿药材。控制饮食。",
    "湿热质": "宜清热利湿，推荐黄芩、黄连、茵陈等清热药材。忌油腻。",
    "血瘀质": "宜活血化瘀，推荐当归、川芎、红花等活血药材。适当运动。",
    "气郁质": "宜疏肝解郁，推荐柴胡、香附、郁金等理气药材。保持心情舒畅。",
    "特禀质": "宜益气固表，推荐黄芪、防风、白术等固表药材。注意过敏源。",
    "平和质": "体质平和，保持良好生活习惯即可。均衡饮食，适度运动。",
}


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

async def _get_user_constitution(db: DbAdapter, user_id: str) -> dict[str, Any] | None:
    """Get user's constitution info from user_profiles (spec §1.5).

    Returns None if the user has no constitution_type set.
    """
    row = await db.query_one(
        "SELECT constitution_type, constitution_secondary FROM user_profiles WHERE user_id = ?",
        (user_id,),
    )
    if not row or not row.get("constitution_type"):
        return None

    secondary: list[str] = []
    raw_secondary = row.get("constitution_secondary")
    if raw_secondary:
        if isinstance(raw_secondary, str):
            try:
                secondary = json.loads(raw_secondary)
            except (json.JSONDecodeError, TypeError):
                secondary = []
        elif isinstance(raw_secondary, list):
            secondary = raw_secondary

    return {
        "primary": row["constitution_type"],
        "secondary": secondary,
    }


def _generate_mock_reply(
    message: str,
    matched_keywords: list[str],
    constitution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a mock AI response (MVP placeholder).

    In production, this would forward to an actual AI model.
    For MVP, returns a structured placeholder with optional constitution context.
    """
    # Emergency keywords always take priority over constitution advice
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

    # Build constitution context note (spec §1.5 — 体质感知)
    constitution_note = ""
    if constitution:
        constitution_note = (
            f"\n\n📌 根据您的体质档案（主体质：{constitution['primary']}），以下建议供参考：\n"
        )
        advice = CONSTITUTION_ADVICE.get(constitution["primary"], "")
        if advice:
            constitution_note += advice
        if constitution.get("secondary"):
            constitution_note += (
                f"\n兼夹体质：{'、'.join(constitution['secondary'])}，调理时需兼顾。"
            )

    reply_text = (
        f"收到您的咨询：「{message}」。"
        f"这是MVP版本的模拟回复，正式版将接入AI大模型提供专业中医药咨询服务。"
        f"{constitution_note}"
    )

    reasoning: list[dict[str, Any]] = [
        {"step": "safety_keyword_check", "result": "passed"},
    ]
    if constitution:
        reasoning.append({
            "step": "constitution_context",
            "result": "injected",
            "primary_type": constitution["primary"],
        })
    reasoning.append({"step": "ai_processing", "result": "mock_response"})

    return {
        "reply": reply_text,
        "safety_warning": None,
        "model_used": "mock-v1",
        "reasoning_trace": reasoning,
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
    matched_keywords = check_emergency_keywords(body.message)

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

    constitution = await _get_user_constitution(db, current_user["id"])

    messages = [{"role": "user", "content": body.message}]
    if body.history:
        messages = [*body.history, {"role": "user", "content": body.message}]

    reply_text = await chat_completion(messages, constitution)

    if not reply_text.endswith(DISCLAIMER):
        reply_text = f"{reply_text}\n\n{DISCLAIMER}"

    reasoning: list[dict[str, Any]] = [
        {"step": "safety_keyword_check", "result": "passed"},
    ]
    if constitution:
        reasoning.append({
            "step": "constitution_context",
            "result": "injected",
            "primary_type": constitution["primary"],
        })
    reasoning.append({"step": "llm_completion", "result": "success", "model": settings.LLM_MODEL})

    return {
        "reply": reply_text,
        "safety_warning": None,
        "model_used": settings.LLM_MODEL if has_api_key() else "fallback",
        "reasoning_trace": reasoning,
    }


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Streaming SSE endpoint for real-time AI response display."""
    matched_keywords = check_emergency_keywords(body.message)

    if matched_keywords:
        async def emergency_stream():
            yield f"data: {json.dumps({'content': EMERGENCY_WARNING, 'done': True})}\n\n"
        return StreamingResponse(emergency_stream(), media_type="text/event-stream")

    constitution = await _get_user_constitution(db, current_user["id"])

    messages = [{"role": "user", "content": body.message}]
    if body.history:
        messages = [*body.history, {"role": "user", "content": body.message}]

    async def generate():
        async for chunk in chat_completion_stream(messages, constitution):
            yield f"data: {json.dumps({'content': chunk})}\n\n"
        tail = "\n\n" + DISCLAIMER
        yield f"data: {json.dumps({'content': tail, 'done': True})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


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


@router.post("/save-card", status_code=status.HTTP_201_CREATED)
async def save_as_knowledge_card(
    body: dict,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Save an AI response as a knowledge card in knowledge_entries."""
    title = body.get("title")
    content = body.get("content")
    if not title or not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="title and content are required",
        )

    user_id = current_user["id"]
    entry_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    tags = body.get("tags", [])
    if isinstance(tags, list):
        tags = json.dumps(tags, ensure_ascii=False)
    else:
        tags = "[]"

    await db.execute(
        """INSERT INTO knowledge_entries
           (id, user_id, entry_type, title, content, summary, tags,
            source_type, source_url, is_starred, created_at, updated_at)
           VALUES (?, ?, 'knowledge_card', ?, ?, NULL, ?, 'chat', ?, 0, ?, ?)""",
        (
            entry_id,
            user_id,
            title,
            content,
            tags,
            body.get("conversation_id"),
            now,
            now,
        ),
    )

    row = await db.query_one(
        "SELECT * FROM knowledge_entries WHERE id = ?",
        (entry_id,),
    )
    result = dict(row)
    if isinstance(result.get("tags"), str):
        try:
            result["tags"] = json.loads(result["tags"])
        except (json.JSONDecodeError, TypeError):
            result["tags"] = []
    if "is_starred" in result:
        result["is_starred"] = bool(result["is_starred"])
    return result
