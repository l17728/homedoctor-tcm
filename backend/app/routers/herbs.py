"""Herbs router — list, detail, search."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.database import DbAdapter, get_db
from app.repository import HerbRepository

router = APIRouter(prefix="/api/herbs", tags=["herbs"])


def _parse_herb(row: dict[str, Any]) -> dict[str, Any]:
    """Parse a herb row, converting JSON strings to dicts."""
    result = dict(row)
    if isinstance(result.get("properties"), str):
        try:
            result["properties"] = json.loads(result["properties"])
        except (json.JSONDecodeError, TypeError):
            result["properties"] = {}
    return result


@router.get("")
async def list_herbs(
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    category: str | None = Query(None),
    db: DbAdapter = Depends(get_db),
):
    """List herbs with pagination and optional category filter."""
    repo = HerbRepository(db)
    rows, total = await repo.list_herbs(page=page, page_size=pageSize, category=category)
    herbs = [_parse_herb(r) for r in rows]
    total_pages = (total + pageSize - 1) // pageSize
    return {
        "items": herbs,
        "total": total,
        "page": page,
        "pageSize": pageSize,
        "totalPages": total_pages,
    }


@router.get("/search")
async def search_herbs(
    q: str = Query(..., min_length=1),
    db: DbAdapter = Depends(get_db),
):
    """Full-text search across herbs."""
    repo = HerbRepository(db)
    rows = await repo.search_herbs(q)
    herbs = [_parse_herb(r) for r in rows]
    return {"items": herbs, "total": len(herbs)}


@router.get("/{herb_id}")
async def get_herb(herb_id: str, db: DbAdapter = Depends(get_db)):
    """Get herb detail by ID."""
    repo = HerbRepository(db)
    row = await repo.get_herb(herb_id)
    if not row:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该中药",
        )
    return _parse_herb(row)
