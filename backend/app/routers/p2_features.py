"""P2 features: conversation summary, feedback, freshness, auto-extract.

Endpoints:
  POST /api/chat/{conversation_id}/summarize    — one-click conversation → knowledge
  POST /api/knowledge/{entity_id}/feedback       — user rating (helpful/inaccurate/report)
  GET  /api/knowledge/{entity_id}/feedback        — get feedback summary
  POST /api/admin/freshness-check                 — trigger knowledge freshness scan
  GET  /api/admin/freshness-stats                 — freshness statistics
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import get_current_user, require_admin
from app.database import DbAdapter, get_db

router = APIRouter(prefix="/api", tags=["p2-features"])


class FeedbackRequest(BaseModel):
    rating: str = Field(..., description="helpful / inaccurate / report")
    comment: str = ""


class SummarizeRequest(BaseModel):
    title: str = ""
    auto_import: bool = True


@router.post("/chat/{conversation_id}/summarize")
async def summarize_conversation(
    conversation_id: str,
    body: SummarizeRequest,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """One-click: summarize a conversation and import as knowledge.

    Extracts symptoms/formulas/herbs from the conversation, creates a
    knowledge card entity, and runs the agent pipeline.
    """
    rows = await db.query(
        "SELECT messages FROM conversations WHERE id = ? AND user_id = ?",
        (conversation_id, current_user["id"]),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="对话不存在")

    messages_raw = rows[0].get("messages", "[]")
    if isinstance(messages_raw, str):
        try:
            messages = json.loads(messages_raw)
        except json.JSONDecodeError:
            messages = []
    else:
        messages = messages_raw

    if not messages or len(messages) < 2:
        raise HTTPException(status_code=400, detail="对话内容太少，无法总结")

    conversation_text = "\n".join(
        f"{m.get('role', 'user')}: {m.get('content', '')}"
        for m in messages[-20:]
        if m.get("content")
    )

    if len(conversation_text) < 50:
        raise HTTPException(status_code=400, detail="对话内容太短")

    from app.llm import chat_completion, has_api_key
    title = body.title or f"对话总结_{conversation_id[:8]}"

    if has_api_key():
        summary_prompt = f"""请总结以下中医健康对话的要点，提取有价值的知识。

对话内容：
{conversation_text[:3000]}

请提取：
1. 用户的主要症状/健康问题
2. AI给出的证候判断和调理建议
3. 涉及的中药/方剂/穴位/功法
4. 饮食和生活建议

返回JSON：
{{"summary": "200字以内的总结", "symptoms": ["症状1", ...], "formulas": ["方剂1", ...], "herbs": ["中药1", ...], "advice": "调理建议"}}
"""
        try:
            llm_response = await chat_completion([
                {"role": "user", "content": summary_prompt},
            ])
            import re
            from app.json_extractor import extract_json
            parsed = extract_json(llm_response)
            if parsed:
                extracted = json.loads(match.group())
            else:
                extracted = {"summary": llm_response[:200]}
        except Exception:
            extracted = {"summary": conversation_text[:200]}
    else:
        extracted = {"summary": conversation_text[:200]}

    if not body.auto_import:
        return {"extracted": extracted, "imported": False}

    from app.knowledge_agent import process_input
    result = await process_input(
        db,
        content=conversation_text,
        title=title,
        source_type="chat",
    )

    if result.get("entity_id"):
        from app.agent_tools import log_action
        await log_action(
            db, "conversation_import", "chat", conversation_id,
            result["entity_id"],
            {"extracted": extracted, "conversation_id": conversation_id},
            "imported",
        )

    return {
        "extracted": extracted,
        "imported": True,
        "entity_id": result.get("entity_id"),
        "decision": result.get("decision"),
        "trust_level": result.get("trust_level", "B"),
        "trust_score": result.get("trust_score", 50),
        "message": result.get("message", "已入库"),
    }


@router.post("/knowledge/{entity_id}/feedback")
async def submit_feedback(
    entity_id: str,
    body: FeedbackRequest,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """User rates knowledge quality (helpful/inaccurate/report)."""
    if body.rating not in ("helpful", "inaccurate", "report"):
        raise HTTPException(status_code=400, detail="rating must be helpful/inaccurate/report")

    import uuid
    try:
        await db.execute(
            """INSERT OR REPLACE INTO knowledge_feedback
               (id, entity_id, user_id, rating, comment)
               VALUES (?, ?, ?, ?, ?)""",
            (f"fb-{uuid.uuid4()}", entity_id, current_user["id"], body.rating, body.comment),
        )
    except Exception:
        await db.execute(
            """UPDATE knowledge_feedback SET rating = ?, comment = ?
               WHERE entity_id = ? AND user_id = ?""",
            (body.rating, body.comment, entity_id, current_user["id"]),
        )

    if body.rating in ("inaccurate", "report"):
        count_row = await db.query_one(
            "SELECT COUNT(*) AS c FROM knowledge_feedback WHERE entity_id = ? AND rating IN ('inaccurate','report')",
            (entity_id,),
        )
        count = count_row["c"] if count_row else 0
        if count >= 3:
            from app.agent_tools import log_action
            await log_action(
                db, "trust_downgrade_request", "feedback", "", entity_id,
                {"report_count": count, "reason": f"{count}个用户标记不准确"},
                "pending_admin_review",
            )

    return {"message": "反馈已提交", "rating": body.rating}


@router.get("/knowledge/{entity_id}/feedback")
async def get_feedback(
    entity_id: str,
    db: DbAdapter = Depends(get_db),
    _: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Get feedback summary for an entity."""
    rows = await db.query(
        "SELECT rating, COUNT(*) as c FROM knowledge_feedback WHERE entity_id = ? GROUP BY rating",
        (entity_id,),
    )
    summary = {r["rating"]: r["c"] for r in rows}
    return {"entity_id": entity_id, "feedback": summary}


@router.post("/admin/freshness-check")
async def freshness_check(
    db: DbAdapter = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    """Scan knowledge freshness — mark outdated content."""
    rows = await db.query(
        """SELECT id, entity_id, content_date, freshness_status
             FROM knowledge_provenance
            WHERE content_date IS NOT NULL"""
    )

    from datetime import datetime
    updated = 0
    for row in rows:
        try:
            content_date = datetime.strptime(row["content_date"][:10], "%Y-%m-%d")
            age_days = (datetime.now() - content_date).days
            if age_days > 365 * 5:
                status = "outdated"
            elif age_days > 365 * 2:
                status = "aging"
            else:
                status = "current"
            if status != row.get("freshness_status"):
                await db.execute(
                    "UPDATE knowledge_provenance SET freshness_status = ? WHERE id = ?",
                    (status, row["id"]),
                )
                updated += 1
        except (ValueError, TypeError):
            pass

    return {"scanned": len(rows), "updated": updated}


@router.get("/admin/freshness-stats")
async def freshness_stats(
    db: DbAdapter = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    """Freshness statistics."""
    rows = await db.query(
        """SELECT freshness_status, COUNT(*) as c
             FROM knowledge_provenance GROUP BY freshness_status"""
    )
    return {"distribution": {r["freshness_status"]: r["c"] for r in rows}}
