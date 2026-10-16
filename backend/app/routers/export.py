"""Data export router — PIPL 合规数据导出 (auth required).

GET /api/export — returns ALL user data as JSON for download.

Sections: profile, medicines, reminders, constitution_assessments,
conversations, knowledge_entries, medication_logs (via family_members JOIN —
medication_logs.family_member_id references family_members.id, NOT user_id),
health_logs, medical_visits, medication_plans (with nested plan_items),
favorites (收藏/书签), share_cards.
"""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)
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
    # medication_logs.family_member_id references family_members.id — join
    # through family_members to scope by the owning user_id.
    rows = await db.query(
        "SELECT ml.*, fm.name AS family_member_name "
        "FROM medication_logs ml "
        "JOIN family_members fm ON ml.family_member_id = fm.id "
        "WHERE fm.user_id = ? ORDER BY ml.date DESC",
        (user_id,),
    )
    for r in rows:
        if "taken" in r:
            r["taken"] = bool(r["taken"])
    return rows


async def _export_health_logs(db: DbAdapter, user_id: str) -> list[dict[str, Any]]:
    rows = await db.query(
        "SELECT * FROM health_logs WHERE user_id = ? ORDER BY log_date DESC, created_at DESC",
        (user_id,),
    )
    return rows


async def _export_medical_visits(db: DbAdapter, user_id: str) -> list[dict[str, Any]]:
    rows = await db.query(
        "SELECT * FROM medical_visits WHERE user_id = ? ORDER BY visit_date DESC, created_at DESC",
        (user_id,),
    )
    for r in rows:
        r["attachments"] = _parse_json_field(r.get("attachments"), [])
    return rows


async def _export_medication_plans(db: DbAdapter, user_id: str) -> list[dict[str, Any]]:
    plans = await db.query(
        "SELECT * FROM medication_plans WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    )
    if not plans:
        return []
    items = await db.query(
        "SELECT * FROM plan_items WHERE plan_id IN "
        "(SELECT id FROM medication_plans WHERE user_id = ?) ORDER BY sort_order",
        (user_id,),
    )
    for it in items:
        it["times"] = _parse_json_field(it.get("times"), [])
    by_plan: dict[str, list[dict[str, Any]]] = {}
    for it in items:
        by_plan.setdefault(it["plan_id"], []).append(it)
    for p in plans:
        p["items"] = by_plan.get(p["id"], [])
    return plans


async def _export_favorites(db: DbAdapter, user_id: str) -> list[dict[str, Any]]:
    rows = await db.query(
        "SELECT * FROM favorites WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    )
    for r in rows:
        r["tags"] = _parse_json_field(r.get("tags"), [])
        if "is_starred" in r:
            r["is_starred"] = bool(r["is_starred"])
    return rows


async def _export_share_cards(db: DbAdapter, user_id: str) -> list[dict[str, Any]]:
    rows = await db.query(
        "SELECT * FROM share_cards WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    )
    for r in rows:
        r["card_data"] = _parse_json_field(r.get("card_data"), {})
        if "is_monthly_report" in r:
            r["is_monthly_report"] = bool(r["is_monthly_report"])
    return rows


@router.get("")
async def export_user_data(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Export ALL user data as JSON — PIPL 合规个人信息导出.

    Returns user profile, medicines, reminders, constitution assessments,
    chat conversations, knowledge entries, medication logs (via family
    members), health logs, medical visits, medication plans (with items),
    favorites (收藏/书签), and share cards.
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
    health_logs = await _export_health_logs(db, user_id)
    medical_visits = await _export_medical_visits(db, user_id)
    medication_plans = await _export_medication_plans(db, user_id)
    favorites = await _export_favorites(db, user_id)
    share_cards = await _export_share_cards(db, user_id)

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
            "health_logs": health_logs,
            "medical_visits": medical_visits,
            "medication_plans": medication_plans,
            "favorites": favorites,
            "share_cards": share_cards,
        },
    }
