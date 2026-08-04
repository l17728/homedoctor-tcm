"""Bookmarks router — 多态收藏 + 标签溯源 + 合集 (spec §7.5).

Enhanced bookmark system layered on top of the existing ``favorites`` table.
No DDL changes — all bookmark types and collections are stored in ``favorites``:

- ``entry_type`` = herb / formula / therapy / knowledge / external → bookmark
- ``entry_type`` = collection → 合集; ``content`` stores member bookmark IDs as JSON
- ``source_type`` tracks provenance: chat / herb_detail / search / manual ...
- ``tags`` stores a JSON array for multi-tag filtering (AND / OR)

All text values are Chinese domain language (spec §1.7).
"""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import get_current_user
from app.database import DbAdapter, get_db

router = APIRouter(prefix="/api/bookmarks", tags=["bookmarks"])

CST = timezone(timedelta(hours=8))

VALID_BOOKMARK_TYPES = {"herb", "formula", "therapy", "knowledge", "external"}
VALID_SOURCES = {
    "chat", "herb_detail", "formula_detail", "therapy_detail",
    "search", "manual", "comparison",
}
COLLECTION_TYPE = "collection"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")


def _parse_bookmark(row: dict[str, Any]) -> dict[str, Any]:
    """Parse a favorites row, converting JSON strings to Python objects."""
    result = dict(row)
    if isinstance(result.get("tags"), str):
        try:
            result["tags"] = json.loads(result["tags"])
        except (json.JSONDecodeError, TypeError):
            result["tags"] = []
    if not isinstance(result.get("tags"), list):
        result["tags"] = []
    if isinstance(result.get("content"), str) and result.get("entry_type") == COLLECTION_TYPE:
        try:
            result["content"] = json.loads(result["content"])
        except (json.JSONDecodeError, TypeError):
            result["content"] = []
    if "is_starred" in result:
        result["is_starred"] = bool(result["is_starred"])
    return result


def _parse_tags(raw: Any) -> str:
    if isinstance(raw, list):
        return json.dumps(raw, ensure_ascii=False)
    return "[]"


# ---------------------------------------------------------------------------
# Bookmark list + create (root paths — no conflict with /{bookmark_id})
# ---------------------------------------------------------------------------

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_bookmark(
    body: dict,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """创建书签 — herb / formula / therapy / knowledge / external."""
    bookmark_type = body.get("entry_type") or body.get("type")
    title = body.get("title")

    if not bookmark_type or not title:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="entry_type 和 title 为必填项",
        )

    if bookmark_type not in VALID_BOOKMARK_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"entry_type 必须是 {sorted(VALID_BOOKMARK_TYPES)} 之一",
        )

    user_id = current_user["id"]
    bookmark_id = str(uuid.uuid4())
    source_type = body.get("source_type", "manual")
    if source_type not in VALID_SOURCES:
        source_type = "manual"

    await db.execute(
        """INSERT INTO favorites
           (id, user_id, entry_type, entry_id, title, content, tags,
            source_type, is_starred, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            bookmark_id, user_id, bookmark_type,
            body.get("entry_id"), title, body.get("content"),
            _parse_tags(body.get("tags", [])),
            source_type,
            1 if body.get("is_starred") else 0,
            _now(), _now(),
        ),
    )

    row = await db.query_one("SELECT * FROM favorites WHERE id = ?", (bookmark_id,))
    return _parse_bookmark(row)


@router.get("")
async def list_bookmarks(
    entry_type: str | None = Query(None, description="按类型筛选"),
    is_starred: bool | None = Query(None, description="只看星标"),
    tags: str | None = Query(None, description="逗号分隔标签列表"),
    tag_logic: str = Query("OR", description="标签逻辑: OR 或 AND"),
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """列出当前用户的书签，支持类型 / 星标 / 标签 (AND|OR) 筛选."""
    user_id = current_user["id"]
    sql = "SELECT * FROM favorites WHERE user_id = ? AND entry_type != ?"
    params: list[Any] = [user_id, COLLECTION_TYPE]

    if entry_type is not None:
        if entry_type not in VALID_BOOKMARK_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"entry_type 必须是 {sorted(VALID_BOOKMARK_TYPES)} 之一",
            )
        sql += " AND entry_type = ?"
        params.append(entry_type)

    if is_starred is not None:
        sql += " AND is_starred = ?"
        params.append(1 if is_starred else 0)

    sql += " ORDER BY created_at DESC"
    rows = await db.query(sql, tuple(params))
    bookmarks = [_parse_bookmark(r) for r in rows]

    if tags:
        requested_tags = [t.strip() for t in tags.split(",") if t.strip()]
        if requested_tags:
            filtered: list[dict[str, Any]] = []
            for bm in bookmarks:
                bm_tags = set(bm.get("tags", []))
                if tag_logic.upper() == "AND":
                    if all(t in bm_tags for t in requested_tags):
                        filtered.append(bm)
                else:
                    if any(t in bm_tags for t in requested_tags):
                        filtered.append(bm)
            bookmarks = filtered

    return {"items": bookmarks, "total": len(bookmarks)}


# ---------------------------------------------------------------------------
# Static sub-paths — MUST be before /{bookmark_id} to avoid shadowing
# ---------------------------------------------------------------------------

@router.post("/check")
async def check_bookmark(
    body: dict,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """检查某实体是否已被收藏."""
    user_id = current_user["id"]
    entry_type = body.get("entry_type")
    entry_id = body.get("entry_id")

    if not entry_type or not entry_id:
        return {"is_bookmarked": False}

    row = await db.query_one(
        """SELECT id FROM favorites
           WHERE user_id = ? AND entry_type = ? AND entry_id = ?
             AND entry_type != ?""",
        (user_id, entry_type, entry_id, COLLECTION_TYPE),
    )
    return {"is_bookmarked": row is not None, "bookmark_id": row["id"] if row else None}


@router.post("/collections", status_code=status.HTTP_201_CREATED)
async def create_collection(
    body: dict,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """创建合集 — 书签的逻辑分组."""
    title = body.get("title")
    if not title:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="title 为必填项",
        )

    user_id = current_user["id"]
    collection_id = str(uuid.uuid4())
    initial_members = body.get("bookmark_ids", [])
    if not isinstance(initial_members, list):
        initial_members = []

    await db.execute(
        """INSERT INTO favorites
           (id, user_id, entry_type, entry_id, title, content, tags,
            source_type, is_starred, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            collection_id, user_id, COLLECTION_TYPE, None,
            title,
            json.dumps(initial_members, ensure_ascii=False),
            _parse_tags(body.get("tags", [])),
            "manual",
            1 if body.get("is_starred") else 0,
            _now(), _now(),
        ),
    )

    row = await db.query_one("SELECT * FROM favorites WHERE id = ?", (collection_id,))
    return _parse_bookmark(row)


@router.get("/collections")
async def list_collections(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """列出当前用户的所有合集，含成员数量."""
    user_id = current_user["id"]
    rows = await db.query(
        "SELECT * FROM favorites WHERE user_id = ? AND entry_type = ? ORDER BY created_at DESC",
        (user_id, COLLECTION_TYPE),
    )
    collections = []
    for r in rows:
        parsed = _parse_bookmark(r)
        members = parsed.get("content", []) if isinstance(parsed.get("content"), list) else []
        parsed["member_count"] = len(members)
        collections.append(parsed)
    return {"items": collections, "total": len(collections)}


@router.get("/collections/{collection_id}")
async def get_collection(
    collection_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取合集详情，含完整成员书签."""
    user_id = current_user["id"]
    row = await db.query_one(
        "SELECT * FROM favorites WHERE id = ? AND user_id = ? AND entry_type = ?",
        (collection_id, user_id, COLLECTION_TYPE),
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该合集",
        )

    collection = _parse_bookmark(row)
    member_ids = collection.get("content", [])
    if not isinstance(member_ids, list):
        member_ids = []

    members: list[dict[str, Any]] = []
    for mid in member_ids:
        bm = await db.query_one(
            "SELECT * FROM favorites WHERE id = ? AND user_id = ?",
            (mid, user_id),
        )
        if bm:
            members.append(_parse_bookmark(bm))

    collection["members"] = members
    collection["member_count"] = len(members)
    return collection


@router.post("/collections/{collection_id}/items")
async def add_to_collection(
    collection_id: str,
    body: dict,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """向合集添加书签（支持批量）."""
    user_id = current_user["id"]
    col = await db.query_one(
        "SELECT * FROM favorites WHERE id = ? AND user_id = ? AND entry_type = ?",
        (collection_id, user_id, COLLECTION_TYPE),
    )
    if not col:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该合集",
        )

    bookmark_ids = body.get("bookmark_ids", [])
    if not isinstance(bookmark_ids, list):
        bookmark_ids = [bookmark_ids] if bookmark_ids else []
    if not bookmark_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="bookmark_ids 为必填项",
        )

    try:
        members: list[str] = (
            json.loads(col["content"]) if isinstance(col["content"], str) else col["content"]
        )
    except (json.JSONDecodeError, TypeError):
        members = []
    if not isinstance(members, list):
        members = []

    added: list[str] = []
    for bid in bookmark_ids:
        bm = await db.query_one(
            "SELECT id FROM favorites WHERE id = ? AND user_id = ? AND entry_type != ?",
            (bid, user_id, COLLECTION_TYPE),
        )
        if bm and bid not in members:
            members.append(bid)
            added.append(bid)

    await db.execute(
        "UPDATE favorites SET content = ?, updated_at = ? WHERE id = ?",
        (json.dumps(members, ensure_ascii=False), _now(), collection_id),
    )

    return {
        "collection_id": collection_id,
        "added": added,
        "total_members": len(members),
    }


@router.delete("/collections/{collection_id}/items/{bookmark_id}")
async def remove_from_collection(
    collection_id: str,
    bookmark_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """从合集中移除单个书签."""
    user_id = current_user["id"]
    col = await db.query_one(
        "SELECT * FROM favorites WHERE id = ? AND user_id = ? AND entry_type = ?",
        (collection_id, user_id, COLLECTION_TYPE),
    )
    if not col:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该合集",
        )

    try:
        members: list[str] = (
            json.loads(col["content"]) if isinstance(col["content"], str) else col["content"]
        )
    except (json.JSONDecodeError, TypeError):
        members = []

    members = [m for m in members if m != bookmark_id]

    await db.execute(
        "UPDATE favorites SET content = ?, updated_at = ? WHERE id = ?",
        (json.dumps(members, ensure_ascii=False), _now(), collection_id),
    )

    return {
        "collection_id": collection_id,
        "removed": bookmark_id,
        "total_members": len(members),
    }


@router.delete("/collections/{collection_id}")
async def delete_collection(
    collection_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """删除合集（不删除其中的书签本身）."""
    user_id = current_user["id"]
    existing = await db.query_one(
        "SELECT * FROM favorites WHERE id = ? AND user_id = ? AND entry_type = ?",
        (collection_id, user_id, COLLECTION_TYPE),
    )
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该合集",
        )

    await db.execute(
        "DELETE FROM favorites WHERE id = ? AND user_id = ?",
        (collection_id, user_id),
    )
    return {"detail": "合集已删除"}


# ---------------------------------------------------------------------------
# Parameterized routes — MUST come last
# ---------------------------------------------------------------------------

@router.get("/{bookmark_id}")
async def get_bookmark(
    bookmark_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取单个书签详情."""
    user_id = current_user["id"]
    row = await db.query_one(
        "SELECT * FROM favorites WHERE id = ? AND user_id = ?",
        (bookmark_id, user_id),
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该书签",
        )
    return _parse_bookmark(row)


@router.put("/{bookmark_id}")
async def update_bookmark(
    bookmark_id: str,
    body: dict,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """更新书签的标签、备注、星标状态."""
    user_id = current_user["id"]
    existing = await db.query_one(
        "SELECT * FROM favorites WHERE id = ? AND user_id = ? AND entry_type != ?",
        (bookmark_id, user_id, COLLECTION_TYPE),
    )
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该书签",
        )

    set_parts: list[str] = []
    values: list[Any] = []

    for key in ("title", "content"):
        if key in body and body[key] is not None:
            set_parts.append(f"{key} = ?")
            values.append(body[key])

    if "tags" in body and body["tags"] is not None:
        set_parts.append("tags = ?")
        values.append(_parse_tags(body["tags"]))

    if "is_starred" in body and body["is_starred"] is not None:
        set_parts.append("is_starred = ?")
        values.append(1 if body["is_starred"] else 0)

    if "source_type" in body and body["source_type"] is not None:
        set_parts.append("source_type = ?")
        values.append(body["source_type"])

    if set_parts:
        set_parts.append("updated_at = ?")
        values.append(_now())
        values.append(bookmark_id)
        values.append(user_id)
        await db.execute(
            f"UPDATE favorites SET {', '.join(set_parts)} WHERE id = ? AND user_id = ?",
            tuple(values),
        )

    row = await db.query_one("SELECT * FROM favorites WHERE id = ?", (bookmark_id,))
    return _parse_bookmark(row)


@router.delete("/{bookmark_id}")
async def delete_bookmark(
    bookmark_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """删除书签，同时从所有合集中移除引用."""
    user_id = current_user["id"]
    existing = await db.query_one(
        "SELECT * FROM favorites WHERE id = ? AND user_id = ? AND entry_type != ?",
        (bookmark_id, user_id, COLLECTION_TYPE),
    )
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该书签",
        )

    await db.execute(
        "DELETE FROM favorites WHERE id = ? AND user_id = ?",
        (bookmark_id, user_id),
    )

    collections = await db.query(
        "SELECT id, content FROM favorites WHERE user_id = ? AND entry_type = ?",
        (user_id, COLLECTION_TYPE),
    )
    for col in collections:
        try:
            members = json.loads(col["content"]) if isinstance(col["content"], str) else col["content"]
        except (json.JSONDecodeError, TypeError):
            members = []
        if bookmark_id in members:
            members = [m for m in members if m != bookmark_id]
            await db.execute(
                "UPDATE favorites SET content = ?, updated_at = ? WHERE id = ?",
                (json.dumps(members, ensure_ascii=False), _now(), col["id"]),
            )

    return {"detail": "已删除"}
