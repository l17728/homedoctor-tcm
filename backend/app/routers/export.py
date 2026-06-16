"""Data export router — PIPL 合规数据导出 (auth required).

GET /api/export — returns ALL user data as JSON for download.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.database import DbAdapter, get_db

router = APIRouter(prefix="/api/export", tags=["export"])


def _parse_json_field(val: Any, default: Any) -> Any:
    """Parse a JSON string field, returning default on failure."""
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return default
    if val is None:
        return default
    return val


async def _export_profile(db: DbAdapter, user_id: str) -> dict[str, Any] | None:
    row = await db.query_one(
        "SELECT * FROM user_profiles WHERE user_id = ?",
        (user_id,),
    )
    if not row:
        return None
    for field in ("allergies", "health_conditions", "constitution_secondary"):
        row[field] = _parse_json_field(row.get(field), [])
    if "is_pregnant" in row:
        row["is_pregnant"] = bool(row["is_pregnant"])
    return row


async def _export_medicines(db: DbAdapter, tenant_id: str) -> list[dict[str, Any]]:
    rows = await db.query(
        "SELECT * FROM medicines WHERE tenant_id = ? ORDER BY created_at",
        (tenant_id,),
    )
    for r in rows:
        for field in ("active_ingredients", "batches", "photos"):
            r[field] = _parse_json_field(r.get(field), [])
        for field in ("herbal_fields", "properties"):
            r[field] = _parse_json_field(r.get(field), {})
    return rows


async def _export_reminders(db: DbAdapter, user_id: str) -> list[dict[str, Any]]:
    rows = await db.query(
        "SELECT * FROM reminders WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    )
    for r in rows:
        r["times"] = _parse_json_field(r.get("times"), [])
        if "enabled" in r:
            r["enabled"] = bool(r["enabled"])
    return rows


async def _export_constitution(db: DbAdapter, user_id: str) -> list[dict[str, Any]]:
    rows = await db.query(
        "SELECT * FROM constitution_assessments WHERE user_id = ? ORDER BY assessed_at DESC",
        (user_id,),
    )
    for r in rows:
        r["results"] = _parse_json_field(r.get("results"), {})
        r["secondary_types"] = _parse_json_field(r.get("secondary_types"), [])
        r["raw_answers"] = _parse_json_field(r.get("raw_answers"), {})
    return rows


async def _export_conversations(db: DbAdapter, user_id: str) -> list[dict[str, Any]]:
    rows = await db.query(
        "SELECT * FROM conversations WHERE user_id = ? ORDER BY updated_at DESC",
        (user_id,),
    )
    for r in rows:
        r["messages"] = _parse_json_field(r.get("messages"), [])
        r["reasoning_trace"] = _parse_json_field(r.get("reasoning_trace"), [])
    return rows


async def _export_knowledge(db: DbAdapter, user_id: str) -> list[dict[str, Any]]:
    rows = await db.query(
        "SELECT * FROM knowledge_entries WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    )
    for r in rows:
        r["tags"] = _parse_json_field(r.get("tags"), [])
        if "is_starred" in r:
            r["is_starred"] = bool(r["is_starred"])
    return rows


async def _export_medication_logs(db: DbAdapter, user_id: str) -> list[dict[str, Any]]:
    rows = await db.query(
        "SELECT * FROM medication_logs WHERE family_member_id = ? ORDER BY date DESC",
        (user_id,),
    )
    for r in rows:
        if "taken" in r:
            r["taken"] = bool(r["taken"])
    return rows


@router.get("")
async def export_user_data(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Export ALL user data as JSON — PIPL 合规个人信息导出.

    Returns user profile, medicines, reminders, constitution assessments,
    chat conversations, knowledge entries, and medication logs.
    """
    user_id = current_user["id"]
    tenant_id = current_user.get("family_id", "default")

    profile = await _export_profile(db, user_id)
    medicines = await _export_medicines(db, tenant_id)
    reminders = await _export_reminders(db, user_id)
    constitution = await _export_constitution(db, user_id)
    conversations = await _export_conversations(db, user_id)
    knowledge = await _export_knowledge(db, user_id)
    medication_logs = await _export_medication_logs(db, user_id)

    return {
        "export_date": datetime.now(timezone.utc).isoformat(),
        "user": {
            "id": user_id,
            "username": current_user.get("username"),
            "family_id": tenant_id,
        },
        "data": {
            "profile": profile,
            "medicines": medicines,
            "reminders": reminders,
            "constitution_assessments": constitution,
            "conversations": conversations,
            "knowledge_entries": knowledge,
            "medication_logs": medication_logs,
        },
    }
