from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import get_current_user
from app.audit import log_audit
from app.database import DbAdapter, get_db
from app.models import ReminderCreate, ReminderUpdate
from app.repository import current_tenant_id, current_member_id

router = APIRouter(prefix="/api/reminders", tags=["reminders"])

CST = timezone(timedelta(hours=8))


def _parse_reminder(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    if isinstance(result.get("times"), str):
        try:
            result["times"] = json.loads(result["times"])
        except (json.JSONDecodeError, TypeError):
            result["times"] = []
    if "enabled" in result:
        result["enabled"] = bool(result["enabled"])
    return result


def _compute_slot_status(scheduled_time: str, now: datetime) -> str:
    sh, sm = scheduled_time.split(":")
    scheduled = now.replace(hour=int(sh), minute=int(sm), second=0, microsecond=0)
    delta = now - scheduled
    if delta > timedelta(hours=2):
        return "漏服"
    return "待服"


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_reminder(
    body: ReminderCreate,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    reminder_id = str(uuid.uuid4())
    user_id = current_user["id"]
    mid = current_member_id.get()
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    await db.execute(
        """INSERT INTO reminders
           (id, user_id, family_member_id, title, herb_name, formula_name, medicine_name, dosage,
            frequency, times, start_date, end_date, notes, enabled,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            reminder_id,
            user_id,
            mid,
            body.title,
            body.herb_name,
            body.formula_name,
            body.medicine_name,
            body.dosage,
            body.frequency,
            json.dumps(body.times, ensure_ascii=False),
            body.start_date,
            body.end_date,
            body.notes,
            1 if body.enabled else 0,
            now,
            now,
        ),
    )
    row = await db.query_one("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
    await log_audit(db, tenant_id=current_tenant_id.get(), user_id=user_id,
                    action="create", entity_type="reminder", entity_id=reminder_id,
                    changes={"title": body.title, "times": body.times})
    return _parse_reminder(row)


@router.get("")
async def list_reminders(
    enabled: bool | None = Query(None),
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]
    mid = current_member_id.get()
    sql = "SELECT * FROM reminders WHERE user_id = ?"
    params: list[Any] = [user_id]
    if mid:
        sql += " AND family_member_id = ?"
        params.append(mid)
    if enabled is not None:
        sql += " AND enabled = ?"
        params.append(1 if enabled else 0)
    sql += " ORDER BY created_at DESC"
    rows = await db.query(sql, tuple(params))
    return {"items": [_parse_reminder(r) for r in rows], "total": len(rows)}


@router.get("/today")
async def get_today_reminders(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]
    mid = current_member_id.get()
    now = datetime.now(CST)
    today = now.strftime("%Y-%m-%d")
    if mid:
        rows = await db.query(
            """SELECT * FROM reminders
               WHERE user_id = ? AND family_member_id = ? AND enabled = 1
                 AND start_date <= ?
                 AND (end_date IS NULL OR end_date >= ?)
               ORDER BY created_at DESC""",
            (user_id, mid, today, today),
        )
    else:
        rows = await db.query(
            """SELECT * FROM reminders
               WHERE user_id = ? AND enabled = 1
                 AND start_date <= ?
                 AND (end_date IS NULL OR end_date >= ?)
               ORDER BY created_at DESC""",
            (user_id, today, today),
        )
    # Fetch today's medication logs to determine actual status
    logs = await db.query(
        """SELECT * FROM medication_logs
           WHERE family_member_id = ? AND date = ?""",
        (user_id, today),
    )
    taken_set: set[str] = set()
    for log in logs:
        # Key by medicine_id (which stores the reminder_id) to track taken status
        taken_set.add(log["medicine_id"])

    slots: list[dict[str, Any]] = []
    for row in rows:
        reminder = _parse_reminder(row)
        for t in reminder.get("times", []):
            # If logged as taken, override computed status
            if reminder["id"] in taken_set:
                slot_status = "已服"
            else:
                slot_status = _compute_slot_status(t, now)
            slots.append({
                "reminder_id": reminder["id"],
                "title": reminder["title"],
                "herb_name": reminder.get("herb_name"),
                "formula_name": reminder.get("formula_name"),
                "medicine_name": reminder.get("medicine_name"),
                "dosage": reminder.get("dosage"),
                "notes": reminder.get("notes"),
                "time": t,
                "status": slot_status,
            })
    slots.sort(key=lambda s: s["time"])
    return {"date": today, "items": slots, "total": len(slots)}


@router.get("/history")
async def get_reminder_history(
    days: int = Query(7, ge=1, le=90),
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]
    since = (datetime.now(CST) - timedelta(days=days)).strftime("%Y-%m-%d")

    rows = await db.query(
        """SELECT ml.id, ml.date, ml.medicine_id as reminder_id, ml.taken,
                  ml.skipped_reason, ml.created_at,
                  r.title, r.herb_name, r.formula_name, r.medicine_name
           FROM medication_logs ml
           LEFT JOIN reminders r ON ml.medicine_id = r.id
           WHERE ml.family_member_id = ? AND ml.date >= ?
           ORDER BY ml.created_at DESC
           LIMIT 200""",
        (user_id, since),
    )

    items = []
    for row in rows:
        item = dict(row)
        item["taken"] = bool(item.get("taken", 0))
        items.append(item)

    taken_count = sum(1 for i in items if i["taken"])
    total = len(items)
    adherence_rate = round(taken_count / total * 100, 1) if total > 0 else 0.0

    return {
        "items": items,
        "total": total,
        "taken_count": taken_count,
        "adherence_rate": adherence_rate,
        "days": days,
    }


@router.get("/{reminder_id}")
async def get_reminder(
    reminder_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]
    row = await db.query_one(
        "SELECT * FROM reminders WHERE id = ? AND user_id = ?",
        (reminder_id, user_id),
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该提醒",
        )
    return _parse_reminder(row)


@router.put("/{reminder_id}")
async def update_reminder(
    reminder_id: str,
    body: ReminderUpdate,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]
    existing = await db.query_one(
        "SELECT * FROM reminders WHERE id = ? AND user_id = ?",
        (reminder_id, user_id),
    )
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该提醒",
        )
    set_parts: list[str] = []
    values: list[Any] = []
    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key == "times" and value is not None:
            set_parts.append("times = ?")
            values.append(json.dumps(value, ensure_ascii=False))
        elif key == "enabled" and value is not None:
            set_parts.append("enabled = ?")
            values.append(1 if value else 0)
        elif value is not None:
            set_parts.append(f"{key} = ?")
            values.append(value)
    if set_parts:
        now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
        set_parts.append("updated_at = ?")
        values.append(now)
        values.append(reminder_id)
        values.append(user_id)
        await db.execute(
            f"UPDATE reminders SET {', '.join(set_parts)} WHERE id = ? AND user_id = ?",
            tuple(values),
        )
    row = await db.query_one("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
    await log_audit(db, tenant_id=current_tenant_id.get(), user_id=user_id,
                    action="update", entity_type="reminder", entity_id=reminder_id, changes=update_data)
    return _parse_reminder(row)


@router.put("/{reminder_id}/toggle")
async def toggle_reminder(
    reminder_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]
    existing = await db.query_one(
        "SELECT * FROM reminders WHERE id = ? AND user_id = ?",
        (reminder_id, user_id),
    )
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该提醒",
        )
    new_val = 0 if existing["enabled"] else 1
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    await db.execute(
        "UPDATE reminders SET enabled = ?, updated_at = ? WHERE id = ? AND user_id = ?",
        (new_val, now, reminder_id, user_id),
    )
    row = await db.query_one("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
    await log_audit(db, tenant_id=current_tenant_id.get(), user_id=user_id,
                    action="toggle", entity_type="reminder", entity_id=reminder_id,
                    changes={"enabled": bool(new_val)})
    return _parse_reminder(row)


@router.delete("/{reminder_id}")
async def delete_reminder(
    reminder_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]
    existing = await db.query_one(
        "SELECT * FROM reminders WHERE id = ? AND user_id = ?",
        (reminder_id, user_id),
    )
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该提醒",
        )
    await db.execute(
        "DELETE FROM reminders WHERE id = ? AND user_id = ?",
        (reminder_id, user_id),
    )
    await log_audit(db, tenant_id=current_tenant_id.get(), user_id=user_id,
                    action="delete", entity_type="reminder", entity_id=reminder_id)
    return {"detail": "已删除"}


@router.post("/{reminder_id}/check-in", status_code=status.HTTP_201_CREATED)
async def check_in_reminder(
    reminder_id: str,
    body: dict,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Mark a reminder slot as taken/skipped by inserting into medication_logs."""
    user_id = current_user["id"]
    reminder = await db.query_one(
        "SELECT * FROM reminders WHERE id = ? AND user_id = ?",
        (reminder_id, user_id),
    )
    if not reminder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该提醒",
        )

    now = datetime.now(CST)
    today = now.strftime("%Y-%m-%d")
    log_id = str(uuid.uuid4())
    taken = 1 if body.get("taken", True) else 0
    date_val = body.get("date", today)

    await db.execute(
        """INSERT INTO medication_logs (id, family_member_id, date, medicine_id, taken, skipped_reason, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            log_id,
            user_id,
            date_val,
            reminder_id,
            taken,
            body.get("skipped_reason"),
            now.strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )

    row = await db.query_one("SELECT * FROM medication_logs WHERE id = ?", (log_id,))
    result = dict(row)
    if "taken" in result:
        result["taken"] = bool(result["taken"])
    await log_audit(db, tenant_id=current_tenant_id.get(), user_id=user_id,
                    action="check-in", entity_type="medication_log", entity_id=log_id,
                    changes={"reminder_id": reminder_id, "taken": bool(taken), "date": date_val})
    return result
