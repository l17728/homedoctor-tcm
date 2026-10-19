"""AI Chat router — conversation with safety-first design.

Endpoints:
- POST /api/chat         — send a message, get AI response with safety check
- GET  /api/chat/history — list user's conversations
- POST /api/chat/conversations — save a conversation
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.config import settings
from app.database import DbAdapter, get_db
from app.upload_utils import read_upload_limited
from app.entity_filter import scan_and_link
from app.knowledge_reader import build_graph_context
from app.llm import (
    DISCLAIMER,
    _extract_herb_names_with_db,
    chat_completion,
    chat_completion_stream,
    chat_completion_with_image,
    encode_image,
    has_api_key,
)
from app.safety_engine import run_safety_check
from app.safety_keywords import (
    EMERGENCY_WARNING,
    PSYCHOLOGICAL_CRISIS_WARNING,
    check_emergency_keywords,
    check_psychological_crisis,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

# 历史消息输入上限：超出时截断保留最近 20 条（防止上下文过长/滥用）
MAX_CHAT_HISTORY = 20


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
    crisis_keywords: list[str] | None = None,
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

    # Psychological crisis: dedicated gentle response, NOT a 120 emergency
    if crisis_keywords:
        return {
            "reply": PSYCHOLOGICAL_CRISIS_WARNING,
            "safety_warning": PSYCHOLOGICAL_CRISIS_WARNING,
            "model_used": "safety-layer",
            "reasoning_trace": [
                {"step": "psychological_crisis_check", "result": "crisis_detected",
                 "keywords": crisis_keywords},
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


async def _precheck_combination_safety(
    db: DbAdapter, message: str
) -> tuple[str | None, list[str], list[str]]:
    """配伍安全前置检查（backend review P2-8，spec §15.3 第1层）。

    对用户消息中提取的药材名快速跑 run_safety_check 的硬规则层；
    出现 critical/high 警告时返回 (警告文案, 提到的药材, 警告标题)，
    否则返回 (None, [], [])。任何内部异常都不阻断对话（非阻塞设计）。
    """
    try:
        herbs = await _extract_herb_names_with_db(message, db)
    except Exception as exc:
        logger.warning("chat herb extraction failed: %s", exc)
        return None, [], []
    if not herbs:
        return None, [], []

    try:
        result = await run_safety_check(db=db, herb_names=herbs, medicine_names=[])
    except Exception as exc:
        logger.warning("chat safety precheck failed: %s", exc)
        return None, [], []

    blocking = [w for w in result.warnings if w.severity in ("critical", "high")]
    if not blocking:
        return None, [], []

    lines = [f"【{w.title}】{w.detail}" for w in blocking]
    warning_text = "⚠ 配伍安全警告：" + "；".join(lines)
    return warning_text, herbs, [w.title for w in blocking]


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
    crisis_keywords = check_psychological_crisis(body.message)

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

    if crisis_keywords:
        return {
            "reply": PSYCHOLOGICAL_CRISIS_WARNING,
            "safety_warning": PSYCHOLOGICAL_CRISIS_WARNING,
            "model_used": "safety-layer",
            "reasoning_trace": [
                {"step": "psychological_crisis_check", "result": "crisis_detected",
                 "keywords": crisis_keywords},
            ],
        }

    constitution = await _get_user_constitution(db, current_user["id"])

    # 配伍安全前置检查（P2-8）：对消息中提到的药材先跑五层安全硬规则
    safety_warning_text, mentioned_herbs, warning_titles = (
        await _precheck_combination_safety(db, body.message)
    )

    knowledge_ctx = await build_graph_context(db, body.message)

    # 历史消息截断：最多保留最近 20 条
    history = body.history[-MAX_CHAT_HISTORY:] if body.history else []
    messages = [*history, {"role": "user", "content": body.message}]

    if has_api_key():
        reply_text = await chat_completion(messages, constitution, knowledge_ctx)
        if not reply_text.endswith(DISCLAIMER):
            reply_text = f"{reply_text}\n\n{DISCLAIMER}"
    else:
        mock = _generate_mock_reply(body.message, [], constitution)
        reply_text = mock["reply"]
        if not reply_text.endswith(DISCLAIMER):
            reply_text = f"{reply_text}\n\n{DISCLAIMER}"

    # 有配伍警告时，在回复最前面拼接警告段落
    if safety_warning_text:
        reply_text = f"{safety_warning_text}\n\n{reply_text}"

    reasoning: list[dict[str, Any]] = [
        {"step": "safety_keyword_check", "result": "passed"},
    ]
    if safety_warning_text:
        reasoning.append({
            "step": "safety_precheck",
            "result": "blocking_warning",
            "herbs": mentioned_herbs,
            "warnings": warning_titles,
        })
    if knowledge_ctx:
        reasoning.append({
            "step": "knowledge_graph_context",
            "result": "injected",
            "context_length": len(knowledge_ctx),
        })
    if constitution:
        reasoning.append({
            "step": "constitution_context",
            "result": "injected",
            "primary_type": constitution["primary"],
        })
    reasoning.append({"step": "llm_completion", "result": "success", "model": settings.LLM_MODEL})

    # Non-blocking: scan the AI reply for knowledge-graph entity mentions.
    try:
        await scan_and_link(
            db, reply_text,
            source_type="chat", source_id=current_user["id"],
            relationship_type="mentions",
        )
    except Exception as exc:
        logger.warning("scan_and_link failed: %s", exc)

    return {
        "reply": reply_text,
        "safety_warning": safety_warning_text,
        "model_used": settings.LLM_MODEL if has_api_key() else "mock-v1",
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
    crisis_keywords = check_psychological_crisis(body.message)

    if matched_keywords:
        async def emergency_stream():
            yield f"data: {json.dumps({'content': EMERGENCY_WARNING, 'done': True})}\n\n"
        return StreamingResponse(emergency_stream(), media_type="text/event-stream")

    if crisis_keywords:
        async def crisis_stream():
            yield f"data: {json.dumps({'content': PSYCHOLOGICAL_CRISIS_WARNING, 'done': True})}\n\n"
        return StreamingResponse(crisis_stream(), media_type="text/event-stream")

    constitution = await _get_user_constitution(db, current_user["id"])

    # 配伍安全前置检查（P2-8）：流式路径同样先跑硬规则
    safety_warning_text, _, _ = await _precheck_combination_safety(db, body.message)

    knowledge_ctx = await build_graph_context(db, body.message)

    # 历史消息截断：最多保留最近 20 条
    history = body.history[-MAX_CHAT_HISTORY:] if body.history else []
    messages = [*history, {"role": "user", "content": body.message}]

    async def generate():
        full_response = ""
        if safety_warning_text:
            yield f"data: {json.dumps({'content': safety_warning_text + chr(10) + chr(10)})}\n\n"
        async for chunk in chat_completion_stream(messages, constitution, knowledge_ctx):
            full_response += chunk
            yield f"data: {json.dumps({'content': chunk})}\n\n"

        try:
            from app.llm import _validate_and_augment
            validated = await _validate_and_augment(full_response)
            if isinstance(validated, str) and len(validated) > len(full_response):
                suffix = validated[len(full_response):]
                if suffix and suffix.strip():
                    yield f"data: {json.dumps({'content': suffix})}\n\n"
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Streaming hallucination defense failed: %s", exc)

        tail = "\n\n" + DISCLAIMER
        yield f"data: {json.dumps({'content': tail, 'done': True})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


MAX_IMAGE_SIZE = 10 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


@router.post("/image")
async def chat_with_image(
    message: str = Form(...),
    image: UploadFile = File(...),
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Send a message with an image for multimodal AI analysis.

    Use cases (spec §16.2, §18):
    - Medication photo recognition
    - Medical report/document reading
    - Skin condition visual reference
    """
    if image.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"不支持的图片格式：{image.content_type}。请上传 JPG/PNG/WebP/GIF。",
        )

    raw = await read_upload_limited(image, MAX_IMAGE_SIZE, "图片大小不能超过 10MB。")

    matched_keywords = check_emergency_keywords(message)
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
    image_b64 = encode_image(raw, image.content_type or "image/jpeg")

    reply_text = await chat_completion_with_image(
        message, image_b64, image.content_type or "image/jpeg", constitution,
    )

    if not reply_text.endswith(DISCLAIMER):
        reply_text = f"{reply_text}\n\n{DISCLAIMER}"

    reasoning: list[dict[str, Any]] = [
        {"step": "safety_keyword_check", "result": "passed"},
        {"step": "image_validation", "result": "passed",
         "mime": image.content_type, "size": len(raw)},
    ]
    if constitution:
        reasoning.append({
            "step": "constitution_context",
            "result": "injected",
            "primary_type": constitution["primary"],
        })
    reasoning.append({"step": "llm_vision_completion", "result": "success",
                      "model": settings.LLM_VISION_MODEL})

    return {
        "reply": reply_text,
        "safety_warning": None,
        "model_used": settings.LLM_VISION_MODEL if has_api_key() else "fallback",
        "reasoning_trace": reasoning,
    }


@router.get("/history")
async def list_conversations(
    page: int = Query(1, ge=1, description="页码（从1开始）"),
    pageSize: int = Query(20, ge=1, le=100, description="每页条数（1-100）"),
    q: str | None = None,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List the current user's conversations, with optional keyword search."""
    user_id = current_user["id"]

    if q:
        like_pattern = f"%{q}%"
        count_row = await db.query_one(
            """SELECT COUNT(*) as cnt FROM conversations
               WHERE user_id = ? AND (title LIKE ? OR messages LIKE ?)""",
            (user_id, like_pattern, like_pattern),
        )
        total = count_row["cnt"] if count_row else 0

        offset = (page - 1) * pageSize
        rows = await db.query(
            """SELECT * FROM conversations
               WHERE user_id = ? AND (title LIKE ? OR messages LIKE ?)
               ORDER BY updated_at DESC
               LIMIT ? OFFSET ?""",
            (user_id, like_pattern, like_pattern, pageSize, offset),
        )
    else:
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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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
