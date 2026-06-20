"""Extractor AI router — knowledge auto-extraction endpoints (spec §8.4).

Endpoints:
- POST /api/extractor/extract       — extract knowledge from provided messages
- POST /api/extractor/auto-extract  — run extraction on user's recent conversations
- GET  /api/extractor/recent        — list recently auto-extracted knowledge entries
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.database import DbAdapter, get_db
from app.extractor import auto_extract_for_user, extract_knowledge

router = APIRouter(prefix="/api/extractor", tags=["extractor"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ExtractRequest(BaseModel):
    messages: list[dict[str, Any]] = Field(
        ..., description="Conversation messages to extract knowledge from"
    )


class ExtractResponse(BaseModel):
    items: list[dict[str, Any]] = Field(
        default_factory=list, description="Extracted knowledge items"
    )
    count: int = Field(0, description="Number of items extracted")
    llm_available: bool = Field(
        True, description="Whether the LLM was available for extraction"
    )


class AutoExtractResponse(BaseModel):
    extracted: int = Field(0, description="Number of new knowledge entries saved")
    rate_limited: bool = Field(
        False, description="True if rate limit prevented extraction"
    )
    message: str = Field("", description="Status message")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_entry(row: dict[str, Any]) -> dict[str, Any]:
    """Parse a knowledge_entry row, converting JSON strings to objects."""
    result = dict(row)
    if isinstance(result.get("tags"), str):
        try:
            result["tags"] = json.loads(result["tags"])
        except (json.JSONDecodeError, TypeError):
            result["tags"] = []
    if "is_starred" in result:
        result["is_starred"] = bool(result["is_starred"])
    return result


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/extract", response_model=ExtractResponse)
async def extract_endpoint(
    body: ExtractRequest,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Extract knowledge items from a provided set of messages.

    This endpoint does **not** save the extracted items — it returns them
    for the client to review. Use ``/auto-extract`` for saving.
    """
    if not body.messages:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="messages cannot be empty",
        )

    items = await extract_knowledge(body.messages, db)

    # Check if LLM was available (empty result could mean no knowledge or LLM down)
    from app.config import settings as _settings

    llm_available = bool(_settings.LLM_API_KEY)

    return ExtractResponse(
        items=items,
        count=len(items),
        llm_available=llm_available,
    )


@router.post("/auto-extract", response_model=AutoExtractResponse)
async def auto_extract_endpoint(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Run knowledge extraction on the user's recent conversations.

    Automatically processes the user's recent conversations, extracts
    knowledge items, deduplicates against existing entries, and saves
    new items to the knowledge_entries table.

    Rate limited: max 1 auto-extract per hour per user.
    """
    user_id = current_user["id"]

    # Pre-check rate limit to provide a clear message
    from datetime import timedelta

    one_hour_ago = (
        datetime.now(timezone.utc) - timedelta(hours=1)
    ).isoformat()
    recent = await db.query_one(
        """SELECT COUNT(*) as cnt FROM knowledge_entries
           WHERE user_id = ? AND source_type = 'extractor' AND created_at > ?""",
        (user_id, one_hour_ago),
    )

    if recent and recent["cnt"] > 0:
        return AutoExtractResponse(
            extracted=0,
            rate_limited=True,
            message="每小时只能自动提取一次，请稍后再试",
        )

    count = await auto_extract_for_user(user_id, db)

    if count == 0:
        # Could be rate limited (re-checked inside) or no new knowledge
        return AutoExtractResponse(
            extracted=0,
            rate_limited=False,
            message="未发现新的知识点，或LLM服务暂不可用",
        )

    return AutoExtractResponse(
        extracted=count,
        rate_limited=False,
        message=f"成功提取 {count} 条知识点",
    )


@router.get("/recent")
async def recent_extractions(
    limit: int = Query(20, ge=1, le=100, description="Max items to return"),
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List recently auto-extracted knowledge entries for the current user.

    Returns entries created by the extractor (``source_type='extractor'``),
    ordered by creation time descending.
    """
    user_id = current_user["id"]

    rows = await db.query(
        """SELECT * FROM knowledge_entries
           WHERE user_id = ? AND source_type = 'extractor'
           ORDER BY created_at DESC
           LIMIT ?""",
        (user_id, limit),
    )

    items = [_parse_entry(r) for r in rows]
    return {"items": items, "total": len(items)}
