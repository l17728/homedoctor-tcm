"""Account router — PIPL-compliant hard deletion of all user data (spec §12.2).

Endpoints:
- GET  /api/account/preview  — preview data counts before deletion
- DELETE /api/account         — permanently erase ALL user data (PIPL §47)

The deletion is IRREVERSIBLE. All user-owned tables are hard-deleted in
dependency order (children first). The audit deletion record is preserved
as the sole compliance artifact after erasure.

Schema audit (app/db/schema.py — every table checked for user keys):
  user_id-keyed    : conversations, knowledge_entries, favorites (also backs
                     /api/bookmarks), constitution_assessments, user_profiles,
                     reminders, family_members, health_logs, medical_visits,
                     medication_plans, share_cards, classic_annotations,
                     classic_study_notes, knowledge_feedback,
                     user_interest_profiles, user_notes
  sharer/viewer    : family_shares (sharer_id OR viewer_id)
  tenant_id-keyed  : medicines, knowledge_entities (private entities only —
                     global rows have tenant_id NULL), entity_relationships,
                     audit_log (special: deletion record preserved)
  child tables     : medication_logs (via family_members), plan_items
                     (via medication_plans), knowledge_chunks /
                     chunk_embeddings / knowledge_provenance /
                     knowledge_conflicts (via private knowledge_entities)
SQLite foreign_keys is OFF and no ON DELETE CASCADE exists anywhere, so every
child table must be deleted explicitly, children before parents.
"""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.audit import log_audit
from app.auth import get_current_user
from app.database import DbAdapter, get_db

router = APIRouter(prefix="/api/account", tags=["account"])

# Spec §12.2 — encrypted backups still contain the erased history; it is
# disclosed to the user and must be purged as backups rotate (≤30 days).
_BACKUP_RETENTION_NOTE = "加密备份文件含历史数据，将于30天内随备份轮换删除"

# ---------------------------------------------------------------------------
# Deletion plan — single source of truth for BOTH preview counts and the
# actual DELETE. Each entry: (display_name, delete_sql, param_codes)
#   param_codes: tuple of "u" (user_id) / "t" (tenant_id == family_id)
# Every SQL MUST start with "DELETE FROM <table>" so the preview can derive
# "SELECT COUNT(*) AS cnt FROM <table>" with the identical WHERE clause.
# Order matters: children before parents (FK enforcement is OFF — nothing
# cascades, and orphans would survive if a child were forgotten).
# ---------------------------------------------------------------------------

_DELETION_PLAN: list[tuple[str, str, tuple[str, ...]]] = [
    # --- children keyed through family_members / medication_plans ---
    ("medication_logs",
     "DELETE FROM medication_logs WHERE family_member_id IN "
     "(SELECT id FROM family_members WHERE user_id = ?)",
     ("u",)),
    ("plan_items",
     "DELETE FROM plan_items WHERE plan_id IN "
     "(SELECT id FROM medication_plans WHERE user_id = ?)",
     ("u",)),
    # --- user_id-keyed personal data ---
    ("conversations", "DELETE FROM conversations WHERE user_id = ?", ("u",)),
    ("knowledge_entries", "DELETE FROM knowledge_entries WHERE user_id = ?", ("u",)),
    ("favorites", "DELETE FROM favorites WHERE user_id = ?", ("u",)),
    ("constitution_assessments",
     "DELETE FROM constitution_assessments WHERE user_id = ?", ("u",)),
    ("user_profiles", "DELETE FROM user_profiles WHERE user_id = ?", ("u",)),
    ("reminders", "DELETE FROM reminders WHERE user_id = ?", ("u",)),
    ("health_logs", "DELETE FROM health_logs WHERE user_id = ?", ("u",)),
    ("medical_visits", "DELETE FROM medical_visits WHERE user_id = ?", ("u",)),
    ("medication_plans", "DELETE FROM medication_plans WHERE user_id = ?", ("u",)),
    ("share_cards", "DELETE FROM share_cards WHERE user_id = ?", ("u",)),
    ("classic_annotations",
     "DELETE FROM classic_annotations WHERE user_id = ?", ("u",)),
    ("classic_study_notes",
     "DELETE FROM classic_study_notes WHERE user_id = ?", ("u",)),
    ("knowledge_feedback", "DELETE FROM knowledge_feedback WHERE user_id = ?", ("u",)),
    ("user_interest_profiles",
     "DELETE FROM user_interest_profiles WHERE user_id = ?", ("u",)),
    ("user_notes", "DELETE FROM user_notes WHERE user_id = ?", ("u",)),
    # --- family sharing (user may be sharer OR viewer) ---
    ("family_shares",
     "DELETE FROM family_shares WHERE sharer_id = ? OR viewer_id = ?",
     ("u", "u")),
    # --- tenant-keyed knowledge (private entities + their children) ---
    ("chunk_embeddings",
     "DELETE FROM chunk_embeddings WHERE chunk_id IN "
     "(SELECT id FROM knowledge_chunks WHERE entity_id IN "
     "(SELECT id FROM knowledge_entities WHERE tenant_id = ?))",
     ("t",)),
    ("knowledge_chunks",
     "DELETE FROM knowledge_chunks WHERE entity_id IN "
     "(SELECT id FROM knowledge_entities WHERE tenant_id = ?)",
     ("t",)),
    ("knowledge_provenance",
     "DELETE FROM knowledge_provenance WHERE entity_id IN "
     "(SELECT id FROM knowledge_entities WHERE tenant_id = ?)",
     ("t",)),
    ("knowledge_conflicts",
     "DELETE FROM knowledge_conflicts WHERE entity_id IN "
     "(SELECT id FROM knowledge_entities WHERE tenant_id = ?)",
     ("t",)),
    ("entity_relationships",
     "DELETE FROM entity_relationships WHERE tenant_id = ? "
     "OR source_entity_id IN (SELECT id FROM knowledge_entities WHERE tenant_id = ?) "
     "OR target_entity_id IN (SELECT id FROM knowledge_entities WHERE tenant_id = ?)",
     ("t", "t", "t")),
    ("knowledge_entities",
     "DELETE FROM knowledge_entities WHERE tenant_id = ?",
     ("t",)),
    # --- tenant-keyed household data ---
    ("medicines", "DELETE FROM medicines WHERE tenant_id = ?", ("t",)),
    # --- family members (after medication_logs) ---
    ("family_members", "DELETE FROM family_members WHERE user_id = ?", ("u",)),
]


def _plan_params(codes: tuple[str, ...], user_id: str, tenant_id: str) -> tuple[str, ...]:
    """Expand param codes into a concrete SQL parameter tuple."""
    return tuple(user_id if c == "u" else tenant_id for c in codes)


def _count_sql(delete_sql: str) -> str:
    """Derive the preview COUNT query from a plan DELETE statement."""
    return "SELECT COUNT(*) AS cnt" + delete_sql[len("DELETE"):]


@router.get("/preview")
async def preview_account_data(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Preview the data that would be deleted for the current user.

    Returns row counts per user-owned table — derived from the SAME
    _DELETION_PLAN that drives the actual erasure, so preview always
    matches what DELETE removes. Helps the user confirm what will be
    permanently erased before proceeding.
    """
    user_id = current_user["id"]
    family_id = current_user["family_id"]

    counts: dict[str, int] = {}

    for display_name, delete_sql, codes in _DELETION_PLAN:
        row = await db.query_one(
            _count_sql(delete_sql),
            _plan_params(codes, user_id, family_id),
        )
        counts[display_name] = row["cnt"] if row else 0

    # audit_log — all prior entries are removed; the deletion entry that is
    # logged during DELETE itself is new and therefore not counted here.
    row = await db.query_one(
        "SELECT COUNT(*) AS cnt FROM audit_log WHERE tenant_id = ?",
        (family_id,),
    )
    counts["audit_log"] = row["cnt"] if row else 0

    return {
        "user_id": user_id,
        "username": current_user.get("username"),
        "data_counts": counts,
        "total_records": sum(counts.values()),
        "note": _BACKUP_RETENTION_NOTE,
    }


@router.delete("")
async def delete_account(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Erase the account and all related rows atomically."""
    async with db.transaction():
        return await _delete_account_in_transaction(db, current_user)


async def _delete_account_in_transaction(
    db: DbAdapter, current_user: dict
):
    """Permanently delete the current user's account and ALL associated data.

    PIPL §47 right to erasure — this is a HARD delete, not a soft delete.
    The operation is irreversible.

    Deletion order (children first, user record last):
      1. Log audit record (action=account_deletion) — compliance trail
      2. Every table in _DELETION_PLAN (children before parents), covering
         medication_logs, plan_items, all user_id-keyed tables, family_shares,
         tenant-private knowledge entities and their children, medicines,
         family_members
      3. audit_log (all prior entries; the deletion record survives)
      4. families
      5. users (FINAL)

    Returns 200 with deletion confirmation and per-table deleted row counts.
    """
    user_id = current_user["id"]
    username = current_user.get("username")
    family_id = current_user["family_id"]
    timestamp = datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # 1. Audit record FIRST — compliance proof that erasure was requested
    # ------------------------------------------------------------------
    deletion_hash = await log_audit(
        db,
        tenant_id=family_id,
        user_id=user_id,
        action="account_deletion",
        entity_type="user",
        entity_id=user_id,
        changes={
            "reason": "PIPL_right_to_erasure",
            "username": username,
            "requested_at": timestamp,
        },
    )

    # Retrieve the deletion audit entry ID so we can preserve it
    deletion_entry = await db.query_one(
        "SELECT id FROM audit_log WHERE hash = ?",
        (deletion_hash,),
    )
    deletion_audit_id = deletion_entry["id"] if deletion_entry else None

    # ------------------------------------------------------------------
    # 2. Delete every user-owned table (children first). Count rows right
    #    before each DELETE so the reported statistics are exact.
    # ------------------------------------------------------------------
    deleted_counts: dict[str, int] = {}

    for display_name, delete_sql, codes in _DELETION_PLAN:
        params = _plan_params(codes, user_id, family_id)
        row = await db.query_one(_count_sql(delete_sql), params)
        deleted_counts[display_name] = row["cnt"] if row else 0
        await db.execute(delete_sql, params)

    # ------------------------------------------------------------------
    # 3. audit_log — delete all prior entries, preserve deletion record
    # ------------------------------------------------------------------
    row = await db.query_one(
        "SELECT COUNT(*) AS cnt FROM audit_log WHERE tenant_id = ?",
        (family_id,),
    )
    audit_total = row["cnt"] if row else 0
    if deletion_audit_id:
        cursor = await db.execute(
            "DELETE FROM audit_log WHERE tenant_id = ? AND id != ?",
            (family_id, deletion_audit_id),
        )
    else:
        # Fallback: keep all account_deletion entries
        cursor = await db.execute(
            "DELETE FROM audit_log WHERE tenant_id = ? AND action != 'account_deletion'",
            (family_id,),
        )
    # rows removed = prior entries (incl. the just-inserted deletion entry is
    # excluded by the WHERE) — derive from the cursor for exactness
    removed = getattr(cursor, "rowcount", None)
    deleted_counts["audit_log"] = removed if isinstance(removed, int) and removed >= 0 else max(audit_total - 1, 0)

    # ------------------------------------------------------------------
    # 4. families
    # ------------------------------------------------------------------
    cursor = await db.execute(
        "DELETE FROM families WHERE owner_id = ?",
        (user_id,),
    )
    removed = getattr(cursor, "rowcount", None)
    deleted_counts["families"] = removed if isinstance(removed, int) and removed >= 0 else 0

    # ------------------------------------------------------------------
    # 5. users — FINAL
    # ------------------------------------------------------------------
    cursor = await db.execute(
        "DELETE FROM users WHERE id = ?",
        (user_id,),
    )
    removed = getattr(cursor, "rowcount", None)
    deleted_counts["users"] = removed if isinstance(removed, int) and removed >= 0 else 0

    return JSONResponse(
        status_code=200,
        content={
            "deleted": True,
            "timestamp": timestamp,
            "message": "您的账户及所有数据已永久删除",
            "deleted_counts": deleted_counts,
            "total_deleted": sum(deleted_counts.values()),
            "note": _BACKUP_RETENTION_NOTE,
        },
    )
