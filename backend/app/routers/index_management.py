"""Index lifecycle management — TTL + hit rate + deletion recommendations.

Core principle: system NEVER auto-deletes. It scans periodically and
generates recommendations with reasons. Admin decides.
'Keep' (no action) ≠ 'Exempt' — system re-evaluates next scan unless
explicitly exempted.

Endpoints:
  GET  /api/admin/deletion-recommendations  — list with priority + reasons
  POST /api/admin/deletion-execute           — delete (admin confirmed)
  POST /api/admin/deletion-exempt            — 'don't recommend again'
  DELETE /api/admin/deletion-exempt/{id}     — remove exemption
  GET  /api/admin/deletion-exemptions        — list exemptions
  GET  /api/admin/index-stats                — index statistics
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth import get_current_user, require_admin
from app.database import DbAdapter, get_db

router = APIRouter(prefix="/api/admin", tags=["index-management"])


class DeleteRequest(BaseModel):
    chunk_ids: list[str]


class ExemptRequest(BaseModel):
    target_type: str = "chunk"
    target_id: str
    reason: str = ""


@router.get("/deletion-recommendations")
async def get_recommendations(
    days_threshold: int = Query(90, ge=1),
    min_hits: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: DbAdapter = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    """Get chunk deletion recommendations sorted by priority."""
    rows = await db.query(
        """SELECT kc.id, kc.entity_id, kc.chunk_text, kc.source_url, kc.source_type,
                  kc.hit_count, kc.last_hit_at, kc.created_at,
                  CAST((julianday('now') - julianday(kc.created_at)) AS INTEGER) AS age_days,
                  ke.title AS entity_title, ke.entity_type,
                  (SELECT trust_level FROM knowledge_provenance WHERE entity_id = kc.entity_id
                   ORDER BY imported_at DESC LIMIT 1) AS trust_level
             FROM knowledge_chunks kc
             LEFT JOIN knowledge_entities ke ON ke.id = kc.entity_id
            WHERE kc.source_type = 'external'
              AND kc.hit_count <= ?
              AND CAST((julianday('now') - julianday(kc.created_at)) AS INTEGER) > ?
              AND kc.id NOT IN (SELECT target_id FROM deletion_exemptions WHERE target_type='chunk')
            ORDER BY age_days DESC, kc.hit_count ASC
            LIMIT ?""",
        (min_hits, days_threshold, limit),
    )

    recommendations = []
    for r in rows:
        priority = _calculate_priority(r)
        text_preview = (r.get("chunk_text") or "")[:80].replace("\n", " ")
        if len(r.get("chunk_text") or "") > 80:
            text_preview += "..."

        reasons = []
        if r["age_days"] > 90:
            reasons.append(f"存活{r['age_days']}天")
        if r["hit_count"] == 0:
            reasons.append("从未被搜索命中")
        else:
            reasons.append(f"仅命中{r['hit_count']}次")
        trust = r.get("trust_level") or "C"
        if trust in ("B", "C"):
            reasons.append(f"信任等级{trust}")
        reasons.append(f"来源: {r.get('source_url') or '未知'}")

        recommendations.append({
            "chunk_id": r["id"],
            "entity_id": r.get("entity_id") or "",
            "entity_title": r.get("entity_title") or "",
            "text_preview": text_preview,
            "source_url": r.get("source_url") or "",
            "source_type": r.get("source_type", "external"),
            "age_days": r["age_days"],
            "hit_count": r["hit_count"],
            "trust_level": trust,
            "priority": priority,
            "reasons": reasons,
            "recommendation": _build_recommendation_text(r, reasons),
        })

    recommendations.sort(key=lambda x: x["priority"], reverse=True)
    return {"recommendations": recommendations, "total": len(recommendations)}


@router.post("/deletion-execute")
async def execute_deletion(
    body: DeleteRequest,
    db: DbAdapter = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    """Delete chunks — admin confirmed."""
    deleted = 0
    for chunk_id in body.chunk_ids:
        await db.execute("DELETE FROM chunk_embeddings WHERE chunk_id = ?", (chunk_id,))
        cursor = await db.execute("DELETE FROM knowledge_chunks WHERE id = ?", (chunk_id,))
        deleted += cursor.rowcount
    return {"deleted": deleted, "message": f"已删除{deleted}条索引"}


@router.post("/deletion-exempt")
async def add_exemption(
    body: ExemptRequest,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Mark: 'don't recommend deletion for this item again'."""
    import uuid
    try:
        await db.execute(
            """INSERT INTO deletion_exemptions (id, target_type, target_id, exempted_by, exempt_reason)
               VALUES (?, ?, ?, ?, ?)""",
            (f"exempt-{uuid.uuid4()}", body.target_type, body.target_id,
             current_user["id"], body.reason),
        )
    except Exception:
        return {"message": "已存在豁免标记"}
    return {"message": "已设置豁免"}


@router.delete("/deletion-exempt/{target_id}")
async def remove_exemption(
    target_id: str,
    db: DbAdapter = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    """Remove exemption — resume scanning for this item."""
    cursor = await db.execute(
        "DELETE FROM deletion_exemptions WHERE target_id = ?", (target_id,)
    )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="豁免标记不存在")
    return {"message": "已移除豁免，恢复扫描"}


@router.get("/deletion-exemptions")
async def list_exemptions(
    db: DbAdapter = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    """List all exemptions."""
    rows = await db.query("SELECT * FROM deletion_exemptions ORDER BY created_at DESC")
    return {"items": [dict(r) for r in rows], "total": len(rows)}


@router.get("/index-stats")
async def index_stats(
    db: DbAdapter = Depends(get_db),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    """Index statistics for admin dashboard."""
    total = await db.query_one("SELECT COUNT(*) AS c FROM knowledge_chunks")
    external = await db.query_one("SELECT COUNT(*) AS c FROM knowledge_chunks WHERE source_type='external'")
    embeddings = await db.query_one("SELECT COUNT(*) AS c FROM chunk_embeddings")
    zero_hit = await db.query_one("SELECT COUNT(*) AS c FROM knowledge_chunks WHERE hit_count=0 AND source_type='external'")
    stale = await db.query_one("SELECT COUNT(*) AS c FROM knowledge_chunks WHERE chunk_type='external_stale'")
    exempt = await db.query_one("SELECT COUNT(*) AS c FROM deletion_exemptions")

    avg_hit_row = await db.query_one(
        "SELECT AVG(hit_count) AS avg FROM knowledge_chunks WHERE source_type='external'"
    )

    return {
        "total_chunks": total["c"] if total else 0,
        "internal_chunks": (total["c"] if total else 0) - (external["c"] if external else 0),
        "external_chunks": external["c"] if external else 0,
        "total_embeddings": embeddings["c"] if embeddings else 0,
        "zero_hit_external": zero_hit["c"] if zero_hit else 0,
        "stale_urls": stale["c"] if stale else 0,
        "exemptions": exempt["c"] if exempt else 0,
        "avg_hit_rate": round(avg_hit_row["avg"] or 0, 2) if avg_hit_row else 0,
    }


def _calculate_priority(row: dict) -> float:
    """Calculate deletion priority 0-100 (higher = more recommended to delete)."""
    score = 0.0
    age = row.get("age_days", 0)
    score += min(age / 365, 1.0) * 30

    hits = row.get("hit_count", 0)
    score += max(0, (10 - hits) / 10) * 25

    trust = row.get("trust_level") or "C"
    trust_weight = {"S": 0, "A": 5, "B": 15, "C": 20}
    score += trust_weight.get(trust, 20)

    return round(score, 1)


def _build_recommendation_text(row: dict, reasons: list[str]) -> str:
    trust = row.get("trust_level") or "C"
    entity = row.get("entity_title") or "未知"
    return f"建议清理：信任{trust}级、{reasons[0]}、{reasons[1]}。关联实体：{entity}。精华知识已入库，外部索引可安全清理。"
