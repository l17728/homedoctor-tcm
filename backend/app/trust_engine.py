"""Trust engine — knowledge trust hierarchy, safety sandbox, and trust flow.

Implements the four-level trust system (S/A/B/C) that acts as the
"immune system" for medical knowledge safety.

Trust levels:
  S — System authoritative (textbooks, pharmacopeia, expert-verified seeds)
  A — Authoritative sources (official medical sites, journals, AI-panel approved)
  B — User imported (blogs, WeChat articles, manual entry)
  C — Web Search results (random search engine results)

Safety rules:
  - Safety engine reads ONLY S+A level knowledge
  - AI Q&A can reference S+A+B (B tagged "仅供参考")
  - Search results visible at all levels (C included)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.database import DbAdapter

logger = logging.getLogger(__name__)

LEVEL_S = "S"
LEVEL_A = "A"
LEVEL_B = "B"
LEVEL_C = "C"

_LEVEL_ORDER = {LEVEL_S: 0, LEVEL_A: 1, LEVEL_B: 2, LEVEL_C: 3}

SAFETY_THRESHOLD = LEVEL_A
AI_QA_THRESHOLD = LEVEL_B
SEARCH_THRESHOLD = LEVEL_C

DOMAIN_TRUST_MAP: dict[str, str] = {
    "satcm.gov.cn": LEVEL_S,
    "cntcm.ac.cn": LEVEL_S,
    "cnki.net": LEVEL_A,
    "wanfangdata.com.cn": LEVEL_A,
    "pubmed.ncbi.nlm.nih.gov": LEVEL_A,
    "ncbi.nlm.nih.gov": LEVEL_A,
    "39yst.com": LEVEL_B,
    "zyys.com": LEVEL_B,
}


def get_domain_trust(url: str) -> str:
    """Determine initial trust level from URL domain."""
    if not url:
        return LEVEL_C
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.lower()
    for trusted_domain, level in DOMAIN_TRUST_MAP.items():
        if trusted_domain in domain:
            return level
    return LEVEL_C


def can_enter_safety_check(trust_level: str) -> bool:
    """Only S+A level knowledge can influence safety engine decisions."""
    return _LEVEL_ORDER.get(trust_level, 3) <= _LEVEL_ORDER[SAFETY_THRESHOLD]


def can_reference_in_ai(trust_level: str) -> bool:
    """S+A+B can be referenced in AI responses (B tagged as unverified)."""
    return _LEVEL_ORDER.get(trust_level, 3) <= _LEVEL_ORDER[AI_QA_THRESHOLD]


def is_visible_in_search(trust_level: str) -> bool:
    """All levels visible in search results."""
    return True


def calculate_trust_score(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate multi-AI model reviews into a trust score and level.

    Each review has: medical_accuracy, completeness, source_reliability (0-100),
    recommendation ('adopt'/'review'/'reject').

    Returns: {score, level, decision, consensus_count}
    """
    if not reviews:
        return {"score": 0, "level": LEVEL_C, "decision": "rejected", "consensus_count": 0}

    scores = []
    adopt_count = 0
    reject_count = 0

    for r in reviews:
        avg = (
            float(r.get("medical_accuracy", 50))
            + float(r.get("completeness", 50))
            + float(r.get("source_reliability", 50))
        ) / 3
        scores.append(avg)
        rec = r.get("recommendation", "review")
        if rec == "adopt":
            adopt_count += 1
        elif rec == "reject":
            reject_count += 1

    overall = sum(scores) / len(scores)
    total = len(reviews)
    consensus_threshold = max(1, total // 2 + 1)

    if adopt_count >= consensus_threshold and overall >= 80:
        return {
            "score": round(overall, 1),
            "level": LEVEL_A,
            "decision": "adopted",
            "consensus_count": adopt_count,
        }
    elif adopt_count >= consensus_threshold and overall >= 60:
        return {
            "score": round(overall, 1),
            "level": LEVEL_B,
            "decision": "pending_review",
            "consensus_count": adopt_count,
        }
    elif reject_count >= consensus_threshold:
        return {
            "score": round(overall, 1),
            "level": LEVEL_C,
            "decision": "rejected",
            "consensus_count": reject_count,
        }
    else:
        return {
            "score": round(overall, 1),
            "level": LEVEL_B,
            "decision": "pending_review",
            "consensus_count": adopt_count,
        }


async def record_provenance(
    db: DbAdapter,
    entity_id: str,
    source_type: str,
    source_url: str = "",
    source_title: str = "",
    trust_level: str = LEVEL_C,
    trust_score: float = 0,
    review_details: dict[str, Any] | None = None,
    imported_by: str = "",
    content_date: str = "",
) -> str:
    """Record knowledge provenance (blood lineage)."""
    import uuid
    from urllib.parse import urlparse

    domain = urlparse(source_url).netloc if source_url else ""

    pid = f"prov-{uuid.uuid4()}"
    await db.execute(
        """INSERT INTO knowledge_provenance
           (id, entity_id, source_type, source_url, source_title, source_domain,
            trust_level, trust_score, review_details, content_date, imported_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            pid, entity_id, source_type, source_url, source_title, domain,
            trust_level, trust_score,
            json.dumps(review_details or {}, ensure_ascii=False),
            content_date, imported_by,
        ),
    )
    return pid


async def get_provenance(db: DbAdapter, entity_id: str) -> list[dict[str, Any]]:
    """Get all provenance records for an entity."""
    rows = await db.query(
        "SELECT * FROM knowledge_provenance WHERE entity_id = ? ORDER BY imported_at DESC",
        (entity_id,),
    )
    return [_format_provenance(r) for r in rows]


async def get_trust_level(db: DbAdapter, entity_id: str) -> str:
    """Get the highest trust level across all provenance records."""
    rows = await db.query(
        "SELECT trust_level FROM knowledge_provenance WHERE entity_id = ?",
        (entity_id,),
    )
    if not rows:
        return LEVEL_C
    levels = [r["trust_level"] for r in rows]
    return min(levels, key=lambda l: _LEVEL_ORDER.get(l, 3))


async def update_trust_level(
    db: DbAdapter,
    entity_id: str,
    new_level: str,
    reason: str = "",
    verified_by: str = "",
) -> None:
    """Update trust level for an entity's latest provenance record."""
    await db.execute(
        """UPDATE knowledge_provenance
           SET trust_level = ?, verified_by = ?, verified_at = datetime('now')
           WHERE entity_id = ? AND id = (
               SELECT id FROM knowledge_provenance WHERE entity_id = ?
               ORDER BY imported_at DESC LIMIT 1
           )""",
        (new_level, verified_by, entity_id, entity_id),
    )
    if reason:
        latest = await db.query_one(
            "SELECT review_details FROM knowledge_provenance WHERE entity_id = ? ORDER BY imported_at DESC LIMIT 1",
            (entity_id,),
        )
        if latest:
            details = json.loads(latest.get("review_details") or "{}")
            details["level_change_reason"] = reason
            # SQLite UPDATE has no ORDER BY/LIMIT — target the latest
            # provenance row via subquery (same pattern as above).
            await db.execute(
                """UPDATE knowledge_provenance
                   SET review_details = ?
                   WHERE entity_id = ? AND id = (
                       SELECT id FROM knowledge_provenance WHERE entity_id = ?
                       ORDER BY imported_at DESC LIMIT 1
                   )""",
                (json.dumps(details, ensure_ascii=False), entity_id, entity_id),
            )


async def filter_by_trust(
    db: DbAdapter,
    entity_ids: list[str],
    min_level: str = LEVEL_A,
) -> list[str]:
    """Filter entity IDs to only those meeting the minimum trust threshold."""
    if not entity_ids:
        return []
    allowed = [lvl for lvl, order in _LEVEL_ORDER.items() if order <= _LEVEL_ORDER.get(min_level, 1)]
    placeholders_ids = ",".join("?" * len(entity_ids))
    placeholders_levels = ",".join("?" * len(allowed))
    rows = await db.query(
        f"""SELECT DISTINCT entity_id FROM knowledge_provenance
            WHERE entity_id IN ({placeholders_ids})
            AND trust_level IN ({placeholders_levels})""",
        tuple(entity_ids) + tuple(allowed),
    )
    return [r["entity_id"] for r in rows]


def _format_provenance(row: dict[str, Any]) -> dict[str, Any]:
    details = row.get("review_details")
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except (json.JSONDecodeError, TypeError):
            details = {}
    return {
        "id": row.get("id", ""),
        "entity_id": row.get("entity_id", ""),
        "source_type": row.get("source_type", ""),
        "source_url": row.get("source_url") or "",
        "source_title": row.get("source_title") or "",
        "source_domain": row.get("source_domain") or "",
        "trust_level": row.get("trust_level", LEVEL_C),
        "trust_score": row.get("trust_score", 0),
        "review_details": details if isinstance(details, dict) else {},
        "content_date": row.get("content_date") or "",
        "freshness_status": row.get("freshness_status", "current"),
        "imported_by": row.get("imported_by") or "",
        "imported_at": row.get("imported_at") or "",
        "verified_by": row.get("verified_by") or "",
        "verified_at": row.get("verified_at") or "",
    }


UPGRADE_THRESHOLDS = {
    LEVEL_B: {"min_helpful": 5, "max_negative": 0, "min_age_days": 7},
    LEVEL_A: {"min_helpful": 10, "max_negative": 0, "min_age_days": 30},
}


async def check_trust_upgrade(db: DbAdapter, entity_id: str) -> dict[str, Any]:
    """Check if an entity qualifies for a trust level upgrade based on feedback.

    Returns {"eligible": bool, "new_level": str, "reason": str}.
    """
    current = await get_trust_level(db, entity_id)
    if current not in (LEVEL_B, LEVEL_A):
        return {"eligible": False, "new_level": current, "reason": "当前级别不支持自动升级"}

    threshold = UPGRADE_THRESHOLDS.get(current)
    if not threshold:
        return {"eligible": False, "new_level": current, "reason": "无升级路径"}

    helpful = await db.query_one(
        "SELECT COUNT(*) AS c FROM knowledge_feedback WHERE entity_id = ? AND rating = 'helpful'",
        (entity_id,),
    )
    helpful_count = helpful["c"] if helpful else 0

    negative = await db.query_one(
        "SELECT COUNT(*) AS c FROM knowledge_feedback WHERE entity_id = ? AND rating IN ('inaccurate','report')",
        (entity_id,),
    )
    negative_count = negative["c"] if negative else 0

    age_row = await db.query_one(
        """SELECT julianday('now') - julianday(MIN(imported_at)) AS age_days
           FROM knowledge_provenance WHERE entity_id = ?""",
        (entity_id,),
    )
    age_days = age_row["age_days"] if age_row and age_row["age_days"] else 0

    if helpful_count < threshold["min_helpful"]:
        return {"eligible": False, "new_level": current,
                "reason": f"需要{threshold['min_helpful']}个好评，当前{helpful_count}"}
    if negative_count > threshold["max_negative"]:
        return {"eligible": False, "new_level": current,
                "reason": f"存在{negative_count}个差评/举报"}
    if age_days < threshold["min_age_days"]:
        return {"eligible": False, "new_level": current,
                "reason": f"需要入库{threshold['min_age_days']}天，当前{int(age_days)}天"}

    new_level = LEVEL_A if current == LEVEL_B else LEVEL_S
    await update_trust_level(
        db, entity_id, new_level,
        reason=f"自动升级：{helpful_count}好评/{negative_count}差评/入库{int(age_days)}天",
        verified_by="auto_upgrade",
    )
    logger.info("trust_upgrade: %s %s→%s (%d helpful, %d negative, %d days)",
                entity_id, current, new_level, helpful_count, negative_count, int(age_days))
    return {"eligible": True, "new_level": new_level,
            "reason": f"满足升级条件：{helpful_count}好评/{negative_count}差评/入库{int(age_days)}天"}


async def auto_upgrade_eligible_entities(db: DbAdapter) -> list[dict[str, Any]]:
    """Scan all B/A-level entities and upgrade those meeting feedback thresholds.

    Called periodically by the scheduler.
    """
    rows = await db.query(
        """SELECT DISTINCT ke.id FROM knowledge_entities ke
           JOIN knowledge_provenance kp ON kp.entity_id = ke.id
           WHERE ke.status = 'active' AND kp.trust_level IN ('B', 'A')
           AND kp.id = (
               SELECT id FROM knowledge_provenance
               WHERE entity_id = ke.id ORDER BY imported_at DESC LIMIT 1
           )"""
    )
    upgraded: list[dict[str, Any]] = []
    for row in rows:
        try:
            result = await check_trust_upgrade(db, row["id"])
            if result["eligible"]:
                upgraded.append({
                    "entity_id": row["id"],
                    "new_level": result["new_level"],
                    "reason": result["reason"],
                })
        except Exception as exc:
            logger.warning("trust_upgrade check failed for %s: %s", row.get("id"), exc)
    if upgraded:
        logger.info("trust_upgrade: %d entities upgraded", len(upgraded))
    return upgraded
