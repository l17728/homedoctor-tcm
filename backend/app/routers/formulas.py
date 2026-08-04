"""Formulas router — list, detail, safety check, TTS-ready text."""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)
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


# Herbs that serve as 使药 (envoy/guide) — harmonize or guide to meridians
ENVOY_HERBS = {"甘草", "大枣", "生姜", "薄荷"}


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


def _parse_dose_num(dose: Any) -> float:
    """Extract a numeric dosage value from a dose string like '9g', '12克', '3枚'.

    Returns 0.0 if no number can be extracted.
    """
    if isinstance(dose, (int, float)):
        return float(dose)
    if not isinstance(dose, str):
        return 0.0
    m = re.search(r"\d+(?:\.\d+)?", dose)
    return float(m.group(0)) if m else 0.0


def _extract_herbs_with_dosage(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract herbs with name + dosage info from a parsed formula row.

    Checks composition list (with dose field) and properties fallback.
    Returns list of {"name", "dosage", "dosage_num"} dicts.
    """
    herbs: list[dict[str, Any]] = []

    composition = parsed.get("composition")
    if isinstance(composition, list):
        for item in composition:
            if isinstance(item, dict):
                name = item.get("name")
                dose = item.get("dose") or item.get("dosage") or ""
                if isinstance(name, str) and name.strip():
                    herbs.append({
                        "name": name.strip(),
                        "dosage": str(dose),
                        "dosage_num": _parse_dose_num(dose),
                    })
            elif isinstance(item, str) and item.strip():
                herbs.append({
                    "name": item.strip(),
                    "dosage": "",
                    "dosage_num": 0.0,
                })

    if not herbs:
        props = parsed.get("properties")
        if isinstance(props, str):
            try:
                props = json.loads(props)
            except (json.JSONDecodeError, TypeError):
                props = {}
        if isinstance(props, dict):
            herbs_field = props.get("herbs")
            if isinstance(herbs_field, list):
                for item in herbs_field:
                    if isinstance(item, dict):
                        name = item.get("name", "")
                        dose = item.get("dosage") or item.get("dose", "")
                        if name:
                            herbs.append({
                                "name": name,
                                "dosage": str(dose),
                                "dosage_num": _parse_dose_num(dose),
                            })
                    elif isinstance(item, str) and item.strip():
                        herbs.append({
                            "name": item.strip(),
                            "dosage": "",
                            "dosage_num": 0.0,
                        })

    return herbs


def classify_herb_roles(herbs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Classify herbs as 君/臣/佐/使 based on dosage ratio (spec §2.2).

    MVP heuristic:
    - Highest dosage = 君药 (sovereign)
    - Second tier (≥80% of max) = 君药
    - ≥40% of max = 臣药 (minister)
    - Lower = 佐药 (assistant)
    - Specific herbs (甘草/大枣/生姜/薄荷) = 使药 (envoy)

    Returns: list of {"name", "role", "dosage", "rationale"} sorted by dosage desc.
    """
    if not herbs:
        return []

    sorted_herbs = sorted(herbs, key=lambda h: h.get("dosage_num", 0), reverse=True)
    max_dosage = sorted_herbs[0].get("dosage_num", 0) or 1

    result: list[dict[str, Any]] = []
    for i, herb in enumerate(sorted_herbs):
        name = herb.get("name", "")
        dosage = herb.get("dosage", "")
        dosage_num = herb.get("dosage_num", 0)

        if name in ENVOY_HERBS:
            role = "使药"
            rationale = f"{name}为引经药或调和药"
        elif i == 0 or dosage_num >= max_dosage * 0.8:
            role = "君药"
            rationale = "主药，用量最大，针对主证"
        elif dosage_num >= max_dosage * 0.4:
            role = "臣药"
            rationale = "辅助君药，加强治疗作用"
        else:
            role = "佐药"
            rationale = "辅助治疗，或制约君药偏性"

        result.append({
            "name": name,
            "role": role,
            "dosage": dosage,
            "rationale": rationale,
        })

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
    """Get formula detail by ID.

    The response includes a ``herb_roles`` field with best-effort 君臣佐使
    classification (spec §2.2).
    """
    repo = FormulaRepository(db)
    row = await repo.get_formula(formula_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该方剂",
        )
    parsed = _parse_formula(row)
    herbs_with_dosage = _extract_herbs_with_dosage(parsed)
    parsed["herb_roles"] = classify_herb_roles(herbs_with_dosage)
    return parsed


def _formula_summary(row: dict[str, Any]) -> dict[str, Any]:
    parsed = _parse_formula(row)
    return {
        "id": parsed.get("id", ""),
        "name": parsed.get("name", ""),
        "category": parsed.get("category", ""),
        "source": parsed.get("source", ""),
        "efficacy": parsed.get("efficacy", ""),
        "derived_from_id": parsed.get("derived_from_id"),
    }


@router.get("/{formula_id}/tree")
async def get_formula_tree(formula_id: str, db: DbAdapter = Depends(get_db)):
    """Build the derivation tree (演化树) for a formula (spec §4.2 US-4).

    Traverses the ``derived_from_id`` chain upward to collect ancestors,
    and queries for all formulas whose ``derived_from_id`` points to this
    formula to collect direct children (one level).

    Returns::

        {
          "formula": {...},          # the queried formula (summary)
          "parent": {...} | null,    # immediate parent if derived_from_id set
          "ancestors": [...],        # root → ... → parent (ordered)
          "children": [...],         # formulas derived directly from this one
          "has_tree": bool           # true if any parent/children exist
        }
    """
    repo = FormulaRepository(db)
    row = await repo.get_formula(formula_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该方剂",
        )

    parsed = _parse_formula(row)
    formula_summary = _formula_summary(row)

    # --- Ancestors: walk derived_from_id chain upward ---
    ancestors: list[dict[str, Any]] = []
    parent_summary: dict[str, Any] | None = None
    current_parent_id = parsed.get("derived_from_id")
    visited: set[str] = {formula_id}
    guard = 0

    while current_parent_id and guard < 50:
        if current_parent_id in visited:
            break
        visited.add(current_parent_id)
        parent_row = await repo.get_formula(current_parent_id)
        if not parent_row:
            break
        parent_parsed = _parse_formula(parent_row)
        ancestors.append(_formula_summary(parent_row))
        if parent_summary is None:
            parent_summary = _formula_summary(parent_row)
        current_parent_id = parent_parsed.get("derived_from_id")
        guard += 1

    # ancestors is ordered [parent, grandparent, ...] → reverse to [root, ..., parent]
    ancestors.reverse()

    # --- Children: direct descendants ---
    children_rows = await db.query(
        "SELECT * FROM formulas WHERE derived_from_id = ? ORDER BY name",
        (formula_id,),
    )
    children = [_formula_summary(r) for r in children_rows]

    has_tree = bool(parent_summary or children)

    return {
        "formula": formula_summary,
        "parent": parent_summary,
        "ancestors": ancestors,
        "children": children,
        "has_tree": has_tree,
    }


@router.get("/{formula_id}/roles")
async def get_formula_herb_roles(
    formula_id: str, db: DbAdapter = Depends(get_db)
):
    """Return the 君臣佐使 role classification for a formula's herbs (spec §2.2)."""
    repo = FormulaRepository(db)
    row = await repo.get_formula(formula_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该方剂",
        )
    parsed = _parse_formula(row)
    herbs_with_dosage = _extract_herbs_with_dosage(parsed)
    roles = classify_herb_roles(herbs_with_dosage)
    return {"formula_id": formula_id, "name": parsed.get("name", ""), "herb_roles": roles}


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
