"""健康分享卡 & 月度家庭健康报告 router — spec §13.3 V3.

Endpoints (all require auth):
    POST   /api/share-cards/generate             — 生成分享卡 (summary/seasonal/constitution)
    GET    /api/share-cards/list                  — 历史卡片列表
    GET    /api/share-cards/{id}                  — 卡片详情
    DELETE /api/share-cards/{id}                  — 删除卡片
    POST   /api/share-cards/monthly-report        — 生成月度家庭健康报告
    GET    /api/share-cards/monthly-report/latest — 获取最近月度报告

All cards/reports are persisted so they can be listed, retrieved, and deleted.
"""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from app.auth import get_current_user
from app.database import DbAdapter, get_db
from app.share_card import (
    CARD_TYPES,
    generate_monthly_report,
    generate_share_card,
)

router = APIRouter(prefix="/api/share-cards", tags=["share-cards"])

CST = timezone(timedelta(hours=8))


async def _persist_card(
    db: DbAdapter,
    user_id: str,
    family_id: str,
    member_id: str | None,
    card_type: str,
    card_data: dict[str, Any],
    *,
    month: str | None = None,
    is_monthly: bool = False,
) -> str:
    card_id = str(uuid.uuid4())
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    await db.execute(
        """INSERT INTO share_cards
           (id, user_id, family_id, member_id, card_type, card_data, month,
            is_monthly_report, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            card_id,
            user_id,
            family_id,
            member_id,
            card_type,
            json.dumps(card_data, ensure_ascii=False),
            month,
            1 if is_monthly else 0,
            now,
        ),
    )
    return card_id


def _row_to_card(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "family_id": row["family_id"],
        "member_id": row.get("member_id"),
        "card_type": row["card_type"],
        "card_data": json.loads(row["card_data"]) if row.get("card_data") else {},
        "month": row.get("month"),
        "is_monthly_report": bool(row.get("is_monthly_report", 0)),
        "created_at": row["created_at"],
    }


# ---------------------------------------------------------------------------
# Card generation & CRUD
# ---------------------------------------------------------------------------

@router.post("/generate")
async def generate_card(
    body: dict[str, Any],
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """生成健康分享卡.

    Body: ``{"member_id": "...", "card_type": "summary|seasonal|constitution"}``

    Returns persisted card with structured ``card_data`` for frontend rendering.
    """
    card_type = body.get("card_type", "summary")
    if card_type not in CARD_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的卡片类型：{card_type}，可选值：summary、seasonal、constitution",
        )

    member_id = body.get("member_id")
    user_id = current_user["id"]
    family_id = current_user.get("family_id") or user_id

    if member_id:
        exists = await db.query_one(
            "SELECT id FROM family_members WHERE id = ? AND user_id = ?",
            (member_id, user_id),
        )
        if not exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="未找到该家庭成员",
            )

    card_data = await generate_share_card(
        db, member_id, user_id, family_id, card_type
    )

    card_id = await _persist_card(
        db, user_id, family_id, member_id, card_type, card_data
    )

    return {
        "id": card_id,
        "card_data": card_data,
    }


@router.get("/list")
async def list_cards(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """列出当前用户的历史分享卡（不含月度报告）."""
    rows = await db.query(
        "SELECT * FROM share_cards "
        "WHERE user_id = ? AND is_monthly_report = 0 "
        "ORDER BY created_at DESC",
        (current_user["id"],),
    )
    items = [_row_to_card(r) for r in rows]
    return {"items": items, "total": len(items)}


@router.get("/{card_id}")
async def get_card(
    card_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取单张卡片详情."""
    row = await db.query_one(
        "SELECT * FROM share_cards WHERE id = ? AND user_id = ?",
        (card_id, current_user["id"]),
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该分享卡",
        )
    return _row_to_card(row)


@router.delete("/{card_id}")
async def delete_card(
    card_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """删除一张分享卡."""
    row = await db.query_one(
        "SELECT id FROM share_cards WHERE id = ? AND user_id = ?",
        (card_id, current_user["id"]),
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该分享卡",
        )
    await db.execute(
        "DELETE FROM share_cards WHERE id = ? AND user_id = ?",
        (card_id, current_user["id"]),
    )
    return {"detail": "已删除"}


# ---------------------------------------------------------------------------
# Monthly Family Health Report
# ---------------------------------------------------------------------------

@router.post("/monthly-report")
async def create_monthly_report(
    body: dict[str, Any] = None,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """生成月度家庭健康报告.

    Body (all optional):
        ``{"month": "2026-06", "member_ids": ["id1", "id2"]}``

    - 无 month → 当前月
    - 无 member_ids → 全部家庭成员
    """
    body = body or {}
    user_id = current_user["id"]
    family_id = current_user.get("family_id") or user_id

    month = body.get("month")
    if month:
        try:
            y, m = month.split("-")
            int(y)
            int(m)
            month = f"{int(y):04d}-{int(m):02d}"
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无效的月份格式：{month}，请使用 YYYY-MM 格式",
            )

    member_ids = body.get("member_ids")
    if member_ids is not None:
        if not isinstance(member_ids, list):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="member_ids 必须是数组",
            )
        for mid in member_ids:
            exists = await db.query_one(
                "SELECT id FROM family_members WHERE id = ? AND user_id = ?",
                (mid, user_id),
            )
            if not exists:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"未找到家庭成员：{mid}",
                )

    report = await generate_monthly_report(
        db, member_ids, user_id, family_id, month
    )

    resolved_month = report["month"]
    report_id = await _persist_card(
        db,
        user_id,
        family_id,
        None,
        "monthly_report",
        report,
        month=resolved_month,
        is_monthly=True,
    )

    return {
        "id": report_id,
        "report_data": report,
        "members": report.get("members", []),
    }


@router.get("/monthly-report/latest")
async def get_latest_monthly_report(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取最近一次月度家庭健康报告."""
    row = await db.query_one(
        "SELECT * FROM share_cards "
        "WHERE user_id = ? AND is_monthly_report = 1 "
        "ORDER BY created_at DESC LIMIT 1",
        (current_user["id"],),
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="暂无月度报告，请先生成",
        )
    return _row_to_card(row)
