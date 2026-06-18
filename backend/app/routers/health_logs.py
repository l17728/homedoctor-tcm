from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import get_current_user
from app.audit import log_audit
from app.database import DbAdapter, get_db
from app.models import HealthLogCreate, HealthLogUpdate
from app.repository import current_tenant_id, current_member_id

router = APIRouter(prefix="/api/health-logs", tags=["health-logs"])

CST = timezone(timedelta(hours=8))


def _now() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")


def _parse_log(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    return result


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_health_log(
    body: HealthLogCreate,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]
    log_id = str(uuid.uuid4())
    mid = body.family_member_id or current_member_id.get()

    existing = await db.query_one(
        "SELECT id FROM health_logs WHERE user_id = ? AND log_date = ? AND "
        "(family_member_id IS ? OR family_member_id = ?)",
        (user_id, body.log_date, mid, mid),
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{body.log_date} 已有打卡记录，请使用编辑功能",
        )

    await db.execute(
        """INSERT INTO health_logs
           (id, user_id, family_member_id, log_date,
            systolic, diastolic, blood_sugar, weight, sleep_hours, mood, notes,
            created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            log_id,
            user_id,
            mid,
            body.log_date,
            body.systolic,
            body.diastolic,
            body.blood_sugar,
            body.weight,
            body.sleep_hours,
            body.mood,
            body.notes,
            _now(),
        ),
    )
    row = await db.query_one("SELECT * FROM health_logs WHERE id = ?", (log_id,))
    await log_audit(
        db,
        tenant_id=current_tenant_id.get(),
        user_id=user_id,
        action="create",
        entity_type="health_log",
        entity_id=log_id,
        changes={"log_date": body.log_date},
    )
    return _parse_log(row)


@router.get("")
async def list_health_logs(
    days: int = Query(30, ge=1, le=365, description="最近 N 天"),
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]
    mid = current_member_id.get()
    now = datetime.now(CST)
    since = (now - timedelta(days=days)).strftime("%Y-%m-%d")

    if mid:
        rows = await db.query(
            """SELECT * FROM health_logs
               WHERE user_id = ? AND family_member_id = ? AND log_date >= ?
               ORDER BY log_date DESC, created_at DESC""",
            (user_id, mid, since),
        )
    else:
        rows = await db.query(
            """SELECT * FROM health_logs
               WHERE user_id = ? AND log_date >= ?
               ORDER BY log_date DESC, created_at DESC""",
            (user_id, since),
        )
    return {"items": [_parse_log(r) for r in rows], "total": len(rows), "days": days}


@router.get("/latest")
async def get_latest_health_log(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]
    mid = current_member_id.get()
    if mid:
        row = await db.query_one(
            """SELECT * FROM health_logs
               WHERE user_id = ? AND family_member_id = ?
               ORDER BY log_date DESC, created_at DESC LIMIT 1""",
            (user_id, mid),
        )
    else:
        row = await db.query_one(
            """SELECT * FROM health_logs
               WHERE user_id = ?
               ORDER BY log_date DESC, created_at DESC LIMIT 1""",
            (user_id,),
        )
    if not row:
        return {"item": None}
    return {"item": _parse_log(row)}


@router.get("/{log_id}")
async def get_health_log(
    log_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]
    row = await db.query_one(
        "SELECT * FROM health_logs WHERE id = ? AND user_id = ?",
        (log_id, user_id),
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该健康日志",
        )
    return _parse_log(row)


@router.put("/{log_id}")
async def update_health_log(
    log_id: str,
    body: HealthLogUpdate,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]
    existing = await db.query_one(
        "SELECT * FROM health_logs WHERE id = ? AND user_id = ?",
        (log_id, user_id),
    )
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该健康日志",
        )

    update_data = body.model_dump(exclude_unset=True)
    if "systolic" in update_data and "diastolic" not in update_data and existing.get("diastolic") is not None:
        if update_data["systolic"] is not None and update_data["systolic"] <= existing["diastolic"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="收缩压必须大于舒张压",
            )

    set_parts: list[str] = []
    values: list[Any] = []
    for key, value in update_data.items():
        set_parts.append(f"{key} = ?")
        values.append(value)
    if set_parts:
        values.append(log_id)
        values.append(user_id)
        await db.execute(
            f"UPDATE health_logs SET {', '.join(set_parts)} WHERE id = ? AND user_id = ?",
            tuple(values),
        )

    await log_audit(
        db,
        tenant_id=current_tenant_id.get(),
        user_id=user_id,
        action="update",
        entity_type="health_log",
        entity_id=log_id,
        changes=update_data,
    )
    row = await db.query_one("SELECT * FROM health_logs WHERE id = ?", (log_id,))
    return _parse_log(row)


@router.delete("/{log_id}")
async def delete_health_log(
    log_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]
    existing = await db.query_one(
        "SELECT * FROM health_logs WHERE id = ? AND user_id = ?",
        (log_id, user_id),
    )
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该健康日志",
        )
    await db.execute(
        "DELETE FROM health_logs WHERE id = ? AND user_id = ?",
        (log_id, user_id),
    )
    await log_audit(
        db,
        tenant_id=current_tenant_id.get(),
        user_id=user_id,
        action="delete",
        entity_type="health_log",
        entity_id=log_id,
    )
    return {"detail": "已删除该健康日志"}
