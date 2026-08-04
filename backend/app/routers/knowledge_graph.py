"""Knowledge graph router — graph visualization endpoints (spec §9/§13.3 V3)."""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.auth import get_current_user

from app.database import DbAdapter, get_db
from app.graph_engine import build_graph, build_snapshot
from app.kg_rebuild import rebuild_all_edges

router = APIRouter(prefix="/api/kg", tags=["knowledge-graph"])


@router.get("/graph")
async def get_graph(
    types: str | None = Query(None, description="逗号分隔的节点类型，如 herb,formula"),
    q: str | None = Query(None, description="关键词搜索"),
    limit: int = Query(500, ge=1, le=2000),
    db: DbAdapter = Depends(get_db),
):
    """全图/筛选视图 — 跨类型收集节点，再取节点之间的边。"""
    type_list = (
        [t.strip() for t in types.split(",") if t.strip()] if types else None
    )
    return await build_graph(db, node_types=type_list, q=q, limit=limit)


@router.get("/snapshot/{node_type}/{node_id}")
async def get_snapshot(
    node_type: str,
    node_id: str,
    depth: int = Query(1, ge=1, le=3),
    db: DbAdapter = Depends(get_db),
):
    """BFS 邻域 — 从根节点出发，最多 ``depth`` 跳。"""
    return await build_snapshot(db, node_type, node_id, max_depth=depth)


@router.post("/rebuild")
async def rebuild(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """重建全部派生边（组成/主治/配伍禁忌/中西药交互）。"""
    return await rebuild_all_edges(db)


@router.get("/node/{node_id}")
async def get_node(node_id: str, db: DbAdapter = Depends(get_db)):
    """节点详情 — 返回完整属性。"""
    row = await db.query_one("SELECT * FROM graph_nodes WHERE id = ?", (node_id,))
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="节点不存在"
        )
    result: dict[str, Any] = dict(row)
    if isinstance(result.get("properties"), str):
        try:
            result["properties"] = json.loads(result["properties"])
        except (json.JSONDecodeError, TypeError):
            result["properties"] = {}
    return result
