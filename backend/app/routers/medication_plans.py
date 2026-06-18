from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.audit import log_audit
from app.database import DbAdapter, get_db
from app.models import (
    MedicationPlanCreate,
    MedicationPlanUpdate,
    PlanItemCreate,
)
from app.repository import current_tenant_id
from app.schedule_engine import (
    MedicationInput,
    generate_weekly_schedule,
    verify_existing_schedule,
    expert_review_schedule,
)

router = APIRouter(prefix="/api/medication-plans", tags=["medication-plans"])

CST = timezone(timedelta(hours=8))


def _now() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Auto-schedule request models
# ---------------------------------------------------------------------------

class AutoScheduleMedication(BaseModel):
    name: str = Field(min_length=1, description="药物名称")
    type: str = Field(default="中药", description="药物类型：西药/中药/中成药/中药方剂")
    dosage: str = Field(default="", description="剂量，如 1片 / 10g / 每次5ml")
    frequency: str = Field(default="每日1次", description="频次：每日1次/每日2次/每日3次/隔日1次")
    notes: str = Field(default="", description="用药备注，如 饭后吃")


class AutoScheduleRequest(BaseModel):
    medications: list[AutoScheduleMedication] = Field(
        min_length=1, description="药物列表"
    )
    user_profile: dict[str, Any] | None = Field(
        default=None, description="用户画像：{age, is_pregnant, constitution}"
    )


class VerifyScheduleRequest(BaseModel):
    days: list[dict[str, Any]] = Field(
        description="待验证的周排程，每天含 slots 列表"
    )


def _parse_plan_item(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    if isinstance(result.get("times"), str):
        try:
            result["times"] = json.loads(result["times"])
        except (json.JSONDecodeError, TypeError):
            result["times"] = []
    return result


async def _fetch_plan(db: DbAdapter, plan_id: str, user_id: str) -> dict[str, Any]:
    plan = await db.query_one(
        "SELECT * FROM medication_plans WHERE id = ? AND user_id = ?",
        (plan_id, user_id),
    )
    if not plan:
        return {}
    plan_dict = dict(plan)
    items = await db.query(
        "SELECT * FROM plan_items WHERE plan_id = ? ORDER BY sort_order ASC, rowid ASC",
        (plan_id,),
    )
    plan_dict["items"] = [_parse_plan_item(i) for i in items]
    return plan_dict


async def _generate_reminder_for_item(
    db: DbAdapter,
    plan: dict[str, Any],
    item: PlanItemCreate,
    user_id: str,
) -> str:
    """Create a reminder for a plan item and return the reminder id."""
    reminder_id = str(uuid.uuid4())
    now = _now()
    title = f"{plan['name']} - {item.medicine_name}"
    start_date = plan.get("start_date") or _today()
    enabled = 1 if plan.get("status", "active") == "active" else 0

    await db.execute(
        """INSERT INTO reminders
           (id, user_id, family_member_id, title, herb_name, formula_name, medicine_name, dosage,
            frequency, times, start_date, end_date, notes, enabled,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            reminder_id,
            user_id,
            plan.get("family_member_id"),
            title,
            None,
            None,
            item.medicine_name,
            item.dosage,
            item.frequency,
            json.dumps(item.times, ensure_ascii=False),
            start_date,
            plan.get("end_date"),
            item.notes,
            enabled,
            now,
            now,
        ),
    )
    return reminder_id


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def list_plans(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]
    rows = await db.query(
        "SELECT * FROM medication_plans WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    )
    plans = []
    for row in rows:
        plan_dict = dict(row)
        items = await db.query(
            "SELECT * FROM plan_items WHERE plan_id = ? ORDER BY sort_order ASC, rowid ASC",
            (plan_dict["id"],),
        )
        plan_dict["items"] = [_parse_plan_item(i) for i in items]
        plans.append(plan_dict)
    return {"items": plans, "total": len(plans)}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_plan(
    body: MedicationPlanCreate,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]
    plan_id = str(uuid.uuid4())
    now = _now()
    start_date = body.start_date or _today()

    await db.execute(
        """INSERT INTO medication_plans
           (id, user_id, family_member_id, name, description, status, start_date, end_date,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            plan_id,
            user_id,
            body.family_member_id,
            body.name,
            body.description,
            body.status,
            start_date,
            body.end_date,
            now,
            now,
        ),
    )

    plan_row = await db.query_one(
        "SELECT * FROM medication_plans WHERE id = ?", (plan_id,)
    )
    plan_dict = dict(plan_row)

    created_items: list[dict[str, Any]] = []
    for idx, item in enumerate(body.items):
        item_id = str(uuid.uuid4())
        reminder_id = await _generate_reminder_for_item(
            db, plan_dict, item, user_id
        )
        await db.execute(
            """INSERT INTO plan_items
               (id, plan_id, medicine_name, dosage, frequency, times, notes, sort_order, reminder_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item_id,
                plan_id,
                item.medicine_name,
                item.dosage,
                item.frequency,
                json.dumps(item.times, ensure_ascii=False),
                item.notes,
                item.sort_order if item.sort_order is not None else idx,
                reminder_id,
            ),
        )
        item_row = await db.query_one(
            "SELECT * FROM plan_items WHERE id = ?", (item_id,)
        )
        created_items.append(_parse_plan_item(dict(item_row)))

    await log_audit(
        db,
        tenant_id=current_tenant_id.get(),
        user_id=user_id,
        action="create",
        entity_type="medication_plan",
        entity_id=plan_id,
        changes={"name": body.name, "items_count": len(body.items)},
    )

    plan_dict["items"] = created_items
    return plan_dict


# ---------------------------------------------------------------------------
# Auto-schedule (intelligent scheduling engine)
# ---------------------------------------------------------------------------

@router.post("/auto-schedule")
async def auto_schedule(
    body: AutoScheduleRequest,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Generate an intelligent weekly medication schedule.

    Accepts a list of medications, runs five-layer safety checks, and returns
    an optimal weekly timetable (周一~周五) with conflict resolution,
    spacing enforcement, and human-readable reasons.
    """
    medications = [
        MedicationInput(
            name=m.name,
            type=m.type,
            dosage=m.dosage,
            frequency=m.frequency,
            notes=m.notes,
        )
        for m in body.medications
    ]

    schedule = await generate_weekly_schedule(
        db, medications, body.user_profile
    )

    await log_audit(
        db,
        tenant_id=current_tenant_id.get(),
        user_id=current_user["id"],
        action="auto_schedule",
        entity_type="medication_plan",
        entity_id="auto-schedule",
        changes={
            "medication_count": len(medications),
            "safety_verified": schedule.safety_verified,
            "conflicts": len(schedule.conflicts_found),
        },
    )

    return asdict(schedule)


@router.post("/auto-schedule/verify")
async def verify_schedule(
    body: VerifyScheduleRequest,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Verify that an existing schedule has no safety violations."""
    result = await verify_existing_schedule(db, body.model_dump())
    return result


@router.post("/auto-schedule/expert-review")
async def expert_review(
    body: dict,
    current_user: dict = Depends(get_current_user),
):
    """Multi-AI expert consensus review of a generated schedule.

    Sends the schedule to 3 LLM models (Kimi/GLM/Qwen) for independent
    safety, timing, dosage, and completeness evaluation. Requires ≥2/3
    approval for consensus_pass=True.
    """
    schedule = body.get("schedule", {})
    medications = body.get("medications", [])

    review = await expert_review_schedule(schedule, medications)

    await log_audit(
        db=None,
        tenant_id=current_tenant_id.get(),
        user_id=current_user["id"],
        action="expert_review",
        entity_type="medication_schedule",
        entity_id="expert-review",
        changes={
            "consensus_pass": review.get("consensus_pass"),
            "approval_count": review.get("approval_count"),
            "average_score": review.get("average_score"),
        },
    ) if False else None

    return review


@router.get("/{plan_id}")
async def get_plan(
    plan_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]
    plan = await _fetch_plan(db, plan_id, user_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该用药套餐",
        )
    return plan


@router.put("/{plan_id}")
async def update_plan(
    plan_id: str,
    body: MedicationPlanUpdate,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]
    existing = await db.query_one(
        "SELECT * FROM medication_plans WHERE id = ? AND user_id = ?",
        (plan_id, user_id),
    )
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该用药套餐",
        )

    update_data = body.model_dump(exclude_unset=True)
    set_parts: list[str] = []
    values: list[Any] = []
    for key, value in update_data.items():
        set_parts.append(f"{key} = ?")
        values.append(value)
    if set_parts:
        set_parts.append("updated_at = ?")
        values.append(_now())
        values.extend([plan_id, user_id])
        await db.execute(
            f"UPDATE medication_plans SET {', '.join(set_parts)} WHERE id = ? AND user_id = ?",
            tuple(values),
        )

    await log_audit(
        db,
        tenant_id=current_tenant_id.get(),
        user_id=user_id,
        action="update",
        entity_type="medication_plan",
        entity_id=plan_id,
        changes=update_data,
    )

    return await _fetch_plan(db, plan_id, user_id)


@router.delete("/{plan_id}")
async def delete_plan(
    plan_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]
    existing = await db.query_one(
        "SELECT * FROM medication_plans WHERE id = ? AND user_id = ?",
        (plan_id, user_id),
    )
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该用药套餐",
        )

    items = await db.query(
        "SELECT reminder_id FROM plan_items WHERE plan_id = ?", (plan_id,)
    )
    for item in items:
        rid = item.get("reminder_id")
        if rid:
            await db.execute("DELETE FROM reminders WHERE id = ?", (rid,))
    await db.execute("DELETE FROM plan_items WHERE plan_id = ?", (plan_id,))
    await db.execute(
        "DELETE FROM medication_plans WHERE id = ? AND user_id = ?",
        (plan_id, user_id),
    )

    await log_audit(
        db,
        tenant_id=current_tenant_id.get(),
        user_id=user_id,
        action="delete",
        entity_type="medication_plan",
        entity_id=plan_id,
        changes={"deleted_reminders": len(items)},
    )

    return {"detail": "已删除用药套餐及其关联提醒"}


@router.post("/{plan_id}/pause")
async def pause_plan(
    plan_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]
    existing = await db.query_one(
        "SELECT * FROM medication_plans WHERE id = ? AND user_id = ?",
        (plan_id, user_id),
    )
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该用药套餐",
        )

    now = _now()
    await db.execute(
        "UPDATE medication_plans SET status = 'paused', updated_at = ? WHERE id = ? AND user_id = ?",
        (now, plan_id, user_id),
    )
    items = await db.query(
        "SELECT reminder_id FROM plan_items WHERE plan_id = ?", (plan_id,)
    )
    for item in items:
        rid = item.get("reminder_id")
        if rid:
            await db.execute(
                "UPDATE reminders SET enabled = 0, updated_at = ? WHERE id = ?",
                (now, rid),
            )

    await log_audit(
        db,
        tenant_id=current_tenant_id.get(),
        user_id=user_id,
        action="pause",
        entity_type="medication_plan",
        entity_id=plan_id,
        changes={"status": "paused", "paused_reminders": len(items)},
    )

    return await _fetch_plan(db, plan_id, user_id)


@router.post("/{plan_id}/resume")
async def resume_plan(
    plan_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]
    existing = await db.query_one(
        "SELECT * FROM medication_plans WHERE id = ? AND user_id = ?",
        (plan_id, user_id),
    )
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该用药套餐",
        )

    now = _now()
    await db.execute(
        "UPDATE medication_plans SET status = 'active', updated_at = ? WHERE id = ? AND user_id = ?",
        (now, plan_id, user_id),
    )
    items = await db.query(
        "SELECT reminder_id FROM plan_items WHERE plan_id = ?", (plan_id,)
    )
    for item in items:
        rid = item.get("reminder_id")
        if rid:
            await db.execute(
                "UPDATE reminders SET enabled = 1, updated_at = ? WHERE id = ?",
                (now, rid),
            )

    await log_audit(
        db,
        tenant_id=current_tenant_id.get(),
        user_id=user_id,
        action="resume",
        entity_type="medication_plan",
        entity_id=plan_id,
        changes={"status": "active", "resumed_reminders": len(items)},
    )

    return await _fetch_plan(db, plan_id, user_id)
