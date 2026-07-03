"""P3 features: personalization, community consensus, URL refresh, cross-lingual.

Endpoints:
  GET  /api/user/interests                   — user interest profile
  POST /api/admin/community-consensus-scan   — detect multi-user consensus → upgrade trust
  POST /api/admin/url-health-check           — check external URLs for 404
  GET  /api/admin/url-health-stats           — stale URL statistics
  POST /api/admin/translate-check            — detect & flag non-Chinese content
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import get_current_user, require_admin
from app.database import DbAdapter, get_db

router = APIRouter(prefix="/api", tags=["p3-features"])


@router.post("/admin/feeder/scan")
async def feeder_scan(
    max_feeds: int = 10,
    db: DbAdapter = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    """Trigger knowledge feeder scan — discovers gaps and feeds URLs."""
    from app.knowledge_feeder import run_feeder_scan
    return await run_feeder_scan(db, max_feeds=max_feeds)


@router.get("/user/interests")
async def get_user_interests(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Get user's interest profile (auto-built from search history)."""
    rows = await db.query(
        "SELECT interest_domain, search_count, last_searched FROM user_interest_profiles WHERE user_id = ? ORDER BY search_count DESC",
        (current_user["id"],),
    )
    return {"interests": [dict(r) for r in rows], "total": len(rows)}


async def record_user_interest(db: DbAdapter, user_id: str, query: str) -> None:
    """Record a search query to build user interest profile."""
    domain = _classify_search_domain(query)
    if not domain:
        return
    existing = await db.query_one(
        "SELECT search_count FROM user_interest_profiles WHERE user_id = ? AND interest_domain = ?",
        (user_id, domain),
    )
    if existing:
        await db.execute(
            "UPDATE user_interest_profiles SET search_count = search_count + 1, last_searched = datetime('now') WHERE user_id = ? AND interest_domain = ?",
            (user_id, domain),
        )
    else:
        await db.execute(
            "INSERT INTO user_interest_profiles (user_id, interest_domain, search_count, last_searched) VALUES (?, ?, 1, datetime('now'))",
            (user_id, domain),
        )


def _classify_search_domain(query: str) -> str:
    """Classify a search query into an interest domain."""
    domain_keywords = {
        "老年慢性病": ["降压", "血糖", "糖尿病", "关节", "腰痛", "失眠", "心悸", "高血压"],
        "儿科调理": ["小儿", "儿童", "孩子", "宝宝", "发烧", "感冒", "脾胃"],
        "妇科养生": ["月经", "痛经", "更年期", "产后", "带下", "不孕"],
        "补益养生": ["补气", "补血", "补肾", "壮阳", "延年", "保健"],
        "经络穴位": ["穴位", "经络", "针灸", "推拿", "按摩"],
        "功法修炼": ["太极", "八段锦", "气功", "站桩", "打坐", "冥想"],
        "食疗药膳": ["食疗", "药膳", "饮食", "药茶", "代茶"],
    }
    for domain, keywords in domain_keywords.items():
        for kw in keywords:
            if kw in query:
                return domain
    return ""


@router.post("/admin/community-consensus-scan")
async def community_consensus_scan(
    db: DbAdapter = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    """Detect multi-user consensus → auto-upgrade trust level.

    When ≥3 independent users import knowledge about the same entity,
    the system upgrades trust from B to A (community validation).
    """
    rows = await db.query(
        """SELECT entity_id, COUNT(DISTINCT imported_by) AS source_count, AVG(trust_score) AS avg_score
             FROM knowledge_provenance
            WHERE trust_level = 'B' AND imported_by IS NOT NULL AND imported_by != ''
            GROUP BY entity_id
            HAVING source_count >= 3"""
    )

    upgraded = 0
    for row in rows:
        from app.trust_engine import update_trust_level
        await update_trust_level(
            db, row["entity_id"], "A",
            reason=f"社区共识：{row['source_count']}个独立来源",
        )
        upgraded += 1

    return {"scanned": len(rows), "upgraded": upgraded}


@router.post("/admin/url-health-check")
async def url_health_check(
    db: DbAdapter = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    """Check external URLs for 404 — mark stale chunks."""
    rows = await db.query(
        """SELECT DISTINCT source_url FROM knowledge_chunks
            WHERE source_type = 'external' AND source_url IS NOT NULL LIMIT 100"""
    )

    import httpx
    checked = 0
    stale = 0
    for row in rows:
        url = row["source_url"]
        from app.url_validator import validate_external_url
        if not validate_external_url(url):
            stale += 1
            continue
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.head(url, follow_redirects=True)
            checked += 1
            if resp.status_code == 404:
                await db.execute(
                    "UPDATE knowledge_chunks SET chunk_type = 'external_stale' WHERE source_url = ?",
                    (url,),
                )
                stale += 1
        except Exception:
            stale += 1

    return {"checked": checked, "stale": stale}


@router.get("/admin/url-health-stats")
async def url_health_stats(
    db: DbAdapter = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    """URL health statistics."""
    total = await db.query_one(
        "SELECT COUNT(DISTINCT source_url) AS c FROM knowledge_chunks WHERE source_type='external'"
    )
    stale = await db.query_one(
        "SELECT COUNT(DISTINCT source_url) AS c FROM knowledge_chunks WHERE chunk_type='external_stale'"
    )
    return {
        "total_external_urls": total["c"] if total else 0,
        "stale_urls": stale["c"] if stale else 0,
    }


@router.post("/admin/translate-check")
async def translate_check(
    db: DbAdapter = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    """Detect non-Chinese content in recent imports — flag for translation."""
    rows = await db.query(
        """SELECT id, title, summary FROM knowledge_entities
            WHERE status = 'active' AND created_at > datetime('now', '-30 days')
            LIMIT 100"""
    )

    flagged = []
    for row in rows:
        text = f"{row.get('title', '')} {row.get('summary', '')}"
        has_chinese = any('\u4e00' <= ch <= '\u9fff' for ch in text[:200])
        has_latin = any('a' <= ch.lower() <= 'z' for ch in text[:200])
        if has_latin and not has_chinese:
            flagged.append({"entity_id": row["id"], "title": row["title"]})

    return {"checked": len(rows), "flagged_for_translation": len(flagged), "items": flagged[:10]}


# ---------------------------------------------------------------------------
# Agent memory & conversation API
# ---------------------------------------------------------------------------

@router.get("/admin/agent/memories")
async def list_agent_memories(
    agent_name: str | None = None,
    memory_type: str | None = None,
    q: str | None = None,
    limit: int = 20,
    db: DbAdapter = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    from app.agent_memory import memory_search
    results = await memory_search(db, agent_name, q or "", memory_type, limit=limit)
    return {"items": results, "total": len(results)}


@router.post("/admin/agent/memories")
async def save_agent_memory(
    body: dict[str, Any],
    db: DbAdapter = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    from app.agent_memory import memory_save
    mid = await memory_save(
        db,
        body.get("agent_name", "shared"),
        body.get("content", ""),
        body.get("memory_type", "experience"),
        confidence=body.get("confidence", 0.5),
    )
    return {"id": mid, "message": "记忆已保存"}


@router.delete("/admin/agent/memories/{memory_id}")
async def delete_agent_memory(
    memory_id: str,
    db: DbAdapter = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    await db.execute("UPDATE agent_memories SET superseded_by = 'deleted' WHERE id = ?", (memory_id,))
    return {"message": "已标记为过时"}


@router.get("/admin/agent/conversations")
async def list_agent_conversations(
    agent_name: str | None = None,
    limit: int = 30,
    db: DbAdapter = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    from app.agent_communication import get_conversation_history
    results = await get_conversation_history(db, agent_name, limit)
    return {"items": results, "total": len(results)}


@router.get("/admin/agent/config")
async def get_agent_config(
    agent_name: str = "shared",
    db: DbAdapter = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    from app.agent_tools import tool_get_config
    return await tool_get_config(db, agent_name)


@router.put("/admin/agent/config")
async def set_agent_config(
    body: dict[str, Any],
    db: DbAdapter = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    from app.agent_tools import tool_set_config
    return await tool_set_config(db, body.get("agent_name", "shared"), body.get("key", ""), body.get("value"))


@router.post("/admin/agent/optimize-prompt")
async def optimize_agent_prompt(
    body: dict[str, Any],
    db: DbAdapter = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    agent_name = body.get("agent_name", "shared")
    current_prompt = body.get("current_prompt", "")
    auto_apply = body.get("auto_apply", False)

    if auto_apply:
        from app.agent_tools import tool_optimize_and_apply
        return await tool_optimize_and_apply(db, agent_name, current_prompt)

    from app.agent_tools import tool_optimize_prompt
    suggestions = await tool_optimize_prompt(db, agent_name, current_prompt)
    return {"suggestions": suggestions}
