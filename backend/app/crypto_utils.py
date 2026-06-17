"""File-level encryption utilities for backup/restore (spec §12.1).

Uses AES-256-GCM authenticated encryption when the ``cryptography`` package is
available. Falls back to an insecure XOR-based obfuscation otherwise (logged as
a warning) so the rest of the application keeps functioning.

Encrypted file format (when AES-256-GCM is available)::

    offset  size   field
    0       4      magic bytes  b"HDEC"  (HomeDoctor Encrypted)
    4       12     nonce (random per encryption)
    16      N      ciphertext + 16-byte GCM authentication tag

The 256-bit key is derived from the caller-supplied password via PBKDF2-HMAC-SHA256
with a fixed application salt and 100000 iterations. A fresh random nonce per
encryption guarantees ciphertext uniqueness even for identical plaintexts.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: 4-byte file magic identifying HomeDoctor encrypted backups.
MAGIC: bytes = b"HDEC"

#: AES-GCM standard nonce length (96 bits).
_NONCE_LEN: int = 12

#: AES-256 key length (256 bits).
_KEY_LEN: int = 32

#: PBKDF2 iteration count (OWASP 2023 recommendation floor).
_ITERATIONS: int = 100_000

#: Fixed application-level salt for PBKDF2. The salt is not secret; its purpose
#: is to prevent precomputed rainbow-table attacks against the derived key. The
#: real secret is the caller-supplied password (app SECRET_KEY).
_SALT: bytes = b"homedoctor-backup-salt-v1"

try:  # pragma: no cover - import gate exercised in both branches at runtime
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM as _AESGCM
    from cryptography.exceptions import InvalidTag as _InvalidTag

    _HAS_CRYPTOGRAPHY = True
except ImportError:  # pragma: no cover
    _AESGCM = None  # type: ignore[assignment]
    _InvalidTag = None  # type: ignore[assignment]
    _HAS_CRYPTOGRAPHY = False
    logger.warning(
        "cryptography package not installed, using insecure fallback "
        "for backup encryption. Install `cryptography` for AES-256-GCM."
    )


class DecryptionError(Exception):
    """Raised when a file cannot be decrypted (wrong key or corrupted data)."""


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------


def _derive_key(password: str) -> bytes:
    """Derive a 32-byte AES-256 key from a password via PBKDF2-HMAC-SHA256."""
    if not isinstance(password, str) or not password:
        raise ValueError("encryption password must be a non-empty string")
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        _SALT,
        _ITERATIONS,
        dklen=_KEY_LEN,
    )


def has_cryptography() -> bool:
    """Return True when the secure AES-256-GCM backend is available."""
    return _HAS_CRYPTOGRAPHY


# ---------------------------------------------------------------------------
# AES-256-GCM implementation
# ---------------------------------------------------------------------------


def _encrypt_gcm(plaintext: bytes, password: str) -> bytes:
    """Encrypt with AES-256-GCM. Returns MAGIC + nonce + ciphertext+tag."""
    key = _derive_key(password)
    nonce = secrets.token_bytes(_NONCE_LEN)
    aesgcm = _AESGCM(key)
    # AESGCM.encrypt appends the 16-byte GCM tag to the ciphertext.
    ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data=None)
    return MAGIC + nonce + ciphertext


def _decrypt_gcm(blob: bytes, password: str) -> bytes:
    """Decrypt a MAGIC+nonce+ciphertext blob produced by _encrypt_gcm."""
    if len(blob) < len(MAGIC) + _NONCE_LEN + 16:  # 16 = minimum GCM tag
        raise DecryptionError("encrypted payload is too small / truncated")
    nonce = blob[len(MAGIC):len(MAGIC) + _NONCE_LEN]
    ciphertext = blob[len(MAGIC) + _NONCE_LEN:]
    key = _derive_key(password)
    aesgcm = _AESGCM(key)
    try:
        return aesgcm.decrypt(nonce, ciphertext, associated_data=None)
    except _InvalidTag as exc:  # type: ignore[misc]
        raise DecryptionError("decryption failed: wrong key or corrupted data") from exc


# ---------------------------------------------------------------------------
# Insecure XOR fallback (cryptography unavailable)
# ---------------------------------------------------------------------------


def _xor_bytes(data: bytes, key: bytes) -> bytes:
    """XOR `data` against a repeating `key` (NOT cryptographically secure)."""
    if not key:
        raise ValueError("xor key must be non-empty")
    klen = len(key)
    return bytes(b ^ key[i % klen] for i, b in enumerate(data))


def _encrypt_xor(plaintext: bytes, password: str) -> bytes:
    """Insecure obfuscation fallback. Same envelope format as GCM for parity."""
    key = _derive_key(password)
    nonce = secrets.token_bytes(_NONCE_LEN)
    # Mix the nonce into the keystream so repeated plaintexts differ.
    stream = hashlib.sha256(key + nonce).digest()
    ciphertext = _xor_bytes(plaintext, stream)
    return MAGIC + nonce + ciphertext


def _decrypt_xor(blob: bytes, password: str) -> bytes:
    """Reverse of _encrypt_xor."""
    if len(blob) < len(MAGIC) + _NONCE_LEN:
        raise DecryptionError("encrypted payload is too small / truncated")
    nonce = blob[len(MAGIC):len(MAGIC) + _NONCE_LEN]
    ciphertext = blob[len(MAGIC) + _NONCE_LEN:]
    key = _derive_key(password)
    stream = hashlib.sha256(key + nonce).digest()
    return _xor_bytes(ciphertext, stream)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_encrypted(path: str) -> bool:
    """Return True if the file at *path* begins with the ``HDEC`` magic header."""
    try:
        with open(path, "rb") as fh:
            return fh.read(len(MAGIC)) == MAGIC
    except (OSError, FileNotFoundError):
        return False


def encrypt_bytes(plaintext: bytes, password: str) -> bytes:
    """Encrypt a byte string and return the full encrypted envelope.

    Uses AES-256-GCM when ``cryptography`` is installed, otherwise an insecure
    XOR fallback (a warning is logged at import time).
    """
    if _HAS_CRYPTOGRAPHY:
        return _encrypt_gcm(plaintext, password)
    return _encrypt_xor(plaintext, password)


def decrypt_bytes(blob: bytes, password: str) -> bytes:
    """Decrypt an envelope produced by :func:`encrypt_bytes`.

    Raises :class:`DecryptionError` if the magic header is missing/invalid, the
    payload is truncated, or (GCM mode) authentication fails (wrong key).
    """
    if blob[:len(MAGIC)] != MAGIC:
        raise DecryptionError("invalid magic header (not an HDEC file)")
    payload = blob[len(MAGIC):]
    # Re-prepend MAGIC so the internal helpers can slice uniformly.
    full = MAGIC + payload
    if _HAS_CRYPTOGRAPHY:
        return _decrypt_gcm(full, password)
    return _decrypt_xor(full, password)


def encrypt_file(source_path: str, dest_path: str, password: str) -> None:
    """Encrypt the file at *source_path* into *dest_path* using AES-256-GCM.

    The source file is read fully into memory, encrypted, and written atomically
    to *dest_path*. The plaintext source is left untouched (callers delete it
    when appropriate, e.g. the backup router deletes the intermediate ``.db``
    copy after encryption).
    """
    with open(source_path, "rb") as fh:
        plaintext = fh.read()
    blob = encrypt_bytes(plaintext, password)
    # Atomic write: write to a temp sibling then rename.
    tmp_path = dest_path + ".tmp"
    with open(tmp_path, "wb") as fh:
        fh.write(blob)
    os.replace(tmp_path, dest_path)


def decrypt_file(source_path: str, dest_path: str, password: str) -> None:
    """Decrypt a file produced by :func:`encrypt_file` into *dest_path*.

    Raises :class:`DecryptionError` on magic mismatch, truncation, or GCM
    authentication failure (wrong key / tampered ciphertext).
    """
    with open(source_path, "rb") as fh:
        blob = fh.read()
    plaintext = decrypt_bytes(blob, password)
    tmp_path = dest_path + ".tmp"
    with open(tmp_path, "wb") as fh:
        fh.write(plaintext)
    os.replace(tmp_path, dest_path)
