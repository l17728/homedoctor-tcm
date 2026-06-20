"""Database layer: DbAdapter ABC + SqliteAdapter with aiosqlite."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite


# ---------------------------------------------------------------------------
# DDL — all tables from spec §10.6
# ---------------------------------------------------------------------------

DDL_STATEMENTS = [
    # -- 用户与家庭
    """CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        display_name TEXT,
        family_id TEXT,
        settings TEXT DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS families (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        owner_id TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS family_members (
        id TEXT PRIMARY KEY,
        family_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        name TEXT,
        relation TEXT,
        gender TEXT,
        constitution_type TEXT,
        constitution_sub TEXT,
        health_profile TEXT DEFAULT '{}',
        is_pregnant INTEGER DEFAULT 0,
        date_of_birth TEXT,
        weight_kg REAL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    # -- 中药方剂知识
    """CREATE TABLE IF NOT EXISTS herbs (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        aliases TEXT,
        nature TEXT,
        flavor TEXT,
        meridians TEXT,
        efficacy TEXT,
        indications TEXT,
        contraindications TEXT,
        dosage_min_g REAL,
        dosage_max_g REAL,
        toxicity TEXT,
        category TEXT,
        processing_method TEXT,
        origin TEXT,
        source_ref TEXT,
        properties TEXT DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS formulas (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        source TEXT,
        category TEXT,
        composition TEXT DEFAULT '[]',
        efficacy TEXT,
        indications TEXT,
        modifications TEXT DEFAULT '[]',
        modifications_structured TEXT DEFAULT '[]',
        derived_from_id TEXT,
        properties TEXT DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    # -- 家庭药箱
    """CREATE TABLE IF NOT EXISTS medicines (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        family_member_id TEXT,
        name TEXT NOT NULL,
        brand TEXT,
        type TEXT NOT NULL,
        specification TEXT,
        unit TEXT,
        quantity INTEGER DEFAULT 0,
        production_date TEXT,
        expiry_date TEXT,
        opened_date TEXT,
        shelf_life_after_open TEXT,
        dosage_instructions TEXT,
        contraindications TEXT,
        barcode TEXT,
        drug_class TEXT,
        active_ingredients TEXT DEFAULT '[]',
        herbal_fields TEXT DEFAULT '{}',
        batches TEXT DEFAULT '[]',
        photos TEXT DEFAULT '[]',
        properties TEXT DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    # -- AI对话
    """CREATE TABLE IF NOT EXISTS conversations (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        title TEXT,
        model_id TEXT,
        messages TEXT DEFAULT '[]',
        reasoning_trace TEXT DEFAULT '[]',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    # -- 知识收藏
    """CREATE TABLE IF NOT EXISTS knowledge_entries (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        entry_type TEXT NOT NULL,
        title TEXT,
        content TEXT,
        summary TEXT,
        tags TEXT DEFAULT '[]',
        category_path TEXT,
        source_type TEXT,
        source_url TEXT,
        is_starred INTEGER DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    # -- 安全规则
    """CREATE TABLE IF NOT EXISTS safety_rules (
        id TEXT PRIMARY KEY,
        rule_type TEXT NOT NULL,
        drug_a TEXT NOT NULL,
        drug_b TEXT,
        severity TEXT NOT NULL DEFAULT 'warning',
        mechanism TEXT,
        action TEXT,
        source TEXT,
        enabled INTEGER DEFAULT 1
    )""",
    # -- 用药打卡
    """CREATE TABLE IF NOT EXISTS medication_logs (
        id TEXT PRIMARY KEY,
        family_member_id TEXT NOT NULL,
        date TEXT NOT NULL,
        medicine_id TEXT NOT NULL,
        taken INTEGER DEFAULT 1,
        skipped_reason TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    # -- 体质自测评估记录 (spec §2.3 / §4.2)
    """CREATE TABLE IF NOT EXISTS constitution_assessments (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        assessed_at TEXT NOT NULL DEFAULT (datetime('now')),
        results TEXT NOT NULL DEFAULT '{}',
        primary_type TEXT NOT NULL,
        secondary_types TEXT DEFAULT '[]',
        raw_answers TEXT NOT NULL DEFAULT '{}',
        FOREIGN KEY (user_id) REFERENCES users(id)
    )""",
    # -- 用户体质档案 (spec §4.2)
    """CREATE TABLE IF NOT EXISTS user_profiles (
        user_id TEXT PRIMARY KEY,
        display_name TEXT,
        birth_year INTEGER,
        gender TEXT,
        height_cm REAL,
        weight_kg REAL,
        constitution_type TEXT,
        constitution_secondary TEXT DEFAULT '[]',
        allergies TEXT DEFAULT '[]',
        health_conditions TEXT DEFAULT '[]',
        is_pregnant INTEGER DEFAULT 0,
        liver_disease INTEGER DEFAULT 0,
        kidney_disease INTEGER DEFAULT 0,
        blood_type TEXT,
        notes TEXT,
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    )""",
    # -- 吃药提醒 (spec §20)
    """CREATE TABLE IF NOT EXISTS reminders (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        family_member_id TEXT,
        title TEXT NOT NULL,
        herb_name TEXT,
        formula_name TEXT,
        medicine_name TEXT,
        dosage TEXT,
        frequency TEXT NOT NULL DEFAULT 'daily',
        times TEXT NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT,
        notes TEXT,
        enabled INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    )""",
    """CREATE TABLE IF NOT EXISTS audit_log (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        user_id TEXT,
        action TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id TEXT,
        changes TEXT,
        prev_hash TEXT,
        hash TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS favorites (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        entry_type TEXT NOT NULL,
        entry_id TEXT,
        title TEXT,
        content TEXT,
        tags TEXT DEFAULT '[]',
        source_type TEXT,
        is_starred INTEGER DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    # -- 外治理疗知识库 (spec §9.6 / §10.6.1)
    """CREATE TABLE IF NOT EXISTS therapies (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        risk_level TEXT NOT NULL DEFAULT 'medium',
        home_use_safe INTEGER NOT NULL DEFAULT 0,
        display_only INTEGER NOT NULL DEFAULT 0,
        description TEXT,
        indications TEXT,
        contraindications TEXT,
        operation_steps TEXT,
        duration TEXT,
        frequency TEXT,
        precautions TEXT,
        properties TEXT DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    # -- 疗法穴位关联 (spec §9.6.4)
    """CREATE TABLE IF NOT EXISTS therapy_acupoints (
        id TEXT PRIMARY KEY,
        therapy_id TEXT NOT NULL,
        acupoint_name TEXT NOT NULL,
        location TEXT,
        function TEXT,
        meridian TEXT,
        is_primary INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (therapy_id) REFERENCES therapies(id)
    )""",
    # -- 疗法专用安全规则 (spec §9.6.6)
    """CREATE TABLE IF NOT EXISTS therapy_safety_rules (
        id TEXT PRIMARY KEY,
        therapy_category TEXT,
        rule_type TEXT NOT NULL,
        condition_text TEXT NOT NULL,
        action TEXT NOT NULL,
        severity TEXT NOT NULL DEFAULT 'warning',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    # -- 用药套餐 (spec §20.5) — groups multiple medicines into a shared-schedule plan
    """CREATE TABLE IF NOT EXISTS medication_plans (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        family_member_id TEXT,
        name TEXT NOT NULL,
        description TEXT,
        status TEXT DEFAULT 'active',
        start_date TEXT,
        end_date TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    )""",
    """CREATE TABLE IF NOT EXISTS plan_items (
        id TEXT PRIMARY KEY,
        plan_id TEXT NOT NULL,
        medicine_name TEXT NOT NULL,
        dosage TEXT,
        frequency TEXT,
        times TEXT,
        notes TEXT,
        sort_order INTEGER DEFAULT 0,
        reminder_id TEXT,
        FOREIGN KEY (plan_id) REFERENCES medication_plans(id)
    )""",
    # -- 子女远程协助：家庭数据共享 (spec §22)
    """CREATE TABLE IF NOT EXISTS family_shares (
        id TEXT PRIMARY KEY,
        sharer_id TEXT NOT NULL,
        viewer_id TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT '家属查看',
        status TEXT NOT NULL DEFAULT 'active',
        alert_config TEXT DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(sharer_id, viewer_id)
    )""",
    # -- 知识图谱：节点与边 (spec §9/§13.3 V3)
    # 结构化数据是权威来源；图谱从 herbs/formulas/therapies/safety_rules 派生重建。
    """CREATE TABLE IF NOT EXISTS graph_nodes (
        id TEXT PRIMARY KEY,
        node_type TEXT NOT NULL,
        label TEXT NOT NULL,
        properties TEXT DEFAULT '{}',
        search_text TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS graph_edges (
        id TEXT PRIMARY KEY,
        edge_type TEXT NOT NULL,
        source_id TEXT NOT NULL,
        target_id TEXT NOT NULL,
        properties TEXT DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_graph_nodes_type ON graph_nodes(node_type)",
    "CREATE INDEX IF NOT EXISTS idx_graph_edges_source ON graph_edges(source_id)",
    "CREATE INDEX IF NOT EXISTS idx_graph_edges_target ON graph_edges(target_id)",
    "CREATE INDEX IF NOT EXISTS idx_graph_edges_type ON graph_edges(edge_type)",
    # -- 经典读诵：中医典籍书架 (spec §7.x 经典读诵)
    """CREATE TABLE IF NOT EXISTS classics (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        author TEXT,
        dynasty TEXT,
        category TEXT,
        description TEXT,
        cover_color TEXT DEFAULT '#1890ff',
        total_chapters INTEGER DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS classic_chapters (
        id TEXT PRIMARY KEY,
        classic_id TEXT NOT NULL,
        chapter_number INTEGER NOT NULL,
        title TEXT NOT NULL,
        original_text TEXT NOT NULL,
        translation TEXT,
        translator_notes TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (classic_id) REFERENCES classics(id)
    )""",
    """CREATE TABLE IF NOT EXISTS classic_annotations (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        classic_id TEXT NOT NULL,
        chapter_id TEXT NOT NULL,
        start_offset INTEGER NOT NULL,
        end_offset INTEGER NOT NULL,
        selected_text TEXT NOT NULL,
        note_type TEXT NOT NULL DEFAULT 'annotation',
        content TEXT NOT NULL,
        ai_model TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (chapter_id) REFERENCES classic_chapters(id)
    )""",
    """CREATE TABLE IF NOT EXISTS classic_study_notes (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        classic_id TEXT NOT NULL,
        chapter_id TEXT,
        content TEXT DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_classic_chapters_classic ON classic_chapters(classic_id)",
    "CREATE INDEX IF NOT EXISTS idx_classic_annotations_user_chapter ON classic_annotations(user_id, chapter_id)",
    "CREATE INDEX IF NOT EXISTS idx_classic_study_notes_user_classic ON classic_study_notes(user_id, classic_id)",
    # -- 健康分享卡 & 月度家庭健康报告 (spec §13.3 V3)
    # 结构化数据是权威来源；分享卡为派生视图，持久化以便列表/删除/回顾。
    """CREATE TABLE IF NOT EXISTS share_cards (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        family_id TEXT NOT NULL,
        member_id TEXT,
        card_type TEXT NOT NULL,
        card_data TEXT NOT NULL DEFAULT '{}',
        month TEXT,
        is_monthly_report INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_share_cards_user ON share_cards(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_share_cards_family ON share_cards(family_id)",
    "CREATE INDEX IF NOT EXISTS idx_share_cards_monthly ON share_cards(is_monthly_report, month)",
    # -- 每日健康打卡 (血压/血糖/体重/睡眠/心情)
    """CREATE TABLE IF NOT EXISTS health_logs (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        family_member_id TEXT,
        log_date TEXT NOT NULL,
        systolic INTEGER,
        diastolic INTEGER,
        blood_sugar REAL,
        weight REAL,
        sleep_hours REAL,
        mood TEXT,
        notes TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_health_logs_user_date ON health_logs(user_id, log_date)",
    # -- 统一知识实体注册表 (spec §9 — 统一知识实体系统)
    # 结构化数据是权威来源；本表为跨类型实体统一注册（中药/方剂/理疗/症状/文章/茶饮等）
    """CREATE TABLE IF NOT EXISTS knowledge_entities (
        id TEXT PRIMARY KEY,
        entity_type TEXT NOT NULL,
        source_table TEXT NOT NULL,
        source_id TEXT,
        title TEXT NOT NULL,
        summary TEXT,
        keywords TEXT DEFAULT '[]',
        tags TEXT DEFAULT '[]',
        category TEXT,
        content_preview TEXT,
        properties TEXT DEFAULT '{}',
        source_type TEXT DEFAULT 'system',
        status TEXT DEFAULT 'active',
        tenant_id TEXT DEFAULT NULL,
        view_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_ke_type ON knowledge_entities(entity_type)",
    "CREATE INDEX IF NOT EXISTS idx_ke_category ON knowledge_entities(category)",
    "CREATE INDEX IF NOT EXISTS idx_ke_status ON knowledge_entities(status)",
    # -- 实体关系引擎 — entity_relationships
    # 取代 graph_edges 成为权威关系存储；图谱可从此派生重建
    """CREATE TABLE IF NOT EXISTS entity_relationships (
        id TEXT PRIMARY KEY,
        source_entity_id TEXT NOT NULL,
        target_entity_id TEXT NOT NULL,
        relationship_type TEXT NOT NULL,
        properties TEXT DEFAULT '{}',
        weight REAL DEFAULT 1.0,
        tenant_id TEXT DEFAULT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (source_entity_id) REFERENCES knowledge_entities(id),
        FOREIGN KEY (target_entity_id) REFERENCES knowledge_entities(id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_er_source ON entity_relationships(source_entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_er_target ON entity_relationships(target_entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_er_type ON entity_relationships(relationship_type)",
    # -- RAG 知识分块 (spec §RAG — 语义检索)
    # 结构化实体(knowledge_entities)被切分为语义块后嵌入向量，用于混合检索。
    """CREATE TABLE IF NOT EXISTS knowledge_chunks (
        id TEXT PRIMARY KEY,
        entity_id TEXT,
        chunk_index INTEGER DEFAULT 0,
        chunk_text TEXT NOT NULL,
        chunk_type TEXT DEFAULT 'content',
        hierarchy_path TEXT,
        hierarchy_level INTEGER DEFAULT 0,
        token_count INTEGER DEFAULT 0,
        metadata TEXT DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_kc_entity ON knowledge_chunks(entity_id)",
    # -- RAG 向量嵌入存储 (spec §RAG — BGE-M3 1024维)
    # 嵌入以 JSON 字符串存储；检索时加载到内存做 numpy 余弦相似度。
    """CREATE TABLE IF NOT EXISTS chunk_embeddings (
        chunk_id TEXT PRIMARY KEY,
        embedding TEXT NOT NULL,
        model_name TEXT DEFAULT 'bge-m3',
        dim INTEGER DEFAULT 1024,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
]

FTS_STATEMENTS = [
    """CREATE VIRTUAL TABLE IF NOT EXISTS herbs_fts USING fts5(
        name, aliases, efficacy, indications, category,
        content=herbs, content_rowid=rowid
    )""",
    """CREATE VIRTUAL TABLE IF NOT EXISTS formulas_fts USING fts5(
        name, source, efficacy, indications, category,
        content=formulas, content_rowid=rowid
    )""",
    """CREATE VIRTUAL TABLE IF NOT EXISTS therapies_fts USING fts5(
        name, category, description, indications, contraindications,
        content=therapies, content_rowid=rowid
    )""",
]

# Module-level DB adapter reference — set by main.py during startup
_db_adapter: DbAdapter | None = None


def set_db(adapter: DbAdapter) -> None:
    """Set the global DB adapter (called during app startup)."""
    global _db_adapter
    _db_adapter = adapter


def get_db() -> DbAdapter:
    """FastAPI dependency that provides the database adapter."""
    if _db_adapter is None:
        raise RuntimeError("Database not initialized")
    return _db_adapter


FTS_TRIGGERS = [
    """CREATE TRIGGER IF NOT EXISTS herbs_ai AFTER INSERT ON herbs BEGIN
        INSERT INTO herbs_fts(rowid, name, aliases, efficacy, indications, category)
        VALUES (new.rowid, new.name, new.aliases, new.efficacy, new.indications, new.category);
    END""",
    """CREATE TRIGGER IF NOT EXISTS herbs_ad AFTER DELETE ON herbs BEGIN
        INSERT INTO herbs_fts(herbs_fts, rowid, name, aliases, efficacy, indications, category)
        VALUES ('delete', old.rowid, old.name, old.aliases, old.efficacy, old.indications, old.category);
    END""",
    """CREATE TRIGGER IF NOT EXISTS formulas_ai AFTER INSERT ON formulas BEGIN
        INSERT INTO formulas_fts(rowid, name, source, efficacy, indications, category)
        VALUES (new.rowid, new.name, new.source, new.efficacy, new.indications, new.category);
    END""",
    """CREATE TRIGGER IF NOT EXISTS formulas_ad AFTER DELETE ON formulas BEGIN
        INSERT INTO formulas_fts(formulas_fts, rowid, name, source, efficacy, indications, category)
        VALUES ('delete', old.rowid, old.name, old.source, old.efficacy, old.indications, old.category);
    END""",
    """CREATE TRIGGER IF NOT EXISTS therapies_ai AFTER INSERT ON therapies BEGIN
        INSERT INTO therapies_fts(rowid, name, category, description, indications, contraindications)
        VALUES (new.rowid, new.name, new.category, new.description, new.indications, new.contraindications);
    END""",
    """CREATE TRIGGER IF NOT EXISTS therapies_ad AFTER DELETE ON therapies BEGIN
        INSERT INTO therapies_fts(therapies_fts, rowid, name, category, description, indications, contraindications)
        VALUES ('delete', old.rowid, old.name, old.category, old.description, old.indications, old.contraindications);
    END""",
]


# ---------------------------------------------------------------------------
# DbAdapter ABC
# ---------------------------------------------------------------------------

class DbAdapter(ABC):
    """Abstract database adapter — all database operations go through this."""

    @abstractmethod
    async def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        """Execute a SELECT and return all rows as dicts."""

    @abstractmethod
    async def query_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        """Execute a SELECT and return one row as dict, or None."""

    @abstractmethod
    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        """Execute an INSERT/UPDATE/DELETE and return the cursor."""

    @abstractmethod
    @asynccontextmanager
    async def transaction(self):
        """Context manager for a transaction — commit on success, rollback on error."""


# ---------------------------------------------------------------------------
# SqliteAdapter
# ---------------------------------------------------------------------------

def _try_enable_sqlcipher() -> bool:
    """Attempt to enable SQLCipher by monkey-patching sqlite3 with pysqlcipher3.

    Returns True if encryption is active, False otherwise.
    Called once at module import time if DB_ENCRYPTION_KEY is set.
    """
    import sqlite3 as _stdlib_sqlite3

    key = os.environ.get("HOMEDOCTOR_DB_ENCRYPTION_KEY", "")
    if not key:
        return False

    try:
        import pysqlcipher3.dbapi2 as _sqlcipher
    except ImportError:
        logging.getLogger(__name__).warning(
            "DB_ENCRYPTION_KEY is set but pysqlcipher3 is not installed — "
            "database will NOT be encrypted. Install with: pip install pysqlcipher3"
        )
        return False

    _stdlib_sqlite3.connect = _sqlcipher.connect  # type: ignore[method-assign]
    logging.getLogger(__name__).info("SQLCipher enabled — database encryption active")
    return True


_SQLCIPHER_ACTIVE = _try_enable_sqlcipher()


class SqliteAdapter(DbAdapter):
    """aiosqlite implementation of DbAdapter."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None
        self._encryption_key: str | None = os.environ.get("HOMEDOCTOR_DB_ENCRYPTION_KEY", "") or None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row

        if self._encryption_key and _SQLCIPHER_ACTIVE:
            await self._conn.execute(f"PRAGMA key = '{self._encryption_key}'")
            await self._conn.execute("PRAGMA cipher_compatibility = 4")

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    def _ensure_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._conn

    async def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        conn = self._ensure_conn()
        cursor = await conn.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def query_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        conn = self._ensure_conn()
        cursor = await conn.execute(sql, params)
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        conn = self._ensure_conn()
        stripped = sql.strip().upper()

        if stripped in ("COMMIT", "ROLLBACK"):
            try:
                return await conn.execute(sql, params)
            except sqlite3.OperationalError:
                return None  # type: ignore[return-value]

        cursor = await conn.execute(sql, params)
        if stripped.startswith(("INSERT", "UPDATE", "DELETE", "REPLACE")):
            try:
                await conn.commit()
            except sqlite3.OperationalError:
                pass
        return cursor

    @asynccontextmanager
    async def transaction(self):
        conn = self._ensure_conn()
        try:
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

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
            pass  # Table might not exist yet or column already added


async def init_db(db: DbAdapter) -> None:
    """Create all tables and FTS indexes."""
    for stmt in DDL_STATEMENTS:
        await db.execute(stmt)
    for stmt in FTS_STATEMENTS + FTS_TRIGGERS:
        try:
            await db.execute(stmt)
        except Exception:
            # FTS5 might not be available in all SQLite builds; skip gracefully
            pass
    # Migration: add family_member_id to reminders for existing databases
    await _migrate_reminders_member_id(db)
    # Migration: add liver_disease/kidney_disease to user_profiles for existing databases
    await _migrate_user_profiles_liver_kidney(db)
    # Migration: add tenant_id to knowledge_entities and entity_relationships (Phase 2)
    await _migrate_knowledge_tenant_id(db)


async def seed_safety_rules(db: DbAdapter) -> None:
    """Seed hardcoded safety rules from spec §15.2 — idempotent."""
    rules: list[dict[str, Any]] = []

    # --- 十八反 (18 mutual incompatibilities) ---
    wutou_herbs = ["附子", "川乌", "草乌", "天雄"]
    for w in wutou_herbs:
        for partner in ["半夏", "瓜蒌", "贝母", "白蔹", "白及"]:
            rules.append({
                "id": f"18fan-{w}-{partner}",
                "rule_type": "十八反",
                "drug_a": w,
                "drug_b": partner,
                "severity": "critical",
                "mechanism": f"乌头类({w})与{partner}属于十八反禁忌配伍",
                "action": "禁止同用",
                "source": "十八反",
            })
    for partner in ["甘遂", "京大戟", "芫花", "海藻"]:
        rules.append({
            "id": f"18fan-甘草-{partner}",
            "rule_type": "十八反",
            "drug_a": "甘草",
            "drug_b": partner,
            "severity": "critical",
            "mechanism": f"甘草与{partner}属于十八反禁忌配伍",
            "action": "禁止同用",
            "source": "十八反",
        })
    for partner in ["人参", "党参", "丹参", "玄参", "沙参", "苦参", "细辛", "芍药"]:
        rules.append({
            "id": f"18fan-藜芦-{partner}",
            "rule_type": "十八反",
            "drug_a": "藜芦",
            "drug_b": partner,
            "severity": "critical",
            "mechanism": f"藜芦与{partner}属于十八反禁忌配伍",
            "action": "禁止同用",
            "source": "十八反",
        })

    # --- 十九畏 (19 mutual antagonisms) ---
    antagonisms = [
        ("硫磺", "朴硝"), ("水银", "砒霜"), ("狼毒", "密陀僧"),
        ("巴豆", "牵牛子"), ("丁香", "郁金"), ("牙硝", "三棱"),
        ("川乌", "犀角"), ("草乌", "犀角"), ("人参", "五灵脂"),
        ("官桂", "石脂"),
    ]
    for a, b in antagonisms:
        rules.append({
            "id": f"19wei-{a}-{b}",
            "rule_type": "十九畏",
            "drug_a": a,
            "drug_b": b,
            "severity": "critical",
            "mechanism": f"{a}与{b}属于十九畏禁忌配伍",
            "action": "禁止同用",
            "source": "十九畏",
        })

    # --- 中西药致命交互 R-01 to R-10 ---
    herb_drug_rules = [
        {
            "id": "R-01",
            "rule_type": "中西药交互",
            "drug_a": "华法林",
            "drug_b": None,
            "severity": "critical",
            "mechanism": "协同抗凝，可能导致颅内出血",
            "action": "禁止同用",
            "source": "中西药交互R-01",
            "_herbs": ["当归", "丹参", "三七", "红花", "水蛭", "银杏叶"],
        },
        {
            "id": "R-02",
            "rule_type": "中西药交互",
            "drug_a": "华法林",
            "drug_b": None,
            "severity": "critical",
            "mechanism": "诱导CYP酶，血栓风险",
            "action": "禁止同用",
            "source": "中西药交互R-02",
            "_herbs": ["人参"],
        },
        {
            "id": "R-03",
            "rule_type": "中西药交互",
            "drug_a": "地高辛",
            "drug_b": None,
            "severity": "critical",
            "mechanism": "心律失常协同，洋地黄中毒",
            "action": "禁止同用",
            "source": "中西药交互R-03",
            "_herbs": ["麻黄", "桂枝"],
        },
        {
            "id": "R-04",
            "rule_type": "中西药交互",
            "drug_a": "MAOI类药物",
            "drug_b": None,
            "severity": "critical",
            "mechanism": "高血压危象，致命血压飙升",
            "action": "禁止同用",
            "source": "中西药交互R-04",
            "_herbs": ["麻黄"],
        },
        {
            "id": "R-05",
            "rule_type": "中西药交互",
            "drug_a": "他汀类",
            "drug_b": None,
            "severity": "critical",
            "mechanism": "CYP3A4酶抑制，横纹肌溶解",
            "action": "禁止同用",
            "source": "中西药交互R-05",
            "_herbs": ["五味子"],
        },
        {
            "id": "R-06",
            "rule_type": "中西药交互",
            "drug_a": "降糖药",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "协同降糖，严重低血糖",
            "action": "谨慎同用，需监测血糖",
            "source": "中西药交互R-06",
            "_herbs": ["葛根", "苦瓜", "桑叶"],
        },
        {
            "id": "R-07",
            "rule_type": "中西药交互",
            "drug_a": "降压药",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "甘草含甘草酸导致水钠潴留，血压反升",
            "action": "谨慎同用，需监测血压",
            "source": "中西药交互R-07",
            "_herbs": ["甘草"],
        },
        {
            "id": "R-08",
            "rule_type": "中西药交互",
            "drug_a": "抗血小板药",
            "drug_b": None,
            "severity": "critical",
            "mechanism": "协同抗血小板，出血风险",
            "action": "禁止同用",
            "source": "中西药交互R-08",
            "_herbs": ["银杏叶", "丹参", "当归", "三七"],
        },
        {
            "id": "R-09",
            "rule_type": "中西药交互",
            "drug_a": "四环素",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "鳌合反应，抗生素失效",
            "action": "禁止同用",
            "source": "中西药交互R-09",
            "_herbs": ["石膏", "牡蛎", "龙骨"],
        },
        {
            "id": "R-10",
            "rule_type": "中西药交互",
            "drug_a": "铁剂",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "不溶性鞣酸铁，吸收丧失",
            "action": "禁止同用",
            "source": "中西药交互R-10",
            "_herbs": ["大黄", "虎杖", "地榆"],
        },
        {
            "id": "R-11",
            "rule_type": "中西药交互",
            "drug_a": "SSRI抗抑郁药",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "银杏叶增强5-HT活性，合用增加5-HT综合征风险",
            "action": "谨慎同用",
            "source": "中西药交互R-11",
            "_herbs": ["银杏叶"],
        },
        {
            "id": "R-12",
            "rule_type": "中西药交互",
            "drug_a": "华法林",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "人参可能降低华法林抗凝效果，增加血栓风险",
            "action": "谨慎同用，需监测INR",
            "source": "中西药交互R-12",
            "_herbs": ["人参"],
        },
        {
            "id": "R-13",
            "rule_type": "中西药交互",
            "drug_a": "CYP3A4底物",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "贯叶连翘(圣约翰草)诱导CYP3A4酶，降低多种药物血药浓度",
            "action": "谨慎同用",
            "source": "中西药交互R-13",
            "_herbs": ["贯叶连翘"],
        },
        {
            "id": "R-14",
            "rule_type": "中西药交互",
            "drug_a": "环孢素",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "黄连素可能降低环孢素免疫抑制效果",
            "action": "谨慎同用，需监测血药浓度",
            "source": "中西药交互R-14",
            "_herbs": ["黄连素", "黄连"],
        },
        {
            "id": "R-15",
            "rule_type": "中西药交互",
            "drug_a": "锂剂",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "丹参可能增加锂离子排泄减少或重吸收，导致锂中毒风险",
            "action": "谨慎同用，需监测血锂浓度",
            "source": "中西药交互R-15",
            "_herbs": ["丹参"],
        },
        {
            "id": "R-16",
            "rule_type": "中西药交互",
            "drug_a": "抗凝药",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "大蒜具有抗血小板作用，合用增加出血风险",
            "action": "谨慎同用",
            "source": "中西药交互R-16",
            "_herbs": ["大蒜"],
        },
        {
            "id": "R-17",
            "rule_type": "中西药交互",
            "drug_a": "抗凝药",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "生姜具有轻度抗血小板作用，合用增加出血风险",
            "action": "谨慎同用",
            "source": "中西药交互R-17",
            "_herbs": ["生姜"],
        },
        {
            "id": "R-18",
            "rule_type": "中西药交互",
            "drug_a": "抗凝药",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "鱼油含Omega-3脂肪酸，高剂量可增加出血风险",
            "action": "谨慎同用",
            "source": "中西药交互R-18",
            "_herbs": ["鱼油"],
        },
        {
            "id": "R-19",
            "rule_type": "中西药交互",
            "drug_a": "降糖药",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "苦瓜具有降糖作用，合用可能导致严重低血糖",
            "action": "谨慎同用，需监测血糖",
            "source": "中西药交互R-19",
            "_herbs": ["苦瓜"],
        },
        {
            "id": "R-20",
            "rule_type": "中西药交互",
            "drug_a": "利尿药",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "甘草含甘草酸引起假性醛固酮增多症，合用利尿药可致严重低钾血症",
            "action": "谨慎同用，需监测血钾",
            "source": "中西药交互R-20",
            "_herbs": ["甘草"],
        },
        {
            "id": "R-21",
            "rule_type": "中西药交互",
            "drug_a": "地高辛",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "甘草可致低钾血症，低钾增加地高辛毒性及心律失常风险",
            "action": "谨慎同用，需监测血钾和地高辛浓度",
            "source": "中西药交互R-21",
            "_herbs": ["甘草"],
        },
        {
            "id": "R-22",
            "rule_type": "中西药交互",
            "drug_a": "CYP3A4底物",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "五味子可抑制或诱导CYP3A4酶，影响多种药物代谢",
            "action": "谨慎同用",
            "source": "中西药交互R-22",
            "_herbs": ["五味子"],
        },
        {
            "id": "R-23",
            "rule_type": "中西药交互",
            "drug_a": "CYP1A2底物",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "黄芩可抑制CYP1A2酶，影响茶碱、咖啡因等药物代谢",
            "action": "谨慎同用",
            "source": "中西药交互R-23",
            "_herbs": ["黄芩"],
        },
        {
            "id": "R-24",
            "rule_type": "中西药交互",
            "drug_a": "免疫抑制剂",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "柴胡具有免疫调节作用，可能影响免疫抑制剂疗效",
            "action": "谨慎同用",
            "source": "中西药交互R-24",
            "_herbs": ["柴胡"],
        },
        {
            "id": "R-25",
            "rule_type": "中西药交互",
            "drug_a": "抗凝药",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "蒲黄具有活血化瘀作用，合用抗凝药增加出血风险",
            "action": "谨慎同用",
            "source": "中西药交互R-25",
            "_herbs": ["蒲黄"],
        },
        {
            "id": "R-26",
            "rule_type": "中西药交互",
            "drug_a": "抗血小板药",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "三七具有抗血小板聚集作用，合用增加出血风险",
            "action": "谨慎同用",
            "source": "中西药交互R-26",
            "_herbs": ["三七"],
        },
        {
            "id": "R-27",
            "rule_type": "中西药交互",
            "drug_a": "抗凝药",
            "drug_b": None,
            "severity": "critical",
            "mechanism": "水蛭含水蛭素有强抗凝作用，合用抗凝药可致严重出血",
            "action": "禁止同用",
            "source": "中西药交互R-27",
            "_herbs": ["水蛭"],
        },
        {
            "id": "R-28",
            "rule_type": "中西药交互",
            "drug_a": "铁剂",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "地榆含大量鞣质，与铁剂形成不溶性复合物影响吸收",
            "action": "间隔2小时以上",
            "source": "中西药交互R-28",
            "_herbs": ["地榆"],
        },
        {
            "id": "R-29",
            "rule_type": "中西药交互",
            "drug_a": "铁剂",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "五倍子含大量鞣酸，与铁剂结合形成不溶性鞣酸铁",
            "action": "间隔2小时以上",
            "source": "中西药交互R-29",
            "_herbs": ["五倍子"],
        },
        {
            "id": "R-30",
            "rule_type": "中西药交互",
            "drug_a": "铁剂",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "诃子含鞣质，与铁剂结合影响吸收",
            "action": "间隔2小时以上",
            "source": "中西药交互R-30",
            "_herbs": ["诃子"],
        },
    ]

    # Expand herb-drug rules: each herb × drug becomes one row
    for r in herb_drug_rules:
        herbs_list = r.pop("_herbs")
        for herb in herbs_list:
            rules.append({**r, "id": f"{r['id']}-{herb}", "drug_b": herb})

    # --- 食物禁忌 (Food-drug / food-herb interaction rules) ---
    food_rules = [
        ("食物禁忌-F01", "葡萄柚", "降压药(钙通道阻滞剂)", "warning",
         "葡萄柚汁抑制CYP3A4，显著升高降压药血药浓度", "避免同食", "食物禁忌"),
        ("食物禁忌-F02", "萝卜", "人参", "warning",
         "萝卜破气，与人参补气功效相抵消", "避免同食", "食物禁忌"),
        ("食物禁忌-F03", "浓茶", "铁剂", "warning",
         "茶鞣酸与铁结合形成不溶性复合物，影响铁吸收", "间隔2小时", "食物禁忌"),
        ("食物禁忌-F04", "牛奶", "四环素类", "warning",
         "钙离子与四环素发生螯合反应，影响抗生素吸收", "间隔2小时", "食物禁忌"),
        ("食物禁忌-F05", "酒精", "头孢类", "critical",
         "双硫仑反应——面部潮红、心悸、呼吸困难，严重可危及生命", "绝对禁酒", "食物禁忌"),
        ("食物禁忌-F06", "酒精", "甲硝唑", "critical",
         "双硫仑反应——面部潮红、恶心、心悸", "绝对禁酒", "食物禁忌"),
    ]
    for rule_id, food, drug, severity, mechanism, action, rule_type in food_rules:
        rules.append({
            "id": rule_id,
            "rule_type": rule_type,
            "drug_a": food,
            "drug_b": drug,
            "severity": severity,
            "mechanism": mechanism,
            "action": action,
            "source": rule_type,
        })

    # Insert all rules idempotently
    for rule in rules:
        await db.execute(
            """INSERT OR IGNORE INTO safety_rules
               (id, rule_type, drug_a, drug_b, severity, mechanism, action, source, enabled)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                rule["id"], rule["rule_type"], rule["drug_a"], rule["drug_b"],
                rule["severity"], rule["mechanism"], rule["action"], rule["source"],
            ),
        )


async def seed_test_data(db: DbAdapter) -> None:
    """Seed 2-3 test herbs and formulas for development."""
    herbs = [
        {
            "id": "herb-001", "name": "黄芪", "aliases": "绵芪,黄耆",
            "nature": "微温", "flavor": "甘", "meridians": "脾,肺",
            "efficacy": "补气升阳，固表止汗，利水消肿，生津养血，行滞通痹，托毒排脓，敛疮生肌",
            "indications": "气虚乏力，食少便溏，中气下陷，久泻脱肛，便血崩漏，表虚自汗",
            "contraindications": "表实邪盛，气滞湿阻，食积内停，阴虚阳亢，疮痈初起或溃后热毒尚盛者",
            "dosage_min_g": 9, "dosage_max_g": 30, "toxicity": "无毒",
            "category": "补虚药", "properties": json.dumps({"pharmacologicalClass": "免疫调节"}, ensure_ascii=False),
        },
        {
            "id": "herb-002", "name": "当归", "aliases": "秦归,云归",
            "nature": "温", "flavor": "甘,辛", "meridians": "肝,心,脾",
            "efficacy": "补血活血，调经止痛，润肠通便",
            "indications": "血虚萎黄，眩晕心悸，月经不调，经闭痛经，虚寒腹痛，风湿痹痛",
            "contraindications": "湿盛中满，大便泄泻者慎用",
            "dosage_min_g": 6, "dosage_max_g": 12, "toxicity": "无毒",
            "category": "补虚药", "properties": json.dumps({"pharmacologicalClass": "补血"}, ensure_ascii=False),
        },
        {
            "id": "herb-003", "name": "甘草", "aliases": "国老,蜜草",
            "nature": "平", "flavor": "甘", "meridians": "心,肺,脾,胃",
            "efficacy": "补脾益气，清热解毒，祛痰止咳，缓急止痛，调和诸药",
            "indications": "脾胃虚弱，倦怠乏力，心悸气短，咳嗽痰多，脘腹四肢挛急疼痛",
            "contraindications": "不宜与京大戟、芫花、甘遂、海藻同用。湿盛胀满者慎用",
            "dosage_min_g": 2, "dosage_max_g": 10, "toxicity": "无毒",
            "category": "补虚药", "properties": json.dumps({"pharmacologicalClass": "抗炎"}, ensure_ascii=False),
        },
    ]
    for h in herbs:
        await db.execute(
            """INSERT OR IGNORE INTO herbs
               (id, name, aliases, nature, flavor, meridians, efficacy, indications,
                contraindications, dosage_min_g, dosage_max_g, toxicity, category, properties)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (h["id"], h["name"], h["aliases"], h["nature"], h["flavor"], h["meridians"],
             h["efficacy"], h["indications"], h["contraindications"],
             h["dosage_min_g"], h["dosage_max_g"], h["toxicity"], h["category"], h["properties"]),
        )

    formulas = [
        {
            "id": "formula-001", "name": "四君子汤", "source": "《太平惠民和剂局方》",
            "category": "补益剂",
            "composition": json.dumps([
                {"name": "人参", "dose": "9g", "role": "君"},
                {"name": "白术", "dose": "9g", "role": "臣"},
                {"name": "茯苓", "dose": "9g", "role": "佐"},
                {"name": "甘草", "dose": "6g", "role": "使"},
            ], ensure_ascii=False),
            "efficacy": "益气健脾",
            "indications": "脾胃气虚证。面色萎白，语声低微，气短乏力，食少便溏",
            "modifications": "[]", "modifications_structured": "[]",
            "properties": "{}",
        },
        {
            "id": "formula-002", "name": "四物汤", "source": "《太平惠民和剂局方》",
            "category": "补益剂",
            "composition": json.dumps([
                {"name": "熟地黄", "dose": "12g", "role": "君"},
                {"name": "当归", "dose": "9g", "role": "臣"},
                {"name": "白芍", "dose": "9g", "role": "佐"},
                {"name": "川芎", "dose": "6g", "role": "佐"},
            ], ensure_ascii=False),
            "efficacy": "补血调血",
            "indications": "营血虚滞证。头晕目眩，心悸失眠，面色无华，妇人月经不调",
            "modifications": "[]", "modifications_structured": "[]",
            "properties": "{}",
        },
    ]
    for f in formulas:
        await db.execute(
            """INSERT OR IGNORE INTO formulas
               (id, name, source, category, composition, efficacy, indications,
                modifications, modifications_structured, properties)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (f["id"], f["name"], f["source"], f["category"], f["composition"],
             f["efficacy"], f["indications"], f["modifications"],
             f["modifications_structured"], f["properties"]),
        )

    await seed_therapy_data(db)


async def seed_therapy_data(db: DbAdapter) -> None:
    """Seed therapy knowledge base (spec §9.6) — 33 therapies + acupoints + safety rules."""
    from app.therapy_data import THERAPIES, THERAPY_SAFETY_RULES

    for t in THERAPIES:
        acupoints = t.get("acupoints", [])
        props = t.get("properties", {})
        await db.execute(
            """INSERT OR IGNORE INTO therapies
               (id, name, category, risk_level, home_use_safe, display_only,
                description, indications, contraindications, operation_steps,
                duration, frequency, precautions, properties)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                t["id"], t["name"], t["category"], t["risk_level"],
                t["home_use_safe"], t["display_only"],
                t["description"], t["indications"], t["contraindications"],
                t["operation_steps"], t["duration"], t["frequency"],
                t["precautions"], json.dumps(props, ensure_ascii=False),
            ),
        )
        for ap in acupoints:
            ap_id = f"{t['id']}-acp-{ap['acupoint_name']}"
            await db.execute(
                """INSERT OR IGNORE INTO therapy_acupoints
                   (id, therapy_id, acupoint_name, location, function, meridian, is_primary)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    ap_id, t["id"], ap["acupoint_name"], ap.get("location"),
                    ap.get("function"), ap.get("meridian"), ap.get("is_primary", 0),
                ),
            )

    for rule in THERAPY_SAFETY_RULES:
        await db.execute(
            """INSERT OR IGNORE INTO therapy_safety_rules
               (id, therapy_category, rule_type, condition_text, action, severity)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                rule["id"], rule["therapy_category"], rule["rule_type"],
                rule["condition_text"], rule["action"], rule["severity"],
            ),
        )
