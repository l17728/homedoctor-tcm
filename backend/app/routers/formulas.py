"""Formulas router — list, detail, safety check, TTS-ready text."""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.auth import get_current_user
from app.database import DbAdapter, get_db
from app.models import SafetyCheckResponseV2, SafetyWarningV2
from app.repository import FormulaRepository
from app.safety_engine import run_safety_check

router = APIRouter(prefix="/api/formulas", tags=["formulas"])


# Leading run of CJK chars (BMP + Ext-A) = herb name. Stops before dosage/digits.
_CJK_RUN = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]+")
# Dosage tokens glued to herb names in free text: 30g / 10克 / 三钱 / 2枚 ...
_DOSAGE_TOKEN = re.compile(
    r"(?:\d+(?:\.\d+)?\s*(?:g|克|kg|毫升|ml|枚|片|钱|两|分)|[一二三四五六七八九十百]+\s*(?:钱|两|分|克|枚|片))",
    re.IGNORECASE,
)


def extract_herb_names(formula_data: dict[str, Any]) -> list[str]:
    """Extract herb names from a parsed formula row.

    Checks three storage formats in priority order:

    1. ``composition`` column: JSON array of ``{"name", "dose", "role"}`` dicts.
    2. ``properties["herbs"]``: JSON array of herb-name strings.
    3. ``properties["组成"]`` / ``properties["composition"]``: free text parsed
       with :func:`_parse_text_herbs`.

    Returns de-duplicated names preserving first-seen order.
    """
    names: list[str] = []

    composition = formula_data.get("composition")
    if isinstance(composition, list):
        for item in composition:
            if isinstance(item, dict):
                n = item.get("name")
                if isinstance(n, str) and n.strip():
                    names.append(n.strip())
            elif isinstance(item, str) and item.strip():
                names.append(item.strip())

    if not names:
        props = formula_data.get("properties")
        if isinstance(props, str):
            try:
                props = json.loads(props)
            except (json.JSONDecodeError, TypeError):
                props = {}
        if isinstance(props, dict):
            herbs_field = props.get("herbs")
            if isinstance(herbs_field, list):
                for item in herbs_field:
                    if isinstance(item, str) and item.strip():
                        names.append(item.strip())
            elif not names:
                text = props.get("组成") or props.get("composition")
                if isinstance(text, str) and text.strip():
                    names.extend(_parse_text_herbs(text))

    seen: set[str] = set()
    unique: list[str] = []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            unique.append(n)
    return unique


def _parse_text_herbs(text: str) -> list[str]:
    names: list[str] = []
    chunks = re.split(r"[\s,，;；、]+", text)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        cleaned = _DOSAGE_TOKEN.sub("", chunk).strip()
        m = _CJK_RUN.match(cleaned)
        if m:
            names.append(m.group(0))
    if not names:
        for m in _CJK_RUN.finditer(text):
            names.append(m.group(0))
    return names


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


@router.get("/{formula_id}/safety-check", response_model=SafetyCheckResponseV2)
async def check_formula_safety(
    formula_id: str,
    user: dict = Depends(get_current_user),
    db: DbAdapter = Depends(get_db),
):
    """Check safety of all herbs in a formula via the five-layer engine.

    Loads the formula, extracts herb names from its ``composition`` (or
    ``properties`` fallback), then delegates to
    :func:`app.safety_engine.run_safety_check`.
    """
    repo = FormulaRepository(db)
    row = await repo.get_formula(formula_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该方剂",
        )

    parsed = _parse_formula(row)
    herb_names = extract_herb_names(parsed)

    result = await run_safety_check(db=db, herb_names=herb_names)

    warnings = [
        SafetyWarningV2(
            layer=w.layer,
            severity=w.severity,
            title=w.title,
            detail=w.detail,
            herbs=w.herbs,
            action=w.action,
            source=w.source,
        )
        for w in result.warnings
    ]
    return SafetyCheckResponseV2(
        safe=result.safe,
        warnings=warnings,
        disclaimer=result.disclaimer,
        checked_herbs=result.checked_herbs,
        checked_medicines=result.checked_medicines,
        unknown_herbs=result.unknown_herbs,
        unknown_medicines=result.unknown_medicines,
    )


def _build_tts_text(formula_name: str, result: Any) -> str:
    parts: list[str] = [f"方剂{formula_name}的安全检查结果。"]
    if result.safe:
        parts.append("未发现配伍禁忌，整体安全。")
    else:
        parts.append(f"共发现{len(result.warnings)}项需要注意的问题。")
        for w in result.warnings:
            herbs_str = "、".join(w.herbs) if w.herbs else ""
            parts.append(
                f"{w.title}：涉及{herbs_str}。{w.detail}建议{w.action}。"
            )
    if result.unknown_herbs:
        parts.append("以下药材未在数据库中找到：" + "、".join(result.unknown_herbs) + "。")
    parts.append(result.disclaimer)
    return "\n".join(parts)


@router.get("/{formula_id}/safety-text")
async def formula_safety_text(
    formula_id: str,
    user: dict = Depends(get_current_user),
    db: DbAdapter = Depends(get_db),
):
    """Return a TTS-ready plain-text summary of a formula's safety check.

    The response body is ``text/plain; charset=utf-8`` so it can be fed
    directly to a speech-synthesis engine for the elderly-mode voice feature.
    """
    repo = FormulaRepository(db)
    row = await repo.get_formula(formula_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该方剂",
        )

    parsed = _parse_formula(row)
    herb_names = extract_herb_names(parsed)
    result = await run_safety_check(db=db, herb_names=herb_names)
    text = _build_tts_text(parsed.get("name", formula_id), result)
    return Response(content=text, media_type="text/plain; charset=utf-8")
