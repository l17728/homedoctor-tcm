"""Database migrations — schema evolution and initialization."""

from __future__ import annotations

import logging
from app.db.adapter import DbAdapter
from app.db.schema import DDL_STATEMENTS, FTS_STATEMENTS, FTS_TRIGGERS

logger = logging.getLogger(__name__)

__all__ = ["init_db"]


def _is_benign(exc: Exception) -> bool:
    """True for the expected idempotency noise (column/table already exists)."""
    msg = str(exc).lower()
    return (
        "duplicate column name" in msg
        or "already exists" in msg
        or "no such table" in msg
    )


async def _migrate_reminders_member_id(db: DbAdapter) -> None:
    """Add family_member_id column to reminders table if missing (backward compat for existing DBs)."""
    try:
        cols = await db.query("PRAGMA table_info(reminders)")
        if not any(c["name"] == "family_member_id" for c in cols):
            await db.execute("ALTER TABLE reminders ADD COLUMN family_member_id TEXT")
    except Exception as exc:
        if not _is_benign(exc):
            logger.exception("migration _migrate_reminders_member_id failed")
            raise


async def _migrate_user_profiles_liver_kidney(db: DbAdapter) -> None:
    """Add liver_disease and kidney_disease columns to user_profiles if missing (backward compat)."""
    try:
        cols = await db.query("PRAGMA table_info(user_profiles)")
        col_names = [c["name"] for c in cols]
        if "liver_disease" not in col_names:
            await db.execute("ALTER TABLE user_profiles ADD COLUMN liver_disease INTEGER DEFAULT 0")
        if "kidney_disease" not in col_names:
            await db.execute("ALTER TABLE user_profiles ADD COLUMN kidney_disease INTEGER DEFAULT 0")
    except Exception as exc:
        if not _is_benign(exc):
            logger.exception("migration _migrate_user_profiles_liver_kidney failed")
            raise


async def _migrate_knowledge_tenant_id(db: DbAdapter) -> None:
    """Add tenant_id column to knowledge_entities and entity_relationships (Phase 2 unified model).

    NULL = global shared knowledge (system herbs/formulas/symptoms).
    Non-NULL = family-private entity or relationship.
    """
    for table in ("knowledge_entities", "entity_relationships"):
        try:
            cols = await db.query(f"PRAGMA table_info({table})")
            if not any(c["name"] == "tenant_id" for c in cols):
                await db.execute(f"ALTER TABLE {table} ADD COLUMN tenant_id TEXT DEFAULT NULL")
        except Exception as exc:
            if not _is_benign(exc):
                logger.exception("migration _migrate_knowledge_tenant_id(%s) failed", table)
                raise
    for stmt in (
        "CREATE INDEX IF NOT EXISTS idx_ke_tenant ON knowledge_entities(tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_er_tenant ON entity_relationships(tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_kc_source_type ON knowledge_chunks(source_type)",
    ):
        try:
            await db.execute(stmt)
        except Exception as exc:
            if not _is_benign(exc):
                logger.exception("migration index failed: %s", stmt)
                raise


async def _migrate_chunks_source(db: DbAdapter) -> None:
    """Add source columns + lifecycle tracking to knowledge_chunks."""
    try:
        cols = await db.query("PRAGMA table_info(knowledge_chunks)")
        col_names = [c["name"] for c in cols]
        for col, ddl in [
            ("source_url", "ALTER TABLE knowledge_chunks ADD COLUMN source_url TEXT"),
            ("source_type", "ALTER TABLE knowledge_chunks ADD COLUMN source_type TEXT DEFAULT 'internal'"),
            ("hit_count", "ALTER TABLE knowledge_chunks ADD COLUMN hit_count INTEGER DEFAULT 0"),
            ("last_hit_at", "ALTER TABLE knowledge_chunks ADD COLUMN last_hit_at TEXT"),
            ("text_summary", "ALTER TABLE knowledge_chunks ADD COLUMN text_summary TEXT"),
        ]:
            if col not in col_names:
                await db.execute(ddl)
    except Exception as exc:
        if not _is_benign(exc):
            logger.exception("migration _migrate_chunks_source failed")
            raise

async def init_db(db: DbAdapter) -> None:
    """Create all tables and FTS indexes."""
    # Backward-compat migrations MUST run before DDL: old databases lack the
    # new columns, so DDL statements like CREATE INDEX ... ON
    # knowledge_chunks(source_type) would fail ("no such column") because
    # CREATE TABLE IF NOT EXISTS is a no-op on the existing old table.
    await _migrate_reminders_member_id(db)
    await _migrate_user_profiles_liver_kidney(db)
    await _migrate_knowledge_tenant_id(db)
    await _migrate_chunks_source(db)

    for stmt in DDL_STATEMENTS:
        await db.execute(stmt)
    # Post-DDL migration pass: idempotent no-op on fully-migrated DBs, but
    # guarantees any column the CREATE TABLE didn't include gets added.
    await _migrate_chunks_source(db)
    for stmt in FTS_STATEMENTS + FTS_TRIGGERS:
        try:
            await db.execute(stmt)
        except Exception as exc:
            if not _is_benign(exc):
                logger.warning("FTS statement skipped (%s): %s", str(exc)[:60], stmt[:60])

    for table in ("herbs_fts", "formulas_fts"):
        try:
            await db.execute(f"INSERT INTO {table}({table}) VALUES('rebuild')")
        except Exception as exc:
            logger.warning("FTS rebuild skipped for %s: %s", table, str(exc)[:60])

    from app.agent_tools import _load_configs_from_db
    await _load_configs_from_db(db)

