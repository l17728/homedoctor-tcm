"""Unified knowledge entity system (spec §9 — 统一知识实体系统).

Bridges the four existing knowledge sources (herbs / formulas / therapies /
safety_rules) plus AI-imported content into a single searchable registry
(``knowledge_entities``) with a typed relationship engine
(``entity_relationships``).

Architecture (AGENTS.md §1.4 — 结构化是权威):
- Existing tables (herbs/formulas/therapies) remain the authoritative source.
- ``knowledge_entities`` is a registry that *mirrors* them for unified search.
- ``entity_relationships`` is the authoritative relationship store; the legacy
  ``graph_edges`` table can be derived from it via :mod:`app.kg_rebuild`.

Chinese domain language throughout (AGENTS.md §1.7): enum values, search
facets, relationship labels, and AI prompts all use Chinese.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings
from app.database import DbAdapter
from app.repository import current_tenant_id

logger = logging.getLogger(__name__)

CST = timezone(__import__("datetime").timedelta(hours=8))


# ---------------------------------------------------------------------------
# Relationship types — Chinese domain language (AGENTS.md §1.7)
# ---------------------------------------------------------------------------

RELATIONSHIP_TYPES: dict[str, str] = {
    "contains": "组成",          # formula contains herb
    "treats": "主治",            # herb/formula treats symptom
    "indicated_for": "适用于",    # therapy indicated for condition
    "interacts_with": "交互",    # herb-drug interaction
    "synergy_with": "协同",      # herbs that work well together
    "derived_from": "源于",      # formula derived from another
    "variant_of": "变种",        # processed variant
    "contraindicated": "禁忌",   # herb-herb contraindication
}

RELATIONSHIP_LABEL_TO_CODE: dict[str, str] = {v: k for k, v in RELATIONSHIP_TYPES.items()}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")


def _entity_id() -> str:
    return f"ke-{uuid.uuid4()}"


def _relationship_id(source: str, target: str, rel_type: str) -> str:
    return f"er:{rel_type}:{source}->{target}"


def _safe_json(raw: Any, default: Any) -> Any:
    if isinstance(raw, (list, dict)):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return default
    return default


def _ctx_tenant() -> str:
    """Current tenant from the request context (set by middleware from JWT)."""
    return current_tenant_id.get() or "default"


def _visibility_sql(alias: str = "") -> str:
    """SQL fragment matching global rows (tenant_id IS NULL) + current tenant."""
    prefix = f"{alias}." if alias else ""
    return f"({prefix}tenant_id IS NULL OR {prefix}tenant_id = ?)"


def _parse_entity_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize a knowledge_entities row — parse JSON columns to objects."""
    result = dict(row)
    for key in ("keywords", "tags"):
        result[key] = _safe_json(result.get(key), [])
    result["properties"] = _safe_json(result.get("properties"), {})
    return result


def _parse_relationship_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize an entity_relationships row — parse properties JSON."""
    result = dict(row)
    result["properties"] = _safe_json(result.get("properties"), {})
    result["label"] = RELATIONSHIP_TYPES.get(result.get("relationship_type", ""), result.get("relationship_type", ""))
    return result


# ---------------------------------------------------------------------------
# Entity Registry
# ---------------------------------------------------------------------------

async def register_entity(
    db: DbAdapter,
    entity_type: str,
    source_table: str,
    source_id: str | None,
    title: str,
    summary: str = "",
    keywords: list[str] | None = None,
    tags: list[str] | None = None,
    category: str | None = None,
    content_preview: str | None = None,
    properties: dict[str, Any] | None = None,
    source_type: str = "system",
    status: str = "active",
    tenant_id: str | None = None,
) -> str:
    """Register or update an entity in the unified registry. Returns entity_id.

    If an entity with the same ``(source_table, source_id, tenant_id)`` already
    exists, its mutable fields are updated in place (upsert semantics). The
    dedup scope matches the tenant exactly — a tenant-scoped registration
    never upserts a global (``tenant_id IS NULL``) row or another tenant's
    row. Entities with ``source_id IS NULL`` are always treated as new (used
    by AI imports where each import is unique).
    """
    keywords = keywords or []
    tags = tags or []
    properties = properties or {}
    now = _now()

    existing: dict[str, Any] | None = None
    if source_id:
        existing = await db.query_one(
            """SELECT id FROM knowledge_entities
               WHERE source_table = ? AND source_id = ? AND tenant_id IS ?""",
            (source_table, source_id, tenant_id),
        )

    if existing:
        entity_id = existing["id"]
        await db.execute(
            """UPDATE knowledge_entities SET
                   entity_type = ?, title = ?, summary = ?, keywords = ?,
                   tags = ?, category = ?, content_preview = ?,
                   properties = ?, source_type = ?, status = ?, updated_at = ?
               WHERE id = ?""",
            (
                entity_type, title, summary,
                json.dumps(keywords, ensure_ascii=False),
                json.dumps(tags, ensure_ascii=False),
                category, content_preview,
                json.dumps(properties, ensure_ascii=False),
                source_type, status, now, entity_id,
            ),
        )
        return entity_id

    entity_id = _entity_id()
    await db.execute(
        """INSERT INTO knowledge_entities
               (id, entity_type, source_table, source_id, title, summary,
                keywords, tags, category, content_preview, properties,
                source_type, status, tenant_id, view_count, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
        (
            entity_id, entity_type, source_table, source_id, title, summary,
            json.dumps(keywords, ensure_ascii=False),
            json.dumps(tags, ensure_ascii=False),
            category, content_preview,
            json.dumps(properties, ensure_ascii=False),
            source_type, status, tenant_id, now, now,
        ),
    )
    return entity_id


async def get_or_create_entity(
    db: DbAdapter,
    entity_type: str,
    source_table: str,
    source_id: str,
    title: str,
    tenant_id: str | None = None,
) -> str:
    """Find existing entity by ``(source_table, source_id, tenant_id)`` or create.

    Lighter-weight variant of :func:`register_entity` for callers that only
    need the id (e.g. linking extracted entities by name during AI import).
    """
    existing = await db.query_one(
        """SELECT id FROM knowledge_entities
           WHERE source_table = ? AND source_id = ? AND tenant_id IS ?""",
        (source_table, source_id, tenant_id),
    )
    if existing:
        return existing["id"]
    return await register_entity(
        db, entity_type=entity_type, source_table=source_table,
        source_id=source_id, title=title, tenant_id=tenant_id,
    )


async def get_entity(db: DbAdapter, entity_id: str) -> dict[str, Any] | None:
    """Get entity visible to the current tenant, with parsed JSON fields.

    Global entities (``tenant_id IS NULL``) are visible to everyone; private
    entities only to their owning tenant. Returns ``None`` if missing or not
    visible.
    """
    row = await db.query_one(
        f"SELECT * FROM knowledge_entities WHERE id = ? AND {_visibility_sql()}",
        (entity_id, _ctx_tenant()),
    )
    return _parse_entity_row(row) if row else None


async def update_entity(
    db: DbAdapter,
    entity_id: str,
    *,
    summary: str | None = None,
    tags: list[str] | None = None,
    keywords: list[str] | None = None,
    category: str | None = None,
    properties: dict[str, Any] | None = None,
    status: str | None = None,
) -> dict[str, Any] | None:
    """Update mutable fields on a tenant-visible entity. Returns updated entity.

    Only entities visible to the current tenant (global or own-tenant) can be
    updated; anything else returns ``None``. Write access to *global* entities
    is admin-only and enforced at the router layer.
    """
    existing = await get_entity(db, entity_id)
    if not existing:
        return None

    new_summary = summary if summary is not None else existing.get("summary")
    new_tags = tags if tags is not None else existing.get("tags", [])
    new_keywords = keywords if keywords is not None else existing.get("keywords", [])
    new_category = category if category is not None else existing.get("category")
    new_status = status if status is not None else existing.get("status")
    new_props = properties if properties is not None else existing.get("properties", {})

    await db.execute(
        f"""UPDATE knowledge_entities SET
               summary = ?, tags = ?, keywords = ?, category = ?,
               properties = ?, status = ?, updated_at = ?
            WHERE id = ? AND {_visibility_sql()}""",
        (
            new_summary,
            json.dumps(new_tags, ensure_ascii=False),
            json.dumps(new_keywords, ensure_ascii=False),
            new_category,
            json.dumps(new_props, ensure_ascii=False),
            new_status,
            _now(),
            entity_id,
            _ctx_tenant(),
        ),
    )
    return await get_entity(db, entity_id)


async def increment_view_count(db: DbAdapter, entity_id: str) -> None:
    """Atomically bump ``view_count`` for a tenant-visible entity."""
    await db.execute(
        f"UPDATE knowledge_entities SET view_count = view_count + 1 "
        f"WHERE id = ? AND {_visibility_sql()}",
        (entity_id, _ctx_tenant()),
    )


async def search_entities(
    db: DbAdapter,
    q: str = "",
    entity_type: str | None = None,
    category: str | None = None,
    tag: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """Unified search across all entity types.

    Searches across ``title``, ``summary``, ``keywords``, and ``tags`` using
    ``LIKE``. Returns ``{items, total, page, page_size, facets}`` where
    ``facets`` is ``{entity_type: count}`` over the *unfiltered-by-type* match
    set so the UI can render type tabs with counts.
    """
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    offset = (page - 1) * page_size

    where_parts: list[str] = [_visibility_sql(), "status = 'active'"]
    params: list[Any] = [_ctx_tenant()]

    if q:
        like = f"%{q}%"
        where_parts.append(
            "(title LIKE ? OR summary LIKE ? OR keywords LIKE ? OR tags LIKE ?)"
        )
        params.extend([like, like, like, like])
    if entity_type:
        where_parts.append("entity_type = ?")
        params.append(entity_type)
    if category:
        where_parts.append("category = ?")
        params.append(category)
    if tag:
        where_parts.append("tags LIKE ?")
        params.append(f"%{tag}%")

    where_sql = " AND ".join(where_parts)

    # Facets: counts per entity_type over the full match set (ignoring
    # entity_type filter, but keeping q/category/tag filters) so the UI can
    # show "全部 / 中药(N) / 方剂(M) / ..." tabs.
    facet_where = f"status = 'active' AND {_visibility_sql()}"
    facet_params: list[Any] = [_ctx_tenant()]
    if q:
        like = f"%{q}%"
        facet_where += " AND (title LIKE ? OR summary LIKE ? OR keywords LIKE ? OR tags LIKE ?)"
        facet_params.extend([like, like, like, like])
    if category:
        facet_where += " AND category = ?"
        facet_params.append(category)
    if tag:
        facet_where += " AND tags LIKE ?"
        facet_params.append(f"%{tag}%")

    facet_rows = await db.query(
        f"SELECT entity_type, COUNT(*) AS cnt FROM knowledge_entities "
        f"WHERE {facet_where} GROUP BY entity_type",
        tuple(facet_params),
    )
    facets = {r["entity_type"]: r["cnt"] for r in facet_rows}

    total_row = await db.query_one(
        f"SELECT COUNT(*) AS cnt FROM knowledge_entities WHERE {where_sql}",
        tuple(params),
    )
    total = total_row["cnt"] if total_row else 0

    rows = await db.query(
        f"""SELECT * FROM knowledge_entities
            WHERE {where_sql}
            ORDER BY
                CASE WHEN title LIKE ? THEN 0 ELSE 1 END,
                view_count DESC,
                created_at DESC
            LIMIT ? OFFSET ?""",
        tuple(params + [f"%{q}%" if q else "%", page_size, offset]),
    )
    items = [_parse_entity_row(r) for r in rows]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "facets": facets,
    }


async def list_by_type(
    db: DbAdapter,
    entity_type: str,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """List entities by type with pagination."""
    return await search_entities(
        db, q="", entity_type=entity_type, page=page, page_size=page_size,
    )


async def get_type_facets(db: DbAdapter) -> dict[str, int]:
    """Return ``{entity_type: count}`` over active entities visible to this tenant."""
    rows = await db.query(
        f"""SELECT entity_type, COUNT(*) AS cnt
            FROM knowledge_entities
            WHERE status = 'active' AND {_visibility_sql()}
            GROUP BY entity_type
            ORDER BY cnt DESC""",
        (_ctx_tenant(),),
    )
    return {r["entity_type"]: r["cnt"] for r in rows}


async def list_popular(db: DbAdapter, limit: int = 10) -> list[dict[str, Any]]:
    """Most viewed entities (``view_count DESC``) visible to this tenant."""
    limit = max(1, min(100, limit))
    rows = await db.query(
        f"""SELECT * FROM knowledge_entities
            WHERE status = 'active' AND view_count > 0 AND {_visibility_sql()}
            ORDER BY view_count DESC, created_at DESC LIMIT ?""",
        (_ctx_tenant(), limit),
    )
    return [_parse_entity_row(r) for r in rows]


async def list_recent(db: DbAdapter, limit: int = 10) -> list[dict[str, Any]]:
    """Recently added entities (``created_at DESC``) visible to this tenant."""
    limit = max(1, min(100, limit))
    rows = await db.query(
        f"""SELECT * FROM knowledge_entities
            WHERE status = 'active' AND {_visibility_sql()}
            ORDER BY created_at DESC LIMIT ?""",
        (_ctx_tenant(), limit),
    )
    return [_parse_entity_row(r) for r in rows]


# ---------------------------------------------------------------------------
# Relationship Engine
# ---------------------------------------------------------------------------

async def create_relationship(
    db: DbAdapter,
    source_id: str,
    target_id: str,
    rel_type: str,
    properties: dict[str, Any] | None = None,
    weight: float = 1.0,
    tenant_id: str | None = None,
) -> str:
    """Create an entity_relationship row. Idempotent on ``(source, target, type, tenant)``.

    ``rel_type`` may be either the code (``"contains"``) or the Chinese label
    (``"组成"``) — both are normalized via :data:`RELATIONSHIP_TYPES`.
    ``tenant_id IS NULL`` creates a global relationship; callers should pass
    the current tenant for user-curated edges (visibility of both endpoints
    is enforced at the router layer).
    """
    normalized = RELATIONSHIP_TYPES.get(rel_type, rel_type)
    props_json = json.dumps(properties or {}, ensure_ascii=False)
    rel_id = _relationship_id(source_id, target_id, normalized)

    existing = await db.query_one(
        """SELECT id FROM entity_relationships
           WHERE source_entity_id = ? AND target_entity_id = ?
             AND relationship_type = ? AND tenant_id IS ?""",
        (source_id, target_id, normalized, tenant_id),
    )
    if existing:
        await db.execute(
            """UPDATE entity_relationships SET
                   properties = ?, weight = ?, created_at = ?
               WHERE id = ?""",
            (props_json, weight, _now(), existing["id"]),
        )
        return existing["id"]

    await db.execute(
        """INSERT INTO entity_relationships
               (id, source_entity_id, target_entity_id, relationship_type,
                properties, weight, tenant_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (rel_id, source_id, target_id, normalized, props_json, weight, tenant_id, _now()),
    )
    return rel_id


async def get_relationships(
    db: DbAdapter,
    entity_id: str,
    direction: str = "both",
) -> list[dict[str, Any]]:
    """Get all relationships for an entity, tenant-scoped.

    Both the relationship row and the joined partner entity must be visible
    to the current tenant (global or own-tenant). ``direction`` is one of
    ``"outgoing"``, ``"incoming"``, or ``"both"``.
    """
    results: list[dict[str, Any]] = []
    tenant = _ctx_tenant()

    if direction in ("outgoing", "both"):
        rows = await db.query(
            f"""SELECT er.*, ke.title AS target_title, ke.entity_type AS target_type,
                      ke.category AS target_category
               FROM entity_relationships er
               LEFT JOIN knowledge_entities ke ON ke.id = er.target_entity_id
               WHERE er.source_entity_id = ?
                 AND {_visibility_sql('er')}
                 AND (ke.tenant_id IS NULL OR ke.tenant_id = ?)
               ORDER BY er.relationship_type, er.weight DESC""",
            (entity_id, tenant, tenant),
        )
        for r in rows:
            parsed = _parse_relationship_row(r)
            parsed["direction"] = "outgoing"
            results.append(parsed)

    if direction in ("incoming", "both"):
        rows = await db.query(
            f"""SELECT er.*, ke.title AS source_title, ke.entity_type AS source_type,
                      ke.category AS source_category
               FROM entity_relationships er
               LEFT JOIN knowledge_entities ke ON ke.id = er.source_entity_id
               WHERE er.target_entity_id = ?
                 AND {_visibility_sql('er')}
                 AND (ke.tenant_id IS NULL OR ke.tenant_id = ?)
               ORDER BY er.relationship_type, er.weight DESC""",
            (entity_id, tenant, tenant),
        )
        for r in rows:
            parsed = _parse_relationship_row(r)
            parsed["direction"] = "incoming"
            # Normalize partner fields so outgoing/incoming have a consistent shape
            parsed["target_title"] = parsed.pop("source_title", None)
            parsed["target_type"] = parsed.pop("source_type", None)
            parsed["target_category"] = parsed.pop("source_category", None)
            results.append(parsed)

    return results


async def get_related_entities(
    db: DbAdapter,
    entity_id: str,
    rel_type: str | None = None,
) -> list[dict[str, Any]]:
    """Get entities related to ``entity_id`` visible to this tenant (either direction)."""
    normalized = RELATIONSHIP_TYPES.get(rel_type, rel_type) if rel_type else None
    tenant = _ctx_tenant()

    outgoing_sql = (
        f"""SELECT ke.* FROM entity_relationships er
           JOIN knowledge_entities ke ON ke.id = er.target_entity_id
           WHERE er.source_entity_id = ?
             AND {_visibility_sql('er')}
             AND {_visibility_sql('ke')}"""
    )
    incoming_sql = (
        f"""SELECT ke.* FROM entity_relationships er
           JOIN knowledge_entities ke ON ke.id = er.source_entity_id
           WHERE er.target_entity_id = ?
             AND {_visibility_sql('er')}
             AND {_visibility_sql('ke')}"""
    )

    if normalized:
        outgoing_sql += " AND er.relationship_type = ?"
        incoming_sql += " AND er.relationship_type = ?"
        out_rows = await db.query(outgoing_sql, (entity_id, tenant, tenant, normalized))
        in_rows = await db.query(incoming_sql, (entity_id, tenant, tenant, normalized))
    else:
        out_rows = await db.query(outgoing_sql, (entity_id, tenant, tenant))
        in_rows = await db.query(incoming_sql, (entity_id, tenant, tenant))

    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for r in out_rows + in_rows:
        if r["id"] not in seen:
            seen.add(r["id"])
            merged.append(_parse_entity_row(r))
    return merged


async def count_relationships(db: DbAdapter) -> dict[str, int]:
    """Return ``{relationship_type: count}`` over relationships visible to this tenant."""
    rows = await db.query(
        f"""SELECT relationship_type, COUNT(*) AS cnt
            FROM entity_relationships
            WHERE {_visibility_sql()}
            GROUP BY relationship_type
            ORDER BY cnt DESC""",
        (_ctx_tenant(),),
    )
    return {r["relationship_type"]: r["cnt"] for r in rows}


# ---------------------------------------------------------------------------
# AI Processing Pipeline
# ---------------------------------------------------------------------------

ANALYSIS_PROMPT_TEMPLATE = """分析以下中医健康知识内容，提取结构化信息：
标题：{title}
内容：{content}

返回JSON：
{{
    "entity_type": "herb|formula|therapy|symptom|tea_recipe|health_method|article",
    "category": "分类（如：补气药/解表剂/温里剂）",
    "summary": "100字以内的内容摘要",
    "keywords": ["关键词1", "关键词2"],
    "tags": ["标签1", "标签2"],
    "extracted_entities": [
        {{"type": "herb", "name": "黄芪", "context": "提到的上下文"}},
        {{"type": "symptom", "name": "气虚", "context": "..."}}
    ],
    "relationships": [
        {{"source": "黄芪", "target": "气虚", "type": "treats"}}
    ]
}}"""


_KNOWN_ENTITY_TYPES = frozenset({
    "herb", "formula", "therapy", "symptom",
    "acupoint", "meridian", "health_practice", "practice_school",
    "tea_recipe", "health_method", "article", "person",
})

_DEFAULT_ENTITY_TYPE = "article"


async def _get_known_entity_types(db: DbAdapter) -> set[str]:
    """Get all entity types currently in the database + known defaults."""
    try:
        rows = await db.query("SELECT DISTINCT entity_type FROM knowledge_entities")
        db_types = {r["entity_type"] for r in rows if r.get("entity_type")}
        return db_types | _KNOWN_ENTITY_TYPES
    except Exception:
        return set(_KNOWN_ENTITY_TYPES)


def _parse_llm_json(raw: str) -> dict[str, Any]:
    """Best-effort JSON extraction from an LLM response.

    LLMs often wrap JSON in markdown fences or prepend commentary. This helper
    strips such wrappers and returns an empty dict on failure.
    """
    if not raw:
        return {}
    text = raw.strip()
    # Strip ```json ... ``` fences
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    # Find first { ... last } as a fallback
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


async def _call_llm_for_analysis(title: str, content: str) -> dict[str, Any]:
    """Send content to the LLM for structured analysis.

    Returns the parsed JSON dict, or an empty dict if the LLM is unavailable
    (no API key) or the call fails — enabling graceful degradation in tests
    and offline environments.
    """
    if not settings.LLM_API_KEY:
        logger.info("LLM_API_KEY not configured — skipping AI analysis")
        return {}

    prompt = ANALYSIS_PROMPT_TEMPLATE.format(title=title[:200], content=content[:2000])

    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.LLM_MODEL,
        "messages": [
            {"role": "system", "content": "你是一个中医药知识结构化助手。只返回JSON，不要任何额外文字。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 1024,
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{settings.LLM_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            content_text = data["choices"][0]["message"]["content"]
            return _parse_llm_json(content_text)
    except Exception as exc:
        logger.warning("AI analysis LLM call failed: %s", exc)
        return {}


async def _find_or_create_entity_by_name(
    db: DbAdapter,
    name: str,
    entity_type: str,
    context: str = "",
    tenant_id: str | None = None,
) -> str | None:
    """Find a tenant-visible knowledge_entity by title (any type) or create a stub.

    Used during AI import to link extracted entities (herbs / symptoms) by
    name. Lookup prefers global + own-tenant entities so another family's
    private stub is never linked or leaked. Returns ``None`` if the name is
    empty.
    """
    if not name or not name.strip():
        return None
    name = name.strip()
    tenant = tenant_id if tenant_id is not None else _ctx_tenant()

    existing = await db.query_one(
        f"""SELECT id FROM knowledge_entities
            WHERE title = ? AND status = 'active' AND {_visibility_sql()}
            LIMIT 1""",
        (name, tenant),
    )
    if existing:
        return existing["id"]

    # Don't auto-create symptom entities en masse — only herbs/formulas/therapies
    # are seeded as canonical entities. Symptom/condition stubs are created
    # lazily here so relationships have a target to point at.
    safe_type = entity_type if entity_type in _KNOWN_ENTITY_TYPES else _DEFAULT_ENTITY_TYPE
    return await register_entity(
        db,
        entity_type=safe_type,
        source_table="ai_extracted",
        source_id=f"name:{name}",
        title=name,
        summary=context[:200] if context else "",
        source_type="ai_extracted",
        tenant_id=tenant_id,
    )


async def process_imported_content(
    db: DbAdapter,
    title: str,
    content: str,
    source_type: str = "import",
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Full AI pipeline for processing imported knowledge.

    Steps (spec §9 — 统一知识实体系统):
    1. Send content to the LLM for structured analysis (graceful skip if no key).
    2. Parse the LLM JSON response.
    3. Create the primary ``knowledge_entity`` row (tenant-scoped when
       ``tenant_id`` is passed — HTTP import endpoints pass the caller's
       family so imported knowledge stays private to that family).
    4. Link each extracted entity (create-or-find by name, tenant-visible).
    5. Create relationships between the primary entity and the extracted ones.
    6. Return the processed entity + AI metadata.

    When the LLM is unavailable, falls back to a heuristic entity (type =
    ``"article"``) so the import still succeeds — only without AI enrichment.
    """
    if not title or not title.strip():
        raise ValueError("title must not be empty")
    if not content or not content.strip():
        raise ValueError("content must not be empty")

    title = title.strip()
    content = content.strip()

    analysis = await _call_llm_for_analysis(title, content)

    entity_type = analysis.get("entity_type", _DEFAULT_ENTITY_TYPE)
    if entity_type not in _KNOWN_ENTITY_TYPES:
        entity_type = _DEFAULT_ENTITY_TYPE

    category = analysis.get("category") or None
    summary = (analysis.get("summary") or content[:200]).strip()
    keywords = analysis.get("keywords") or []
    tags = analysis.get("tags") or []
    extracted = analysis.get("extracted_entities") or []
    relationships = analysis.get("relationships") or []

    if not isinstance(keywords, list):
        keywords = []
    if not isinstance(tags, list):
        tags = []

    primary_id = await register_entity(
        db,
        entity_type=entity_type,
        source_table="ai_import",
        source_id=None,  # each import is unique — no dedup by source_id
        title=title,
        summary=summary,
        keywords=[str(k) for k in keywords if k],
        tags=[str(t) for t in tags if t],
        category=category,
        content_preview=content[:500],
        properties={"ai_analyzed": bool(analysis), "raw_analysis": analysis},
        source_type=source_type,
        tenant_id=tenant_id,
    )

    linked_entities: list[dict[str, Any]] = []
    for ext in extracted:
        if not isinstance(ext, dict):
            continue
        ext_name = str(ext.get("name") or "").strip()
        ext_type = str(ext.get("type") or "").strip()
        ext_context = str(ext.get("context") or "").strip()
        if not ext_name:
            continue
        linked_id = await _find_or_create_entity_by_name(
            db, ext_name, ext_type, ext_context, tenant_id=tenant_id,
        )
        if linked_id and linked_id != primary_id:
            linked_entities.append({
                "entity_id": linked_id,
                "name": ext_name,
                "type": ext_type,
                "context": ext_context,
            })

    created_relationships: list[dict[str, Any]] = []
    for rel in relationships:
        if not isinstance(rel, dict):
            continue
        src_name = str(rel.get("source") or "").strip()
        tgt_name = str(rel.get("target") or "").strip()
        rel_type = str(rel.get("type") or "").strip()
        if not src_name or not tgt_name or not rel_type:
            continue
        # Resolve names to entity ids — prefer the primary entity when the LLM
        # named it as the source/target.
        src_id = primary_id if src_name == title else await _find_or_create_entity_by_name(
            db, src_name, "article", tenant_id=tenant_id,
        )
        tgt_id = primary_id if tgt_name == title else await _find_or_create_entity_by_name(
            db, tgt_name, "article", tenant_id=tenant_id,
        )
        if not src_id or not tgt_id:
            continue
        rel_id = await create_relationship(db, src_id, tgt_id, rel_type, tenant_id=tenant_id)
        created_relationships.append({
            "relationship_id": rel_id,
            "source": src_name,
            "target": tgt_name,
            "type": rel_type,
        })

    entity = await get_entity(db, primary_id)
    return {
        "entity": entity,
        "ai_analyzed": bool(analysis),
        "linked_entities": linked_entities,
        "relationships_created": created_relationships,
    }
