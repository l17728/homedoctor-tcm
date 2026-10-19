"""Explicit transaction API tests for SqliteAdapter (begin/commit/rollback).

Covers (task: 事务原子性):
  * multi-write explicit transaction + mid-transaction exception → full rollback
  * writes after the transaction still auto-commit normally
  * commit failure propagates (and releases the bus)
  * other tasks' execute() queue while an explicit transaction is open
  * uncommitted writes are invisible to other connections (real isolation)
  * PRAGMA key statement is quote-escaped (binding is impossible for PRAGMA)
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading

import pytest
import pytest_asyncio

from app.db.adapter import SqliteAdapter, _pragma_key_sql


@pytest_asyncio.fixture
async def adapter(tmp_path):
    a = SqliteAdapter(str(tmp_path / "tx.db"))
    await a.connect()
    await a.execute("CREATE TABLE IF NOT EXISTS tx_probe (id INTEGER PRIMARY KEY, val TEXT)")
    yield a
    await a.close()


async def _count(adapter: SqliteAdapter, table: str = "tx_probe") -> int:
    row = await adapter.query_one(f"SELECT COUNT(*) AS n FROM {table}")
    return int(row["n"])


class TestBeginCommitRollback:
    @pytest.mark.asyncio
    async def test_commit_persists_all_writes(self, adapter):
        await adapter.begin()
        assert adapter.in_transaction is True
        await adapter.execute("INSERT INTO tx_probe (val) VALUES ('a')")
        await adapter.execute("INSERT INTO tx_probe (val) VALUES ('b')")
        await adapter.commit()
        assert adapter.in_transaction is False
        assert await _count(adapter) == 2

    @pytest.mark.asyncio
    async def test_rollback_discards_all_writes(self, adapter):
        await adapter.begin()
        await adapter.execute("INSERT INTO tx_probe (val) VALUES ('x')")
        await adapter.execute("INSERT INTO tx_probe (val) VALUES ('y')")
        await adapter.rollback()
        assert adapter.in_transaction is False
        assert await _count(adapter) == 0

    @pytest.mark.asyncio
    async def test_mid_transaction_exception_rolls_back_everything(self, adapter):
        with pytest.raises(RuntimeError):
            await adapter.begin()
            try:
                await adapter.execute("INSERT INTO tx_probe (val) VALUES ('first')")
                await adapter.execute("INSERT INTO tx_probe (val) VALUES ('second')")
                raise RuntimeError("mid-transaction failure")
            except Exception:
                await adapter.rollback()
                raise
        assert adapter.in_transaction is False
        assert await _count(adapter) == 0

    @pytest.mark.asyncio
    async def test_writes_after_rollback_still_auto_commit(self, adapter):
        await adapter.begin()
        await adapter.execute("INSERT INTO tx_probe (val) VALUES ('lost')")
        await adapter.rollback()
        await adapter.execute("INSERT INTO tx_probe (val) VALUES ('kept')")
        rows = await adapter.query("SELECT val FROM tx_probe")
        assert [r["val"] for r in rows] == ["kept"]
        # Truly committed: visible from a second, independent connection.
        conn = sqlite3.connect(adapter.db_path)
        assert conn.execute("SELECT COUNT(*) FROM tx_probe").fetchone()[0] == 1
        conn.close()

    @pytest.mark.asyncio
    async def test_uncommitted_writes_invisible_to_other_connections(self, adapter):
        await adapter.begin()
        await adapter.execute("INSERT INTO tx_probe (val) VALUES ('uncommitted')")
        conn = sqlite3.connect(adapter.db_path)
        n = conn.execute("SELECT COUNT(*) FROM tx_probe").fetchone()[0]
        conn.close()
        assert n == 0, "explicit transaction must isolate uncommitted writes"
        await adapter.rollback()

    @pytest.mark.asyncio
    async def test_commit_outside_transaction_raises(self, adapter):
        with pytest.raises(RuntimeError):
            await adapter.commit()

    @pytest.mark.asyncio
    async def test_nested_begin_raises(self, adapter):
        await adapter.begin()
        with pytest.raises(RuntimeError):
            await adapter.begin()
        await adapter.rollback()

    @pytest.mark.asyncio
    async def test_rollback_without_transaction_is_noop(self, adapter):
        await adapter.rollback()  # must not raise
        assert adapter.in_transaction is False


class TestFailurePropagation:
    @pytest.mark.asyncio
    async def test_commit_failure_propagates_and_bus_released(self, adapter, monkeypatch):
        await adapter.begin()
        await adapter.execute("INSERT INTO tx_probe (val) VALUES ('will-not-survive')")

        conn = adapter._conn
        real_execute = conn.execute

        async def failing_execute(sql, params=()):
            if sql.strip().upper() == "COMMIT":
                raise sqlite3.OperationalError("disk I/O error")
            return await real_execute(sql, params)

        monkeypatch.setattr(conn, "execute", failing_execute)
        with pytest.raises(sqlite3.OperationalError):
            await adapter.commit()
        monkeypatch.undo()

        assert adapter.in_transaction is False
        # The bus must be usable again (lock released, no lingering tx).
        await adapter.execute("INSERT INTO tx_probe (val) VALUES ('after')")
        rows = await adapter.query("SELECT val FROM tx_probe ORDER BY id")
        assert [r["val"] for r in rows] == ["after"]

    @pytest.mark.asyncio
    async def test_begin_failure_propagates_and_bus_released(self, adapter, monkeypatch):
        conn = adapter._conn
        real_execute = conn.execute

        async def failing_execute(sql, params=()):
            if sql.strip().upper() == "BEGIN":
                raise sqlite3.OperationalError(
                    "cannot start a transaction within a transaction"
                )
            return await real_execute(sql, params)

        monkeypatch.setattr(conn, "execute", failing_execute)
        with pytest.raises(sqlite3.OperationalError):
            await adapter.begin()
        monkeypatch.undo()

        assert adapter.in_transaction is False
        await adapter.execute("INSERT INTO tx_probe (val) VALUES ('ok')")
        assert await _count(adapter) == 1


class TestBusExclusivity:
    @pytest.mark.asyncio
    async def test_other_tasks_queue_during_transaction(self, adapter):
        await adapter.begin()
        await adapter.execute("INSERT INTO tx_probe (val) VALUES ('tx-write')")

        outside = asyncio.create_task(
            adapter.execute("INSERT INTO tx_probe (val) VALUES ('outside')")
        )
        # The outside write must stay queued while the transaction is open.
        await asyncio.sleep(0.2)
        assert not outside.done(), "other tasks' writes must queue during a transaction"
        assert await _count(adapter) == 1

        await adapter.commit()
        await asyncio.wait_for(outside, timeout=10)
        rows = await adapter.query("SELECT val FROM tx_probe ORDER BY id")
        assert [r["val"] for r in rows] == ["tx-write", "outside"]

    @pytest.mark.asyncio
    async def test_other_tasks_queue_to_begin_transaction(self, adapter):
        acquired = asyncio.Event()

        async def queued_transaction():
            await adapter.begin()
            acquired.set()
            await adapter.commit()

        await adapter.begin()
        queued = asyncio.create_task(queued_transaction())
        await asyncio.sleep(0)
        assert not acquired.is_set()

        await adapter.commit()
        await asyncio.wait_for(acquired.wait(), timeout=1)
        await queued
        assert adapter.in_transaction is False

    @pytest.mark.asyncio
    async def test_owner_reads_pass_through_inside_transaction(self, adapter):
        await adapter.begin()
        await adapter.execute("INSERT INTO tx_probe (val) VALUES ('v1')")
        # Same-task reads inside the transaction see uncommitted writes and
        # must not deadlock on the bus lock.
        row = await adapter.query_one("SELECT val FROM tx_probe")
        assert row["val"] == "v1"
        await adapter.rollback()

    @pytest.mark.asyncio
    async def test_cancelled_transaction_rolls_back_and_drains_worker_before_unlock(self, adapter):
        """Cancellation must not release the bus while SQLite's worker is busy."""
        entered_worker = threading.Event()
        release_worker = threading.Event()

        def block_in_sqlite_worker():
            entered_worker.set()
            release_worker.wait(timeout=5)
            return "finished"

        await adapter._conn.create_function("block_in_worker", 0, block_in_sqlite_worker)

        async def cancelled_transaction():
            async with adapter.transaction():
                await adapter.execute("INSERT INTO tx_probe (val) VALUES ('rollback-me')")
                await adapter.query("SELECT block_in_worker()")

        task = asyncio.create_task(cancelled_transaction())
        assert await asyncio.to_thread(entered_worker.wait, 3), "SQLite worker did not enter blocking function"
        task.cancel()

        # The worker has not finished the SELECT, so cleanup must remain queued
        # behind it and the bus must remain held until ROLLBACK completes.
        await asyncio.sleep(0.05)
        assert not task.done()
        outside_query = asyncio.create_task(_count(adapter))
        await asyncio.sleep(0.05)
        assert not outside_query.done()

        release_worker.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=3)
        assert await asyncio.wait_for(outside_query, timeout=3) == 0
        assert adapter.in_transaction is False


class TestPragmaKeyEscaping:
    def test_pragma_key_sql_escapes_single_quotes(self):
        sql = _pragma_key_sql("a'b; DROP TABLE x--b")
        assert "''" in sql
        # The escaped statement must parse as one harmless pragma on a real
        # SQLite connection (unescaped it is a syntax error).
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute(sql)
        finally:
            conn.close()

    def test_pragma_key_sql_plain_key_unchanged(self):
        assert _pragma_key_sql("normal-key-123") == "PRAGMA key = 'normal-key-123'"

    def test_configured_database_key_fails_closed_without_sqlcipher(self, tmp_path, monkeypatch):
        import app.db.adapter as adapter_module

        database_path = tmp_path / "must-not-be-created.db"
        monkeypatch.setenv("HOMEDOCTOR_DB_ENCRYPTION_KEY", "configured-secret")
        monkeypatch.setattr(adapter_module, "_SQLCIPHER_ACTIVE", False)

        with pytest.raises(RuntimeError, match="refusing to open or create an unencrypted database"):
            SqliteAdapter(str(database_path))
        assert not database_path.exists()
