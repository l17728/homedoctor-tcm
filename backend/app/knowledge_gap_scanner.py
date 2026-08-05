"""Universal knowledge gap scanner — comprehensive one-click inspection.

Scans ALL entity types for incomplete content, identifies specific missing
fields per type, and fills gaps using web search + LLM processing.

Key design principles:
- Per-type completion templates (what "complete" means for each entity type)
- Smart gap detection (field-level, not just "is it empty")
- Merge into existing entities (UPDATE, not INSERT — avoids duplication)
- LLM autonomy (LLM can adjust search queries and prompts)
- "Just enough" filling (only fills missing fields, never overwrites existing)
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.database import DbAdapter

logger = logging.getLogger(__name__)

ENTITY_COMPLETION_TEMPLATES: dict[str, dict[str, Any]] = {
    "herb": {
        "required_fields": [
            "nature", "flavor", "meridian", "dosage_min_g", "dosage_max_g",
            "efficacy", "contraindications",
        ],
        "min_completeness": 60,
        "search_template": "中药 {title} 性味 归经 功效 用量 禁忌 中医药典",
        "llm_prompt": (
            "请补充中药【{title}】的以下缺失信息：{missing_fields}。\n"
            "基于《中药学》教材和中国药典，只返回缺失字段的JSON。\n"
            "格式：{{\"field1\": \"value1\", ...}}"
        ),
    },
    "acupoint": {
        "required_fields": [
            "location", "needling", "moxibustion", "functions",
            "indications", "meridian",
        ],
        "min_completeness": 50,
        "search_template": "穴位 {title} 定位 针刺方法 灸法 主治功效 经络",
        "llm_prompt": (
            "请补充穴位【{title}】的以下缺失信息：{missing_fields}。\n"
            "参考《针灸学》教材标准定位和刺法。只返回缺失字段的JSON。\n"
            "格式：{{\"field1\": \"value1\", ...}}"
        ),
    },
    "meridian": {
        "required_fields": [
            "organ", "point_count", "common_indications", "route_description",
        ],
        "min_completeness": 50,
        "search_template": "经络 {title} 循行路线 主治病候 穴位数目 中医经络",
        "llm_prompt": (
            "请补充经络【{title}】的以下缺失信息：{missing_fields}。\n"
            "参考《经络学》教材。只返回缺失字段的JSON。\n"
            "格式：{{\"field1\": \"value1\", ...}}"
        ),
    },
    "formula": {
        "required_fields": [
            "composition", "usage", "indications", "contraindications",
        ],
        "min_completeness": 60,
        "search_template": "方剂 {title} 组成用法 君臣佐使 主治 禁忌 方剂学",
        "llm_prompt": (
            "请补充方剂【{title}】的以下缺失信息：{missing_fields}。\n"
            "参考《方剂学》教材。只返回缺失字段的JSON。\n"
            "格式：{{\"field1\": \"value1\", ...}}"
        ),
    },
    "therapy": {
        "required_fields": [
            "description", "indications", "contraindications",
        ],
        "min_completeness": 50,
        "search_template": "中医外治法 {title} 操作方法 适应症 禁忌症",
        "llm_prompt": (
            "请补充外治理疗【{title}】的以下缺失信息：{missing_fields}。\n"
            "参考《中医外科学》和操作规范。只返回缺失字段的JSON。\n"
            "格式：{{\"field1\": \"value1\", ...}}"
        ),
    },
    "health_practice": {
        "required_fields": [
            "essence", "steps", "benefits", "contraindications",
        ],
        "min_completeness": 50,
        "search_template": "养生功法 {title} 功理 心法 步骤 功效 禁忌",
        "llm_prompt": (
            "请补充养生功法【{title}】的以下缺失信息：{missing_fields}。\n"
            "参考中医养生学和传统功法文献。只返回缺失字段的JSON。\n"
            "格式：{{\"field1\": \"value1\", ...}}"
        ),
    },
}

DEFAULT_TEMPLATE: dict[str, Any] = {
    "required_fields": ["summary"],
    "min_completeness": 50,
    "search_template": "{title} {entity_type} 中医 详细介绍",
    "llm_prompt": (
        "请补充【{title}】的以下缺失信息：{missing_fields}。\n"
        "只返回缺失字段的JSON。格式：{{\"field1\": \"value1\", ...}}"
    ),
}


def _get_template(entity_type: str) -> dict[str, Any]:
    return ENTITY_COMPLETION_TEMPLATES.get(entity_type, DEFAULT_TEMPLATE)


def _parse_properties(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def _check_field_value(val: Any) -> bool:
    if val is None:
        return False
    if isinstance(val, str) and val.strip() == "":
        return False
    if isinstance(val, (list, dict)) and len(val) == 0:
        return False
    return True


def detect_entity_gaps(
    entity: dict[str, Any],
    entity_type: str,
) -> dict[str, Any]:
    """Check a single entity for missing fields based on its type template.

    Returns {"completeness": float, "missing_fields": [str], "present_fields": [str]}.
    """
    template = _get_template(entity_type)
    required = template["required_fields"]
    props = _parse_properties(entity.get("properties"))

    present: list[str] = []
    missing: list[str] = []
    for field in required:
        val = props.get(field)
        if _check_field_value(val):
            present.append(field)
        else:
            missing.append(field)

    total = len(required)
    completeness = round(len(present) / total * 100, 1) if total > 0 else 100.0

    return {
        "completeness": completeness,
        "missing_fields": missing,
        "present_fields": present,
    }


async def scan_all_gaps(
    db: DbAdapter,
    entity_types: list[str] | None = None,
    min_completeness: float | None = None,
    limit_per_type: int = 20,
) -> dict[str, Any]:
    """Scan all entity types for content gaps.

    Returns per-type summary + prioritized gap list.
    """
    if entity_types is None:
        entity_types = list(ENTITY_COMPLETION_TEMPLATES.keys())

    all_rows = await db.query(
        """SELECT id, entity_type, title, summary, properties, category, view_count
           FROM knowledge_entities
           WHERE status = 'active'
           ORDER BY view_count ASC"""
    )

    type_summary: dict[str, dict[str, Any]] = {}
    gaps: list[dict[str, Any]] = []

    for row in all_rows:
        etype = row.get("entity_type", "")
        if etype not in entity_types:
            continue

        template = _get_template(etype)
        threshold = min_completeness or template["min_completeness"]

        analysis = detect_entity_gaps(row, etype)
        if analysis["completeness"] >= threshold:
            continue

        type_summary.setdefault(etype, {"total": 0, "gaps": 0, "avg_completeness": []})
        type_summary[etype]["total"] += 1
        type_summary[etype]["gaps"] += 1
        type_summary[etype]["avg_completeness"].append(analysis["completeness"])

        gaps.append({
            "entity_id": row["id"],
            "entity_type": etype,
            "title": row.get("title", ""),
            "completeness": analysis["completeness"],
            "missing_fields": analysis["missing_fields"],
            "category": row.get("category"),
        })

    for etype, summary in type_summary.items():
        avg = summary["avg_completeness"]
        summary["avg_completeness"] = round(sum(avg) / len(avg), 1) if avg else 0
        del summary["avg_completeness"]  # remove list, keep float

    gaps.sort(key=lambda g: g["completeness"])

    for etype in entity_types:
        if etype not in type_summary:
            type_summary[etype] = {"total": 0, "gaps": 0, "avg_completeness": 100.0}

    return {
        "type_summary": type_summary,
        "total_gaps": len(gaps),
        "gaps": gaps[:limit_per_type * len(entity_types)],
    }


def _build_search_query(title: str, missing_fields: list[str], entity_type: str) -> str:
    template = _get_template(entity_type)
    return template["search_template"].format(
        title=title,
        entity_type=entity_type,
        missing_fields=" ".join(missing_fields),
    )


def _build_llm_prompt(title: str, missing_fields: list[str], entity_type: str,
                      web_context: str = "") -> str:
    template = _get_template(entity_type)
    prompt = template["llm_prompt"].format(
        title=title,
        missing_fields="、".join(missing_fields),
        entity_type=entity_type,
    )
    if web_context:
        prompt += f"\n\n参考网络资料：\n{web_context[:1000]}"
    prompt += "\n\n重要：只返回缺失字段的JSON，不要返回已存在的字段。保持简洁准确。"
    return prompt


def _deep_merge(existing: dict[str, Any], additions: dict[str, Any]) -> dict[str, Any]:
    """Merge additions into existing properties without overwriting present fields."""
    merged = dict(existing)
    for key, new_val in additions.items():
        if not _check_field_value(new_val):
            continue
        old_val = merged.get(key)
        if _check_field_value(old_val):
            if isinstance(old_val, list) and isinstance(new_val, list):
                for item in new_val:
                    if item not in old_val:
                        old_val.append(item)
            continue
        merged[key] = new_val
    return merged


async def _try_web_search(query: str, num: int = 2) -> str:
    """Search web for context. Returns empty string if unavailable."""
    import os
    api_key = os.environ.get("WEB_SEARCH_API_KEY", "")
    if not api_key:
        return ""

    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.exa.ai/search",
                json={"query": query, "numResults": num, "type": "neural"},
                headers={"x-api-key": api_key},
            )
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                texts = []
                for r in results[:2]:
                    text = r.get("text") or r.get("summary") or ""
                    if text:
                        texts.append(text[:500])
                return "\n".join(texts)
    except Exception as exc:
        logger.debug("web search failed: %s", exc)

    return ""


async def fill_entity_gap(
    db: DbAdapter,
    entity: dict[str, Any],
    missing_fields: list[str],
    entity_type: str,
) -> dict[str, Any]:
    """Fill a single entity's missing fields using LLM (+ optional web search).

    Returns {"entity_id": str, "filled_fields": [...], "skipped": bool, "reason": str}.
    """
    entity_id = entity["entity_id"]
    title = entity["title"]

    search_query = _build_search_query(title, missing_fields, entity_type)
    web_context = await _try_web_search(search_query)

    prompt = _build_llm_prompt(title, missing_fields, entity_type, web_context)

    try:
        from app.llm_unified import llm_chat
        reply = await llm_chat(db, [{"role": "user", "content": prompt}])
    except Exception as exc:
        logger.warning("gap_fill LLM call failed for %s: %s", title, exc)
        return {"entity_id": entity_id, "filled_fields": [], "skipped": True, "reason": str(exc)[:80]}

    if not reply or not reply.strip():
        return {"entity_id": entity_id, "filled_fields": [], "skipped": True, "reason": "LLM返回空"}

    from app.json_extractor import extract_json
    additions = extract_json(reply)

    if not isinstance(additions, dict) or not additions:
        return {"entity_id": entity_id, "filled_fields": [], "skipped": True, "reason": "无法解析JSON"}

    cleaned: dict[str, Any] = {}
    for field in missing_fields:
        if field in additions and _check_field_value(additions[field]):
            cleaned[field] = additions[field]

    if not cleaned:
        return {"entity_id": entity_id, "filled_fields": [], "skipped": True, "reason": "无有效新增字段"}

    row = await db.query_one(
        "SELECT properties FROM knowledge_entities WHERE id = ?", (entity_id,)
    )
    if not row:
        return {"entity_id": entity_id, "filled_fields": [], "skipped": True, "reason": "实体不存在"}

    existing_props = _parse_properties(row.get("properties"))
    merged = _deep_merge(existing_props, cleaned)

    await db.execute(
        "UPDATE knowledge_entities SET properties = ?, updated_at = datetime('now') WHERE id = ?",
        (json.dumps(merged, ensure_ascii=False), entity_id),
    )

    filled_keys = list(cleaned.keys())

    try:
        from app.agent_tools import log_action
        await log_action(
            db, "gap_fill", entity_type, title, entity_id,
            {"filled_fields": filled_keys, "fields_before": len(existing_props),
             "fields_after": len(merged)},
            "filled",
        )
    except Exception:
        pass

    logger.info("gap_fill: %s/%s filled %d fields: %s",
                entity_type, title, len(filled_keys), filled_keys)

    return {"entity_id": entity_id, "title": title, "type": entity_type,
            "filled_fields": filled_keys, "skipped": False}


async def run_comprehensive_scan(
    db: DbAdapter,
    max_fills: int = 50,
    entity_types: list[str] | None = None,
) -> dict[str, Any]:
    """One-click comprehensive knowledge inspection + filling.

    Flow:
      1. Scan all entity types for gaps
      2. Sort by completeness (lowest first)
      3. Fill top N gaps using web search + LLM
      4. Return summary

    This is the main entry point for the "一键巡检" feature.
    """
    logger.info("comprehensive_scan: starting (max_fills=%d)", max_fills)

    scan_result = await scan_all_gaps(db, entity_types=entity_types, limit_per_type=max_fills)
    gaps = scan_result["gaps"][:max_fills]

    filled: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[str] = []

    for i, gap in enumerate(gaps):
        try:
            result = await fill_entity_gap(db, gap, gap["missing_fields"], gap["entity_type"])
            if result.get("skipped"):
                skipped.append(result)
            else:
                filled.append(result)
        except Exception as exc:
            errors.append(f"{gap['title']}: {str(exc)[:60]}")
            logger.warning("gap_fill error for %s: %s", gap.get("title"), exc)

    summary = {
        "scanned_types": list(scan_result["type_summary"].keys()),
        "type_summary": scan_result["type_summary"],
        "total_gaps_found": scan_result["total_gaps"],
        "processed": len(gaps),
        "filled_count": len(filled),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "filled": filled,
        "skipped_details": skipped[:10],
        "errors": errors[:5],
    }

    logger.info("comprehensive_scan: done — %d filled, %d skipped, %d errors",
                len(filled), len(skipped), len(errors))

    return summary
