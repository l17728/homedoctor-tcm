from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.audit import log_audit
from app.config import settings
from app.database import DbAdapter
from app.knowledge_feeder import run_feeder_scan
from app.notify import send_notify
from app.push_service import send_user_push

logger = logging.getLogger(__name__)

_feeder_lock = asyncio.Lock()

# --- feeder 失败退避：失败后 1h 重试，再失败 4h；连续 3 次失败推送告警 ---
FEEDER_RETRY_DELAYS_HOURS: tuple[float, ...] = (1.0, 4.0)
FEEDER_FAILURES_BEFORE_NOTIFY = 3

# --- 每日维护阈值 ---
DISK_WARN_PERCENT = 85.0
BACKUP_MAX_AGE_HOURS = 48.0
CONVERSATION_TTL_DAYS = 30  # 对话保留期（spec §4.1）

# --- 每周摘要：周日晚（本地时间）预生成 ---
WEEKLY_DIGEST_HOUR = 20
try:
    WEEKLY_DIGEST_TIMEZONE = ZoneInfo("Asia/Shanghai")
except ZoneInfoNotFoundError:
    # Windows Python installations may not ship an IANA database. China has
    # used UTC+08:00 without DST since 1991, so this fallback stays equivalent.
    WEEKLY_DIGEST_TIMEZONE = timezone(timedelta(hours=8), "Asia/Shanghai")

# start_scheduler 附带创建的辅助任务（每日维护 + 每周摘要）
_aux_tasks: list[asyncio.Task] = []


def _cancel_task_safely(task: asyncio.Task) -> None:
    """Cancel a task without letting a stale/closed-loop task break the caller."""
    try:
        task.cancel()
    except RuntimeError:
        pass


async def _run_feeder_safe(db: DbAdapter) -> bool:
    """Run one feeder scan under the re-entrance lock. Returns True on success."""
    async with _feeder_lock:
        try:
            result = await run_feeder_scan(db, max_feeds=10)
            logger.info("feeder scan complete: %s", result)
            return True
        except Exception:
            logger.exception("feeder scan failed")
            return False


async def _feeder_loop(db: DbAdapter, interval_hours: float) -> None:
    # Run a first scan shortly after startup instead of sleeping a full
    # interval first: on machines that restart daily (typical local Windows
    # deployment) a sleep-first loop would NEVER fire. The short delay lets
    # app startup finish; the lock prevents overlap with a manual scan.
    await asyncio.sleep(60)
    consecutive_failures = 0
    notified = False
    while True:
        if await _run_feeder_safe(db):
            consecutive_failures = 0
            notified = False
            await asyncio.sleep(interval_hours * 3600)
            continue
        consecutive_failures += 1
        logger.warning(
            "feeder scan failed (%d consecutive); backing off before retry",
            consecutive_failures,
        )
        if consecutive_failures >= FEEDER_FAILURES_BEFORE_NOTIFY and not notified:
            await send_notify(
                "巡检 Agent 连续失败",
                f"知识巡检已连续失败 {consecutive_failures} 次"
                f"（重试间隔 1h→4h 退避），请查看应用日志排查 LLM/网络。",
            )
            notified = True  # 同一失败 streak 只告警一次，成功后重置
        # 退避：第 1 次失败等 1h 重试，之后每次等 4h
        delay_hours = (
            FEEDER_RETRY_DELAYS_HOURS[0]
            if consecutive_failures == 1
            else FEEDER_RETRY_DELAYS_HOURS[-1]
        )
        await asyncio.sleep(delay_hours * 3600)


# ---------------------------------------------------------------------------
# 每日维护：磁盘水位 / 备份新鲜度 / 对话 TTL 清理
# ---------------------------------------------------------------------------

def _data_dir() -> Path:
    """数据库所在目录（与 backup.py 的 _data_dir 同一约定；:memory: 时用 data/）。"""
    db_path = Path(settings.DATABASE_URL)
    if db_path == Path(":memory:"):
        return Path("data")
    return db_path.parent


async def _check_disk_watermark(
    path: Path, threshold_percent: float = DISK_WARN_PERCENT
) -> bool:
    """磁盘水位检查：使用率超过阈值即告警。返回 True=水位正常。"""
    try:
        usage = shutil.disk_usage(str(path))
    except OSError as exc:
        logger.warning("disk watermark check failed for %s: %s", path, exc)
        return True
    percent = usage.used / usage.total * 100 if usage.total else 0.0
    if percent > threshold_percent:
        logger.warning("磁盘水位 %.1f%% 超过阈值 %.1f%%: %s", percent, threshold_percent, path)
        await send_notify(
            "磁盘水位告警",
            f"磁盘使用率 {percent:.1f}%（阈值 {threshold_percent:g}%），路径 {path}。"
            "请尽快清理空间，避免 SQLite 写满损坏数据库。",
        )
        return False
    return True


async def _check_backup_freshness(
    data_dir: Path, max_age_hours: float = BACKUP_MAX_AGE_HOURS
) -> bool:
    """备份新鲜度检查：data 目录最新 backup_*.db* 超过 48h（或不存在）即提醒。"""
    configured = os.environ.get("HOMEDOCTOR_BACKUP_DIR")
    backup_dirs = [Path(configured)] if configured else []
    backup_dirs.append(data_dir)
    candidates = [
        path
        for directory in dict.fromkeys(backup_dirs)
        if directory.is_dir()
        for path in directory.glob("backup_*.db*")
    ]
    if not candidates:
        logger.warning("no backup files found under %s", data_dir)
        await send_notify(
            "备份新鲜度提醒",
            f"data 目录 {data_dir} 下没有任何 backup_*.db* 备份文件，"
            "请立即配置定时备份（参见 docs/DEPLOYMENT.md）。",
        )
        return False
    try:
        latest_mtime = max(p.stat().st_mtime for p in candidates)
    except OSError as exc:
        logger.warning("backup freshness stat failed: %s", exc)
        return True
    age_hours = (time.time() - latest_mtime) / 3600
    if age_hours > max_age_hours:
        logger.warning(
            "latest backup under %s is %.1fh old (threshold %.0fh)",
            data_dir, age_hours, max_age_hours,
        )
        await send_notify(
            "备份新鲜度提醒",
            f"最新备份已 {age_hours:.0f} 小时未更新（阈值 {max_age_hours:.0f}h），"
            f"路径 {data_dir}。请检查定时备份任务是否正常。",
        )
        return False
    return True


async def _cleanup_conversation_ttl(db: DbAdapter, days: int = CONVERSATION_TTL_DAYS) -> int:
    """删除早于 N 天的对话（spec §4.1 保留期）。返回删除行数。

    注：消息以 JSON 内联在 conversations.messages 列（schema 无子表引用
    conversations，FK 已核实），单条 DELETE 即连同消息一起清理；若未来
    增加消息子表，必须先删子表再删 conversations（外键顺序）。
    """
    cursor = await db.execute(
        "DELETE FROM conversations WHERE created_at < datetime('now', ?)",
        (f"-{days} days",),
    )
    removed = cursor.rowcount if cursor is not None else 0
    if removed:
        logger.info("conversation TTL cleanup: removed %d rows older than %dd", removed, days)
    return removed


async def _run_daily_maintenance(db: DbAdapter, data_dir: Path | None = None) -> None:
    """每日维护任务集合（每项独立兜底，单项失败不影响其余）。"""
    directory = data_dir if data_dir is not None else _data_dir()
    try:
        await _check_disk_watermark(directory)
    except Exception:
        logger.exception("disk watermark check crashed")
    try:
        await _check_backup_freshness(directory)
    except Exception:
        logger.exception("backup freshness check crashed")
    try:
        await _cleanup_conversation_ttl(db)
    except Exception:
        logger.exception("conversation TTL cleanup crashed")


async def _daily_loop(db: DbAdapter) -> None:
    # 首轮在启动后不久执行（本地部署常每日重启，sleep-24h 会永远错过），
    # 之后每 24h 一轮。
    await asyncio.sleep(120)
    while True:
        await _run_daily_maintenance(db)
        await asyncio.sleep(24 * 3600)


# ---------------------------------------------------------------------------
# 每周摘要预生成（周日晚）
# ---------------------------------------------------------------------------

def _seconds_until_next_sunday_evening(
    now: datetime | None = None, hour: int = WEEKLY_DIGEST_HOUR
) -> float:
    """Seconds until Sunday at ``hour`` in the product's China timezone."""
    if now is None:
        now = datetime.now(WEEKLY_DIGEST_TIMEZONE)
    elif now.tzinfo is None:
        # Keep deterministic callers/tests ergonomic without inheriting the
        # host/container's timezone configuration.
        now = now.replace(tzinfo=WEEKLY_DIGEST_TIMEZONE)
    else:
        now = now.astimezone(WEEKLY_DIGEST_TIMEZONE)
    days_ahead = (6 - now.weekday()) % 7  # Monday=0 ... Sunday=6
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(
        days=days_ahead
    )
    if target <= now:
        target += timedelta(days=7)
    return (target - now).total_seconds()


async def _generate_weekly_digests(db: DbAdapter) -> int:
    """Create a seven-day activity digest for each active family share."""
    shares = await db.query(
        "SELECT DISTINCT sharer_id, viewer_id FROM family_shares WHERE status = 'active'"
    )
    count = 0
    for share in shares:
        viewer = await db.query_one(
            "SELECT family_id FROM users WHERE id = ?", (share["viewer_id"],)
        )
        tenant_id = (viewer or {}).get("family_id") or "default"
        activity = await db.query(
            """SELECT title, created_at FROM conversations
               WHERE user_id = ? AND datetime(created_at) >= datetime('now', '-7 days')
               ORDER BY datetime(created_at) DESC LIMIT 20""",
            (share["sharer_id"],),
        )
        titles = [str(item.get("title") or "未命名咨询")[:120] for item in activity]
        summary = (
            f"过去7天有{len(activity)}次健康咨询。"
            + ("最近主题：" + "、".join(titles[:5]) + "。" if titles else "")
        )
        await log_audit(
            db,
            tenant_id=tenant_id,
            user_id=share["viewer_id"],
            action="create",
            entity_type="notification",
            entity_id=f"weekly_digest:{share['sharer_id']}",
            changes={
                "title": "本周健康摘要已生成",
                "sharer_id": share["sharer_id"],
                "period_days": 7,
                "consultation_count": len(activity),
                "recent_topics": titles[:5],
                "summary": summary,
                "target": "/remote-assist",
            },
        )
        try:
            await send_user_push(db, share["viewer_id"], "本周健康摘要", summary, "/remote-assist")
        except Exception:
            logger.exception("weekly digest Web Push failed for viewer %s", share["viewer_id"])
        count += 1
    if count:
        logger.info("weekly digest notifications created for %d active shares", count)
    return count


async def _weekly_loop(db: DbAdapter) -> None:
    while True:
        delay = _seconds_until_next_sunday_evening()
        await asyncio.sleep(delay)
        try:
            await _generate_weekly_digests(db)
        except Exception:
            logger.exception("weekly digest generation failed")


def start_scheduler(db: DbAdapter, interval_hours: float = 24) -> asyncio.Task:
    task = asyncio.create_task(_feeder_loop(db, interval_hours))
    for stale in _aux_tasks:
        _cancel_task_safely(stale)
    _aux_tasks.clear()
    _aux_tasks.append(asyncio.create_task(_daily_loop(db)))
    _aux_tasks.append(asyncio.create_task(_weekly_loop(db)))
    logger.info(
        "scheduler started: feeder scan every %s hours (retry backoff 1h→4h); "
        "daily maintenance (disk/backup/TTL); weekly digest Sunday %02d:00",
        interval_hours, WEEKLY_DIGEST_HOUR,
    )
    return task


async def stop_scheduler(task: asyncio.Task) -> None:
    _cancel_task_safely(task)
    pending = [task, *_aux_tasks]
    _aux_tasks.clear()
    for t in pending:
        _cancel_task_safely(t)
    for t in pending:
        try:
            await t
        except asyncio.CancelledError:
            pass
        except RuntimeError:
            # 跨事件循环的陈旧任务（测试场景）——忽略
            pass
        except Exception:
            logger.exception("scheduler task raised on shutdown")
    logger.info("scheduler stopped")
