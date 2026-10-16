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

    async def begin(self) -> None:
        """Start an explicit transaction on the shared connection.

        While the transaction is open, every other database call on this
        adapter (execute/query/query_one, and begin() from other tasks)
        queues until commit()/rollback() ends the transaction.
        """
        raise NotImplementedError

    async def commit(self) -> None:
        """Commit the explicit transaction. Failures propagate."""
        raise NotImplementedError

    async def rollback(self) -> None:
        """Roll back the explicit transaction. Idempotent no-op if none is open."""
        raise NotImplementedError

    @property
    def in_transaction(self) -> bool:
        """True while an explicit begin()/commit()/rollback() transaction is open."""
        return False


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


def _pragma_key_sql(key: str) -> str:
    """Build a safe ``PRAGMA key = '...'`` statement for SQLCipher.

    SQLite does not accept bound parameters in PRAGMA statements
    (``PRAGMA key = ?`` is a syntax error), so the key must be inlined as a
    string literal. Doubling embedded single quotes (standard SQL escaping)
    keeps the value inside the literal — a crafted key containing
    ``'; DROP ...`` cannot break out and inject statements.
    """
    escaped = key.replace("'", "''")
    return f"PRAGMA key = '{escaped}'"


class SqliteAdapter(DbAdapter):
    """aiosqlite implementation of DbAdapter."""

    @property
    def dialect(self) -> str:
        return "sqlite"

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None
        self._encryption_key: str | None = os.environ.get("HOMEDOCTOR_DB_ENCRYPTION_KEY", "") or None
        if self._encryption_key and not _SQLCIPHER_ACTIVE:
            raise RuntimeError(
                "HOMEDOCTOR_DB_ENCRYPTION_KEY is configured, but SQLCipher is unavailable; "
                "refusing to open or create an unencrypted database"
            )
        # Explicit-transaction state: while a transaction is open, the bus
        # lock below is held by the owning task and every other database
        # call queues until the transaction ends.
        self._tx_lock = asyncio.Lock()
        self._in_transaction = False
        self._tx_owner: asyncio.Task | None = None

    @property
    def in_transaction(self) -> bool:
        return self._in_transaction

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row

        if (
            self._encryption_key
            and _SQLCIPHER_ACTIVE
            and not os.environ.get("HOMEDOCTOR_SQLCIPHER_KEY_APPLIED_BY_CONNECT")
        ):
            await self._conn.execute(_pragma_key_sql(self._encryption_key))
            await self._conn.execute("PRAGMA cipher_compatibility = 4")

        # WAL regardless of encryption: crash safety + concurrent readers.
        # (SQLCipher builds also support WAL — the old "plaintext only" gate
        # silently downgraded encrypted deployments to DELETE journal mode.)
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA synchronous=NORMAL")
        # NOTE: foreign_keys stays OFF for now — legacy DBs were built without
        # FK enforcement and may contain orphan rows; enabling it blindly would
        # fail runtime writes. Requires an orphan-audit migration first (TODO).
        # Stop hiding "database is locked" spikes behind a hard 5s error.
        await self._conn.execute("PRAGMA busy_timeout=10000")

    async def close(self) -> None:
        if self._conn:
            if self._in_transaction:
                # Closing with an open transaction: abort it so no partial
                # write survives and tasks queued on the bus are released.
                self._in_transaction = False
                self._tx_owner = None
                try:
                    await self._conn.execute("ROLLBACK")
                except sqlite3.Error:
                    logger.warning("rollback during close failed", exc_info=True)
                if self._tx_lock.locked():
                    self._tx_lock.release()
            await self._conn.close()
            self._conn = None

    def _ensure_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._conn

    # ------------------------------------------------------------------
    # Explicit transaction API (begin/commit/rollback)
    # ------------------------------------------------------------------

    async def begin(self) -> None:
        """Start an explicit transaction and take exclusive ownership of the bus.

        Every execute/query/query_one call from other tasks queues on the bus
        lock until commit()/rollback() ends the transaction; the owning
        task's own statements pass through without auto-commit so they only
        persist at commit time.
        """
        task = asyncio.current_task()
        if task is not None and self._tx_owner is task:
            raise RuntimeError("a transaction is already active on this adapter")
        await self._tx_lock.acquire()
        try:
            # The lock is held for the full lifetime of an explicit transaction.
            # A different task therefore waits here and observes a clean state
            # after its predecessor commits or rolls back.
            if self._in_transaction:
                raise RuntimeError("transaction state is inconsistent with the bus lock")
            conn = self._ensure_conn()
            # Mark ownership before enqueueing BEGIN. If the caller is cancelled
            # while aiosqlite's worker thread is executing it, cleanup must know
            # that a transaction may have started and queue ROLLBACK behind it.
            self._in_transaction = True
            self._tx_owner = task
            await conn.execute("BEGIN")
        except BaseException:
            if self._in_transaction and self._tx_owner is task:
                await self._rollback_transaction()
            elif self._tx_lock.locked():
                self._tx_lock.release()
            raise

    async def commit(self) -> None:
        """Commit the explicit transaction.

        A failed COMMIT (disk full / SQLITE_BUSY) means the write did NOT
        persist — the error propagates. The transaction is aborted
        best-effort first so the bus is always returned to a clean state.
        """
        if not self._in_transaction:
            raise RuntimeError("commit() called outside of an explicit transaction")
        conn = self._ensure_conn()
        try:
            await conn.execute("COMMIT")
        except BaseException:
            # Cancelled awaits do not stop aiosqlite's worker operation. Queue
            # rollback behind it and wait for that operation before releasing
            # the transaction bus, so later requests cannot race the worker.
            await self._rollback_transaction()
            raise
        self._end_transaction()

    async def rollback(self) -> None:
        """Roll back the explicit transaction (idempotent no-op if none is open)."""
        if not self._in_transaction:
            return
        await self._rollback_transaction()

    async def _rollback_transaction(self) -> None:
        """Finish rollback even if the caller is cancelled while SQLite runs it.

        aiosqlite executes SQL in a worker thread. Cancelling the awaiter does
        not cancel a statement already queued there; shielding and draining the
        rollback task preserves statement order before releasing the bus lock.
        """
        conn = self._ensure_conn()
        rollback_task = asyncio.create_task(conn.execute("ROLLBACK"))
        interrupted = False
        try:
            while not rollback_task.done():
                try:
                    await asyncio.shield(rollback_task)
                except asyncio.CancelledError:
                    interrupted = True
            try:
                rollback_task.result()
            except sqlite3.Error:
                # BEGIN may have failed before opening a transaction. Cleanup
                # still must clear ownership and release the serialization bus.
                logger.debug("rollback found no active SQLite transaction", exc_info=True)
        finally:
            self._end_transaction()
        if interrupted:
            raise asyncio.CancelledError

    def _end_transaction(self) -> None:
        self._in_transaction = False
        self._tx_owner = None
        if self._tx_lock.locked():
            self._tx_lock.release()

    @asynccontextmanager
    async def _bus(self):
        """Serialize database access.

        During an explicit transaction the lock is held by the transaction
        owner: its own statements pass through, everything else (including
        statements from other tasks) queues until the transaction ends.
        """
        if self._in_transaction and self._tx_owner is asyncio.current_task():
            yield
            return
        async with self._tx_lock:
            yield

    async def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        async with self._bus():
            conn = self._ensure_conn()
            cursor = await conn.execute(sql, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def query_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        async with self._bus():
            conn = self._ensure_conn()
            cursor = await conn.execute(sql, params)
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        async with self._bus():
            conn = self._ensure_conn()
            stripped = sql.strip().upper()

            if stripped in ("COMMIT", "ROLLBACK"):
                try:
                    return await conn.execute(sql, params)
                except sqlite3.OperationalError:
                    return None  # type: ignore[return-value]

            cursor = await conn.execute(sql, params)
            if (
                stripped.startswith(("INSERT", "UPDATE", "DELETE", "REPLACE"))
                and not self._in_transaction
            ):
                # Skip auto-commit inside an explicit transaction: writes
                # only persist at commit() so a failure anywhere in the
                # transaction rolls back everything.
                # A failed COMMIT (disk full / SQLITE_BUSY) means the write did
                # NOT persist — surfacing it is the only honest option. Swallowing
                # it here made callers believe lost writes had succeeded.
                try:
                    await conn.commit()
                except sqlite3.OperationalError:
                    logger.exception("commit failed (sql starts: %s)", stripped[:40])
                    raise
            return cursor

    @asynccontextmanager
    async def transaction(self):
        await self.begin()
        try:
            yield self._ensure_conn()
            await self.commit()
        except BaseException:
            await self.rollback()
            raise


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------
