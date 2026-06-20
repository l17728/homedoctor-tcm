"""Agent tools — 10 atomic functions for the autonomous knowledge pipeline.

Each tool is self-contained: takes inputs, returns structured output, logs
to agent_logs. Tools can be freely composed by the knowledge_agent pipeline.

Design: all tools are async, fail gracefully (never raise), and write
audit entries for every action.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from app.database import DbAdapter

logger = logging.getLogger(__name__)


async def log_action(
    db: DbAdapter,
    action_type: str,
    source_type: str = "",
    source_ref: str = "",
    entity_id: str = "",
    details: dict[str, Any] | None = None,
    decision: str = "",
) -> str:
    """Write an audit entry to agent_logs."""
    log_id = f"log-{uuid.uuid4()}"
    try:
        await db.execute(
            """INSERT INTO agent_logs (id, action_type, source_type, source_ref,
               entity_id, details, decision)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                log_id, action_type, source_type, source_ref,
                entity_id,
                json.dumps(details or {}, ensure_ascii=False),
                decision,
            ),
        )
    except Exception as exc:
        logger.warning("agent_tools: log_action failed: %s", exc)
    return log_id


async def tool_extract(db: DbAdapter, content: str = "", url: str = "",
                       source_type: str = "text") -> dict[str, Any]:
    """Step 1: Extract raw content from URL or text input."""
    raw_text = content
    title = ""
    images: list[str] = []

    if url and not content:
        try:
            from app.knowledge_parser import parse_url
            result = await parse_url(url)
            raw_text = result.sections_text if hasattr(result, "sections_text") else ""
            if not raw_text and result.sections:
                raw_text = "\n\n".join(
                    s.get("text", "") for s in result.sections if isinstance(s, dict)
                )
            title = result.metadata.get("title", "") if result.metadata else ""
            source_type = "url"
        except Exception as exc:
            logger.warning("agent_tools: extract URL failed: %s", exc)
            raw_text = ""

    if not raw_text or not raw_text.strip():
        await log_action(db, "extract", source_type, url or title, "",
                         {"error": "empty content"}, "skipped")
        return {"text": "", "title": title, "images": [], "decision": "skipped_empty"}

    await log_action(db, "extract", source_type, url or title, "",
                     {"chars": len(raw_text), "title": title}, "extracted")
    return {"text": raw_text, "title": title, "images": images, "decision": "extracted"}


async def tool_analyze(db: DbAdapter, text: str, title: str = "",
                       source_type: str = "text") -> dict[str, Any]:
    """Step 2: LLM analysis — recommend entity type, extract keywords."""
    if not text.strip():
        return {"entity_type": "article", "keywords": [], "summary": "", "decision": "skipped"}

    try:
        from app.knowledge_entity import _call_llm_for_analysis
        analysis = await _call_llm_for_analysis(title or "未命名", text[:2000])
        entity_type = analysis.get("entity_type", "article")
        keywords = analysis.get("keywords", [])
        summary = analysis.get("summary", "")
        category = analysis.get("category", "")
    except Exception as exc:
        logger.warning("agent_tools: LLM analyze failed: %s", exc)
        entity_type = "article"
        keywords = []
        summary = text[:200]
        category = ""

    result = {
        "entity_type": entity_type,
        "keywords": keywords,
        "summary": summary,
        "category": category,
    }
    await log_action(db, "analyze", source_type, title, "",
                     result, "analyzed")
    return result


async def tool_scan_entities(db: DbAdapter, text: str) -> list[dict[str, Any]]:
    """Step 3: Scan text for mentions of known entities."""
    try:
        from app.entity_filter import get_entity_index
        index = await get_entity_index(db)
        mentions = index.scan(text)
        await log_action(db, "scan", "text", "", "",
                         {"found": len(mentions), "names": [m.get("name") for m in mentions[:10]]},
                         "scanned")
        return mentions
    except Exception as exc:
        logger.warning("agent_tools: scan failed: %s", exc)
        return []


async def tool_check_duplicates(db: DbAdapter, title: str,
                                content: str, top_k: int = 5) -> list[dict[str, Any]]:
    """Step 4: Check for duplicates via title exact match + BM25 similarity."""
    exact = await db.query(
        "SELECT id, title, entity_type, summary FROM knowledge_entities "
        "WHERE title = ? AND status = 'active' LIMIT 3",
        (title,),
    )
    candidates = list(exact)

    if len(candidates) < top_k and content.strip():
        try:
            from app.search_pipeline import bm25_search
            bm25_results = await bm25_search(db, title or content[:50], top_k=top_k)
            seen_ids = {c["id"] for c in candidates}
            for r in bm25_results:
                if r.get("entity_id") and r["entity_id"] not in seen_ids:
                    candidates.append(r)
                    seen_ids.add(r["entity_id"])
        except Exception:
            pass

    await log_action(db, "dedup", "text", title, "",
                     {"exact_matches": len(exact), "total_candidates": len(candidates)},
                     "duplicate" if exact else "unique")
    return candidates[:top_k]


async def tool_assess_quality(db: DbAdapter, content: str,
                              entity_type: str = "article") -> dict[str, Any]:
    """Step 5: Quality assessment — score 0-100."""
    if not content.strip():
        return {"score": 0, "decision": "rejected", "reason": "empty"}

    score = 50
    reason = "default"

    text_len = len(content)
    if text_len > 500:
        score += 15
        reason = "substantial_content"
    if text_len > 2000:
        score += 10
        reason = "comprehensive"

    has_chinese = any('\u4e00' <= ch <= '\u9fff' for ch in content[:200])
    if has_chinese:
        score += 10
        reason = "chinese_content"

    if entity_type in ("herb", "formula", "acupoint", "meridian"):
        score += 15
        reason = "specialized_knowledge"

    score = min(score, 100)

    if score >= 80:
        decision = "auto_adopted"
    elif score >= 50:
        decision = "pending_review"
    else:
        decision = "rejected"

    result = {"score": score, "decision": decision, "reason": reason}
    await log_action(db, "quality", "text", "", "",
                     result, decision)
    return result


async def tool_create_or_update_entity(
    db: DbAdapter,
    entity_type: str,
    title: str,
    summary: str,
    properties: dict[str, Any],
    keywords: list[str] | None = None,
    category: str = "",
    source_type: str = "agent",
    duplicates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Step 6: Create new entity or merge into existing duplicate."""
    from app.knowledge_entity import register_entity
    import json as json_mod

    if duplicates:
        existing = duplicates[0]
        eid = existing.get("id") or existing.get("entity_id")
        if eid:
            current = await db.query_one(
                "SELECT properties, summary FROM knowledge_entities WHERE id = ?", (eid,)
            )
            if current:
                current_props = {}
                if isinstance(current.get("properties"), str):
                    try:
                        current_props = json_mod.loads(current["properties"])
                    except Exception:
                        current_props = {}
                elif isinstance(current.get("properties"), dict):
                    current_props = current["properties"]

                merged = {**current_props, **properties}
                merged_summary = summary if len(summary) > len(current.get("summary") or "") else current.get("summary", "")

                await db.execute(
                    "UPDATE knowledge_entities SET properties = ?, summary = ?, "
                    "updated_at = datetime('now') WHERE id = ?",
                    (json_mod.dumps(merged, ensure_ascii=False), merged_summary, eid),
                )
                await log_action(db, "update", source_type, title, eid,
                                 {"merged_fields": list(properties.keys())}, "merged")
                return {"entity_id": eid, "decision": "merged"}

    eid = await register_entity(
        db,
        entity_type=entity_type,
        source_table=source_type,
        source_id=f"agent:{title}",
        title=title,
        summary=summary,
        keywords=keywords or [],
        tags=[],
        category=category or "",
        content_preview="",
        properties=properties,
        source_type=source_type,
    )
    await log_action(db, "create", source_type, title, eid,
                     {"type": entity_type, "title": title}, "created")
    return {"entity_id": eid, "decision": "created"}


async def tool_build_index(db: DbAdapter, entity_id: str) -> dict[str, Any]:
    """Step 7: Incremental RAG indexing for a single entity."""
    try:
        from app.index_manager import build_index_for_entity
        result = await build_index_for_entity(db, entity_id)
        await log_action(db, "index", "auto", "", entity_id,
                         {"chunks": result.get("chunks", 0),
                          "embedded": result.get("embedded", 0)},
                         "indexed")
        return result
    except Exception as exc:
        logger.warning("agent_tools: build_index failed: %s", exc)
        await log_action(db, "index", "auto", "", entity_id,
                         {"error": str(exc)}, "failed")
        return {"chunks": 0, "embedded": 0, "error": str(exc)}


async def tool_push_to_modules(db: DbAdapter, entity_id: str,
                               entity_type: str = "") -> list[str]:
    """Step 8: Check which modules should be notified of new/updated knowledge."""
    pushed: list[str] = []

    if not entity_type:
        row = await db.query_one(
            "SELECT entity_type FROM knowledge_entities WHERE id = ?", (entity_id,)
        )
        if row:
            entity_type = row.get("entity_type", "")

    module_map = {
        "herb": ["safety_engine", "formulation_engine", "herbs_page"],
        "formula": ["formulation_engine", "formulas_page"],
        "acupoint": ["acupoints_page", "meridian_graph"],
        "meridian": ["acupoints_page", "meridian_graph"],
        "therapy": ["therapies_page"],
        "symptom": ["safety_engine", "triage_engine"],
        "health_practice": ["practice_page", "constitution_engine"],
    }

    targets = module_map.get(entity_type, [])
    pushed = targets

    await log_action(db, "push", "auto", "", entity_id,
                     {"entity_type": entity_type, "modules": targets},
                     "pushed" if targets else "no_targets")
    return pushed
