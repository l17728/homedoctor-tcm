"""Database adapter — abstract base and SQLite implementation."""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from abc import ABC, abstractmethod
import aiosqlite
from contextlib import asynccontextmanager
import os
import aiosqlite
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["DbAdapter", "SqliteAdapter", "set_db", "get_db"]

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
    """Abstract database adapter — all database operations go through this.

    Implementations: SqliteAdapter (default), future PostgresAdapter.
    SQL dialect differences are handled by a Dialect object that translates
    common patterns (now(), upsert, json_extract) to the target database.
    """

    @property
    @abstractmethod
    def dialect(self) -> str:
        """Return the SQL dialect name: 'sqlite' or 'postgresql'."""

    @abstractmethod
    async def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        """Execute a SELECT and return all rows as dicts."""

    @abstractmethod
    async def query_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        """Execute a SELECT and return one row as dict, or None."""

    @abstractmethod
    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        """Execute an INSERT/UPDATE/DELETE and return the cursor/result."""

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

    @property
    def dialect(self) -> str:
        return "sqlite"

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

        if not self._encryption_key:
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA synchronous=NORMAL")

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
