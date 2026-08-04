from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from app.database import DbAdapter

logger = logging.getLogger(__name__)

__all__ = [
    "tool_record_provenance",
    "tool_generate_summary",
    "tool_auto_relate",
    "tool_delete_entity",
    "tool_create_relationship",
    "tool_delete_relationship",
    "tool_list_entity_types",
    "tool_list_categories",
]

async def tool_record_provenance(
    db: DbAdapter,
    entity_id: str,
    source_type: str,
    source_url: str = "",
    source_title: str = "",
    trust_level: str = "C",
    trust_score: float = 0,
    review_details: dict[str, Any] | None = None,
    imported_by: str = "",
    content_date: str = "",
) -> str:
    """Record knowledge provenance (blood lineage)."""
    from app.trust_engine import record_provenance
    pid = await record_provenance(
        db, entity_id, source_type, source_url, source_title,
        trust_level, trust_score, review_details, imported_by, content_date,
    )
    from app.agent_tools import log_action

    await log_action(db, "provenance", source_type, source_url, entity_id,
                     {"trust_level": trust_level, "trust_score": trust_score,
                      "provenance_id": pid},
                     "recorded")
    return pid


def tool_generate_summary(chunk_text: str) -> str:
    """Generate human-readable summary for a binary embedding vector."""
    summary = chunk_text[:80].replace("\n", " ").strip()
    if len(chunk_text) > 80:
        summary += "..."
    return summary


async def tool_auto_relate(
    db: DbAdapter,
    entity_id: str,
    entity_type: str,
    title: str,
    summary: str,
    content: str = "",
    max_relations: int = 5,
) -> list[dict[str, Any]]:
    """Automatically discover and create relationships to existing entities.

    Searches for entities of the same type or complementary types,
    uses BM25 + category matching to find candidates, and creates
    'related_to' relationships. Universal — works for all entity types.

    Example: "真气运行法" imported → auto-relates to "打坐", "站桩", "气功"
    """
    search_query = f"{title} {summary[:50]}"
    if content:
        search_query += f" {content[:100]}"

    same_type_rows = await db.query(
        """SELECT id, title, summary, category FROM knowledge_entities
            WHERE entity_type = ? AND id != ? AND status = 'active'
            ORDER BY view_count DESC LIMIT 20""",
        (entity_type, entity_id),
    )

    scored: list[tuple[dict, float, str]] = []
    for r in same_type_rows:
        score = _relation_score(title, summary, r.get("title", ""), r.get("summary", ""))
        if score > 0:
            reason = f"同类功法：{r['title']}"
            scored.append((r, score, reason))

    cross_type_map = {
        "health_practice": ["meridian", "symptom", "therapy"],
        "herb": ["formula", "symptom", "acupoint"],
        "formula": ["herb", "symptom"],
        "acupoint": ["meridian", "symptom"],
        "therapy": ["symptom", "acupoint"],
    }

    for related_type in cross_type_map.get(entity_type, []):
        cross_rows = await db.query(
            """SELECT id, title, summary FROM knowledge_entities
                WHERE entity_type = ? AND status = 'active' LIMIT 10""",
            (related_type,),
        )
        for r in cross_rows:
            score = _relation_score(title, summary, r.get("title", ""), r.get("summary", ""))
            if score > 0.3:
                scored.append((r, score * 0.7, f"跨类关联：{related_type}/{r['title']}"))

    scored.sort(key=lambda x: x[1], reverse=True)

    created: list[dict[str, Any]] = []
    for r, score, reason in scored[:max_relations]:
        rel_id = f"rel-auto-{uuid.uuid4()}"
        try:
            await db.execute(
                """INSERT OR IGNORE INTO entity_relationships
                   (id, source_entity_id, target_entity_id, relationship_type,
                    properties, weight)
                   VALUES (?, ?, ?, 'related_to', ?, ?)""",
                (rel_id, entity_id, r["id"],
                 json.dumps({"reason": reason, "auto_generated": True, "score": round(score, 2)},
                            ensure_ascii=False),
                 round(score, 2)),
            )
            created.append({"target_id": r["id"], "target_title": r["title"], "reason": reason})
        except Exception as exc:
            logger.warning("auto_relate item failed: %s", exc)

    from app.agent_tools import log_action


    await log_action(db, "auto_relate", "auto", "", entity_id,
                     {"relations_created": len(created),
                      "targets": [{"title": c["target_title"], "reason": c["reason"]} for c in created]},
                     "related" if created else "no_relations")
    return created


def _relation_score(title_a: str, summary_a: str, title_b: str, summary_b: str) -> float:
    """Heuristic relevance score between two entities (0-1)."""
    text_a = f"{title_a} {summary_a}"
    text_b = f"{title_b} {summary_b}"

    score = 0.0

    concept_keywords = [
        "气", "血", "丹田", "呼吸", "经", "络", "穴", "阴", "阳", "虚", "实",
        "补", "泻", "寒", "热", "温", "凉", "湿", "风", "痰", "火",
        "脾", "胃", "肝", "肾", "心", "肺", "胆", "大肠", "小肠", "膀胱",
        "太极", "八段", "五禽", "易筋", "六字", "导引", "吐纳", "站桩", "打坐",
        "静坐", "冥想", "禅修", "内丹", "周天", "真气", "元气", "宗气", "营卫",
        "功法", "修炼", "养生", "保健", "调理", "疏通", "强壮",
        "针刺", "艾灸", "推拿", "拔罐", "刮痧", "刺血",
        "黄芪", "人参", "当归", "甘草", "白术", "茯苓",
    ]

    shared_concepts = []
    for kw in concept_keywords:
        if kw in text_a and kw in text_b:
            score += 0.08
            shared_concepts.append(kw)

    for i in range(min(len(title_a), len(title_b), 3)):
        if title_a[i] == title_b[i]:
            score += 0.05

    words_a = set(_extract_words(text_a))
    words_b = set(_extract_words(text_b))
    overlap = words_a & words_b
    if words_a and words_b:
        jaccard = len(overlap) / max(len(words_a | words_b), 1)
        score += jaccard * 0.3

    return min(score, 1.0)


def _extract_words(text: str) -> list[str]:
    """Extract 2-char bigrams from Chinese text."""
    return [text[i:i+2] for i in range(len(text) - 1) if len(text) >= 2]


# ---------------------------------------------------------------------------
# CRUD completion tools (Delete + Relationship management + Metadata)
# ---------------------------------------------------------------------------


async def tool_delete_entity(db: DbAdapter, entity_id: str, confirm: bool = False) -> dict[str, Any]:
    """Delete a knowledge entity and its chunks/embeddings. Requires confirm=True.
    S-level (system authoritative) entities cannot be deleted."""
    if not confirm:
        return {"deleted": False, "message": "需要 confirm=True 才能执行删除"}

    from app.trust_engine import get_trust_level
    trust = await get_trust_level(db, entity_id)
    if trust == "S":
        return {"deleted": False, "message": "S级系统知识不可删除，请先降级或申请豁免"}

    await db.execute("DELETE FROM knowledge_conflicts WHERE entity_id = ?", (entity_id,))
    await db.execute("DELETE FROM knowledge_feedback WHERE entity_id = ?", (entity_id,))
    await db.execute("DELETE FROM user_notes WHERE entity_id = ?", (entity_id,))
    await db.execute("DELETE FROM chunk_embeddings WHERE chunk_id IN (SELECT id FROM knowledge_chunks WHERE entity_id = ?)", (entity_id,))
    await db.execute("DELETE FROM knowledge_chunks WHERE entity_id = ?", (entity_id,))
    await db.execute("DELETE FROM entity_relationships WHERE source_entity_id = ? OR target_entity_id = ?", (entity_id, entity_id))
    await db.execute("DELETE FROM knowledge_provenance WHERE entity_id = ?", (entity_id,))
    cursor = await db.execute("DELETE FROM knowledge_entities WHERE id = ?", (entity_id,))
    from app.agent_tools import log_action

    await log_action(db, "delete_entity", "manual", "", entity_id, {"confirmed": True, "trust_level": trust}, "deleted" if cursor.rowcount > 0 else "not_found")
    return {"deleted": cursor.rowcount > 0, "entity_id": entity_id, "trust_level": trust}


async def tool_create_relationship(
    db: DbAdapter, source_id: str, target_id: str,
    rel_type: str, properties: dict[str, Any] | None = None,
) -> str:
    """Create a specific relationship between two entities."""
    rid = f"rel-manual-{uuid.uuid4()}"
    await db.execute(
        """INSERT OR IGNORE INTO entity_relationships
           (id, source_entity_id, target_entity_id, relationship_type, properties, weight)
           VALUES (?, ?, ?, ?, ?, 1.0)""",
        (rid, source_id, target_id, rel_type,
         json.dumps(properties or {}, ensure_ascii=False)),
    )
    return rid


async def tool_delete_relationship(db: DbAdapter, relationship_id: str) -> bool:
    """Delete a specific relationship."""
    cursor = await db.execute("DELETE FROM entity_relationships WHERE id = ?", (relationship_id,))
    return cursor.rowcount > 0


async def tool_list_entity_types(db: DbAdapter) -> list[dict[str, Any]]:
    """List all entity types with counts (meta-data self-introspection)."""
    rows = await db.query(
        """SELECT entity_type, COUNT(*) as count
           FROM knowledge_entities WHERE status = 'active'
           GROUP BY entity_type ORDER BY count DESC"""
    )
    return [{"type": r["entity_type"], "count": r["count"]} for r in rows]


async def tool_list_categories(db: DbAdapter, entity_type: str | None = None) -> list[dict[str, Any]]:
    """List all categories, optionally filtered by entity type."""
    if entity_type:
        rows = await db.query(
            """SELECT category, COUNT(*) as count FROM knowledge_entities
               WHERE status = 'active' AND entity_type = ? AND category IS NOT NULL AND category != ''
               GROUP BY category ORDER BY count DESC""",
            (entity_type,),
        )
    else:
        rows = await db.query(
            """SELECT category, entity_type, COUNT(*) as count FROM knowledge_entities
               WHERE status = 'active' AND category IS NOT NULL AND category != ''
               GROUP BY category, entity_type ORDER BY count DESC"""
        )
    return [dict(r) for r in rows]
