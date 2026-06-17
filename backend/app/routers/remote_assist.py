"""子女远程协助路由 (spec §22)。

子女可远程查看父母健康数据、接收每周摘要、设置预警阈值。
共享记录存储在 family_shares 表，角色与同意状态存储在 users.settings JSON。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.audit import log_audit
from app.database import DbAdapter, get_db
from app.repository import current_tenant_id

router = APIRouter(prefix="/api/remote-assist", tags=["remote-assist"])

CST = timezone(timedelta(hours=8))

VALID_ROLES = {"管理员", "长辈", "家属查看"}
VALID_SHARE_ROLES = {"家属查看", "管理员"}


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------

class InviteRequest(BaseModel):
    invitee_username: str = Field(min_length=2, max_length=50)
    role: str = Field(default="家属查看")


class AlertConfigRequest(BaseModel):
    missed_reminder_threshold: int | None = Field(default=None, ge=0, le=100)
    expired_medicine_alert: bool | None = None
    low_stock_threshold: int | None = Field(default=None, ge=0, le=999)


class ConsentRequest(BaseModel):
    share_consent: bool


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _parse_settings(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
    if isinstance(raw, dict):
        return raw
    return {}


async def _get_user(db: DbAdapter, user_id: str) -> dict[str, Any] | None:
    return await db.query_one("SELECT * FROM users WHERE id = ?", (user_id,))


async def _get_user_by_username(
    db: DbAdapter, username: str
) -> dict[str, Any] | None:
    return await db.query_one(
        "SELECT * FROM users WHERE username = ?", (username,)
    )


async def _update_user_settings(
    db: DbAdapter, user_id: str, settings: dict[str, Any]
) -> None:
    await db.execute(
        "UPDATE users SET settings = ?, updated_at = datetime('now') WHERE id = ?",
        (json.dumps(settings, ensure_ascii=False), user_id),
    )


async def _verify_share(
    db: DbAdapter, sharer_id: str, viewer_id: str
) -> dict[str, Any]:
    share = await db.query_one(
        """SELECT * FROM family_shares
           WHERE sharer_id = ? AND viewer_id = ? AND status = 'active'""",
        (sharer_id, viewer_id),
    )
    if not share:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权查看该用户数据，未建立共享关系",
        )
    return dict(share)


def _parse_share(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    if isinstance(result.get("alert_config"), str):
        try:
            result["alert_config"] = json.loads(result["alert_config"])
        except (json.JSONDecodeError, TypeError):
            result["alert_config"] = {}
    return result


# ---------------------------------------------------------------------------
# 同意共享 (隐私前置)
# ---------------------------------------------------------------------------

@router.put("/consent")
async def set_share_consent(
    body: ConsentRequest,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """设置数据共享同意状态 (spec §22 隐私要求)。"""
    user = await _get_user(db, current_user["id"])
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    settings = _parse_settings(user.get("settings"))
    settings["share_consent"] = body.share_consent
    settings["consent_updated_at"] = datetime.now(CST).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    await _update_user_settings(db, current_user["id"], settings)
    await log_audit(
        db,
        tenant_id=current_tenant_id.get(),
        user_id=current_user["id"],
        action="update",
        entity_type="share_consent",
        entity_id=current_user["id"],
        changes={"share_consent": body.share_consent},
    )
    return {"share_consent": body.share_consent}


@router.get("/consent")
async def get_share_consent(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询当前用户的数据共享同意状态。"""
    user = await _get_user(db, current_user["id"])
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    settings = _parse_settings(user.get("settings"))
    return {
        "share_consent": settings.get("share_consent", False),
        "role": settings.get("role", "管理员"),
    }


# ---------------------------------------------------------------------------
# 邀请家属查看
# ---------------------------------------------------------------------------

@router.post("/invite", status_code=status.HTTP_201_CREATED)
async def invite_viewer(
    body: InviteRequest,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """邀请家属查看自己的健康数据 (spec §22.1)。

    共享者（当前用户）必须已同意数据共享。
    """
    if body.role not in VALID_SHARE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"角色必须是 {VALID_SHARE_ROLES} 之一",
        )

    sharer = await _get_user(db, current_user["id"])
    if not sharer:
        raise HTTPException(status_code=404, detail="用户不存在")

    sharer_settings = _parse_settings(sharer.get("settings"))
    if not sharer_settings.get("share_consent", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="请先同意数据共享后再邀请家属",
        )

    invitee = await _get_user_by_username(db, body.invitee_username)
    if not invitee:
        raise HTTPException(status_code=404, detail="被邀请用户不存在")
    if invitee["id"] == current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="不能邀请自己",
        )

    existing = await db.query_one(
        "SELECT * FROM family_shares WHERE sharer_id = ? AND viewer_id = ?",
        (current_user["id"], invitee["id"]),
    )
    if existing:
        if existing["status"] == "active":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="该用户已是您的共享查看者",
            )
        await db.execute(
            """UPDATE family_shares
               SET status = 'active', role = ?, alert_config = '{}'
               WHERE id = ?""",
            (body.role, existing["id"]),
        )
        share = await db.query_one(
            "SELECT * FROM family_shares WHERE id = ?", (existing["id"],)
        )
    else:
        share_id = str(uuid.uuid4())
        await db.execute(
            """INSERT INTO family_shares
               (id, sharer_id, viewer_id, role, status, alert_config)
               VALUES (?, ?, ?, ?, 'active', '{}')""",
            (share_id, current_user["id"], invitee["id"], body.role),
        )
        share = await db.query_one(
            "SELECT * FROM family_shares WHERE id = ?", (share_id,)
        )

    invitee_settings = _parse_settings(invitee.get("settings"))
    if "role" not in invitee_settings or invitee_settings["role"] == "管理员":
        if body.role == "家属查看":
            invitee_settings["role"] = "家属查看"
            await _update_user_settings(db, invitee["id"], invitee_settings)

    await log_audit(
        db,
        tenant_id=current_tenant_id.get(),
        user_id=current_user["id"],
        action="create",
        entity_type="family_share",
        entity_id=share["id"],
        changes={
            "viewer": body.invitee_username,
            "role": body.role,
        },
    )
    return _parse_share(share)


@router.delete("/invite/{share_id}")
async def revoke_share(
    share_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """撤销共享关系（仅共享者可撤销）。"""
    share = await db.query_one(
        "SELECT * FROM family_shares WHERE id = ?", (share_id,)
    )
    if not share:
        raise HTTPException(status_code=404, detail="共享记录不存在")
    if share["sharer_id"] != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅共享者可撤销共享",
        )
    await db.execute(
        "UPDATE family_shares SET status = 'revoked' WHERE id = ?",
        (share_id,),
    )
    await log_audit(
        db,
        tenant_id=current_tenant_id.get(),
        user_id=current_user["id"],
        action="delete",
        entity_type="family_share",
        entity_id=share_id,
        changes={"status": "revoked"},
    )
    return {"detail": "已撤销共享"}


# ---------------------------------------------------------------------------
# 共享给我的列表
# ---------------------------------------------------------------------------

@router.get("/shared-with-me")
async def list_shared_with_me(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """列出共享数据给我的账户 (spec §22.2 远程监控面板入口)。"""
    rows = await db.query(
        """SELECT fs.*, u.display_name, u.username
           FROM family_shares fs
           JOIN users u ON fs.sharer_id = u.id
           WHERE fs.viewer_id = ? AND fs.status = 'active'
           ORDER BY fs.created_at DESC""",
        (current_user["id"],),
    )
    items = []
    for row in rows:
        item = _parse_share(row)
        items.append({
            "share_id": item["id"],
            "sharer_id": item["sharer_id"],
            "sharer_name": item.get("display_name") or item.get("username"),
            "role": item["role"],
            "alert_config": item.get("alert_config", {}),
            "created_at": item.get("created_at"),
        })
    return {"items": items, "total": len(items)}


# ---------------------------------------------------------------------------
# 健康概要
# ---------------------------------------------------------------------------

@router.get("/{user_id}/summary")
async def get_health_summary(
    user_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取共享用户的健康概要 (spec §22.2)。

    返回：用药依从率、近期预警、体质概要、漏服提醒数。
    """
    await _verify_share(db, user_id, current_user["id"])

    sharer = await _get_user(db, user_id)
    sharer_family_id = sharer["family_id"] if sharer else user_id

    now = datetime.now(CST)
    seven_days_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")

    log_rows = await db.query(
        """SELECT taken FROM medication_logs
           WHERE family_member_id = ? AND date >= ?""",
        (user_id, seven_days_ago),
    )
    taken_count = sum(1 for r in log_rows if r["taken"])
    missed_count = sum(1 for r in log_rows if not r["taken"])
    total_logs = len(log_rows)
    adherence_rate = (
        round(taken_count / total_logs * 100, 1) if total_logs > 0 else 0.0
    )

    stock_alerts = await _compute_stock_alerts(db, sharer_family_id)

    constitution_row = await db.query_one(
        """SELECT primary_type, secondary_types, assessed_at
           FROM constitution_assessments
           WHERE user_id = ?
           ORDER BY assessed_at DESC LIMIT 1""",
        (user_id,),
    )
    constitution_summary: dict[str, Any] | None = None
    if constitution_row:
        sec = constitution_row.get("secondary_types", "[]")
        if isinstance(sec, str):
            try:
                sec = json.loads(sec)
            except (json.JSONDecodeError, TypeError):
                sec = []
        constitution_summary = {
            "primary_type": constitution_row["primary_type"],
            "secondary_types": sec,
            "assessed_at": constitution_row.get("assessed_at"),
        }

    today = now.strftime("%Y-%m-%d")
    reminder_rows = await db.query(
        """SELECT * FROM reminders
           WHERE user_id = ? AND enabled = 1
             AND start_date <= ?
             AND (end_date IS NULL OR end_date >= ?)""",
        (user_id, today, today),
    )
    missed_reminder_count = 0
    for r in reminder_rows:
        times_raw = r.get("times", "[]")
        if isinstance(times_raw, str):
            try:
                times = json.loads(times_raw)
            except (json.JSONDecodeError, TypeError):
                times = []
        else:
            times = times_raw
        for t in times:
            try:
                sh, sm = t.split(":")
                scheduled = now.replace(
                    hour=int(sh), minute=int(sm), second=0, microsecond=0
                )
                if now - scheduled > timedelta(hours=2):
                    missed_reminder_count += 1
            except (ValueError, AttributeError):
                continue

    return {
        "user_id": user_id,
        "medication_adherence": {
            "rate": adherence_rate,
            "taken_7d": taken_count,
            "missed_7d": missed_count,
            "total_7d": total_logs,
        },
        "recent_alerts": stock_alerts,
        "constitution_summary": constitution_summary,
        "missed_reminders": missed_reminder_count,
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
    }


# ---------------------------------------------------------------------------
# 每周报告
# ---------------------------------------------------------------------------

@router.get("/{user_id}/weekly-report")
async def get_weekly_report(
    user_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """生成本周健康摘要 (spec §22.3)。

    内容：本周服药已服/漏服、新讨论的症状、安全预警、即将补充的药品。
    """
    await _verify_share(db, user_id, current_user["id"])

    sharer = await _get_user(db, user_id)
    sharer_family_id = sharer["family_id"] if sharer else user_id

    now = datetime.now(CST)
    week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    today = now.strftime("%Y-%m-%d")

    log_rows = await db.query(
        """SELECT taken, skipped_reason, date, created_at FROM medication_logs
           WHERE family_member_id = ? AND date >= ?""",
        (user_id, week_ago),
    )
    taken = sum(1 for r in log_rows if r["taken"])
    missed = sum(1 for r in log_rows if not r["taken"])
    adherence = round(taken / len(log_rows) * 100, 1) if log_rows else 0.0

    conv_rows = await db.query(
        """SELECT id, title, messages, created_at FROM conversations
           WHERE user_id = ? AND created_at >= ?""",
        (user_id, week_ago),
    )
    new_symptoms: list[dict[str, Any]] = []
    for c in conv_rows:
        msgs_raw = c.get("messages", "[]")
        if isinstance(msgs_raw, str):
            try:
                msgs = json.loads(msgs_raw)
            except (json.JSONDecodeError, TypeError):
                msgs = []
        else:
            msgs = msgs_raw
        for m in msgs:
            if isinstance(m, dict) and m.get("role") == "user":
                new_symptoms.append({
                    "content": (m.get("content") or "")[:100],
                    "date": c.get("created_at"),
                })

    safety_rows = await db.query(
        """SELECT changes, created_at FROM audit_log
           WHERE user_id = ? AND entity_type = 'safety_check'
             AND created_at >= ?""",
        (user_id, week_ago),
    )
    safety_alerts: list[dict[str, Any]] = []
    for s in safety_rows:
        changes_raw = s.get("changes", "{}")
        if isinstance(changes_raw, str):
            try:
                changes = json.loads(changes_raw)
            except (json.JSONDecodeError, TypeError):
                changes = {}
        else:
            changes = changes_raw
        if changes.get("safe") is False or changes.get("warnings"):
            safety_alerts.append({
                "detail": changes,
                "created_at": s.get("created_at"),
            })

    upcoming_refills = await _compute_upcoming_refills(db, sharer_family_id)

    return {
        "user_id": user_id,
        "period": {"from": week_ago, "to": today},
        "medication": {
            "taken": taken,
            "missed": missed,
            "adherence_rate": adherence,
        },
        "new_symptoms_discussed": new_symptoms[-10:],
        "safety_alerts": safety_alerts,
        "upcoming_refills": upcoming_refills,
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
    }


# ---------------------------------------------------------------------------
# 预警阈值
# ---------------------------------------------------------------------------

@router.post("/{user_id}/alert")
async def set_alert_thresholds(
    user_id: str,
    body: AlertConfigRequest,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """设置预警阈值 (spec §22.2 监控面板)。

    viewer 为被监控的 sharer 设置：漏服提醒阈值、过期药品预警等。
    """
    share = await _verify_share(db, user_id, current_user["id"])

    config: dict[str, Any] = _parse_share(share).get("alert_config", {})
    if not isinstance(config, dict):
        config = {}
    update = body.model_dump(exclude_none=True)
    config.update(update)

    await db.execute(
        "UPDATE family_shares SET alert_config = ? WHERE id = ?",
        (json.dumps(config, ensure_ascii=False), share["id"]),
    )
    await log_audit(
        db,
        tenant_id=current_tenant_id.get(),
        user_id=current_user["id"],
        action="update",
        entity_type="alert_config",
        entity_id=share["id"],
        changes=update,
    )
    return {"alert_config": config}


@router.get("/{user_id}/alerts")
async def check_alerts(
    user_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """检查预警阈值是否被触发 (spec §22.2)。"""
    share = await _verify_share(db, user_id, current_user["id"])
    config = share.get("alert_config", {})
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except (json.JSONDecodeError, TypeError):
            config = {}

    sharer = await _get_user(db, user_id)
    sharer_family_id = sharer["family_id"] if sharer else user_id

    now = datetime.now(CST)
    today = now.strftime("%Y-%m-%d")
    breached: list[dict[str, Any]] = []

    missed_threshold = config.get("missed_reminder_threshold")
    if missed_threshold is not None:
        reminder_rows = await db.query(
            """SELECT times FROM reminders
               WHERE user_id = ? AND enabled = 1
                 AND start_date <= ?
                 AND (end_date IS NULL OR end_date >= ?)""",
            (user_id, today, today),
        )
        missed_today = 0
        for r in reminder_rows:
            times_raw = r.get("times", "[]")
            if isinstance(times_raw, str):
                try:
                    times = json.loads(times_raw)
                except (json.JSONDecodeError, TypeError):
                    times = []
            else:
                times = times_raw
            for t in times:
                try:
                    sh, sm = t.split(":")
                    scheduled = now.replace(
                        hour=int(sh), minute=int(sm), second=0, microsecond=0
                    )
                    if now - scheduled > timedelta(hours=2):
                        missed_today += 1
                except (ValueError, AttributeError):
                    continue
        if missed_today >= missed_threshold:
            breached.append({
                "type": "漏服提醒",
                "severity": "warning",
                "detail": f"今日漏服 {missed_today} 次，超过阈值 {missed_threshold}",
            })

    if config.get("expired_medicine_alert"):
        expired = await db.query(
            """SELECT name, expiry_date FROM medicines
               WHERE tenant_id = ? AND expiry_date IS NOT NULL
               AND date(expiry_date) < date('now')""",
            (sharer_family_id,),
        )
        if expired:
            breached.append({
                "type": "过期药品",
                "severity": "critical",
                "detail": f"发现 {len(expired)} 个过期药品",
                "items": [{"name": r["name"], "expiry_date": r["expiry_date"]} for r in expired],
            })

    low_threshold = config.get("low_stock_threshold")
    if low_threshold is not None:
        low_stock = await db.query(
            """SELECT name, quantity FROM medicines
               WHERE tenant_id = ? AND quantity <= ?""",
            (sharer_family_id, low_threshold),
        )
        if low_stock:
            breached.append({
                "type": "库存不足",
                "severity": "warning",
                "detail": f"发现 {len(low_stock)} 个低库存药品",
                "items": [{"name": r["name"], "quantity": r["quantity"]} for r in low_stock],
            })

    return {
        "user_id": user_id,
        "breached": breached,
        "breach_count": len(breached),
        "checked_at": now.strftime("%Y-%m-%d %H:%M:%S"),
    }


# ---------------------------------------------------------------------------
# 辅助：库存预警与补货计算
# ---------------------------------------------------------------------------

async def _compute_stock_alerts(
    db: DbAdapter, family_id: str
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    expired = await db.query(
        """SELECT name, expiry_date FROM medicines
           WHERE tenant_id = ? AND expiry_date IS NOT NULL
           AND date(expiry_date) < date('now')""",
        (family_id,),
    )
    for r in expired:
        alerts.append({
            "type": "已过期",
            "name": r["name"],
            "severity": "critical",
            "detail": f"过期日期：{r['expiry_date']}",
        })
    expiring = await db.query(
        """SELECT name, expiry_date FROM medicines
           WHERE tenant_id = ? AND expiry_date IS NOT NULL
           AND date(expiry_date) <= date('now', '+7 days')
           AND date(expiry_date) >= date('now')""",
        (family_id,),
    )
    for r in expiring:
        alerts.append({
            "type": "即将过期",
            "name": r["name"],
            "severity": "warning",
            "detail": f"过期日期：{r['expiry_date']}",
        })
    low = await db.query(
        """SELECT name, quantity FROM medicines
           WHERE tenant_id = ? AND quantity <= 7
           ORDER BY quantity ASC""",
        (family_id,),
    )
    for r in low:
        alerts.append({
            "type": "库存不足",
            "name": r["name"],
            "severity": "warning",
            "detail": f"当前库存：{r['quantity']}",
        })
    return alerts


async def _compute_upcoming_refills(
    db: DbAdapter, family_id: str
) -> list[dict[str, Any]]:
    """计算需要补货的药品（库存≤7天量或即将过期）。"""
    refills: list[dict[str, Any]] = []
    low = await db.query(
        """SELECT name, quantity, expiry_date FROM medicines
           WHERE tenant_id = ? AND quantity <= 7
           ORDER BY quantity ASC""",
        (family_id,),
    )
    for r in low:
        refills.append({
            "name": r["name"],
            "quantity": r["quantity"],
            "reason": "库存不足",
        })
    expiring = await db.query(
        """SELECT name, expiry_date FROM medicines
           WHERE tenant_id = ? AND expiry_date IS NOT NULL
           AND date(expiry_date) <= date('now', '+30 days')
           AND date(expiry_date) >= date('now')""",
        (family_id,),
    )
    for r in expiring:
        refills.append({
            "name": r["name"],
            "expiry_date": r["expiry_date"],
            "reason": "即将过期",
        })
    return refills
