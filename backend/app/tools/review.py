from __future__ import annotations

import json
import logging
from typing import Any

from app.database import DbAdapter

logger = logging.getLogger(__name__)

__all__ = [
    "tool_multi_model_review",
    "tool_detect_conflicts",
]

async def tool_multi_model_review(
    db: DbAdapter,
    title: str,
    content: str,
    entity_type: str = "article",
    source_url: str = "",
) -> dict[str, Any]:
    """Multi-AI expert panel review — 3 models vote on accuracy/safety.

    Returns trust score (0-100), trust level (S/A/B/C), and decision.
    """
    from app.trust_engine import calculate_trust_score, get_domain_trust, record_provenance
    from app.model_registry import get_default_models, call_model_direct

    models = await get_default_models(db, "text")
    if not models:
        return {"score": 50, "level": "B", "decision": "pending_review",
                "reviews": [], "reason": "no_models_configured"}

    prompt = f"""你是一位中医药学专家，请评审以下知识的准确性和安全性。

知识标题：{title}
知识内容：{content[:1500]}
知识类型：{entity_type}
来源：{source_url or '未知'}

请从以下维度评分（0-100）：
1. medical_accuracy：内容是否符合中医理论和现代药理研究？
2. completeness：关键信息是否完整（性味/归经/用量/禁忌等）？
3. source_reliability：来源是否权威可信？

请返回JSON：{{"medical_accuracy": N, "completeness": N, "source_reliability": N, "recommendation": "adopt"/"review"/"reject", "reason": "..."}}
"""

    messages = [{"role": "user", "content": prompt}]
    selected = models[:3]

    import asyncio as _aio
    tasks = [call_model_direct(m, messages) for m in selected]
    raw_texts = await _aio.gather(*tasks, return_exceptions=True)

    reviews: list[dict[str, Any]] = []
    for text in raw_texts:
        if isinstance(text, str) and text:
            parsed = _parse_review_json(text)
            if parsed:
                reviews.append(parsed)

    result = calculate_trust_score(reviews)
    result["reviews"] = reviews
    return result


def _parse_review_json(raw: str) -> dict[str, Any]:
    """Extract JSON from LLM review response."""
    if not raw:
        return {}
    import re
    text = raw.strip()
    from app.json_extractor import extract_json
    parsed = extract_json(text)
    if parsed:
        try:
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"recommendation": "review", "reason": raw[:200]}


async def tool_detect_conflicts(
    db: DbAdapter,
    entity_id: str,
    new_properties: dict[str, Any],
) -> list[dict[str, Any]]:
    """Detect conflicts between new and existing entity properties."""
    from app.json_utils import parse_json

    CONFLICT_FIELDS = {
        "dosage_min_g": "数值冲突",
        "dosage_max_g": "数值冲突",
        "nature": "属性冲突",
        "toxicity": "属性冲突",
        "contraindications": "禁忌冲突",
    }

    existing = await db.query_one(
        "SELECT properties FROM knowledge_entities WHERE id = ?", (entity_id,)
    )
    if not existing:
        return []

    existing_props = parse_json(existing.get("properties"), {})
    conflicts: list[dict[str, Any]] = []

    for field, conflict_type in CONFLICT_FIELDS.items():
        old_val = existing_props.get(field)
        new_val = new_properties.get(field)
        if old_val is not None and new_val is not None and str(old_val) != str(new_val):
            resolution = _resolve_conflict(field, old_val, new_val)
            conflicts.append({
                "field": field,
                "type": conflict_type,
                "existing": old_val,
                "incoming": new_val,
                "resolution": resolution,
            })
            import uuid
            await db.execute(
                """INSERT OR IGNORE INTO knowledge_conflicts
                   (id, entity_id, field, conflict_type, existing_value, incoming_value, resolution)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (f"conflict-{uuid.uuid4()}", entity_id, field, conflict_type,
                 str(old_val), str(new_val), json.dumps(resolution, ensure_ascii=False)),
            )

    if conflicts:
        from app.agent_tools import log_action

        await log_action(db, "conflict_detect", "auto", "", entity_id,
                         {"conflicts": len(conflicts), "fields": [c["field"] for c in conflicts]},
                         "conflicts_found" if conflicts else "no_conflicts")

    return conflicts


def _resolve_conflict(field: str, old_val: Any, new_val: Any) -> dict[str, Any]:
    """Resolve a conflict — keep conservative/safer value for safety fields."""
    if field in ("dosage_min_g", "dosage_max_g"):
        try:
            old_f = float(old_val)
            new_f = float(new_val)
            if "min" in field:
                return {"keep": max(old_f, new_f), "reason": "安全引擎取保守值（较高下限）"}
            else:
                return {"keep": min(old_f, new_f), "reason": "安全引擎取保守值（较低上限）"}
        except (ValueError, TypeError):
            pass
    return {"keep": old_val, "reason": "保留高信任等级知识，新值存为'异说'"}


