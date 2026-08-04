"""Herbs router — list, detail, search."""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.database import DbAdapter, get_db
from app.pinyin_data import to_pinyin, to_pinyin_abbrev
from app.repository import HerbRepository
from app.routers.formulas import _parse_formula, extract_herb_names

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


async def _pinyin_search(db: DbAdapter, q: str) -> list[dict[str, Any]]:
    """Search herbs by pinyin (full match or abbreviation).

    Used when the query is ASCII (pinyin input). Matches against both
    full pinyin and first-letter abbreviations of herb names and aliases.
    """
    q_lower = q.lower()
    rows = await db.query("SELECT * FROM herbs ORDER BY name")
    matches: list[dict[str, Any]] = []
    for row in rows:
        name = row.get("name", "")
        aliases_raw = row.get("aliases", "") or ""
        aliases = [a.strip() for a in aliases_raw.split(",") if a.strip()]

        candidates = [name] + aliases
        for candidate in candidates:
            full = to_pinyin(candidate).lower()
            abbrev = to_pinyin_abbrev(candidate).lower()
            if q_lower in full or q_lower in abbrev:
                matches.append(row)
                break
    return matches


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
    """Full-text search across herbs, with pinyin support (spec §2.4).

    - Chinese query: uses FTS5 full-text search
    - ASCII (pinyin) query: matches full pinyin or abbreviations
    """
    if q.isascii():
        pinyin_rows = await _pinyin_search(db, q)
        herbs = [_parse_herb(r) for r in pinyin_rows]
        return {"items": herbs, "total": len(herbs)}

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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该中药",
        )
    return _parse_herb(row)


@router.get("/{herb_id}/formulas")
async def get_herb_formulas(herb_id: str, db: DbAdapter = Depends(get_db)):
    """Find formulas that contain this herb (代表方剂 + 常用配伍).

    Scans all formulas, parses each composition via
    :func:`app.routers.formulas.extract_herb_names`, and returns:

    - ``formulas``: representative formulas containing this herb (≤20).
    - ``common_combinations``: herbs that most frequently co-occur with
      this herb, sorted by co-occurrence count descending (≤10).
    """
    herb = await db.query_one("SELECT name FROM herbs WHERE id = ?", (herb_id,))
    if not herb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该中药",
        )
    herb_name = herb["name"]

    all_formulas = await db.query(
        "SELECT id, name, category, efficacy, composition, properties FROM formulas"
    )
    related: list[dict[str, Any]] = []
    co_occurrence: dict[str, int] = {}

    for f in all_formulas:
        parsed = _parse_formula(f)
        herbs_in_formula = extract_herb_names(parsed)
        if herb_name in herbs_in_formula:
            related.append(
                {
                    "id": f["id"],
                    "name": f["name"],
                    "category": parsed.get("category", "") or "",
                    "efficacy": parsed.get("efficacy", "") or "",
                }
            )
            for h in herbs_in_formula:
                if h != herb_name:
                    co_occurrence[h] = co_occurrence.get(h, 0) + 1

    common_pairs = sorted(
        co_occurrence.items(), key=lambda x: x[1], reverse=True
    )[:10]

    return {
        "herb_name": herb_name,
        "formulas": related[:20],
        "common_combinations": [{"name": h, "count": c} for h, c in common_pairs],
    }
