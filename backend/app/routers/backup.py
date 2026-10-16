"""Backup/Restore router — AES-256-GCM encrypted SQLite backups (spec §12.1).

POST   /api/backup        — create a timestamped, encrypted SQLite backup
GET    /api/backup/list   — list available backups (encrypted + legacy)
POST   /api/restore       — stage a backup for restore-on-restart

Backups are written as ``backup_YYYYMMDD_HHMMSS_<id>.db.enc`` (AES-256-GCM,
``HDEC`` magic header). Legacy timestamp-only plaintext ``backup_*.db`` files remain readable for
backward compatibility. See ``app/crypto_utils.py`` for the encryption envelope.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import get_current_user, require_admin
from app.config import settings
from app.crypto_utils import (
    DecryptionError,
    decrypt_file,
    encrypt_file,
    is_encrypted,
)
from app.database import DbAdapter, get_db

logger = logging.getLogger(__name__)
_BACKUP_FILENAME_RE = re.compile(
    r"backup_\d{8}_\d{6}(?:_[0-9a-f]{12})?\.db(?:\.enc)?\Z"
)

router = APIRouter(prefix="/api/backup", tags=["backup"])


def _data_dir() -> Path:
    db_path = Path(settings.DATABASE_URL)
    data_dir = Path("data") if db_path == Path(":memory:") else db_path.parent
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def _remove_plaintext_snapshot(path: Path) -> None:
    """Remove a sensitive intermediate and fail closed if it cannot be removed."""
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.critical(
            "plaintext backup snapshot could not be removed: %s",
            path,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="鏃犳硶娓呴櫎鏄庢枃澶囦唤涓存椂鏂囦欢锛岃绔嬪嵆妫€鏌ュ浠界洰褰?",
        ) from exc


def _backup_dir() -> Path:
    """Return the configured backup volume, falling back to the database directory."""
    configured = os.environ.get("HOMEDOCTOR_BACKUP_DIR")
    if not configured:
        return _data_dir()
    directory = Path(configured)
    if not directory.is_absolute():
        directory = Path.cwd() / directory
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _backup_dirs() -> list[Path]:
    """Include the configured destination and legacy in-database backups."""
    dirs = [_backup_dir(), _data_dir()]
    return list(dict.fromkeys(dirs))


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


def _decryption_passwords() -> list[str]:
    """Return unique current and rotation-era keys accepted for old backups."""
    values = [
        settings.DB_ENCRYPTION_KEY,
        os.environ.get("HOMEDOCTOR_PREVIOUS_DB_ENCRYPTION_KEY", ""),
        settings.SECRET_KEY,
        os.environ.get("HOMEDOCTOR_PREVIOUS_SECRET_KEY", ""),
    ]
    return list(dict.fromkeys(value for value in values if value))


@router.post("")
async def create_backup(
    current_user: dict = Depends(require_admin),
    db: DbAdapter = Depends(get_db),
):
    """Create an encrypted SQLite backup.

    Flow:
      1. Snapshot the live DB via ``VACUUM INTO ?`` on the app's own adapter
         connection (works on encrypted deployments where a second raw
         connection could not even read the database).
      2. Encrypt the snapshot to ``backup_*.db.enc`` (AES-256-GCM, ``HDEC`` header).
      3. Delete the plaintext intermediate so only ciphertext persists.
    """
    data_dir = _backup_dir()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_id = f"{timestamp}_{uuid.uuid4().hex[:12]}"
    # Unique hidden temp files avoid collisions between simultaneous requests.
    # The final name is published only after encryption completes.
    plain_path = data_dir / f".backup_{backup_id}.db.tmp"
    enc_tmp_path = data_dir / f".backup_{backup_id}.db.enc.tmp"
    enc_path = data_dir / f"backup_{backup_id}.db.enc"
    source = _source_db_path()

    if source == ":memory:":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="内存数据库不支持备份",
        )

    # The snapshot path is generated here from a timestamp; refuse it anyway
    # if any statement metacharacter slipped in (bound parameter or not).
    if any(ch in str(plain_path) for ch in ("'", '"', ";")):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="备份路径包含非法字符",
        )

    # 1. Consistent plaintext snapshot via the app's own (possibly encrypted)
    #    connection. The unique path prevents concurrent requests from
    #    deleting or overwriting another request's snapshot.
    try:
        await db.execute("VACUUM INTO ?", (str(plain_path),))
        os.chmod(plain_path, 0o600)
    except Exception:
        _remove_plaintext_snapshot(plain_path)
        logger.exception("backup snapshot failed for %s", plain_path.name)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="备份快照创建失败",
        )

    # 2. Encrypt the plaintext backup.
    try:
        password = _encryption_password()
        encrypt_file(str(plain_path), str(enc_tmp_path), password)
        # List/restore can only observe a complete, authenticated ciphertext.
        enc_tmp_path.replace(enc_path)
    except Exception:
        # Encryption/publication failed — remove all temporary material so no
        # plaintext snapshot or partial ciphertext remains.
        enc_tmp_path.unlink(missing_ok=True)
        enc_path.unlink(missing_ok=True)
        plain_path.unlink(missing_ok=True)
        logger.exception("backup encryption failed for %s", enc_path.name)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="备份加密失败",
        )

    finally:
        # Always remove the plaintext intermediate, including failed publication.
        _remove_plaintext_snapshot(plain_path)

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
    current_user: dict = Depends(require_admin),
):
    """List backups in the configured backup directory and legacy data directory.

    Returns both modern encrypted (``*.db.enc``) and legacy plaintext
    (``*.db``) backups, each annotated with an ``encrypted`` boolean.
    """
    backups: list[dict[str, Any]] = []
    seen: set[str] = set()

    # Encrypted backups (*.db.enc).
    for data_dir in _backup_dirs():
        for f in sorted(data_dir.glob("backup_*.db.enc"), key=lambda x: x.stat().st_mtime, reverse=True):
            if f.name in seen:
                continue
            seen.add(f.name)
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
        for f in sorted(data_dir.glob("backup_*.db"), key=lambda x: x.stat().st_mtime, reverse=True):
            if f.name in seen:
                continue
            seen.add(f.name)
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
    current_user: dict = Depends(require_admin),
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
    if not _BACKUP_FILENAME_RE.fullmatch(filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的文件名",
        )

    backup_path = next(
        (directory / filename for directory in _backup_dirs() if (directory / filename).is_file()),
        None,
    )

    if backup_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="备份文件不存在",
        )

    restore_pending = _data_dir() / ".restore_pending"

    if filename.endswith(".db.enc") or is_encrypted(str(backup_path)):
        # Decrypt the encrypted backup into the restore-pending slot.
        passwords = _decryption_passwords()
        try:
            last_error: DecryptionError | None = None
            for password in passwords:
                try:
                    decrypt_file(str(backup_path), str(restore_pending), password)
                    last_error = None
                    break
                except DecryptionError as exc:
                    last_error = exc
            if last_error is not None:
                raise last_error
            if not passwords:
                raise DecryptionError("no backup decryption key configured")
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
