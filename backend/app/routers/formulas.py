"""Formulas router — list, detail."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.database import DbAdapter, get_db
from app.repository import FormulaRepository

router = APIRouter(prefix="/api/formulas", tags=["formulas"])


def _parse_formula(row: dict[str, Any]) -> dict[str, Any]:
    """Parse a formula row, converting JSON strings to objects."""
    result = dict(row)
    for field in ("composition", "modifications", "modifications_structured", "properties"):
        if isinstance(result.get(field), str):
            try:
                result[field] = json.loads(result[field])
            except (json.JSONDecodeError, TypeError):
                result[field] = [] if field != "properties" else {}
    return result


@router.get("")
async def list_formulas(
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    category: str | None = Query(None),
    db: DbAdapter = Depends(get_db),
):
    """List formulas with pagination."""
    repo = FormulaRepository(db)
    rows, total = await repo.list_formulas(page=page, page_size=pageSize, category=category)
    formulas = [_parse_formula(r) for r in rows]
    total_pages = (total + pageSize - 1) // pageSize
    return {
        "items": formulas,
        "total": total,
        "page": page,
        "pageSize": pageSize,
        "totalPages": total_pages,
    }


@router.get("/{formula_id}")
async def get_formula(formula_id: str, db: DbAdapter = Depends(get_db)):
    """Get formula detail by ID."""
    repo = FormulaRepository(db)
    row = await repo.get_formula(formula_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该方剂",
        )
    return _parse_formula(row)
