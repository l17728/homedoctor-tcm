"""Tests for AES-256-GCM encrypted backup/restore (spec §12.1).

Covers:
  * crypto_utils unit tests: round-trip, magic header, is_encrypted, wrong key.
  * backup router integration: encrypted backup creation, listing, restore,
    and backward compatibility with legacy plaintext ``.db`` backups.

The backup endpoint snapshots through the application's injected database
adapter, so these API tests use a dedicated ``file_client`` fixture backed by
a real file-based SQLite database inside a temporary directory.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.crypto_utils import (
    MAGIC,
    DecryptionError,
    decrypt_bytes,
    decrypt_file,
    encrypt_bytes,
    encrypt_file,
    is_encrypted,
)
from app.database import SqliteAdapter, init_db, seed_safety_rules, seed_test_data


# ---------------------------------------------------------------------------
# Crypto unit tests
# ---------------------------------------------------------------------------


def test_encrypt_decrypt_roundtrip(tmp_path):
    """encrypt_file -> decrypt_file must reproduce the original bytes."""
    src = tmp_path / "plain.bin"
    enc = tmp_path / "plain.enc"
    dec = tmp_path / "plain.restored"
    payload = b"SQLite-format backup content \x00\x01\x02 " + os.urandom(2048)
    src.write_bytes(payload)

    encrypt_file(str(src), str(enc), "super-secret-password")
    decrypt_file(str(enc), str(dec), "super-secret-password")

    assert dec.read_bytes() == payload


def test_encrypt_bytes_roundtrip_in_memory():
    """encrypt_bytes/decrypt_bytes round-trip without touching disk."""
    payload = b"small in-memory payload"
    blob = encrypt_bytes(payload, "pw")
    assert decrypt_bytes(blob, "pw") == payload


def test_encrypted_file_has_hdec_magic(tmp_path):
    """Encrypted output must start with the 4-byte HDEC magic header."""
    src = tmp_path / "plain.bin"
    enc = tmp_path / "plain.enc"
    src.write_bytes(b"some plaintext content")

    encrypt_file(str(src), str(enc), "pw")

    header = enc.read_bytes()[:4]
    assert header == MAGIC


def test_is_encrypted_detects_encrypted_file(tmp_path):
    """is_encrypted returns True for encrypted files, False for plaintext."""
    plain = tmp_path / "plain.bin"
    enc = tmp_path / "plain.enc"
    plain.write_bytes(b"plaintext content")
    encrypt_file(str(plain), str(enc), "pw")

    assert is_encrypted(str(enc)) is True
    assert is_encrypted(str(plain)) is False


def test_is_encrypted_missing_file_returns_false(tmp_path):
    """is_encrypted returns False (not raise) for a nonexistent path."""
    assert is_encrypted(str(tmp_path / "nope.enc")) is False


def test_wrong_password_raises_decryption_error(tmp_path):
    """Decryption with the wrong key must raise DecryptionError (GCM auth fail)."""
    src = tmp_path / "plain.bin"
    enc = tmp_path / "plain.enc"
    src.write_bytes(b"secret backup data")

    encrypt_file(str(src), str(enc), "correct-password")

    with pytest.raises(DecryptionError):
        decrypt_file(str(enc), str(tmp_path / "out.bin"), "wrong-password")


def test_decrypt_bytes_bad_magic_raises(tmp_path):
    """A file without the HDEC magic must be rejected."""
    with pytest.raises(DecryptionError):
        decrypt_bytes(b"XXXX" + b"not an encrypted payload", "pw")


def test_truncated_encrypted_file_raises(tmp_path):
    """A truncated encrypted blob must raise DecryptionError, not crash."""
    blob = encrypt_bytes(b"x", "pw")
    # Keep magic + partial nonce only.
    truncated = blob[: len(MAGIC) + 4]
    with pytest.raises(DecryptionError):
        decrypt_bytes(truncated, "pw")


def test_empty_password_rejected():
    """An empty password must be rejected before any encryption happens."""
    with pytest.raises(ValueError):
        encrypt_bytes(b"data", "")


# ---------------------------------------------------------------------------
# Fixtures: file-DB-backed test client for backup router integration tests
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def file_client(tmp_path, monkeypatch):
    """A test client backed by a real file SQLite DB (required by backup).

    ``settings.DATABASE_URL`` and the injected adapter point to the same
    on-disk database. Backups default to ``tmp_path`` (the DB file's parent).
    """
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", str(db_file))

    adapter = SqliteAdapter(str(db_file))
    await adapter.connect()
    await init_db(adapter)
    await seed_safety_rules(adapter)
    await seed_test_data(adapter)

    import app.database as db_mod

    prev = db_mod._db_adapter
    db_mod.set_db(adapter)

    import app.main as main_mod

    transport = ASGITransport(app=main_mod.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await adapter.close()
    db_mod.set_db(prev)


@pytest_asyncio.fixture
async def file_auth_headers(file_client: AsyncClient):
    """Register an ADMIN user against the file DB and return auth headers.

    Backup create/restore are admin-only operations (a normal user must not
    be able to roll back the whole multi-tenant database).
    """
    response = await file_client.post(
        "/api/auth/register",
        json={
            # username "admin" is a built-in admin (app.auth.ADMIN_USERNAMES)
            "username": "admin",
            "password": "backuppass123",
            "display_name": "备份管理员",
            "consent_privacy": True,
            "consent_health_data": True,
        },
    )
    assert response.status_code in (200, 201), response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Backup router integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_backup_creates_encrypted_file(file_client, file_auth_headers):
    """POST /api/backup must produce a .db.enc file with the HDEC header."""
    resp = await file_client.post("/api/backup", headers=file_auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["success"] is True
    assert body["encrypted"] is True
    filename = body["filename"]
    assert filename.endswith(".db.enc")

    # Resolve the actual on-disk path from settings.
    from pathlib import Path

    enc_path = Path(settings.DATABASE_URL).parent / filename
    assert enc_path.exists(), "encrypted backup file should exist on disk"
    assert enc_path.read_bytes()[:4] == MAGIC, "must start with HDEC magic"

    # No plaintext .db intermediate should remain.
    plain_path = Path(settings.DATABASE_URL).parent / filename.replace(".db.enc", ".db")
    assert not plain_path.exists(), "plaintext intermediate must be deleted"


@pytest.mark.asyncio
async def test_post_backup_uses_configured_backup_directory(
    file_client, file_auth_headers, tmp_path, monkeypatch
):
    backup_dir = tmp_path / "external-backups"
    monkeypatch.setenv("HOMEDOCTOR_BACKUP_DIR", str(backup_dir))

    response = await file_client.post("/api/backup", headers=file_auth_headers)
    assert response.status_code == 200, response.text
    filename = response.json()["filename"]
    assert (backup_dir / filename).is_file()
    assert not (Path(settings.DATABASE_URL).parent / filename).exists()

    listing = await file_client.get("/api/backup/list", headers=file_auth_headers)
    assert listing.status_code == 200
    assert any(item["filename"] == filename for item in listing.json()["backups"])


@pytest.mark.asyncio
async def test_concurrent_backups_use_unique_paths_and_publish_complete_files(
    file_client, file_auth_headers, monkeypatch
):
    # Freeze timestamps to force same-second contention; request IDs must still
    # keep both plaintext snapshots and final ciphertexts independent.
    from datetime import datetime, timezone
    import app.routers.backup as backup_router

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 15, 3, 0, 0, tzinfo=tz or timezone.utc)

    monkeypatch.setattr(backup_router, "datetime", FixedDateTime)
    responses = await asyncio.gather(*(
        file_client.post("/api/backup", headers=file_auth_headers)
        for _ in range(2)
    ))

    assert all(response.status_code == 200 for response in responses), [r.text for r in responses]
    filenames = [response.json()["filename"] for response in responses]
    assert len(set(filenames)) == 2
    backup_dir = Path(settings.DATABASE_URL).parent
    for filename in filenames:
        assert filename.endswith(".db.enc")
        assert (backup_dir / filename).read_bytes()[:4] == MAGIC
    assert not list(backup_dir.glob(".backup_*.tmp"))


@pytest.mark.asyncio
async def test_list_backups_shows_encrypted_flag(file_client, file_auth_headers):
    """GET /api/backup/list must include encrypted=True for .db.enc files."""
    create = await file_client.post("/api/backup", headers=file_auth_headers)
    assert create.status_code == 200
    filename = create.json()["filename"]

    resp = await file_client.get("/api/backup/list", headers=file_auth_headers)
    assert resp.status_code == 200
    backups = resp.json()["backups"]
    assert any(b["filename"] == filename and b["encrypted"] is True for b in backups)


@pytest.mark.asyncio
async def test_backup_list_restore_full_cycle(file_client, file_auth_headers):
    """Full lifecycle: backup -> list -> restore (decrypt to .restore_pending)."""
    # 1. Create an encrypted backup.
    create = await file_client.post("/api/backup", headers=file_auth_headers)
    assert create.status_code == 200
    filename = create.json()["filename"]
    assert filename.endswith(".db.enc")

    # 2. It appears in the list.
    listing = await file_client.get("/api/backup/list", headers=file_auth_headers)
    assert listing.status_code == 200
    names = [b["filename"] for b in listing.json()["backups"]]
    assert filename in names

    # 3. Restore stages a decrypted .restore_pending.
    restore = await file_client.post(
        "/api/backup/restore",
        headers=file_auth_headers,
        json={"filename": filename},
    )
    assert restore.status_code == 200, restore.text
    assert restore.json()["success"] is True

    from pathlib import Path

    pending = Path(settings.DATABASE_URL).parent / ".restore_pending"
    assert pending.exists(), "decrypted restore-pending file should exist"
    # The restored file is plaintext SQLite (no HDEC magic).
    assert pending.read_bytes()[:4] != MAGIC


@pytest.mark.asyncio
async def test_legacy_db_backup_still_lists_and_restores(
    file_client, file_auth_headers, tmp_path
):
    """Legacy plaintext backup_*.db files must still list and restore.

    Backward compatibility: a pre-encryption-era .db backup placed in the data
    directory must appear in /list with encrypted=False and restore via copy.
    """
    from pathlib import Path

    data_dir = Path(settings.DATABASE_URL).parent
    legacy_name = "backup_19990101_000000.db"
    legacy_path = data_dir / legacy_name
    legacy_path.write_bytes(b"SQLite format 3\x00legacy plaintext content")

    # Listed with encrypted=False.
    listing = await file_client.get("/api/backup/list", headers=file_auth_headers)
    assert listing.status_code == 200
    entries = {b["filename"]: b for b in listing.json()["backups"]}
    assert legacy_name in entries
    assert entries[legacy_name]["encrypted"] is False

    # Restored via copy (no decryption needed).
    restore = await file_client.post(
        "/api/backup/restore",
        headers=file_auth_headers,
        json={"filename": legacy_name},
    )
    assert restore.status_code == 200, restore.text

    pending = data_dir / ".restore_pending"
    assert pending.exists()


@pytest.mark.asyncio
async def test_restore_accepts_previous_backup_key_during_rotation(
    file_client, file_auth_headers, monkeypatch
):
    monkeypatch.setattr(settings, "DB_ENCRYPTION_KEY", "old-backup-password")
    created = await file_client.post("/api/backup", headers=file_auth_headers)
    assert created.status_code == 200, created.text
    filename = created.json()["filename"]

    monkeypatch.setattr(settings, "DB_ENCRYPTION_KEY", "new-backup-password")
    monkeypatch.setenv("HOMEDOCTOR_PREVIOUS_DB_ENCRYPTION_KEY", "old-backup-password")
    restored = await file_client.post(
        "/api/backup/restore", headers=file_auth_headers, json={"filename": filename}
    )
    assert restored.status_code == 200, restored.text
    pending = Path(settings.DATABASE_URL).parent / ".restore_pending"
    assert pending.is_file()
    assert pending.read_bytes().startswith(b"SQLite format 3")


@pytest.mark.asyncio
async def test_restore_nonexistent_file_404(file_client, file_auth_headers):
    """Restoring a missing backup must return 404."""
    resp = await file_client.post(
        "/api/backup/restore",
        headers=file_auth_headers,
        json={"filename": "backup_99999999_999999.db.enc"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_restore_path_traversal_blocked(file_client, file_auth_headers):
    """Path traversal in filename must be rejected with 400."""
    resp = await file_client.post(
        "/api/backup/restore",
        headers=file_auth_headers,
        json={"filename": "../etc/passwd"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_backup_requires_auth(file_client):
    """The backup endpoints must require authentication."""
    r1 = await file_client.post("/api/backup")
    assert r1.status_code == 401
    r2 = await file_client.get("/api/backup/list")
    assert r2.status_code == 401
    r3 = await file_client.post("/api/backup/restore", json={"filename": "x"})
    assert r3.status_code == 401


@pytest.mark.asyncio
async def test_backup_list_requires_admin(client, auth_headers):
    response = await client.get("/api/backup/list", headers=auth_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_restore_rejects_non_backup_filename(file_client, file_auth_headers):
    response = await file_client.post(
        "/api/backup/restore", headers=file_auth_headers,
        json={"filename": "homedoctor.db"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_restore_corrupted_encrypted_returns_400(file_client, file_auth_headers):
    """A tampered .db.enc file must fail decryption with 400, not crash."""
    from pathlib import Path

    data_dir = Path(settings.DATABASE_URL).parent
    bad_name = "backup_19990101_000001.db.enc"
    # Valid magic but garbage ciphertext after nonce.
    blob = MAGIC + b"\x00" * 12 + b"tampered-ciphertext-not-valid-gcm"
    (data_dir / bad_name).write_bytes(blob)

    resp = await file_client.post(
        "/api/backup/restore",
        headers=file_auth_headers,
        json={"filename": bad_name},
    )
    assert resp.status_code == 400
    assert "解密" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Restore-on-restart (_apply_pending_restore) — applied by main.lifespan
# ---------------------------------------------------------------------------

import sqlite3
from pathlib import Path

from app.main import _apply_pending_restore


def _make_sqlite_file(path: Path, rows: list[str]) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE marker (k TEXT)")
    for r in rows:
        conn.execute("INSERT INTO marker VALUES (?)", (r,))
    conn.commit()
    conn.close()


def _marker_values(path: Path) -> list[str]:
    conn = sqlite3.connect(str(path))
    vals = [r[0] for r in conn.execute("SELECT k FROM marker")]
    conn.close()
    return vals


def test_apply_pending_restore_swaps_db(tmp_path, monkeypatch):
    """正常（无加密）路径：pending 通过 integrity_check → 原子换库 + 旧库保留。"""
    monkeypatch.setattr(settings, "DB_ENCRYPTION_KEY", "")
    db_file = tmp_path / "app.db"
    _make_sqlite_file(db_file, ["original"])
    pending = tmp_path / ".restore_pending"
    _make_sqlite_file(pending, ["original", "restored"])

    _apply_pending_restore(db_file)

    assert not pending.exists()
    assert _marker_values(db_file) == ["original", "restored"]
    backup = tmp_path / "app.db.pre_restore_bak"
    assert backup.exists()
    assert _marker_values(backup) == ["original"]


def test_apply_pending_restore_rejects_plaintext_on_encrypted_instance(
    tmp_path, monkeypatch
):
    """加密部署防护：明文 .restore_pending → 拒绝应用，原库一字节不动。"""
    monkeypatch.setattr(settings, "DB_ENCRYPTION_KEY", "test-sqlcipher-key")
    db_file = tmp_path / "app.db"
    _make_sqlite_file(db_file, ["encrypted-live-data"])
    original_bytes = db_file.read_bytes()
    pending = tmp_path / ".restore_pending"
    _make_sqlite_file(pending, ["plaintext-backup"])  # 明文 SQLite 头

    _apply_pending_restore(db_file)

    rejected = tmp_path / ".restore_pending.rejected"
    assert rejected.exists(), "pending must be renamed to .rejected"
    assert not pending.exists()
    assert db_file.read_bytes() == original_bytes, "live DB must be untouched"
    assert not (tmp_path / "app.db.pre_restore_bak").exists()


def test_apply_pending_restore_applies_sqlcipher_key_before_integrity_check(
    tmp_path, monkeypatch
):
    """An encrypted restore must be verified with the configured SQLCipher key."""
    import app.main as main_mod
    import app.db.adapter as adapter_mod

    monkeypatch.setattr(settings, "DB_ENCRYPTION_KEY", "restore-key-with-quotes'")
    monkeypatch.setattr(adapter_mod, "_SQLCIPHER_ACTIVE", True)
    db_file = tmp_path / "app.db"
    _make_sqlite_file(db_file, ["original"])
    pending = tmp_path / ".restore_pending"
    pending.write_bytes(b"SQLCipher ciphertext, not a plaintext SQLite header")

    statements: list[str] = []

    class _Cursor:
        def fetchone(self):
            return ("ok",)

    class _FakeCipherConnection:
        def execute(self, sql):
            statements.append(sql)
            return _Cursor()

        def close(self):
            pass

    monkeypatch.setattr(sqlite3, "connect", lambda path: _FakeCipherConnection())
    _apply_pending_restore(db_file)

    assert statements[0] == "PRAGMA key = 'restore-key-with-quotes'''"
    assert statements[1] == "PRAGMA cipher_compatibility = 4"
    assert statements[2] == "PRAGMA integrity_check"
    assert db_file.read_bytes() == b"SQLCipher ciphertext, not a plaintext SQLite header"
    assert (tmp_path / ".restore_pending").exists() is False


def test_apply_pending_restore_rejects_garbage_pending(tmp_path, monkeypatch):
    """损坏的 pending（非 SQLite 库）→ integrity 拒绝，原库不动。"""
    monkeypatch.setattr(settings, "DB_ENCRYPTION_KEY", "")
    db_file = tmp_path / "app.db"
    _make_sqlite_file(db_file, ["original"])
    original_bytes = db_file.read_bytes()
    (tmp_path / ".restore_pending").write_bytes(b"garbage not a database")

    _apply_pending_restore(db_file)

    assert (tmp_path / ".restore_pending.rejected").exists()
    assert db_file.read_bytes() == original_bytes


def test_apply_pending_restore_rolls_back_on_swap_failure(tmp_path, monkeypatch):
    """swap 中途失败 → .pre_restore_bak 改回原名，杜绝空库启动；恢复被放弃。"""
    monkeypatch.setattr(settings, "DB_ENCRYPTION_KEY", "")
    db_file = tmp_path / "app.db"
    _make_sqlite_file(db_file, ["original"])
    pending = tmp_path / ".restore_pending"
    _make_sqlite_file(pending, ["restored"])

    real_rename = Path.rename
    failed = {"done": False}

    def flaky_rename(self, target):
        # Fail exactly the pending → live-DB swap; the rollback rename of
        # .pre_restore_bak back onto the live path must then succeed.
        if not failed["done"] and target == db_file and self == pending:
            failed["done"] = True
            raise OSError("simulated transient rename failure")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", flaky_rename)

    _apply_pending_restore(db_file)

    assert failed["done"] is True
    assert db_file.exists(), "original DB must be put back — no empty-DB boot"
    assert _marker_values(db_file) == ["original"]
    assert (tmp_path / ".restore_pending.rejected").exists(), (
        "failed restore attempt must be abandoned, not retried forever"
    )


@pytest.mark.asyncio
async def test_backup_restore_restart_cycle_via_http(file_client, file_auth_headers):
    """完整循环：create → list → restore → （模拟重启）_apply_pending_restore。

    The fixture's adapter still holds the live DB open, so the swap happens
    against a copy of the database directory (Windows cannot rename an open
    file) — this validates the on-disk artifacts end to end.
    """
    create = await file_client.post("/api/backup", headers=file_auth_headers)
    assert create.status_code == 200, create.text
    filename = create.json()["filename"]
    assert filename.endswith(".db.enc")

    listing = await file_client.get("/api/backup/list", headers=file_auth_headers)
    assert listing.status_code == 200
    assert filename in [b["filename"] for b in listing.json()["backups"]]

    restore = await file_client.post(
        "/api/backup/restore",
        headers=file_auth_headers,
        json={"filename": filename},
    )
    assert restore.status_code == 200, restore.text

    data_dir = Path(settings.DATABASE_URL).parent
    pending = data_dir / ".restore_pending"
    assert pending.exists()
    assert pending.read_bytes()[:16] == b"SQLite format 3\x00"

    # Simulate the restart-time apply in a copy of the data dir (the live DB
    # file is still open on Windows and cannot be renamed underneath us).
    restart_dir = data_dir.parent / "restart_sim"
    restart_dir.mkdir(exist_ok=True)
    import shutil as _shutil

    sim_live = restart_dir / "app.db"
    _shutil.copy2(str(pending), str(sim_live))  # any valid live DB
    _shutil.copy2(str(pending), str(restart_dir / ".restore_pending"))
    _apply_pending_restore(sim_live)

    assert not (restart_dir / ".restore_pending").exists()
    assert (restart_dir / "app.db.pre_restore_bak").exists()
    conn = sqlite3.connect(str(sim_live))
    tables = {
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    conn.close()
    assert "users" in tables, "restored DB must contain the app schema"
