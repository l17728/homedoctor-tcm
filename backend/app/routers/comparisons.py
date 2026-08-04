"""Comparisons router — 对比分析 (spec §3.4 V2).

Side-by-side comparison of herbs and formulas with similarity / difference
highlighting and combined-usage safety notes.
"""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.database import DbAdapter, get_db
from app.routers.formulas import _parse_formula, extract_herb_names
from app.safety_engine import run_safety_check

router = APIRouter(prefix="/api/comparisons", tags=["comparisons"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_herb(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    if isinstance(result.get("properties"), str):
        try:
            result["properties"] = json.loads(result["properties"])
        except (json.JSONDecodeError, TypeError):
            result["properties"] = {}
    return result


def _split_csv(value: str | None) -> list[str]:
    """Split a comma-separated string into a cleaned list."""
    if not value:
        return []
    return [v.strip() for v in value.replace("，", ",").split(",") if v.strip()]


def _build_herb_property_table(herbs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build a property-by-property comparison table for herbs.

    Each row has: {"field": 字段名, "label": 中文标签, "values": {herb_name: value}, "same": bool}
    """
    fields = [
        ("nature", "药性"),
        ("flavor", "药味"),
        ("meridians", "归经"),
        ("efficacy", "功效"),
        ("indications", "主治"),
        ("dosage_min_g", "最小用量(g)"),
        ("dosage_max_g", "最大用量(g)"),
        ("toxicity", "毒性"),
        ("category", "分类"),
        ("contraindications", "禁忌"),
    ]

    table: list[dict[str, Any]] = []
    for field, label in fields:
        values: dict[str, Any] = {}
        for h in herbs:
            values[h["name"]] = h.get(field, "")
        # Determine if all non-empty values are the same
        non_empty = [str(v) for v in values.values() if v != "" and v is not None]
        same = len(set(non_empty)) <= 1 and len(non_empty) >= 2
        table.append({"field": field, "label": label, "values": values, "same": same})

    return table


def _compute_herb_similarities(herbs: list[dict[str, Any]]) -> list[str]:
    """Identify shared properties across all herbs."""
    similarities: list[str] = []

    if len(herbs) < 2:
        return similarities

    # Shared meridians
    all_meridians: list[set[str]] = []
    for h in herbs:
        meridians = set(_split_csv(h.get("meridians")))
        all_meridians.append(meridians)
    shared_meridians = all_meridians[0]
    for s in all_meridians[1:]:
        shared_meridians &= s
    if shared_meridians:
        names = "、".join(h["name"] for h in herbs)
        similarities.append(f"{names} 均归 {'、'.join(shared_meridians)} 经")

    # Same toxicity
    toxicities = [h.get("toxicity", "") for h in herbs]
    if len(set(toxicities)) == 1 and toxicities[0]:
        similarities.append(f"均为「{toxicities[0]}」")

    # Same nature
    natures = [h.get("nature", "") for h in herbs]
    if len(set(natures)) == 1 and natures[0]:
        similarities.append(f"药性均为「{natures[0]}」")

    # Same category
    categories = [h.get("category", "") for h in herbs]
    if len(set(categories)) == 1 and categories[0]:
        similarities.append(f"同属「{categories[0]}」")

    return similarities


def _compute_herb_differences(herbs: list[dict[str, Any]]) -> list[str]:
    """Identify key differences between herbs."""
    differences: list[str] = []

    if len(herbs) < 2:
        return differences

    # Nature difference
    natures = {h["name"]: h.get("nature", "") for h in herbs}
    if len(set(natures.values())) > 1:
        parts = [f"{name}「{val}」" for name, val in natures.items()]
        differences.append("药性不同：" + "，".join(parts))

    # Flavor difference
    flavors = {h["name"]: h.get("flavor", "") for h in herbs}
    if len(set(flavors.values())) > 1:
        parts = [f"{name}「{val}」" for name, val in flavors.items()]
        differences.append("药味不同：" + "，".join(parts))

    # Primary efficacy focus
    efficacies = {h["name"]: (h.get("efficacy", "") or "")[:20] for h in herbs}
    if len(set(efficacies.values())) > 1:
        parts = [f"{name}偏「{val}…」" for name, val in efficacies.items()]
        differences.append("功效侧重不同：" + "，".join(parts))

    # Dosage range difference
    ranges = {}
    for h in herbs:
        lo = h.get("dosage_min_g")
        hi = h.get("dosage_max_g")
        if lo and hi:
            ranges[h["name"]] = f"{lo}-{hi}g"
    if len(set(ranges.values())) > 1:
        parts = [f"{name}「{val}」" for name, val in ranges.items()]
        differences.append("用量范围不同：" + "，".join(parts))

    return differences


async def _compute_combined_safety_notes(
    db: DbAdapter, herb_names: list[str]
) -> list[str]:
    """Run the safety engine on the combined herb set and extract notes."""
    notes: list[str] = []
    result = await run_safety_check(db=db, herb_names=herb_names)
    for w in result.warnings:
        herbs_str = "、".join(w.herbs) if w.herbs else ""
        notes.append(f"【{w.severity}】{w.title}：涉及{herbs_str}。{w.detail}")
    if result.unknown_herbs:
        notes.append("以下药材未在数据库中找到：" + "、".join(result.unknown_herbs))
    return notes


# ---------------------------------------------------------------------------
# Herb comparison
# ---------------------------------------------------------------------------

@router.post("/herbs")
async def compare_herbs(
    body: dict,
    db: DbAdapter = Depends(get_db),
):
    """多味中药对比分析.

    Body: ``{"herb_ids": ["herb-001", "herb-002", ...]}``

    Returns a side-by-side property table plus similarity / difference /
    safety analysis.
    """
    herb_ids = body.get("herb_ids", [])
    if not isinstance(herb_ids, list) or len(herb_ids) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="至少需要两味中药进行对比",
        )

    herbs: list[dict[str, Any]] = []
    not_found: list[str] = []
    for hid in herb_ids:
        row = await db.query_one("SELECT * FROM herbs WHERE id = ?", (hid,))
        if not row:
            not_found.append(hid)
        else:
            herbs.append(_parse_herb(row))

    if len(herbs) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="至少需要两味有效中药进行对比"
                   + (f"，未找到：{', '.join(not_found)}" if not_found else ""),
        )

    property_table = _build_herb_property_table(herbs)
    similarities = _compute_herb_similarities(herbs)
    differences = _compute_herb_differences(herbs)
    safety_notes = await _compute_combined_safety_notes(
        db, [h["name"] for h in herbs]
    )

    return {
        "herbs": [
            {
                "id": h["id"],
                "name": h["name"],
                "nature": h.get("nature", ""),
                "flavor": h.get("flavor", ""),
                "meridians": h.get("meridians", ""),
                "efficacy": h.get("efficacy", ""),
                "indications": h.get("indications", ""),
                "dosage_min_g": h.get("dosage_min_g"),
                "dosage_max_g": h.get("dosage_max_g"),
                "toxicity": h.get("toxicity", ""),
                "category": h.get("category", ""),
                "contraindications": h.get("contraindications", ""),
            }
            for h in herbs
        ],
        "property_table": property_table,
        "similarities": similarities,
        "differences": differences,
        "safety_notes": safety_notes,
        "not_found": not_found,
    }


@router.get("/herbs/{herb_a}/{herb_b}")
async def compare_two_herbs(
    herb_a: str,
    herb_b: str,
    db: DbAdapter = Depends(get_db),
):
    """快速两味中药对比 (GET 便捷端点)."""
    return await compare_herbs({"herb_ids": [herb_a, herb_b]}, db)


# ---------------------------------------------------------------------------
# Formula comparison
# ---------------------------------------------------------------------------

@router.post("/formulas")
async def compare_formulas(
    body: dict,
    db: DbAdapter = Depends(get_db),
):
    """多方剂对比分析.

    Body: ``{"formula_ids": ["formula-001", "formula-002", ...]}``

    Returns composition overlap, shared herbs, efficacy comparison,
    indications overlap, and safety notes.
    """
    formula_ids = body.get("formula_ids", [])
    if not isinstance(formula_ids, list) or len(formula_ids) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="至少需要两首方剂进行对比",
        )

    formulas: list[dict[str, Any]] = []
    not_found: list[str] = []
    for fid in formula_ids:
        row = await db.query_one("SELECT * FROM formulas WHERE id = ?", (fid,))
        if not row:
            not_found.append(fid)
        else:
            formulas.append(_parse_formula(row))

    if len(formulas) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="至少需要两首有效方剂进行对比"
                   + (f"，未找到：{', '.join(not_found)}" if not_found else ""),
        )

    # Extract herbs from each formula
    formula_herbs: dict[str, set[str]] = {}
    for f in formulas:
        names = set(extract_herb_names(f))
        formula_herbs[f["name"]] = names

    # Shared herbs (in ALL formulas) — copy to avoid in-place mutation
    shared_herbs_set = set(formula_herbs[formulas[0]["name"]])
    for name in list(formula_herbs.keys())[1:]:
        shared_herbs_set &= formula_herbs[name]

    # Herbs unique to each formula
    all_herbs: set[str] = set()
    for names in formula_herbs.values():
        all_herbs |= names

    herbs_unique: dict[str, list[str]] = {}
    for fname, fnames in formula_herbs.items():
        unique = sorted(fnames - shared_herbs_set)
        herbs_unique[fname] = unique

    # Composition overlap ratio (Jaccard)
    overlap_data: list[dict[str, Any]] = []
    formula_names = list(formula_herbs.keys())
    for i, name_a in enumerate(formula_names):
        for name_b in formula_names[i + 1:]:
            set_a = formula_herbs[name_a]
            set_b = formula_herbs[name_b]
            union = set_a | set_b
            intersection = set_a & set_b
            ratio = len(intersection) / len(union) if union else 0.0
            overlap_data.append({
                "formula_a": name_a,
                "formula_b": name_b,
                "shared": sorted(intersection),
                "shared_count": len(intersection),
                "overlap_ratio": round(ratio, 2),
            })

    # Efficacy comparison
    efficacy_comparison = [
        {"name": f["name"], "efficacy": f.get("efficacy", "") or ""}
        for f in formulas
    ]

    # Indications overlap analysis
    indication_keywords: dict[str, set[str]] = {}
    for f in formulas:
        text = f.get("indications", "") or ""
        # Simple keyword extraction: split by common delimiters
        keywords = set()
        for chunk in text.replace("，", " ").replace("。", " ").replace("、", " ").split():
            chunk = chunk.strip()
            if len(chunk) >= 2:
                keywords.add(chunk)
        indication_keywords[f["name"]] = keywords

    shared_indications: set[str] = indication_keywords.get(formula_names[0], set())
    for name in formula_names[1:]:
        shared_indications &= indication_keywords.get(name, set())

    # Property comparison table
    property_table: list[dict[str, Any]] = []
    for field, label in [
        ("category", "分类"),
        ("source", "出处"),
        ("efficacy", "功效"),
        ("indications", "主治"),
    ]:
        values = {f["name"]: f.get(field, "") or "" for f in formulas}
        non_empty = [str(v) for v in values.values() if v]
        same = len(set(non_empty)) <= 1 and len(non_empty) >= 2
        property_table.append({"field": field, "label": label, "values": values, "same": same})

    # Safety: check all herbs from all formulas combined
    all_herb_names: list[str] = []
    seen: set[str] = set()
    for f in formulas:
        for name in extract_herb_names(f):
            if name not in seen:
                all_herb_names.append(name)
                seen.add(name)

    safety_notes = await _compute_combined_safety_notes(db, all_herb_names)

    return {
        "formulas": [
            {
                "id": f["id"],
                "name": f["name"],
                "category": f.get("category", "") or "",
                "source": f.get("source", "") or "",
                "efficacy": f.get("efficacy", "") or "",
                "indications": f.get("indications", "") or "",
                "composition": f.get("composition", []),
                "herb_names": sorted(formula_herbs[f["name"]]),
            }
            for f in formulas
        ],
        "shared_herbs": sorted(shared_herbs_set),
        "shared_herb_count": len(shared_herbs_set),
        "herbs_unique_to_each": herbs_unique,
        "composition_overlap": overlap_data,
        "efficacy_comparison": efficacy_comparison,
        "shared_indications": sorted(shared_indications),
        "property_table": property_table,
        "safety_notes": safety_notes,
        "not_found": not_found,
    }
