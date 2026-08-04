"""Therapies router — 刮痧/推拿/艾灸/拔罐/针刺/刺血 (spec §9.6)."""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.database import DbAdapter, get_db

router = APIRouter(prefix="/api/therapies", tags=["therapies"])


def _parse_therapy(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    if isinstance(result.get("properties"), str):
        try:
            result["properties"] = json.loads(result["properties"])
        except (json.JSONDecodeError, TypeError):
            result["properties"] = {}
    for key in ("home_use_safe", "display_only"):
        if key in result and isinstance(result[key], int):
            result[key] = bool(result[key])
    return result


def _parse_acupoint(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    if "is_primary" in result and isinstance(result["is_primary"], int):
        result["is_primary"] = bool(result["is_primary"])
    return result


@router.get("")
async def list_therapies(
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    category: str | None = Query(None, description="按疗法分类过滤：刮痧/推拿/艾灸/拔罐/针刺/刺血"),
    db: DbAdapter = Depends(get_db),
):
    where = ""
    params: list[Any] = []
    if category:
        where = "WHERE category = ?"
        params.append(category)

    count_row = await db.query_one(
        f"SELECT COUNT(*) as cnt FROM therapies {where}", tuple(params)
    )
    total = count_row["cnt"] if count_row else 0

    offset = (page - 1) * pageSize
    rows = await db.query(
        f"""SELECT id, name, category, risk_level, home_use_safe, display_only,
                  description, indications, duration, frequency, precautions
           FROM therapies {where}
           ORDER BY category, name
           LIMIT ? OFFSET ?""",
        tuple(params + [pageSize, offset]),
    )
    therapies = [_parse_therapy(r) for r in rows]
    total_pages = (total + pageSize - 1) // pageSize
    return {
        "items": therapies,
        "total": total,
        "page": page,
        "pageSize": pageSize,
        "totalPages": total_pages,
    }


@router.get("/categories")
async def list_categories(
    db: DbAdapter = Depends(get_db),
):
    rows = await db.query(
        """SELECT category, COUNT(*) as count
           FROM therapies GROUP BY category ORDER BY category"""
    )
    return {"categories": [{"name": r["category"], "count": r["count"]} for r in rows]}


@router.get("/search")
async def search_therapies(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    category: str | None = Query(None),
    db: DbAdapter = Depends(get_db),
):
    fts_rows = await db.query(
        """SELECT t.* FROM therapies t
           JOIN therapies_fts fts ON t.rowid = fts.rowid
           WHERE therapies_fts MATCH ?
           ORDER BY rank""",
        (q,),
    )

    if not fts_rows:
        like_pattern = f"%{q}%"
        like_rows = await db.query(
            """SELECT * FROM therapies
               WHERE name LIKE ? OR description LIKE ?
                  OR indications LIKE ? OR contraindications LIKE ?""",
            (like_pattern, like_pattern, like_pattern, like_pattern),
        )
        fts_rows = like_rows

    if category:
        fts_rows = [r for r in fts_rows if r.get("category") == category]

    therapies = [_parse_therapy(r) for r in fts_rows]
    return {"items": therapies, "total": len(therapies)}


@router.get("/{therapy_id}")
async def get_therapy(therapy_id: str, db: DbAdapter = Depends(get_db)):
    row = await db.query_one("SELECT * FROM therapies WHERE id = ?", (therapy_id,))
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该疗法",
        )

    therapy = _parse_therapy(row)

    acupoints = await db.query(
        """SELECT acupoint_name, location, function, meridian, is_primary
           FROM therapy_acupoints WHERE therapy_id = ? ORDER BY is_primary DESC""",
        (therapy_id,),
    )
    therapy["acupoints"] = [_parse_acupoint(ap) for ap in acupoints]

    safety_rows = await db.query(
        """SELECT rule_type, condition_text, action, severity, therapy_category
           FROM therapy_safety_rules
           WHERE therapy_category = ? OR therapy_category = 'all'
           ORDER BY
             CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                           WHEN 'medium' THEN 2 ELSE 3 END""",
        (therapy["category"],),
    )
    therapy["safety_rules"] = safety_rows

    return therapy


@router.get("/{therapy_id}/safety")
async def get_therapy_safety(therapy_id: str, db: DbAdapter = Depends(get_db)):
    therapy = await db.query_one(
        "SELECT id, name, category, risk_level, display_only FROM therapies WHERE id = ?",
        (therapy_id,),
    )
    if not therapy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该疗法",
        )

    category = therapy["category"]
    safety_rows = await db.query(
        """SELECT rule_type, condition_text, action, severity, therapy_category
           FROM therapy_safety_rules
           WHERE therapy_category = ? OR therapy_category = 'all'
           ORDER BY
             CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                           WHEN 'medium' THEN 2 ELSE 3 END""",
        (category,),
    )

    return {
        "therapy_id": therapy["id"],
        "therapy_name": therapy["name"],
        "category": category,
        "risk_level": therapy["risk_level"],
        "display_only": bool(therapy["display_only"]),
        "rules": safety_rows,
        "total": len(safety_rows),
    }
