"""Audit chain module — SHA-256 hash chain for tamper-evident logging (spec §10.4).

Each audit entry links to the previous one via hash, forming an append-only chain.
Tampering with any entry breaks the chain, making unauthorized data changes detectable.

Chain formula:
    hash_n = SHA-256(hash_{n-1} + action + entity_type + entity_id + changes + timestamp)
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.database import DbAdapter

logger = logging.getLogger(__name__)

GENESIS_HASH = "0" * 64  # Genesis block hash for the first entry


def compute_hash(
    prev_hash: str,
    action: str,
    entity_type: str,
    entity_id: str | None,
    changes: str,
    timestamp: str,
) -> str:
    """Compute SHA-256 hash chain link.

    Args:
        prev_hash: Hash of the previous audit entry (or GENESIS_HASH for first).
        action: What happened — e.g. "create", "update", "delete", "safety_check".
        entity_type: What entity — e.g. "medicine", "herb", "chat_message", "reminder".
        entity_id: ID of the affected entity (optional).
        changes: JSON string of the changes made.
        timestamp: ISO-8601 timestamp string.

    Returns:
        64-character hex SHA-256 digest.
    """
    payload = f"{prev_hash}|{action}|{entity_type}|{entity_id or ''}|{changes}|{timestamp}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def log_audit(
    db: DbAdapter,
    *,
    tenant_id: str,
    user_id: str | None = None,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    changes: dict[str, Any] | None = None,
) -> str:
    """Append a new entry to the audit chain.

    Args:
        db: Database adapter.
        tenant_id: Tenant (family) ID for isolation.
        user_id: User who triggered the action (optional for system actions).
        action: What happened.
        entity_type: What entity was affected.
        entity_id: ID of the entity.
        changes: Dict of changes (will be JSON-serialized).

    Returns:
        The hash of the newly created audit entry.
    """
    # Fetch the latest hash in this tenant's chain
    row = await db.query_one(
        "SELECT hash FROM audit_log WHERE tenant_id = ? ORDER BY rowid DESC LIMIT 1",
        (tenant_id,),
    )
    prev_hash = row["hash"] if row else GENESIS_HASH

    timestamp = datetime.now(timezone.utc).isoformat()
    changes_str = json.dumps(changes or {}, ensure_ascii=False, sort_keys=True)
    new_hash = compute_hash(prev_hash, action, entity_type, entity_id, changes_str, timestamp)
    entry_id = str(uuid.uuid4())

    await db.execute(
        """INSERT INTO audit_log (id, tenant_id, user_id, action, entity_type, entity_id, changes, prev_hash, hash, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (entry_id, tenant_id, user_id, action, entity_type, entity_id, changes_str, prev_hash, new_hash, timestamp),
    )

    logger.debug("Audit log: %s %s/%s (hash=%s...)", action, entity_type, entity_id, new_hash[:12])
    return new_hash


async def verify_chain(db: DbAdapter, tenant_id: str) -> bool:
    """Verify the integrity of the audit chain for a tenant.

    Recomputes every hash from genesis and checks for tampering.

    Returns:
        True if the chain is intact, False if any entry has been tampered with.
    """
    rows = await db.query(
        "SELECT * FROM audit_log WHERE tenant_id = ? ORDER BY rowid ASC",
        (tenant_id,),
    )

    expected_prev = GENESIS_HASH
    for row in rows:
        if row["prev_hash"] != expected_prev:
            logger.warning("Audit chain broken at entry %s: prev_hash mismatch", row["id"])
            return False

        expected_hash = compute_hash(
            row["prev_hash"],
            row["action"],
            row["entity_type"],
            row["entity_id"],
            row["changes"],
            row["created_at"],
        )
        if row["hash"] != expected_hash:
            logger.warning("Audit chain broken at entry %s: hash mismatch", row["id"])
            return False

        expected_prev = row["hash"]

    return True


async def get_audit_trail(
    db: DbAdapter,
    tenant_id: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Query audit trail entries, optionally filtered by entity.

    Returns:
        List of audit entries (newest first), up to `limit`.
    """
    sql = "SELECT * FROM audit_log WHERE tenant_id = ?"
    params: list[Any] = [tenant_id]

    if entity_type:
        sql += " AND entity_type = ?"
        params.append(entity_type)
    if entity_id:
        sql += " AND entity_id = ?"
        params.append(entity_id)

    sql += " ORDER BY rowid DESC LIMIT ?"
    params.append(limit)

    rows = await db.query(sql, tuple(params))
    return [dict(r) for r in rows]
