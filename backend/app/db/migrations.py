"""Database migrations — schema evolution and initialization."""

from __future__ import annotations

import logging
from app.db.adapter import DbAdapter
from app.db.schema import DDL_STATEMENTS, FTS_STATEMENTS, FTS_TRIGGERS

logger = logging.getLogger(__name__)

__all__ = ["init_db"]

async def _migrate_reminders_member_id(db: DbAdapter) -> None:
    """Add family_member_id column to reminders table if missing (backward compat for existing DBs)."""
    try:
        cols = await db.query("PRAGMA table_info(reminders)")
        if not any(c["name"] == "family_member_id" for c in cols):
            await db.execute("ALTER TABLE reminders ADD COLUMN family_member_id TEXT")
    except Exception:
        pass  # Table might not exist yet or column already added


async def _migrate_user_profiles_liver_kidney(db: DbAdapter) -> None:
    """Add liver_disease and kidney_disease columns to user_profiles if missing (backward compat)."""
    try:
        cols = await db.query("PRAGMA table_info(user_profiles)")
        col_names = [c["name"] for c in cols]
        if "liver_disease" not in col_names:
            await db.execute("ALTER TABLE user_profiles ADD COLUMN liver_disease INTEGER DEFAULT 0")
        if "kidney_disease" not in col_names:
            await db.execute("ALTER TABLE user_profiles ADD COLUMN kidney_disease INTEGER DEFAULT 0")
    except Exception:
        pass


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
        except Exception:
            pass
    for stmt in (
        "CREATE INDEX IF NOT EXISTS idx_ke_tenant ON knowledge_entities(tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_er_tenant ON entity_relationships(tenant_id)",
    ):
        try:
            await db.execute(stmt)
        except Exception:
            pass

    for stmt in (
        "CREATE INDEX IF NOT EXISTS idx_kc_source_type ON knowledge_chunks(source_type)",
    ):
        try:
            await db.execute(stmt)
        except Exception:
            pass


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
    except Exception:
        pass


async def init_db(db: DbAdapter) -> None:
    """Create all tables and FTS indexes."""
    for stmt in DDL_STATEMENTS:
        await db.execute(stmt)
    for stmt in FTS_STATEMENTS + FTS_TRIGGERS:
        try:
            await db.execute(stmt)
        except Exception:
            pass

    for table in ("herbs_fts", "formulas_fts"):
        try:
            await db.execute(f"INSERT INTO {table}({table}) VALUES('rebuild')")
        except Exception:
            pass

    await _migrate_reminders_member_id(db)
    await _migrate_user_profiles_liver_kidney(db)
    await _migrate_knowledge_tenant_id(db)
    await _migrate_chunks_source(db)
    await _migrate_chunks_source(db)

    from app.agent_tools import _load_configs_from_db
    await _load_configs_from_db(db)

