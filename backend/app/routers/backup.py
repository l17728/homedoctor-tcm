"""Backup/Restore router — SQLite backup and restore (auth required).

POST   /api/backup        — create a timestamped SQLite backup
GET    /api/backup/list   — list available backups
POST   /api/restore       — stage a backup for restore-on-restart
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import get_current_user
from app.config import settings

router = APIRouter(prefix="/api/backup", tags=["backup"])


def _data_dir() -> Path:
    db_path = Path(settings.DATABASE_URL)
    data_dir = Path("data") if db_path == Path(":memory:") else db_path.parent
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def _source_db_path() -> str:
    return settings.DATABASE_URL


@router.post("")
async def create_backup(
    current_user: dict = Depends(get_current_user),
):
    """Create a SQLite backup using aiosqlite's online backup API."""
    data_dir = _data_dir()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = data_dir / f"backup_{timestamp}.db"
    source = _source_db_path()

    if source == ":memory:":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="内存数据库不支持备份",
        )

    async with aiosqlite.connect(source) as src:
        async with aiosqlite.connect(str(backup_path)) as dst:
            await src.backup(dst)

    size = backup_path.stat().st_size

    return {
        "success": True,
        "filename": backup_path.name,
        "size_bytes": size,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/list")
async def list_backups(
    current_user: dict = Depends(get_current_user),
):
    """List available backup files in the data directory."""
    data_dir = _data_dir()
    backups: list[dict[str, Any]] = []

    for f in sorted(
        data_dir.glob("backup_*.db"),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    ):
        stat = f.stat()
        backups.append(
            {
                "filename": f.name,
                "size": stat.st_size,
                "created_at": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
            }
        )

    return {"backups": backups}


@router.post("/restore")
async def restore_backup(
    body: dict[str, Any],
    current_user: dict = Depends(get_current_user),
):
    """Stage a backup file for restore-on-restart.

    Copies the backup to data/.restore_pending. The app applies the
    restore on next restart (port of /fighting backup.ts pattern).
    """
    filename = body.get("filename")
    if not filename or not isinstance(filename, str):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="filename is required",
        )

    # Path traversal guard
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的文件名",
        )

    data_dir = _data_dir()
    backup_path = data_dir / filename

    if not backup_path.exists() or not backup_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="备份文件不存在",
        )

    restore_pending = data_dir / ".restore_pending"
    shutil.copy2(str(backup_path), str(restore_pending))

    return {
        "success": True,
        "message": "重启后生效",
        "filename": filename,
    }
