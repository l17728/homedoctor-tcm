"""Backup/Restore router — AES-256-GCM encrypted SQLite backups (spec §12.1).

POST   /api/backup        — create a timestamped, encrypted SQLite backup
GET    /api/backup/list   — list available backups (encrypted + legacy)
POST   /api/restore       — stage a backup for restore-on-restart

Backups are written as ``backup_YYYYMMDD_HHMMSS.db.enc`` (AES-256-GCM, ``HDEC``
magic header). Legacy plaintext ``backup_*.db`` files remain readable for
backward compatibility. See ``app/crypto_utils.py`` for the encryption envelope.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import get_current_user
from app.config import settings
from app.crypto_utils import (
    DecryptionError,
    decrypt_file,
    encrypt_file,
    is_encrypted,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/backup", tags=["backup"])


def _data_dir() -> Path:
    db_path = Path(settings.DATABASE_URL)
    data_dir = Path("data") if db_path == Path(":memory:") else db_path.parent
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def _source_db_path() -> str:
    return settings.DATABASE_URL


def _encryption_password() -> str:
    """Resolve the backup encryption password from settings.

    Prefers ``DB_ENCRYPTION_KEY`` when set, otherwise derives from the app
    ``SECRET_KEY``. Never returns an empty string.
    """
    password = settings.DB_ENCRYPTION_KEY or settings.SECRET_KEY
    if not password:
        # Extremely defensive: SECRET_KEY has a non-empty default, so this only
        # triggers if both are explicitly cleared. We refuse to encrypt with an
        # empty key rather than silently using one.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="未配置加密密钥（SECRET_KEY 为空）",
        )
    return password


@router.post("")
async def create_backup(
    current_user: dict = Depends(get_current_user),
):
    """Create an encrypted SQLite backup.

    Flow:
      1. Online-backup the live SQLite DB to a plaintext ``backup_*.db``.
      2. Encrypt it to ``backup_*.db.enc`` (AES-256-GCM, ``HDEC`` header).
      3. Delete the intermediate plaintext ``.db`` so only ciphertext persists.
    """
    data_dir = _data_dir()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    plain_path = data_dir / f"backup_{timestamp}.db"
    enc_path = data_dir / f"backup_{timestamp}.db.enc"
    source = _source_db_path()

    if source == ":memory:":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="内存数据库不支持备份",
        )

    # 1. SQLite online backup -> plaintext intermediate.
    async with aiosqlite.connect(source) as src:
        async with aiosqlite.connect(str(plain_path)) as dst:
            await src.backup(dst)

    # 2. Encrypt the plaintext backup.
    password = _encryption_password()
    try:
        encrypt_file(str(plain_path), str(enc_path), password)
    except Exception:
        # Encryption failed — remove the partial encrypted file (if any) and
        # the plaintext intermediate so we never leak an unencrypted backup.
        enc_path.unlink(missing_ok=True)
        plain_path.unlink(missing_ok=True)
        logger.exception("backup encryption failed for %s", enc_path.name)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="备份加密失败",
        )

    # 3. Remove the plaintext intermediate (secure: only ciphertext persists).
    plain_path.unlink(missing_ok=True)

    size = enc_path.stat().st_size
    logger.info("created encrypted backup %s (%d bytes)", enc_path.name, size)

    return {
        "success": True,
        "filename": enc_path.name,
        "size_bytes": size,
        "encrypted": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/list")
async def list_backups(
    current_user: dict = Depends(get_current_user),
):
    """List available backup files in the data directory.

    Returns both modern encrypted (``*.db.enc``) and legacy plaintext
    (``*.db``) backups, each annotated with an ``encrypted`` boolean.
    """
    data_dir = _data_dir()
    backups: list[dict[str, Any]] = []

    # Encrypted backups (*.db.enc).
    for f in sorted(
        data_dir.glob("backup_*.db.enc"),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    ):
        stat = f.stat()
        backups.append(
            {
                "filename": f.name,
                "size": stat.st_size,
                "encrypted": True,
                "created_at": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
            }
        )

    # Legacy plaintext backups (*.db) — backward compatible.
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
                "encrypted": is_encrypted(str(f)),
                "created_at": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
            }
        )

    # Re-sort combined list by mtime (most recent first).
    backups.sort(
        key=lambda b: b["created_at"],
        reverse=True,
    )

    return {"backups": backups}


@router.post("/restore")
async def restore_backup(
    body: dict[str, Any],
    current_user: dict = Depends(get_current_user),
):
    """Stage a backup file for restore-on-restart.

    Encrypted ``*.db.enc`` backups are decrypted to ``data/.restore_pending``;
    legacy plaintext ``*.db`` backups are copied as-is. The app applies the
    restore on next restart (port of /fighting backup.ts pattern).
    """
    filename = body.get("filename")
    if not filename or not isinstance(filename, str):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="filename is required",
        )

    # Path traversal guard.
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

    if filename.endswith(".db.enc") or is_encrypted(str(backup_path)):
        # Decrypt the encrypted backup into the restore-pending slot.
        password = _encryption_password()
        try:
            decrypt_file(str(backup_path), str(restore_pending), password)
        except DecryptionError as exc:
            logger.warning("restore decryption failed for %s: %s", filename, exc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="备份解密失败（密钥不匹配或文件损坏）",
            )
        message = "已解密，重启后生效"
    else:
        # Legacy plaintext backup — copy as-is.
        shutil.copy2(str(backup_path), str(restore_pending))
        message = "重启后生效"

    return {
        "success": True,
        "message": message,
        "filename": filename,
    }
