"""智能配伍引擎 — Smart formulation engine (spec §16.3).

Generates herb combination recommendations based on symptoms and constitution,
generates 代茶饮 (tea infusion) recipes, and recommends OTC medicines from the
user's inventory. All recommendations pass through the five-layer safety check
(:func:`app.safety_engine.run_safety_check`) and always carry a disclaimer.

Design rules (per AGENTS.md):
- 中文领域语言 — every enum / label / category uses Chinese原文.
- Hardcoded rules first — safety engine is invoked on every recommendation.
- 结构化是权威 — recommendations are derived from the ``herbs`` /
  ``medicines`` tables; nothing is hallucinated.
"""

from __future__ import annotations

import json
from typing import Any

from app.database import DbAdapter
from app.safety_engine import (
    DISCLAIMER,
    SafetyCheckResult,
    run_safety_check,
)


# ---------------------------------------------------------------------------
# Constitution → beneficial / contraindicated herb categories
# ---------------------------------------------------------------------------
# Sources: 王琦九种体质理论 + 《中药学》分类。
# Keyed by the 体质 names defined in ``constitution_data.NINE_CONSTITUTION_TYPES``.
# Values are substrings matched against ``herbs.category`` — order = priority.

CONSTITUTION_CATEGORY_MAP: dict[str, list[str]] = {
    "平和质": [],  # 平和体质无需特殊匹配，所有药材同等对待
    "气虚质": ["补气", "补虚", "健脾"],
    "阳虚质": ["补阳", "温里", "温阳", "补虚"],
    "阴虚质": ["补阴", "滋阴", "补虚"],
    "痰湿质": ["化痰", "化湿", "利水", "渗湿", "燥湿"],
    "湿热质": ["清热", "燥湿", "利湿", "解毒"],
    "血瘀质": ["活血", "化瘀", "理血"],
    "气郁质": ["理气", "疏肝", "解郁"],
    "特禀质": ["解表", "祛风", "抗敏"],
}


# Contraindication-keyword scan: if a herb's ``contraindications`` text contains
# any of these keywords for the user's constitution, it is filtered out (not
# just deprioritized). This implements spec §16.3 Step 1 "体质" 治法方向.
CONSTITUTION_CONTRA_KEYWORDS: dict[str, list[str]] = {
    "气虚质": ["气虚忌", "气虚慎", "正气虚"],
    "阳虚质": ["阳虚忌", "阴虚阳亢"],
    "阴虚质": ["阴虚忌", "阴虚慎", "阴虚火旺", "阴虚阳亢"],
    "痰湿质": ["湿盛", "痰湿慎"],
    "湿热质": ["湿热忌", "湿热盛"],
    "血瘀质": ["出血", "月经过多", "孕妇"],
    "气郁质": ["气滞", "气郁慎"],
    "特禀质": ["过敏"],
}


# 代茶饮 单味剂量范围 (grams). Spec §16.3 "代茶饮方案（轻症/日常）".
# Tea infusions use smaller doses than decoctions.
TEA_MIN_DOSE_G = 3
TEA_MAX_DOSE_G = 6
TEA_DEFAULT_DOSE_G = 3

# Harmonizer (使药) automatically added to tea recipes when available.
TEA_HARMONIZER = "甘草"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json_field(value: Any, default: Any) -> Any:
    """Parse a possibly-JSON-string field into a Python object."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return default
    return value if value is not None else default


def _herb_match_keywords(herb: dict[str, Any]) -> str:
    """Concatenate every searchable text field for a herb into one blob."""
    parts = [
        herb.get("name") or "",
        herb.get("aliases") or "",
        herb.get("efficacy") or "",
        herb.get("indications") or "",
        herb.get("category") or "",
    ]
    props = _parse_json_field(herb.get("properties"), {})
    if isinstance(props, dict):
        for k in ("pharmacologicalClass", "功效", "主治"):
            v = props.get(k)
            if isinstance(v, str):
                parts.append(v)
    return " ".join(parts)


def _constitution_boost(herb: dict[str, Any], constitution: str | None) -> tuple[int, str]:
    """Score boost for constitution-fit. Returns (boost_points, reason_zh)."""
    if not constitution:
        return 0, ""
    categories = CONSTITUTION_CATEGORY_MAP.get(constitution)
    if not categories:
        return 0, ""
    herb_cat = herb.get("category") or ""
    for i, kw in enumerate(categories):
        if kw and kw in herb_cat:
            # Earlier in the list = higher boost
            boost = max(1, 5 - i)
            return boost, f"体质匹配（{constitution}宜{kw}）"
    return 0, ""


def _constitution_excluded(herb: dict[str, Any], constitution: str | None) -> bool:
    """Return True if the herb is contraindicated for this constitution."""
    if not constitution:
        return False
    keywords = CONSTITUTION_CONTRA_KEYWORDS.get(constitution)
    if not keywords:
        return False
    contra = herb.get("contraindications") or ""
    return any(kw and kw in contra for kw in keywords)


def _symptom_score(herb: dict[str, Any], symptoms: list[str]) -> tuple[int, list[str]]:
    """Score how strongly a herb matches the given symptoms.

    Counts distinct symptom keywords found in the herb's searchable text.
    A match in ``indications`` counts double (clinical use), in ``efficacy``
    counts single, and in name/aliases counts as a strong hint.
    """
    if not symptoms:
        return 0, []
    name_blob = (herb.get("name") or "") + " " + (herb.get("aliases") or "")
    eff_blob = herb.get("efficacy") or ""
    ind_blob = herb.get("indications") or ""
    cat_blob = herb.get("category") or ""

    score = 0
    matched: list[str] = []
    for sym in symptoms:
        s = (sym or "").strip()
        if not s:
            continue
        hit = False
        if s in name_blob:
            score += 5
            hit = True
        if s in ind_blob:
            score += 3
            hit = True
        if s in eff_blob:
            score += 2
            hit = True
        if s in cat_blob:
            score += 1
            hit = True
        if hit:
            matched.append(s)
    return score, matched


def _tea_dose_g(herb: dict[str, Any]) -> int:
    """Compute a safe tea-infusion dose (g) for a herb.

    Strategy: start from the herb's minimum safe decoction dose, then clip into
    the tea range [3, 6]. Fall back to 3g when dosage info is missing.
    """
    dmin = herb.get("dosage_min_g")
    try:
        if dmin is not None:
            base = int(float(dmin))
        else:
            base = TEA_DEFAULT_DOSE_G
    except (TypeError, ValueError):
        base = TEA_DEFAULT_DOSE_G
    return max(TEA_MIN_DOSE_G, min(TEA_MAX_DOSE_G, base))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def recommend_herbs(
    db: DbAdapter,
    symptoms: list[str],
    constitution: str | None = None,
    exclude: list[str] | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Recommend herbs matching the given symptoms and constitution.

    Algorithm:
      1. Load every herb from the DB.
      2. Score each by symptom keyword hits + constitution category boost.
      3. Drop herbs in the user's ``exclude`` list (allergies / preferences).
      4. Drop herbs whose contraindications explicitly mention the constitution.
      5. Sort by score desc, take ``limit`` (default 10).
      6. Run the five-layer safety check across the top picks and surface any
         配伍禁忌 warnings.
      7. Always attach the safety disclaimer.

    Args:
        db: Database adapter.
        symptoms: Free-text symptom keywords, e.g. ``["气虚", "乏力"]``.
        constitution: One of ``NINE_CONSTITUTION_TYPES`` (Chinese), or None.
        exclude: Herb names to filter out (allergies / dislikes).
        limit: Max number of recommendations (clamped to 5-20).

    Returns:
        Dict with keys: ``recommendations`` (list), ``safety_check``
        (SafetyCheckResult as dict), ``disclaimer`` (str).
    """
    exclude_set = {n.strip() for n in (exclude or []) if n and n.strip()}
    limit = max(5, min(20, int(limit)))

    rows = await db.query(
        "SELECT * FROM herbs ORDER BY name"
    )

    scored: list[dict[str, Any]] = []
    for row in rows:
        name = row.get("name") or ""
        if not name or name in exclude_set:
            continue
        if _constitution_excluded(row, constitution):
            continue

        sym_score, matched = _symptom_score(row, symptoms)
        if sym_score == 0 and symptoms:
            # Symptoms were provided but this herb doesn't match any — skip.
            # (When symptoms list is empty, we still surface constitution picks.)
            continue

        const_boost, const_reason = _constitution_boost(row, constitution)
        total = sym_score + const_boost

        reasons: list[str] = []
        if matched:
            reasons.append(f"匹配症状：{'、'.join(matched)}")
        if const_reason:
            reasons.append(const_reason)
        if not reasons:
            reasons.append("综合推荐")

        scored.append({
            "id": row.get("id"),
            "name": name,
            "aliases": row.get("aliases") or "",
            "nature": row.get("nature") or "",
            "flavor": row.get("flavor") or "",
            "meridians": row.get("meridians") or "",
            "efficacy": row.get("efficacy") or "",
            "indications": row.get("indications") or "",
            "contraindications": row.get("contraindications") or "",
            "dosage_min_g": row.get("dosage_min_g"),
            "dosage_max_g": row.get("dosage_max_g"),
            "toxicity": row.get("toxicity") or "",
            "category": row.get("category") or "",
            "properties": _parse_json_field(row.get("properties"), {}),
            "score": total,
            "reason": "；".join(reasons),
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:limit]

    # Always run the five-layer safety check on the recommended set so
    # users see any 配伍禁忌 between picks before they combine them.
    top_names = [h["name"] for h in top]
    safety = await run_safety_check(db, herb_names=top_names)

    return {
        "recommendations": top,
        "symptoms": list(symptoms or []),
        "constitution": constitution,
        "safety_check": _safety_result_to_dict(safety),
        "disclaimer": DISCLAIMER,
    }


async def generate_tea_recipe(
    db: DbAdapter,
    symptoms: list[str],
    constitution: str | None = None,
    exclude: list[str] | None = None,
) -> dict[str, Any]:
    """Generate a 代茶饮 (tea infusion) recipe for the given symptoms.

    Picks 3-5 herbs from :func:`recommend_herbs`, assigns each a safe tea-range
    dose (typically 1/3 ~ 1/2 of the decoction minimum), optionally appends a
    使药 (envoy, e.g. 甘草) for harmonization, then runs the safety check on
    the final combination.

    Returns:
        Dict with: ``name`` (recipe title), ``herbs`` (list of
        ``{name, dose_g, role}``), ``brewing`` (instructions), ``efficacy``,
        ``safety_check``, ``disclaimer``.
    """
    rec = await recommend_herbs(
        db, symptoms=symptoms, constitution=constitution, exclude=exclude, limit=10
    )
    candidates = rec["recommendations"]

    # Aim for 3-5 herbs. Always include at least the top scorer.
    target = 4 if len(candidates) >= 4 else max(3, len(candidates))
    picked = candidates[:target]

    # Pad up to the 3-herb minimum (spec §16.3) when symptom matches are scarce.
    # Fall back to constitution-category herbs or, failing that, any non-toxic
    # herb from the knowledge base so the recipe is always usable.
    if len(picked) < 3:
        existing_names = {h["name"] for h in picked}
        exclude_set = {n.strip() for n in (exclude or []) if n and n.strip()}
        # First try constitution-category matches (no symptom requirement).
        fallback_rows = await db.query("SELECT * FROM herbs ORDER BY name")
        for row in fallback_rows:
            if len(picked) >= 3:
                break
            name = row.get("name") or ""
            if not name or name in existing_names or name in exclude_set:
                continue
            if _constitution_excluded(row, constitution):
                continue
            # Prefer herbs from the constitution's beneficial categories.
            boost, _ = _constitution_boost(row, constitution)
            if boost == 0 and constitution:
                continue  # keep filtering by constitution when one was specified
            picked.append({
                "id": row.get("id"),
                "name": name,
                "aliases": row.get("aliases") or "",
                "nature": row.get("nature") or "",
                "flavor": row.get("flavor") or "",
                "meridians": row.get("meridians") or "",
                "efficacy": row.get("efficacy") or "",
                "indications": row.get("indications") or "",
                "contraindications": row.get("contraindications") or "",
                "dosage_min_g": row.get("dosage_min_g"),
                "dosage_max_g": row.get("dosage_max_g"),
                "toxicity": row.get("toxicity") or "",
                "category": row.get("category") or "",
                "properties": _parse_json_field(row.get("properties"), {}),
                "score": 0,
                "reason": "配伍辅助（体质匹配）",
            })
            existing_names.add(name)
        # Last resort: any non-excluded herb (regardless of constitution).
        if len(picked) < 3:
            for row in fallback_rows:
                if len(picked) >= 3:
                    break
                name = row.get("name") or ""
                if not name or name in existing_names or name in exclude_set:
                    continue
                toxicity = (row.get("toxicity") or "").strip()
                if toxicity and toxicity != "无毒":
                    continue
                picked.append({
                    "id": row.get("id"),
                    "name": name,
                    "aliases": row.get("aliases") or "",
                    "nature": row.get("nature") or "",
                    "flavor": row.get("flavor") or "",
                    "meridians": row.get("meridians") or "",
                    "efficacy": row.get("efficacy") or "",
                    "indications": row.get("indications") or "",
                    "contraindications": row.get("contraindications") or "",
                    "dosage_min_g": row.get("dosage_min_g"),
                    "dosage_max_g": row.get("dosage_max_g"),
                    "toxicity": row.get("toxicity") or "",
                    "category": row.get("category") or "",
                    "properties": _parse_json_field(row.get("properties"), {}),
                    "score": 0,
                    "reason": "配伍辅助",
                })
                existing_names.add(name)

    # Append 甘草 (使药) if available and not already picked, for harmonization.
    picked_names = {h["name"] for h in picked}
    if TEA_HARMONIZER not in picked_names and len(picked) < 5:
        interaction_conflict = await db.query_one(
            """SELECT COUNT(*) AS c FROM safety_rules
               WHERE enabled = 1 AND rule_type = '中西药交互'
               AND drug_a IN (
                   SELECT name FROM medicines WHERE name IN (
                       SELECT drug_a FROM safety_rules WHERE drug_b = ? AND rule_type = '中西药交互'
                   )
               )""",
            (TEA_HARMONIZER,),
        )
        conflict_count = interaction_conflict["c"] if interaction_conflict else 0
        user_meds = exclude_set
        has_interaction_risk = any(
            med in {"降压药", "利尿药", "地高辛", "华法林"} for med in user_meds
        )
        if not has_interaction_risk:
            envoy = await db.query_one(
                "SELECT * FROM herbs WHERE name = ?", (TEA_HARMONIZER,)
            )
            if envoy and envoy["name"] not in picked_names:
                picked.append({
                "id": envoy.get("id"),
                "name": envoy["name"],
                "aliases": envoy.get("aliases") or "",
                "nature": envoy.get("nature") or "",
                "flavor": envoy.get("flavor") or "",
                "meridians": envoy.get("meridians") or "",
                "efficacy": envoy.get("efficacy") or "",
                "indications": envoy.get("indications") or "",
                "contraindications": envoy.get("contraindications") or "",
                "dosage_min_g": envoy.get("dosage_min_g"),
                "dosage_max_g": envoy.get("dosage_max_g"),
                "toxicity": envoy.get("toxicity") or "",
                "category": envoy.get("category") or "",
                "properties": _parse_json_field(envoy.get("properties"), {}),
                "score": 0,
                "reason": "使药，调和诸药",
            })

    # Build recipe herbs with doses + roles.
    recipe_herbs: list[dict[str, Any]] = []
    efficacies: list[str] = []
    non_envoy_idx = 0
    for h in picked:
        dose = _tea_dose_g(h)
        # 甘草 is conventionally 使 (envoy) regardless of position.
        if h["name"] == TEA_HARMONIZER:
            role = "使"
        elif non_envoy_idx == 0:
            role = "君"
            non_envoy_idx += 1
        elif non_envoy_idx == 1:
            role = "臣"
            non_envoy_idx += 1
        else:
            role = "佐"
            non_envoy_idx += 1
        recipe_herbs.append({
            "name": h["name"],
            "dose_g": dose,
            "role": role,
            "reason": h.get("reason", ""),
        })
        if h.get("efficacy"):
            efficacies.append(h["efficacy"])

    herb_names = [h["name"] for h in recipe_herbs]
    safety = await run_safety_check(db, herb_names=herb_names)

    symptom_label = "、".join(symptoms) if symptoms else "日常调理"
    recipe_name = f"{symptom_label}代茶饮"

    herbs_doses = "、".join(
        f"{h['name']}{h['dose_g']}g" for h in recipe_herbs
    )
    brewing = (
        f"1. 取 {herbs_doses}，用清水快速冲洗一遍。\n"
        f"2. 放入保温杯或茶壶，注入 500ml 沸水。\n"
        f"3. 加盖焖泡 10-15 分钟后温服。\n"
        f"4. 可反复冲泡 2-3 次，至味淡为止。\n"
        f"5. 每日 1 剂，建议饭后温服，连续饮用不宜超过 7 天。"
    )

    return {
        "name": recipe_name,
        "herbs": recipe_herbs,
        "brewing": brewing,
        "efficacy": "；".join(efficacies) if efficacies else "依证组合，调理为主",
        "symptoms": list(symptoms or []),
        "constitution": constitution,
        "safety_check": _safety_result_to_dict(safety),
        "disclaimer": DISCLAIMER,
    }


async def recommend_from_inventory(
    db: DbAdapter,
    symptoms: list[str],
    user_medicines: list[dict[str, Any]],
    exclude_expired: bool = True,
) -> dict[str, Any]:
    """Recommend OTC / herbal medicines already in the user's drug cabinet.

    For each medicine in the cabinet, scan its name + active_ingredients +
    herbal_fields (efficacy/indications) for matches against ``symptoms``.
    Expired items are excluded by default (spec §16.4: 配伍推荐自动排除).

    Returns:
        Dict with ``recommendations`` (list of dicts with ``medicine``,
        ``score``, ``reason``, ``in_inventory``=True), ``missing_suggestions``
        (herbs from the knowledge base that match but aren't in the cabinet),
        ``safety_check``, ``disclaimer``.
    """
    from datetime import datetime, timezone, timedelta

    CST = timezone(timedelta(hours=8))
    today = datetime.now(CST).strftime("%Y-%m-%d")

    recommendations: list[dict[str, Any]] = []
    rec_names: list[str] = []

    for med in user_medicines or []:
        name = med.get("name") or ""
        if not name:
            continue

        # Skip expired (spec §16.4).
        if exclude_expired:
            exp = (med.get("expiry_date") or "").strip()
            if exp and exp < today:
                continue
            props = _parse_json_field(med.get("properties"), {})
            if isinstance(props, dict) and props.get("deteriorated"):
                continue

        active = med.get("active_ingredients")
        if isinstance(active, str):
            try:
                active = json.loads(active)
            except (json.JSONDecodeError, TypeError):
                active = []
        active_blob = " ".join(active) if isinstance(active, list) else ""

        herbal = med.get("herbal_fields")
        if isinstance(herbal, str):
            try:
                herbal = json.loads(herbal)
            except (json.JSONDecodeError, TypeError):
                herbal = {}
        herbal_blob = ""
        if isinstance(herbal, dict):
            herbal_blob = " ".join(
                str(v) for v in herbal.values() if isinstance(v, (str, int, float))
            )

        contra_blob = med.get("contraindications") or ""

        score = 0
        matched: list[str] = []
        for sym in symptoms or []:
            s = (sym or "").strip()
            if not s:
                continue
            hit = False
            if s in name:
                score += 5
                hit = True
            if s in active_blob:
                score += 3
                hit = True
            if s in herbal_blob:
                score += 3
                hit = True
            if s in contra_blob:
                # If the symptom appears in contraindications, demote it.
                score -= 2
            if hit:
                matched.append(s)

        if score <= 0:
            continue

        recommendations.append({
            "medicine": {
                "id": med.get("id"),
                "name": name,
                "type": med.get("type") or "",
                "brand": med.get("brand"),
                "quantity": med.get("quantity", 0),
                "expiry_date": med.get("expiry_date"),
                "dosage_instructions": med.get("dosage_instructions") or "",
            },
            "score": score,
            "reason": f"药箱已有，匹配症状：{'、'.join(matched)}",
            "in_inventory": True,
        })
        # For safety check: 中成药/代茶饮 carry herb names, western drugs do not.
        # We pass the medicine name so Layer 1b can fire if relevant.
        rec_names.append(name)

    recommendations.sort(key=lambda x: x["score"], reverse=True)

    # Build "missing suggestions": herbs in the knowledge base that match the
    # symptoms but are not present in the user's inventory. This implements
    # spec §16.3 药箱优先逻辑 step 2 ("推荐必要性最高的缺失项").
    inventory_names = {r["medicine"]["name"] for r in recommendations}
    kb_match = await recommend_herbs(db, symptoms=symptoms, limit=5)
    missing: list[dict[str, Any]] = []
    for h in kb_match["recommendations"]:
        if h["name"] in inventory_names:
            continue
        missing.append({
            "name": h["name"],
            "category": h.get("category") or "",
            "efficacy": h.get("efficacy") or "",
            "reason": h.get("reason") or "",
            "suggestion": "建议购入" + h["name"] + "（"
                          + (h.get("category") or "中药") + "，"
                          + (h.get("efficacy") or "调理用")[:30] + "）",
        })

    # Safety check across combined recommendations (medicines + suggested herbs).
    suggested_herb_names = [m["name"] for m in missing[:3]]
    safety = await run_safety_check(
        db,
        herb_names=suggested_herb_names,
        medicine_names=rec_names,
    )

    return {
        "recommendations": recommendations,
        "missing_suggestions": missing,
        "symptoms": list(symptoms or []),
        "safety_check": _safety_result_to_dict(safety),
        "disclaimer": DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# Internal: serialize SafetyCheckResult
# ---------------------------------------------------------------------------

def _safety_result_to_dict(result: SafetyCheckResult) -> dict[str, Any]:
    """Convert a SafetyCheckResult dataclass into a JSON-friendly dict."""
    return {
        "safe": result.safe,
        "warnings": [
            {
                "layer": w.layer,
                "severity": w.severity,
                "title": w.title,
                "detail": w.detail,
                "herbs": list(w.herbs),
                "action": w.action,
                "source": w.source,
            }
            for w in result.warnings
        ],
        "checked_herbs": list(result.checked_herbs),
        "checked_medicines": list(result.checked_medicines),
        "unknown_herbs": list(result.unknown_herbs),
        "unknown_medicines": list(result.unknown_medicines),
    }
