"""Unified knowledge API — serves herbs/formulas/symptoms from knowledge_entities.

These endpoints read from the unified knowledge_entities table (Phase 2 model)
instead of the legacy herbs/formulas tables. The legacy endpoints remain for
backward compatibility; new consumers should prefer these.

Endpoints:
  GET  /api/knowledge/herbs              — paginated herb list
  GET  /api/knowledge/herbs/{id}         — herb detail + relationships
  GET  /api/knowledge/formulas           — paginated formula list
  GET  /api/knowledge/formulas/{id}      — formula detail + relationships
  GET  /api/knowledge/symptoms           — symptom list (with treating herbs)
  GET  /api/knowledge/graph/{id}         — multi-hop graph traversal
  GET  /api/knowledge/search             — cross-type unified search
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import DbAdapter, get_db
from app.knowledge_reader import (
    get_entity,
    get_entity_with_relations,
    list_entities,
    multi_hop_traverse,
)

router = APIRouter(prefix="/api/knowledge", tags=["unified-knowledge"])


@router.get("/herbs")
async def list_herbs(
    q: str | None = Query(None, description="搜索关键词"),
    category: str | None = Query(None, description="按分类筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: DbAdapter = Depends(get_db),
) -> dict[str, Any]:
    return await list_entities(
        db, "herb", category=category, search=q, page=page, page_size=page_size
    )


@router.get("/herbs/{entity_id}")
async def get_herb(
    entity_id: str,
    db: DbAdapter = Depends(get_db),
) -> dict[str, Any]:
    result = await get_entity_with_relations(db, entity_id)
    if not result:
        raise HTTPException(status_code=404, detail="药材不存在")
    return result


@router.get("/formulas")
async def list_formulas(
    q: str | None = Query(None),
    category: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: DbAdapter = Depends(get_db),
) -> dict[str, Any]:
    return await list_entities(
        db, "formula", category=category, search=q, page=page, page_size=page_size
    )


@router.get("/formulas/{entity_id}")
async def get_formula(
    entity_id: str,
    db: DbAdapter = Depends(get_db),
) -> dict[str, Any]:
    result = await get_entity_with_relations(db, entity_id)
    if not result:
        raise HTTPException(status_code=404, detail="方剂不存在")
    return result


@router.get("/symptoms")
async def list_symptoms(
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: DbAdapter = Depends(get_db),
) -> dict[str, Any]:
    return await list_entities(
        db, "symptom", search=q, page=page, page_size=page_size
    )


@router.get("/meridians")
async def list_meridians(
    q: str | None = Query(None),
    category: str | None = Query(None, description="正经/奇经"),
    db: DbAdapter = Depends(get_db),
) -> dict[str, Any]:
    result = await list_entities(
        db, "meridian", category=category, search=q, page=1, page_size=50
    )
    return result


@router.get("/meridians/{entity_id}")
async def get_meridian(
    entity_id: str,
    db: DbAdapter = Depends(get_db),
) -> dict[str, Any]:
    result = await get_entity_with_relations(db, entity_id)
    if not result:
        raise HTTPException(status_code=404, detail="经络不存在")
    return result


@router.get("/acupoints")
async def list_acupoints(
    q: str | None = Query(None, description="搜索穴名或功能"),
    meridian: str | None = Query(None, description="按经络筛选（经络名或代码）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: DbAdapter = Depends(get_db),
) -> dict[str, Any]:
    result = await list_entities(
        db, "acupoint", search=q, page=page, page_size=page_size
    )
    if meridian and result["items"]:
        filtered = []
        for item in result["items"]:
            props = item.get("properties", {})
            if meridian in (props.get("meridian", ""), props.get("meridian_code", "")):
                filtered.append(item)
        result["items"] = filtered
        result["total"] = len(filtered)
    return result


@router.get("/acupoints/{entity_id}")
async def get_acupoint(
    entity_id: str,
    db: DbAdapter = Depends(get_db),
) -> dict[str, Any]:
    result = await get_entity_with_relations(db, entity_id)
    if not result:
        raise HTTPException(status_code=404, detail="穴位不存在")
    return result


@router.get("/therapies")
async def list_therapies(
    q: str | None = Query(None),
    category: str | None = Query(None, description="针刺/灸法/推拿/拔罐/刮痧/刺血/中药外治"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: DbAdapter = Depends(get_db),
) -> dict[str, Any]:
    return await list_entities(
        db, "therapy", category=category, search=q, page=page, page_size=page_size
    )


@router.get("/therapies/{entity_id}")
async def get_therapy(
    entity_id: str,
    db: DbAdapter = Depends(get_db),
) -> dict[str, Any]:
    result = await get_entity_with_relations(db, entity_id)
    if not result:
        raise HTTPException(status_code=404, detail="疗法不存在")
    return result


@router.get("/graph/{entity_id}")
async def get_graph(
    entity_id: str,
    hops: int = Query(3, ge=1, le=5, description="遍历跳数"),
    db: DbAdapter = Depends(get_db),
) -> dict[str, Any]:
    entity = await get_entity(db, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="实体不存在")
    paths = await multi_hop_traverse(db, entity_id, max_hops=hops)
    return {
        "entity": entity,
        "paths": paths,
        "path_count": len(paths),
    }


@router.get("/search")
async def unified_search(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    type: str | None = Query(None, description="限定类型：herb/formula/symptom/therapy"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: DbAdapter = Depends(get_db),
) -> dict[str, Any]:
    if type:
        return await list_entities(
            db, type, search=q, page=page, page_size=page_size
        )

    types = ["herb", "formula", "acupoint", "meridian", "therapy", "symptom"]
    all_items: list[dict[str, Any]] = []
    for t in types:
        result = await list_entities(
            db, t, search=q, page=1, page_size=page_size
        )
        all_items.extend(result["items"])

    all_items.sort(key=lambda x: x.get("view_count", 0), reverse=True)
    total = len(all_items)
    start = (page - 1) * page_size
    return {
        "items": all_items[start : start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
