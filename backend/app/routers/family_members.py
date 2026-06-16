from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import get_current_user
from app.database import DbAdapter, get_db
from app.models import FamilyMemberCreate, FamilyMemberUpdate

router = APIRouter(prefix="/api/family-members", tags=["family-members"])

CST = timezone(timedelta(hours=8))


def _parse_member(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row)


@router.get("")
async def list_family_members(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]
    rows = await db.query(
        "SELECT * FROM family_members WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    )
    return {"items": [_parse_member(r) for r in rows], "total": len(rows)}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_family_member(
    body: FamilyMemberCreate,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    member_id = str(uuid.uuid4())
    user_id = current_user["id"]
    family_id = current_user.get("family_id") or user_id
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    await db.execute(
        """INSERT INTO family_members
           (id, family_id, user_id, name, relation, gender, date_of_birth, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            member_id,
            family_id,
            user_id,
            body.name,
            body.relation,
            body.gender,
            body.birth_date,
            now,
        ),
    )
    row = await db.query_one("SELECT * FROM family_members WHERE id = ?", (member_id,))
    return _parse_member(row)


@router.put("/{member_id}")
async def update_family_member(
    member_id: str,
    body: FamilyMemberUpdate,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]
    existing = await db.query_one(
        "SELECT * FROM family_members WHERE id = ? AND user_id = ?",
        (member_id, user_id),
    )
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该成员",
        )
    set_parts: list[str] = []
    values: list[Any] = []
    update_data = body.model_dump(exclude_unset=True)
    if "name" in update_data:
        set_parts.append("name = ?")
        values.append(update_data["name"])
    if "relation" in update_data:
        set_parts.append("relation = ?")
        values.append(update_data["relation"])
    if "gender" in update_data:
        set_parts.append("gender = ?")
        values.append(update_data["gender"])
    if "birth_date" in update_data:
        set_parts.append("date_of_birth = ?")
        values.append(update_data["birth_date"])
    if set_parts:
        values.append(member_id)
        values.append(user_id)
        await db.execute(
            f"UPDATE family_members SET {', '.join(set_parts)} WHERE id = ? AND user_id = ?",
            tuple(values),
        )
    row = await db.query_one("SELECT * FROM family_members WHERE id = ?", (member_id,))
    return _parse_member(row)


@router.delete("/{member_id}")
async def delete_family_member(
    member_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]
    existing = await db.query_one(
        "SELECT * FROM family_members WHERE id = ? AND user_id = ?",
        (member_id, user_id),
    )
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该成员",
        )
    await db.execute(
        "DELETE FROM family_members WHERE id = ? AND user_id = ?",
        (member_id, user_id),
    )
    return {"detail": "已删除"}
