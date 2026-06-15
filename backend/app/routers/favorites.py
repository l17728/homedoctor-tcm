"""Favorites/Collection router — 知识收藏系统 (auth required)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import get_current_user
from app.database import DbAdapter, get_db

router = APIRouter(prefix="/api/favorites", tags=["favorites"])

CST = timezone(timedelta(hours=8))


def _parse_entry(row: dict[str, Any]) -> dict[str, Any]:
    """Parse a knowledge_entry row, converting JSON strings."""
    result = dict(row)
    if isinstance(result.get("tags"), str):
        try:
            result["tags"] = json.loads(result["tags"])
        except (json.JSONDecodeError, TypeError):
            result["tags"] = []
    if "is_starred" in result:
        result["is_starred"] = bool(result["is_starred"])
    return result


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_favorite(
    body: dict,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Create a favorite entry (herb/formula/knowledge_card/medicine)."""
    entry_type = body.get("entry_type")
    title = body.get("title")
    if not entry_type or not title:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="entry_type and title are required",
        )

    valid_types = {"herb", "formula", "knowledge_card", "medicine"}
    if entry_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"entry_type must be one of {valid_types}",
        )

    user_id = current_user["id"]
    entry_id = str(uuid.uuid4())
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")

    tags = body.get("tags", [])
    if isinstance(tags, list):
        tags = json.dumps(tags, ensure_ascii=False)
    else:
        tags = "[]"

    await db.execute(
        """INSERT INTO knowledge_entries
           (id, user_id, entry_type, title, content, summary, tags,
            category_path, source_type, source_url, is_starred, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
        (
            entry_id,
            user_id,
            entry_type,
            title,
            body.get("content"),
            body.get("summary"),
            tags,
            body.get("category_path"),
            body.get("source_type"),
            body.get("source_url"),
            now,
            now,
        ),
    )
    row = await db.query_one("SELECT * FROM knowledge_entries WHERE id = ?", (entry_id,))
    return _parse_entry(row)


@router.get("")
async def list_favorites(
    entry_type: str | None = Query(None),
    is_starred: bool | None = Query(None),
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List user's favorites with optional filters."""
    user_id = current_user["id"]
    sql = "SELECT * FROM knowledge_entries WHERE user_id = ?"
    params: list[Any] = [user_id]

    if entry_type is not None:
        sql += " AND entry_type = ?"
        params.append(entry_type)
    if is_starred is not None:
        sql += " AND is_starred = ?"
        params.append(1 if is_starred else 0)

    sql += " ORDER BY created_at DESC"
    rows = await db.query(sql, tuple(params))
    return {"items": [_parse_entry(r) for r in rows], "total": len(rows)}


@router.get("/{entry_id}")
async def get_favorite(
    entry_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get a single favorite entry."""
    user_id = current_user["id"]
    row = await db.query_one(
        "SELECT * FROM knowledge_entries WHERE id = ? AND user_id = ?",
        (entry_id, user_id),
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该收藏",
        )
    return _parse_entry(row)


@router.put("/{entry_id}")
async def update_favorite(
    entry_id: str,
    body: dict,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Update a favorite (add tags, star/unstar, etc.)."""
    user_id = current_user["id"]
    existing = await db.query_one(
        "SELECT * FROM knowledge_entries WHERE id = ? AND user_id = ?",
        (entry_id, user_id),
    )
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该收藏",
        )

    set_parts: list[str] = []
    values: list[Any] = []

    for key in ("title", "content", "summary"):
        if key in body and body[key] is not None:
            set_parts.append(f"{key} = ?")
            values.append(body[key])

    if "tags" in body and body["tags"] is not None:
        set_parts.append("tags = ?")
        values.append(json.dumps(body["tags"], ensure_ascii=False))

    if "is_starred" in body and body["is_starred"] is not None:
        set_parts.append("is_starred = ?")
        values.append(1 if body["is_starred"] else 0)

    if set_parts:
        now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
        set_parts.append("updated_at = ?")
        values.append(now)
        values.append(entry_id)
        values.append(user_id)
        await db.execute(
            f"UPDATE knowledge_entries SET {', '.join(set_parts)} WHERE id = ? AND user_id = ?",
            tuple(values),
        )

    row = await db.query_one("SELECT * FROM knowledge_entries WHERE id = ?", (entry_id,))
    return _parse_entry(row)


@router.delete("/{entry_id}")
async def delete_favorite(
    entry_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Delete a favorite entry."""
    user_id = current_user["id"]
    existing = await db.query_one(
        "SELECT * FROM knowledge_entries WHERE id = ? AND user_id = ?",
        (entry_id, user_id),
    )
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该收藏",
        )
    await db.execute(
        "DELETE FROM knowledge_entries WHERE id = ? AND user_id = ?",
        (entry_id, user_id),
    )
    return {"detail": "已删除"}


@router.post("/check")
async def check_favorite(
    body: dict,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Check if an item is already favorited."""
    user_id = current_user["id"]
    entry_type = body.get("entry_type")
    source_url = body.get("source_id") or body.get("source_url")

    if not entry_type or not source_url:
        return {"is_favorited": False}

    row = await db.query_one(
        """SELECT id FROM knowledge_entries
           WHERE user_id = ? AND entry_type = ? AND source_url = ?""",
        (user_id, entry_type, source_url),
    )
    return {"is_favorited": row is not None, "entry_id": row["id"] if row else None}
