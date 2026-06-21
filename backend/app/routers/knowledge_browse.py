"""Knowledge augmentation router — category browsing + append content flow.

The "追加" (append) feature lets users request content augmentation for any
existing knowledge entity. The agent then:
  1. Searches internal knowledge for what already exists
  2. Searches external index for relevant content
  3. Optionally does Web Search (with user confirmation)
  4. Synthesizes new content from all sources via multi-model consensus
  5. Submits through expert panel review (same trust pipeline as imports)
  6. On approval, appends/updates the entity properties

Supports multiple iterations — user can submit append requests repeatedly.

Endpoints:
  GET  /api/knowledge/categories              — list all categories with counts
  GET  /api/knowledge/browse                  — browse by category/type
  POST /api/knowledge/{id}/append             — request content augmentation
  GET  /api/knowledge/{id}/append/history     — view append request history
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.database import DbAdapter, get_db

router = APIRouter(prefix="/api/knowledge", tags=["knowledge-browse"])


class AppendRequest(BaseModel):
    instruction: str = Field(..., description="用户指示：想追加什么内容")
    auto_web_search: bool = Field(True, description="是否允许Agent自动Web Search补全")


# ---------------------------------------------------------------------------
# Category browsing
# ---------------------------------------------------------------------------

@router.get("/categories")
async def list_categories(
    db: DbAdapter = Depends(get_db),
) -> dict[str, Any]:
    """List all entity types and categories with counts."""
    type_rows = await db.query(
        """SELECT entity_type, COUNT(*) AS count
             FROM knowledge_entities
            WHERE status = 'active'
            GROUP BY entity_type
            ORDER BY count DESC"""
    )

    cat_rows = await db.query(
        """SELECT category, COUNT(*) AS count, entity_type
             FROM knowledge_entities
            WHERE status = 'active' AND category IS NOT NULL AND category != ''
            GROUP BY category, entity_type
            ORDER BY count DESC"""
    )

    type_labels = {
        "herb": "中药", "formula": "方剂", "acupoint": "穴位",
        "meridian": "经络", "therapy": "疗法", "symptom": "症状",
        "health_practice": "养生功法", "practice_school": "门派",
        "article": "文章", "person": "个人",
    }

    types = []
    for r in type_rows:
        types.append({
            "type": r["entity_type"],
            "label": type_labels.get(r["entity_type"], r["entity_type"]),
            "count": r["count"],
        })

    categories_by_type: dict[str, list] = {}
    for r in cat_rows:
        et = r["entity_type"]
        if et not in categories_by_type:
            categories_by_type[et] = []
        categories_by_type[et].append({
            "category": r["category"],
            "count": r["count"],
        })

    return {"types": types, "categories": categories_by_type}


@router.get("/browse")
async def browse(
    type: str = Query(..., description="实体类型"),
    category: str | None = Query(None, description="分类筛选"),
    q: str | None = Query(None, description="关键词搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: DbAdapter = Depends(get_db),
) -> dict[str, Any]:
    """Browse knowledge entities by type and/or category."""
    conditions = ["entity_type = ?", "status = 'active'"]
    params: list[Any] = [type]

    if category:
        conditions.append("category = ?")
        params.append(category)

    if q:
        conditions.append("(title LIKE ? OR summary LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like])

    where = " AND ".join(conditions)
    offset = (page - 1) * page_size

    count_row = await db.query_one(
        f"SELECT COUNT(*) AS c FROM knowledge_entities WHERE {where}", tuple(params)
    )
    total = count_row["c"] if count_row else 0

    rows = await db.query(
        f"""SELECT id, title, summary, category, properties, view_count,
                  (SELECT trust_level FROM knowledge_provenance
                   WHERE entity_id = knowledge_entities.id
                   ORDER BY imported_at DESC LIMIT 1) AS trust_level,
                  (SELECT trust_score FROM knowledge_provenance
                   WHERE entity_id = knowledge_entities.id
                   ORDER BY imported_at DESC LIMIT 1) AS trust_score
             FROM knowledge_entities
            WHERE {where}
            ORDER BY view_count DESC, title ASC
            LIMIT ? OFFSET ?""",
        tuple(params + [page_size, offset]),
    )

    items = []
    for r in rows:
        props = r.get("properties")
        if isinstance(props, str):
            try:
                props = json.loads(props)
            except (json.JSONDecodeError, TypeError):
                props = {}
        items.append({
            "id": r["id"],
            "title": r["title"],
            "summary": r.get("summary") or "",
            "category": r.get("category") or "",
            "view_count": r.get("view_count", 0),
            "trust_level": r.get("trust_level") or "S",
            "trust_score": r.get("trust_score") or 0,
            "properties": props if isinstance(props, dict) else {},
        })

    return {"items": items, "total": total, "page": page, "page_size": page_size}


# ---------------------------------------------------------------------------
# Knowledge append (augmentation) flow
# ---------------------------------------------------------------------------

@router.post("/{entity_id}/append")
async def request_append(
    entity_id: str,
    body: AppendRequest,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Request content augmentation for an existing knowledge entity.

    The agent will:
    1. Read current entity state (what's already there)
    2. Search internal knowledge for related content
    3. Search external index for relevant articles
    4. Optionally Web Search for additional info
    5. Synthesize new content via multi-model consensus
    6. Submit through expert panel review
    7. On approval, merge into entity properties
    """
    entity = await db.query_one(
        "SELECT id, title, entity_type, summary, properties, category FROM knowledge_entities WHERE id = ?",
        (entity_id,),
    )
    if not entity:
        raise HTTPException(status_code=404, detail="知识实体不存在")

    import uuid
    request_id = f"append-{uuid.uuid4()}"

    await _log_append_request(db, request_id, entity_id, current_user["id"], body.instruction, "started")

    current_props = _parse_json_safe(entity.get("properties"), {})

    internal_findings = await _search_internal_for_augmentation(
        db, entity["title"], entity["entity_type"], body.instruction
    )

    external_findings = await _search_external_for_augmentation(
        db, entity["title"], body.instruction
    )

    web_findings: list[dict] = []
    if body.auto_web_search and not internal_findings and not external_findings:
        web_findings = await _web_search_for_augmentation(entity["title"], body.instruction)

    synthesized = await _synthesize_augmentation(
        db, entity, current_props, body.instruction,
        internal_findings, external_findings, web_findings,
    )

    review_result = {"score": 50, "level": "B", "decision": "pending_review"}
    try:
        from app.agent_tools import tool_multi_model_review
        review_result = await tool_multi_model_review(
            db, f"追加内容: {entity['title']}",
            synthesized.get("new_content", "")[:2000],
            entity["entity_type"],
        )
    except Exception:
        pass

    if review_result.get("decision") == "adopted":
        from app.trust_engine import get_trust_level
        entity_trust = await get_trust_level(db, entity_id)
        if entity_trust == "S":
            review_result["decision"] = "pending_review"
            review_result["level"] = "B"
            review_result["score"] = min(review_result.get("score", 50), 79)
        else:
            merged_props = {**current_props, **synthesized.get("new_fields", {})}
            merged_summary = synthesized.get("new_summary") or entity.get("summary", "")

            if len(merged_summary) > len(entity.get("summary") or ""):
                await db.execute(
                    "UPDATE knowledge_entities SET properties = ?, summary = ?, updated_at = datetime('now') WHERE id = ?",
                    (json.dumps(merged_props, ensure_ascii=False), merged_summary, entity_id),
                )

            from app.agent_tools import tool_build_index, tool_record_provenance
            await tool_build_index(db, entity_id)
            await tool_record_provenance(
                db, entity_id, "append", "", body.instruction[:100],
                trust_level=review_result.get("level", "B"),
                trust_score=review_result.get("score", 50),
                imported_by=current_user.get("id", ""),
            )

    from app.agent_tools import log_action
    await log_action(
        db, "append_complete", "augmentation", body.instruction, entity_id,
        {
            "request_id": request_id,
            "internal_sources": len(internal_findings),
            "external_sources": len(external_findings),
            "web_sources": len(web_findings),
            "new_fields": list(synthesized.get("new_fields", {}).keys()),
            "trust_score": review_result.get("score", 0),
            "trust_level": review_result.get("level", "B"),
            "decision": review_result.get("decision", "pending_review"),
        },
        review_result.get("decision", "pending_review"),
    )

    await _update_append_request(db, request_id, "completed", {
        "synthesized_preview": synthesized.get("new_content", "")[:200],
        "review": review_result,
    })

    return {
        "request_id": request_id,
        "entity_id": entity_id,
        "entity_title": entity["title"],
        "decision": review_result.get("decision", "pending_review"),
        "trust_level": review_result.get("level", "B"),
        "trust_score": review_result.get("score", 0),
        "sources_gathered": {
            "internal": len(internal_findings),
            "external": len(external_findings),
            "web": len(web_findings),
        },
        "new_fields": list(synthesized.get("new_fields", {}).keys()),
        "synthesized_preview": synthesized.get("new_content", "")[:300],
        "message": _build_result_message(review_result, synthesized),
    }


@router.get("/{entity_id}/append/history")
async def append_history(
    entity_id: str,
    db: DbAdapter = Depends(get_db),
    _: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """View append request history for an entity."""
    rows = await db.query(
        """SELECT * FROM agent_logs
            WHERE entity_id = ? AND action_type IN ('append_start', 'append_complete')
            ORDER BY created_at DESC LIMIT 20""",
        (entity_id,),
    )
    return {"items": [_format_log(r) for r in rows], "total": len(rows)}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _search_internal_for_augmentation(
    db: DbAdapter, title: str, entity_type: str, instruction: str
) -> list[dict]:
    """Search internal knowledge for content related to the augmentation request."""
    from app.search_pipeline import bm25_search
    query = f"{title} {instruction}"
    results = await bm25_search(db, query, top_k=5)
    return [r for r in results if r.get("entity_id") and r["title"] != title]


async def _search_external_for_augmentation(
    db: DbAdapter, title: str, instruction: str
) -> list[dict]:
    """Search external index for relevant content."""
    rows = await db.query(
        """SELECT kc.chunk_text, kc.source_url, kc.entity_id
             FROM knowledge_chunks kc
            WHERE kc.source_type = 'external'
              AND (kc.chunk_text LIKE ? OR kc.chunk_text LIKE ?)
            LIMIT 5""",
        (f"%{title}%", f"%{instruction[:20]}%"),
    )
    return [dict(r) for r in rows]


async def _web_search_for_augmentation(title: str, instruction: str) -> list[dict]:
    """Web Search for additional content."""
    from app.routers.smart_search import _web_search
    return await _web_search(f"{title} {instruction}", 3)


async def _synthesize_augmentation(
    db: DbAdapter,
    entity: dict,
    current_props: dict,
    instruction: str,
    internal: list,
    external: list,
    web: list,
) -> dict[str, Any]:
    """Use LLM to synthesize new content from all gathered sources."""
    from app.llm import chat_completion, has_api_key

    if not has_api_key():
        return {"new_content": "", "new_fields": {}, "new_summary": ""}

    context_parts = [
        f"当前实体：{entity['title']}（{entity['entity_type']}）",
        f"当前摘要：{entity.get('summary', '')}",
        f"当前属性：{json.dumps(current_props, ensure_ascii=False)[:500]}",
        f"用户请求追加：{instruction}",
    ]

    if internal:
        context_parts.append(f"内部相关知识：{json.dumps([{'title': r.get('title'), 'summary': r.get('summary', '')[:100]} for r in internal[:3]], ensure_ascii=False)}")

    if external:
        context_parts.append(f"外部索引内容：{json.dumps([{'text': r.get('chunk_text', '')[:150], 'url': r.get('source_url')} for r in external[:3]], ensure_ascii=False)}")

    if web:
        context_parts.append(f"Web搜索结果：{json.dumps([{'title': r.get('title'), 'summary': r.get('summary', '')[:100], 'url': r.get('url')} for r in web[:3]], ensure_ascii=False)}")

    prompt = f"""你是中医药知识专家。用户希望为"{entity['title']}"追加以下内容：{instruction}

请综合以上所有来源信息，为这个知识实体生成补充内容。

返回JSON：
{{
  "new_fields": {{"字段名": "值", ...}},
  "new_summary": "更新后的摘要（如果比当前更完整）",
  "new_content": "合成的完整补充内容（用于专家评审）",
  "sources_used": ["内部", "外部", "Web"]
}}

注意：
- 只追加用户请求的内容，不要重写已有内容
- 保持中医术语准确
- 标注信息来源类型
"""

    response = await chat_completion([
        {"role": "system", "content": "\n\n".join(context_parts)},
        {"role": "user", "content": prompt},
    ])

    import re
    try:
        from app.json_extractor import extract_json
        parsed = extract_json(response)
        if parsed:
            result = json.loads(match.group())
            return {
                "new_fields": result.get("new_fields", {}),
                "new_summary": result.get("new_summary", ""),
                "new_content": result.get("new_content", response[:500]),
                "sources_used": result.get("sources_used", []),
            }
    except (json.JSONDecodeError, AttributeError):
        pass

    return {"new_content": response[:500], "new_fields": {}, "new_summary": ""}


async def _log_append_request(
    db: DbAdapter, request_id: str, entity_id: str,
    user_id: str, instruction: str, status: str,
):
    from app.agent_tools import log_action
    await log_action(
        db, "append_start", "augmentation", instruction, entity_id,
        {"request_id": request_id, "user_id": user_id, "instruction": instruction},
        status,
    )


async def _update_append_request(
    db: DbAdapter, request_id: str, status: str, details: dict,
):
    from app.agent_tools import log_action
    await log_action(
        db, "append_update", "augmentation", request_id, "",
        details, status,
    )


def _build_result_message(review: dict, synthesized: dict) -> str:
    decision = review.get("decision", "pending_review")
    score = review.get("score", 0)
    fields = list(synthesized.get("new_fields", {}).keys())

    if decision == "adopted":
        return f"追加完成（信任评分{score}）。已更新字段：{'、'.join(fields) if fields else '摘要'}。"
    elif decision == "pending_review":
        return f"内容已合成（信任评分{score}），待专家审核后生效。"
    else:
        return f"专家评审未通过（评分{score}）。内容保留为参考，未入库。"


def _parse_json_safe(raw: Any, default: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return default
    return default


def _format_log(row: dict) -> dict:
    details = row.get("details")
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except (json.JSONDecodeError, TypeError):
            details = {}
    return {
        "id": row.get("id", ""),
        "action_type": row.get("action_type", ""),
        "details": details if isinstance(details, dict) else {},
        "decision": row.get("decision") or "",
        "created_at": row.get("created_at") or "",
    }
