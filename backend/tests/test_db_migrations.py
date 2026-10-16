"""Database initialization and migration idempotence checks."""

import pytest

from app.database import init_db


@pytest.mark.asyncio
async def test_audit_revocation_lookup_index_is_idempotent_and_used(db):
    """Existing DBs gain the index at startup and revocation lookup uses it."""
    index_name = "idx_audit_log_tenant_entity_lookup"

    await init_db(db)
    await init_db(db)

    indexes = await db.query("PRAGMA index_list(audit_log)")
    assert sum(index["name"] == index_name for index in indexes) == 1

    plan = await db.query(
        "EXPLAIN QUERY PLAN SELECT id FROM audit_log "
        "WHERE tenant_id = ? AND entity_type = ? AND entity_id = ? LIMIT 1",
        ("family", "token_revocation", "jti"),
    )
    assert any(index_name in row["detail"] for row in plan), plan
