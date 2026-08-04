"""Personal knowledge API — family-private health edges to global entities.

Endpoints:
  POST  /api/personal/symptoms        — log a symptom (links to global entity)
  GET   /api/personal/symptoms        — list personal symptoms
  DELETE /api/personal/edges/{edge_id} — remove a personal edge
  GET   /api/personal/edges           — list all personal edges
  GET   /api/personal/graph           — personal health graph (person + edges)
"""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.database import DbAdapter, get_db
from app.personal_knowledge import (
    add_personal_edge,
    ensure_person_entity,
    find_entity_by_title,
    list_personal_edges,
    remove_personal_edge,
)

router = APIRouter(prefix="/api/personal", tags=["personal-knowledge"])


class SymptomLog(BaseModel):
    symptom_name: str = Field(..., description="症状名称（如 气虚乏力）")
    severity: str = Field("轻度", description="严重程度：轻度/中度/重度")
    note: str = Field("", description="备注")


class EdgeCreate(BaseModel):
    target_title: str = Field(..., description="目标实体名称")
    target_type: str = Field("symptom", description="目标实体类型")
    relationship_type: str = Field("has_symptom", description="关系类型")
    properties: dict[str, Any] = Field(default_factory=dict)


def _get_tenant_id(current_user: dict) -> str:
    return current_user.get("tenant_id") or current_user.get("id", "default")


@router.post("/symptoms")
async def log_symptom(
    body: SymptomLog,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Log a personal symptom — creates an edge to the global symptom entity."""
    tenant_id = _get_tenant_id(current_user)
    person_id = await ensure_person_entity(
        db, current_user["id"], tenant_id,
        current_user.get("username", ""),
    )

    target = await find_entity_by_title(db, body.symptom_name, "symptom")
    if not target:
        raise HTTPException(
            status_code=404,
            detail=f"症状「{body.symptom_name}」未在知识库中找到",
        )

    edge_id = await add_personal_edge(
        db, person_id, target["id"], "has_symptom", tenant_id,
        properties={"severity": body.severity, "note": body.note},
    )
    return {
        "edge_id": edge_id,
        "symptom": body.symptom_name,
        "target_entity_id": target["id"],
        "message": f"已记录症状「{body.symptom_name}」",
    }


@router.get("/symptoms")
async def list_symptoms(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """List the current user's personal symptoms with global entity data."""
    tenant_id = _get_tenant_id(current_user)
    person_id = await ensure_person_entity(
        db, current_user["id"], tenant_id,
        current_user.get("username", ""),
    )
    edges = await list_personal_edges(
        db, person_id, tenant_id, relationship_type="has_symptom"
    )
    return {"symptoms": edges, "total": len(edges)}


@router.post("/edges")
async def create_edge(
    body: EdgeCreate,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a personal edge to any global entity (herb, formula, etc.)."""
    tenant_id = _get_tenant_id(current_user)
    person_id = await ensure_person_entity(
        db, current_user["id"], tenant_id,
        current_user.get("username", ""),
    )

    target = await find_entity_by_title(db, body.target_title, body.target_type)
    if not target:
        raise HTTPException(
            status_code=404,
            detail=f"「{body.target_title}」未在知识库中找到（类型: {body.target_type}）",
        )

    edge_id = await add_personal_edge(
        db, person_id, target["id"], body.relationship_type, tenant_id,
        properties=body.properties,
    )
    return {
        "edge_id": edge_id,
        "target": body.target_title,
        "relationship": body.relationship_type,
    }


@router.get("/edges")
async def list_edges(
    relationship_type: str | None = Query(None),
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """List all personal edges for the current user."""
    tenant_id = _get_tenant_id(current_user)
    person_id = await ensure_person_entity(
        db, current_user["id"], tenant_id,
        current_user.get("username", ""),
    )
    edges = await list_personal_edges(
        db, person_id, tenant_id, relationship_type=relationship_type
    )
    return {"edges": edges, "total": len(edges)}


@router.delete("/edges/{edge_id}")
async def delete_edge(
    edge_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Remove a personal edge."""
    tenant_id = _get_tenant_id(current_user)
    deleted = await remove_personal_edge(db, edge_id, tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="边不存在或无权删除")
    return {"message": "已删除", "edge_id": edge_id}


@router.get("/graph")
async def personal_graph(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the user's personal health graph: person entity + all edges."""
    tenant_id = _get_tenant_id(current_user)
    person_id = await ensure_person_entity(
        db, current_user["id"], tenant_id,
        current_user.get("username", ""),
    )
    edges = await list_personal_edges(db, person_id, tenant_id)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for e in edges:
        rel = e["relationship_type"]
        if rel not in grouped:
            grouped[rel] = []
        grouped[rel].append(e)

    return {
        "person_id": person_id,
        "username": current_user.get("username", ""),
        "edge_count": len(edges),
        "groups": grouped,
    }


