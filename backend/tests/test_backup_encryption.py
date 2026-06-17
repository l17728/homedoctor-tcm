"""Tests for AES-256-GCM encrypted backup/restore (spec §12.1).

Covers:
  * crypto_utils unit tests: round-trip, magic header, is_encrypted, wrong key.
  * backup router integration: encrypted backup creation, listing, restore,
    and backward compatibility with legacy plaintext ``.db`` backups.

The backup endpoint connects directly to ``settings.DATABASE_URL`` via
``aiosqlite.connect`` (it does not use the injected in-memory adapter), so the
API tests below use a dedicated ``file_client`` fixture backed by a real
file-based SQLite database inside a tmp directory.
"""

from __future__ import annotations

import os

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

    The backup endpoint opens ``settings.DATABASE_URL`` directly via
    ``aiosqlite.connect`` instead of the injected adapter, so both the injected
    adapter (for auth) and ``settings.DATABASE_URL`` (for backup source) must
    point at the same on-disk database. Backups are written to ``tmp_path``
    (the parent directory of the DB file).
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
    """Register a user against the file DB and return auth headers."""
    response = await file_client.post(
        "/api/auth/register",
        json={
            "username": "backupuser",
            "password": "backuppass123",
            "display_name": "备份用户",
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
