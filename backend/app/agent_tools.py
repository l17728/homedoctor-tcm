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
    """Step 2: LLM analysis — entity type, keywords, summary, structured fields.

    Extracts type-specific structured properties:
      health_practice: steps/breathing/mental_focus/key_points/indications/cautions
      herb: nature/flavor/meridians/dosage/contraindications/toxicity
      acupoint: location/needling/moxibustion/specific_point/functions
      formula: composition/modifications/efficacy
    """
    if not text.strip():
        return {"entity_type": "article", "keywords": [], "summary": "", "structured_fields": {}, "decision": "skipped"}

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

    structured_fields = await _extract_structured_fields(text, title, entity_type)

    result = {
        "entity_type": entity_type,
        "keywords": keywords,
        "summary": summary,
        "category": category,
        "structured_fields": structured_fields,
    }
    await log_action(db, "analyze", source_type, title, "",
                     {k: v for k, v in result.items() if k != "structured_fields"}, "analyzed")
    return result


async def _extract_structured_fields(text: str, title: str, entity_type: str) -> dict[str, Any]:
    """Extract type-specific structured fields from content via LLM."""
    from app.llm import chat_completion, has_api_key

    field_templates: dict[str, dict[str, str]] = {
        "health_practice": {
            "core_essence": "功法精要（1-2句核心原理）",
            "breathing": "呼吸要点",
            "mental_focus": "心法要诀",
            "key_points": "关键要点（JSON数组）",
            "indications": "养生功效（JSON数组）",
            "cautions": "注意事项",
            "duration_minutes": "建议练习时长",
            "best_time": "最佳练习时间",
            "difficulty": "难度（入门/进阶/高级）",
        },
        "herb": {
            "nature": "性（寒/凉/平/温/热+修饰）",
            "flavor": "味（甘/苦/辛/酸/咸等）",
            "meridians": "归经",
            "efficacy": "功效",
            "indications": "主治（JSON数组）",
            "contraindications": "禁忌",
            "dosage_min_g": "最小用量(g)",
            "dosage_max_g": "最大用量(g)",
            "toxicity": "毒性",
        },
        "acupoint": {
            "location": "定位（解剖位置描述）",
            "needling": "刺法",
            "moxibustion": "灸法",
            "functions": "功效（JSON数组）",
            "indications": "主治（JSON数组）",
            "combinations": "常见配伍",
            "specific_point": "特定穴类别",
        },
        "formula": {
            "composition": "组成药物",
            "efficacy": "功用",
            "indications": "主治",
            "modifications": "加减变化",
        },
        "therapy": {
            "technique": "操作方法",
            "indications": "适应症（JSON数组）",
            "frequency": "治疗频次",
            "duration": "每次时长",
            "caution": "注意事项",
        },
    }

    template = field_templates.get(entity_type)
    if not template or not has_api_key():
        return {}

    fields_desc = "\n".join(f'  "{k}": "{v}"' for k, v in template.items())
    prompt = f"""请从以下内容中提取结构化信息。

标题：{title}
内容：{text[:2000]}

请提取以下字段（如果内容中未提及则留空）：
{{
{fields_desc}
}}

只返回JSON，不要其他文字。"""

    try:
        response = await chat_completion([{"role": "user", "content": prompt}])
        import re
        match = re.search(r'\{[^}]+\}', response, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            return {k: v for k, v in parsed.items() if v and str(v).strip()}
    except Exception as exc:
        logger.warning("agent_tools: structured field extraction failed: %s", exc)

    return {}


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
    """Step 4: Check for duplicates — title exact match only (not fuzzy).

    BM25 fuzzy matching was too aggressive (merged "真气运行法" into "站桩"
    because both are health_practice with overlapping keywords). Now only
    exact title match triggers merge. Fuzzy matches are returned as
    'related' candidates but NOT used for merge.
    """
    exact = await db.query(
        "SELECT id, title, entity_type, summary FROM knowledge_entities "
        "WHERE title = ? AND status = 'active' LIMIT 3",
        (title,),
    )
    candidates = list(exact)

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


async def tool_index_external_content(
    db: DbAdapter,
    raw_text: str,
    source_url: str,
    title: str,
    entity_id: str,
) -> dict[str, Any]:
    """Index external content (article URL) without storing the full text.

    Chunks the original text and stores each chunk in knowledge_chunks with
    source_type='external' and source_url set. Generates BGE-M3 embeddings.
    BM25 and semantic search naturally cover these chunks — one unified index.
    """
    from app.chunker import chunk_text, estimate_tokens
    from app.embedding import get_embedding_model
    from app.vector_store import store_embedding

    existing = await db.query(
        "SELECT id FROM knowledge_chunks WHERE source_url = ? LIMIT 1",
        (source_url,),
    )
    if existing:
        await log_action(db, "index_external", "url", source_url, entity_id,
                         {"skipped": "already_indexed"}, "skipped")
        return {"chunks": 0, "embedded": 0, "decision": "already_indexed"}

    chunks = chunk_text(raw_text, max_tokens=512, overlap=50)
    model = get_embedding_model()
    embedded = 0
    chunk_ids: list[str] = []
    chunk_texts: list[str] = []

    for cd in chunks:
        cid = f"ext-chunk-{uuid.uuid4()}"
        chunk_ids.append(cid)
        chunk_texts.append(cd["text"])
        ext_summary = cd["text"][:80].replace("\n", " ").strip()
        if len(cd["text"]) > 80:
            ext_summary += "..."
        await db.execute(
            """INSERT INTO knowledge_chunks
               (id, entity_id, chunk_index, chunk_text, chunk_type,
                hierarchy_path, hierarchy_level, token_count, metadata,
                source_url, source_type, text_summary)
               VALUES (?, ?, ?, ?, 'external', ?, ?, ?, ?, ?, 'external', ?)""",
            (
                cid, entity_id, cd["index"], cd["text"],
                cd.get("hierarchy_path", ""), cd.get("hierarchy_level", 0),
                cd.get("token_count", estimate_tokens(cd["text"])),
                json.dumps({"source_url": source_url, "source_title": title}, ensure_ascii=False),
                source_url,
                ext_summary,
            ),
        )

    if model.available and chunk_texts:
        vectors = model.embed(chunk_texts)
        if vectors:
            for cid, vec in zip(chunk_ids, vectors):
                await store_embedding(db, cid, vec)
            embedded = len(vectors)

    await log_action(db, "index_external", "url", source_url, entity_id,
                     {"chunks": len(chunks), "embedded": embedded, "title": title},
                     "indexed")
    return {"chunks": len(chunks), "embedded": embedded, "decision": "indexed"}


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


# ---------------------------------------------------------------------------
# Trust & Provenance tools (Phase 1 additions)
# ---------------------------------------------------------------------------


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
    reviews: list[dict[str, Any]] = []

    for model in models[:3]:
        text = await call_model_direct(model, messages)
        if text:
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
            return json.loads(json_match.group())
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
        except Exception:
            pass

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
    """Delete a knowledge entity and its chunks/embeddings. Requires confirm=True."""
    if not confirm:
        return {"deleted": False, "message": "需要 confirm=True 才能执行删除"}
    await db.execute("DELETE FROM chunk_embeddings WHERE chunk_id IN (SELECT id FROM knowledge_chunks WHERE entity_id = ?)", (entity_id,))
    await db.execute("DELETE FROM knowledge_chunks WHERE entity_id = ?", (entity_id,))
    await db.execute("DELETE FROM entity_relationships WHERE source_entity_id = ? OR target_entity_id = ?", (entity_id, entity_id))
    await db.execute("DELETE FROM knowledge_provenance WHERE entity_id = ?", (entity_id,))
    cursor = await db.execute("DELETE FROM knowledge_entities WHERE id = ?", (entity_id,))
    await log_action(db, "delete_entity", "manual", "", entity_id, {"confirmed": True}, "deleted" if cursor.rowcount > 0 else "not_found")
    return {"deleted": cursor.rowcount > 0, "entity_id": entity_id}


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


async def tool_query_logs(
    db: DbAdapter,
    entity_id: str | None = None,
    action_type: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Query agent processing logs (self-history introspection)."""
    conditions = []
    params: list[Any] = []
    if entity_id:
        conditions.append("entity_id = ?")
        params.append(entity_id)
    if action_type:
        conditions.append("action_type = ?")
        params.append(action_type)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await db.query(
        f"SELECT * FROM agent_logs {where} ORDER BY created_at DESC LIMIT ?",
        tuple(params + [limit]),
    )
    return [dict(r) for r in rows]


async def tool_optimize_prompt(
    db: DbAdapter, agent_name: str, current_prompt: str,
) -> dict[str, Any]:
    """Analyze own prompt + memories, suggest optimizations."""
    from app.llm_unified import llm_chat
    from app.agent_memory import memory_search
    from app.json_extractor import extract_json

    lessons = await memory_search(db, agent_name, memory_type="lesson", min_confidence=0.6, limit=10)

    prompt = f"""你是{agent_name}。请审视你的系统提示词和最近的教训，提出优化建议。

当前提示词：
{current_prompt[:1000]}

最近的教训（高置信度）：
{chr(10).join(f'- {m["content"][:80]}' for m in lessons) if lessons else '无'}

请分析：
1. 哪些教训应该融入提示词？
2. 提示词中哪些规则可以被简化？
3. 是否有新规则应该添加？

返回JSON：{{"additions": [...], "deletions": [...], "modifications": [...]}}"""

    reply = await llm_chat(db, [{"role": "user", "content": prompt}])
    suggestions = extract_json(reply)

    await memory_save_tool(db, agent_name,
        f"提示词优化建议：{json.dumps(suggestions, ensure_ascii=False)[:200] if isinstance(suggestions, dict) else reply[:200]}",
        "experience", confidence=0.6)

    return suggestions if isinstance(suggestions, dict) else {"raw_suggestions": reply[:500]}


async def tool_generalize_experience(
    db: DbAdapter, agent_name: str, case_description: str,
) -> dict[str, Any]:
    """Extract a generalizable pattern from a specific case."""
    from app.llm_unified import llm_chat
    from app.json_extractor import extract_json

    prompt = f"""从以下具体处理案例中，提取通用规则：

案例：{case_description}

请提取：
1. 这属于哪类问题？
2. 适用的通用解决方案是什么？
3. 下次遇到类似问题应该怎么做？

返回JSON：{{"problem_type": "...", "pattern": "...", "strategy": "..."}}"""

    reply = await llm_chat(db, [{"role": "user", "content": prompt}])
    result = extract_json(reply)

    if isinstance(result, dict):
        await memory_save_tool(db, agent_name,
            f"通用模式[{result.get('problem_type', '')}]：{result.get('strategy', '')}",
            "pattern", confidence=0.7)

    return result if isinstance(result, dict) else {"raw": reply[:500]}


async def memory_save_tool(db: DbAdapter, agent_name: str, content: str,
                           memory_type: str = "experience", confidence: float = 0.5) -> str:
    """Wrapper for agent_memory.memory_save (tool interface)."""
    from app.agent_memory import memory_save
    return await memory_save(db, agent_name, content, memory_type, confidence=confidence)
