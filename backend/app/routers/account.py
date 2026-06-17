"""Account router — PIPL-compliant hard deletion of all user data (spec §12.2).

Endpoints:
- GET  /api/account/preview  — preview data counts before deletion
- DELETE /api/account         — permanently erase ALL user data (PIPL §47)

The deletion is IRREVERSIBLE. All user-owned tables are hard-deleted in
dependency order (children first). The audit deletion record is preserved
as the sole compliance artifact after erasure.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.audit import log_audit
from app.auth import get_current_user
from app.database import DbAdapter, get_db

router = APIRouter(prefix="/api/account", tags=["account"])

# ---------------------------------------------------------------------------
# Tables owned by a user, grouped by the filtering key.
#   user_id-keyed   — personal data tables
#   tenant_id-keyed — family-scoped data (tenant_id == family_id, unique per user)
# ---------------------------------------------------------------------------

# (display_name, table_name, filter_column) for preview counts
_USER_TABLES: list[tuple[str, str, str]] = [
    ("conversations", "conversations", "user_id"),
    ("knowledge_entries", "knowledge_entries", "user_id"),
    ("favorites", "favorites", "user_id"),
    ("constitution_assessments", "constitution_assessments", "user_id"),
    ("user_profiles", "user_profiles", "user_id"),
    ("reminders", "reminders", "user_id"),
    ("family_members", "family_members", "user_id"),
]

_TENANT_TABLES: list[tuple[str, str]] = [
    ("medicines", "medicines"),
]


@router.get("/preview")
async def preview_account_data(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Preview the data that would be deleted for the current user.

    Returns row counts per user-owned table. Helps the user confirm
    what will be permanently erased before proceeding.
    """
    user_id = current_user["id"]
    family_id = current_user["family_id"]

    counts: dict[str, int] = {}

    for display_name, table, col in _USER_TABLES:
        row = await db.query_one(
            f"SELECT COUNT(*) AS cnt FROM {table} WHERE {col} = ?",
            (user_id,),
        )
        counts[display_name] = row["cnt"] if row else 0

    for display_name, table in _TENANT_TABLES:
        row = await db.query_one(
            f"SELECT COUNT(*) AS cnt FROM {table} WHERE tenant_id = ?",
            (family_id,),
        )
        counts[display_name] = row["cnt"] if row else 0

    # medication_logs — linked via family_members
    row = await db.query_one(
        "SELECT COUNT(*) AS cnt FROM medication_logs WHERE family_member_id IN "
        "(SELECT id FROM family_members WHERE user_id = ?)",
        (user_id,),
    )
    counts["medication_logs"] = row["cnt"] if row else 0

    # audit_log
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
    }


@router.delete("")
async def delete_account(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Permanently delete the current user's account and ALL associated data.

    PIPL §47 right to erasure — this is a HARD delete, not a soft delete.
    The operation is irreversible.

    Deletion order (children first, user record last):
      1. Log audit record (action=account_deletion) — compliance trail
      2. medication_logs (via family_members subquery)
      3. conversations
      4. knowledge_entries
      5. favorites
      6. constitution_assessments
      7. user_profiles
      8. reminders
      9. medicines (tenant-scoped)
     10. family_members
     11. audit_log (all prior entries; the deletion record survives)
     12. families
     13. users (FINAL)

    Returns 200 with deletion confirmation.
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
    # 2-10. Delete user-owned data (parameterized, user_id/tenant_id scoped)
    # ------------------------------------------------------------------

    # medication_logs — linked through family_members
    await db.execute(
        "DELETE FROM medication_logs WHERE family_member_id IN "
        "(SELECT id FROM family_members WHERE user_id = ?)",
        (user_id,),
    )

    # conversations (includes embedded messages as JSON array)
    await db.execute(
        "DELETE FROM conversations WHERE user_id = ?",
        (user_id,),
    )

    # knowledge_entries
    await db.execute(
        "DELETE FROM knowledge_entries WHERE user_id = ?",
        (user_id,),
    )

    # favorites
    await db.execute(
        "DELETE FROM favorites WHERE user_id = ?",
        (user_id,),
    )

    # constitution_assessments
    await db.execute(
        "DELETE FROM constitution_assessments WHERE user_id = ?",
        (user_id,),
    )

    # user_profiles
    await db.execute(
        "DELETE FROM user_profiles WHERE user_id = ?",
        (user_id,),
    )

    # reminders
    await db.execute(
        "DELETE FROM reminders WHERE user_id = ?",
        (user_id,),
    )

    # medicines — tenant-scoped (tenant_id == family_id, unique per user)
    await db.execute(
        "DELETE FROM medicines WHERE tenant_id = ?",
        (family_id,),
    )

    # family_members
    await db.execute(
        "DELETE FROM family_members WHERE user_id = ?",
        (user_id,),
    )

    # ------------------------------------------------------------------
    # 11. audit_log — delete all prior entries, preserve deletion record
    # ------------------------------------------------------------------
    if deletion_audit_id:
        await db.execute(
            "DELETE FROM audit_log WHERE tenant_id = ? AND id != ?",
            (family_id, deletion_audit_id),
        )
    else:
        # Fallback: keep all account_deletion entries
        await db.execute(
            "DELETE FROM audit_log WHERE tenant_id = ? AND action != 'account_deletion'",
            (family_id,),
        )

    # ------------------------------------------------------------------
    # 12. families
    # ------------------------------------------------------------------
    await db.execute(
        "DELETE FROM families WHERE owner_id = ?",
        (user_id,),
    )

    # ------------------------------------------------------------------
    # 13. users — FINAL
    # ------------------------------------------------------------------
    await db.execute(
        "DELETE FROM users WHERE id = ?",
        (user_id,),
    )

    return JSONResponse(
        status_code=200,
        content={
            "deleted": True,
            "timestamp": timestamp,
            "message": "您的账户及所有数据已永久删除",
        },
    )
