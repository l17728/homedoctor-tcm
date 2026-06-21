"""Knowledge agent — autonomous 8-step knowledge extraction pipeline.

Treats ALL inputs (URL, text, chat, file) as knowledge sources and
automatically: extracts → analyzes → scans → deduplicates → quality-checks
→ creates/merges → indexes → pushes to modules.

Every step is logged to agent_logs for full audit trail.
The pipeline is resilient: any step failure is caught, logged, and
the pipeline continues with degraded behavior.

Usage:
    from app.knowledge_agent import process_input
    result = await process_input(db, url="https://example.com/article")
    result = await process_input(db, content="黄芪补气升阳...")
    result = await process_input(db, content=chat_summary, source_type="chat")
"""

from __future__ import annotations

import logging
from typing import Any

from app.database import DbAdapter
from app.agent_tools import (
    log_action,
    tool_assess_quality,
    tool_build_index,
    tool_check_duplicates,
    tool_create_or_update_entity,
    tool_extract,
    tool_analyze,
    tool_push_to_modules,
    tool_scan_entities,
)

logger = logging.getLogger(__name__)


async def process_input(
    db: DbAdapter,
    content: str = "",
    url: str = "",
    title: str = "",
    source_type: str = "text",
) -> dict[str, Any]:
    """Run the full 8-step autonomous knowledge processing pipeline.

    Returns a summary dict with entity_id, decision, and log_count.
    Never raises — all errors are caught and logged.
    """
    pipeline_log_id = await log_action(
        db, "pipeline_start", source_type, url or title, "",
        {"content_len": len(content), "url": url, "title": title},
        "started",
    )

    try:
        # Step 1: Extract
        extracted = await tool_extract(db, content=content, url=url, source_type=source_type)
        raw_text = extracted["text"]
        if extracted.get("decision") == "skipped_empty":
            return _result(None, "skipped_empty", "内容为空", pipeline_log_id)
        if not title:
            title = extracted.get("title", "") or _guess_title(raw_text)

        # Step 2: Analyze
        analysis = await tool_analyze(db, raw_text, title, source_type)
        entity_type = analysis.get("entity_type", "article")
        keywords = analysis.get("keywords", [])
        summary = analysis.get("summary", raw_text[:200])

        # Step 2b: Dynamic category classification
        from app.category_classifier import classify_category
        try:
            cat_result = await classify_category(
                db, title, summary, entity_type, raw_text[:500],
            )
            category = cat_result.get("category", analysis.get("category", ""))
            if cat_result.get("is_new"):
                logger.info(
                    "knowledge_agent: new category '%s' created for '%s' (%s)",
                    category, title, entity_type,
                )
        except Exception as exc:
            logger.warning("knowledge_agent: category classification failed: %s", exc)
            category = analysis.get("category", "")

        # Step 3: Scan for known entities
        mentions = await tool_scan_entities(db, raw_text)

        # Step 4: Check duplicates
        duplicates = await tool_check_duplicates(db, title, raw_text)

        # Step 5: Quality assessment + multi-AI review
        quality = await tool_assess_quality(db, raw_text, entity_type)
        if quality.get("decision") == "rejected":
            await log_action(
                db, "pipeline_end", source_type, url or title, "",
                {"reason": "quality_rejected", "score": quality.get("score", 0)},
                "rejected",
            )
            return _result(None, "rejected", f"质量评分过低({quality.get('score', 0)})", pipeline_log_id)

        review_result = {"score": quality.get("score", 50), "level": "B", "decision": "pending_review"}
        try:
            from app.agent_tools import tool_multi_model_review
            review_result = await tool_multi_model_review(
                db, title, raw_text[:2000], entity_type, url,
            )
        except Exception as exc:
            logger.warning("knowledge_agent: multi-model review failed: %s", exc)

        # Step 5b: Conflict detection
        conflicts: list = []
        if duplicates:
            from app.agent_tools import tool_detect_conflicts
            try:
                conflicts = await tool_detect_conflicts(
                    db, duplicates[0].get("id") or duplicates[0].get("entity_id", ""),
                    _build_properties(raw_text, analysis, mentions, source_type, url),
                )
            except Exception:
                pass

        # Step 6: Create or merge entity
        properties = _build_properties(raw_text, analysis, mentions, source_type, url)
        if conflicts:
            for c in conflicts:
                resolution = c.get("resolution", {})
                if isinstance(resolution, dict) and "keep" in resolution:
                    properties[c["field"]] = resolution["keep"]
        create_result = await tool_create_or_update_entity(
            db,
            entity_type=entity_type,
            title=title,
            summary=summary,
            properties=properties,
            keywords=keywords,
            category=category,
            source_type=source_type,
            duplicates=duplicates,
        )
        entity_id = create_result.get("entity_id", "")
        decision = create_result.get("decision", "unknown")

        # Step 6b: Record provenance (blood lineage)
        if entity_id:
            from app.agent_tools import tool_record_provenance
            try:
                await tool_record_provenance(
                    db, entity_id, source_type, url, title,
                    trust_level=review_result.get("level", "B"),
                    trust_score=review_result.get("score", 50),
                    review_details={"reviews": review_result.get("reviews", []),
                                   "conflicts": len(conflicts)},
                    content_date="",
                )
            except Exception as exc:
                logger.warning("knowledge_agent: provenance recording failed: %s", exc)

        # Step 7: Incremental index (internal entity + external content)
        if entity_id:
            await tool_build_index(db, entity_id)
            if url and raw_text and len(raw_text) > 200:
                from app.agent_tools import tool_index_external_content
                await tool_index_external_content(
                    db, raw_text, url, title, entity_id,
                )

        # Step 7b: Auto-relate to existing entities (universal — all types)
        relations_created: list = []
        if entity_id:
            from app.agent_tools import tool_auto_relate
            try:
                relations_created = await tool_auto_relate(
                    db, entity_id, entity_type, title, summary, raw_text[:500],
                )
            except Exception as exc:
                logger.warning("knowledge_agent: auto_relate failed: %s", exc)

        # Step 8: Push to modules
        if entity_id:
            pushed = await tool_push_to_modules(db, entity_id, entity_type)
        else:
            pushed = []

        await log_action(
            db, "pipeline_end", source_type, url or title, entity_id,
            {
                "entity_type": entity_type,
                "decision": decision,
                "quality_score": quality.get("score", 0),
                "duplicates_found": len(duplicates),
                "mentions_found": len(mentions),
                "modules_pushed": pushed,
            },
            decision,
        )

        return _result(entity_id, decision, f"处理完成: {entity_type}/{title}", pipeline_log_id, {
            "entity_type": entity_type,
            "quality_score": quality.get("score", 0),
            "duplicates": len(duplicates),
            "mentions": len(mentions),
            "pushed": pushed,
        })

    except Exception as exc:
        logger.error("knowledge_agent: pipeline failed: %s", exc, exc_info=True)
        await log_action(
            db, "pipeline_error", source_type, url or title, "",
            {"error": str(exc)}, "failed",
        )
        return _result(None, "failed", str(exc), pipeline_log_id)


def _guess_title(text: str) -> str:
    """Guess a title from the first meaningful line of text."""
    for line in text.split("\n"):
        stripped = line.strip().lstrip("#").strip()
        if len(stripped) >= 2 and len(stripped) <= 50:
            return stripped
    return text[:20].strip() or "未命名"


def _build_properties(
    raw_text: str,
    analysis: dict[str, Any],
    mentions: list[dict[str, Any]],
    source_type: str,
    url: str,
) -> dict[str, Any]:
    """Build properties JSON from analysis + structured fields."""
    props: dict[str, Any] = {
        "source_type": source_type,
        "content_length": len(raw_text),
    }
    if url:
        props["source_url"] = url
    if analysis.get("category"):
        props["category"] = analysis["category"]
    if analysis.get("keywords"):
        props["ai_keywords"] = analysis["keywords"]

    structured = analysis.get("structured_fields", {})
    if structured:
        props.update(structured)

    if mentions:
        props["related_entities"] = [
            {"name": m.get("name"), "type": m.get("type")}
            for m in mentions[:10]
        ]
    return props


def _result(
    entity_id: str | None,
    decision: str,
    message: str,
    pipeline_log_id: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "entity_id": entity_id,
        "decision": decision,
        "message": message,
        "pipeline_log_id": pipeline_log_id,
    }
    if extra:
        result.update(extra)
    return result
