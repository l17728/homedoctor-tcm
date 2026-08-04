"""Router for AI model management + agent logs + knowledge processing.

Endpoints:
  GET    /api/models              — list configured models
  POST   /api/models              — add a new model
  PUT    /api/models/{id}         — update model config
  DELETE /api/models/{id}         — remove model
  POST   /api/models/vote         — multi-model voting on a prompt
  POST   /api/agent/process       — trigger autonomous knowledge processing
  GET    /api/agent/logs          — list agent processing logs
  GET    /api/agent/logs/{id}     — get log detail
  PUT    /api/agent/logs/{id}/review — user review/correct agent decision
"""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import get_current_user, require_admin
from app.database import DbAdapter, get_db
from app.model_registry import (
    create_model, delete_model, get_model, list_models,
    multi_model_vote, update_model,
)

router = APIRouter(prefix="/api", tags=["model-registry"])


class ModelCreate(BaseModel):
    name: str
    provider: str = ""
    model_id: str = ""
    api_endpoint: str = ""
    api_key: str = ""
    access_type: str = "api"
    capabilities: list[str] = Field(default_factory=lambda: ["text"])
    max_tokens: int = 4096
    temperature: float = 0.3
    enabled: bool = True
    is_default: bool = False


class ModelUpdate(BaseModel):
    name: str | None = None
    provider: str | None = None
    model_id: str | None = None
    api_endpoint: str | None = None
    api_key: str | None = None
    access_type: str | None = None
    capabilities: list[str] | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    enabled: bool | None = None
    is_default: bool | None = None


class VoteRequest(BaseModel):
    messages: list[dict[str, str]]
    num_models: int = 3
    capability: str = "text"


class ProcessRequest(BaseModel):
    content: str = ""
    url: str = ""
    title: str = ""
    source_type: str = "text"


class LogReview(BaseModel):
    user_action: str = "approved"


@router.get("/models")
async def get_models(
    enabled_only: bool = Query(False),
    db: DbAdapter = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    models = await list_models(db, enabled_only=enabled_only)
    return {"items": models, "total": len(models)}


@router.post("/models")
async def add_model(
    body: ModelCreate,
    db: DbAdapter = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    mid = await create_model(db, **body.model_dump())
    return {"id": mid, "message": "模型已添加"}


@router.put("/models/{model_id}")
async def edit_model(
    model_id: str,
    body: ModelUpdate,
    db: DbAdapter = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    updated = await update_model(db, model_id, **body.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=404, detail="模型不存在")
    return {"message": "已更新"}


@router.delete("/models/{model_id}")
async def remove_model(
    model_id: str,
    db: DbAdapter = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    deleted = await delete_model(db, model_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="模型不存在")
    return {"message": "已删除"}


@router.post("/models/vote")
async def vote(
    body: VoteRequest,
    db: DbAdapter = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    return await multi_model_vote(db, body.messages, body.num_models, body.capability)


@router.post("/agent/process")
async def process_knowledge(
    body: ProcessRequest,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Trigger autonomous knowledge processing pipeline."""
    from app.knowledge_agent import process_input
    result = await process_input(
        db,
        content=body.content,
        url=body.url,
        title=body.title,
        source_type=body.source_type,
    )
    return result


@router.get("/agent/logs")
async def get_logs(
    entity_id: str | None = Query(None),
    action_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: DbAdapter = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    conditions = []
    params: list[Any] = []
    if entity_id:
        conditions.append("entity_id = ?")
        params.append(entity_id)
    if action_type:
        conditions.append("action_type = ?")
        params.append(action_type)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    offset = (page - 1) * page_size
    rows = await db.query(
        f"SELECT * FROM agent_logs {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        tuple(params + [page_size, offset]),
    )
    count_row = await db.query_one(
        f"SELECT COUNT(*) AS c FROM agent_logs {where}", tuple(params)
    )
    total = count_row["c"] if count_row else 0
    return {
        "items": [_format_log(r) for r in rows],
        "total": total,
        "page": page,
    }


@router.get("/agent/logs/{log_id}")
async def get_log(
    log_id: str,
    db: DbAdapter = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    rows = await db.query("SELECT * FROM agent_logs WHERE id = ?", (log_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="日志不存在")
    return _format_log(rows[0])


@router.put("/agent/logs/{log_id}/review")
async def review_log(
    log_id: str,
    body: LogReview,
    db: DbAdapter = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    cursor = await db.execute(
        "UPDATE agent_logs SET user_reviewed = 1, user_action = ? WHERE id = ?",
        (body.user_action, log_id),
    )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="日志不存在")
    return {"message": "已审核"}


def _format_log(row: dict[str, Any]) -> dict[str, Any]:
    details = row.get("details")
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except (json.JSONDecodeError, TypeError):
            details = {}
    return {
        "id": row.get("id", ""),
        "action_type": row.get("action_type", ""),
        "source_type": row.get("source_type") or "",
        "source_ref": row.get("source_ref") or "",
        "entity_id": row.get("entity_id") or "",
        "details": details if isinstance(details, dict) else {},
        "decision": row.get("decision") or "",
        "user_reviewed": bool(row.get("user_reviewed", 0)),
        "user_action": row.get("user_action") or "",
        "created_at": row.get("created_at") or "",
    }
