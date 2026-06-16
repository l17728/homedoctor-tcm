"""Tests for audit chain module (spec §10.4) — SHA-256 hash chain integrity."""

from __future__ import annotations

import pytest

from app.audit import (
    GENESIS_HASH,
    compute_hash,
    log_audit,
    verify_chain,
    get_audit_trail,
)


@pytest.mark.asyncio
async def test_compute_hash_deterministic():
    h1 = compute_hash(GENESIS_HASH, "create", "medicine", "med-1", "{}", "2026-01-01T00:00:00Z")
    h2 = compute_hash(GENESIS_HASH, "create", "medicine", "med-1", "{}", "2026-01-01T00:00:00Z")
    assert h1 == h2
    assert len(h1) == 64


@pytest.mark.asyncio
async def test_compute_hash_different_inputs():
    h1 = compute_hash(GENESIS_HASH, "create", "medicine", "med-1", "{}", "2026-01-01T00:00:00Z")
    h2 = compute_hash(GENESIS_HASH, "update", "medicine", "med-1", "{}", "2026-01-01T00:00:00Z")
    assert h1 != h2


@pytest.mark.asyncio
async def test_log_audit_creates_first_entry(db):
    h = await log_audit(
        db,
        tenant_id="tenant-1",
        user_id="user-1",
        action="create",
        entity_type="medicine",
        entity_id="med-1",
        changes={"name": "板蓝根颗粒"},
    )
    assert len(h) == 64

    trail = await get_audit_trail(db, tenant_id="tenant-1")
    assert len(trail) == 1
    assert trail[0]["action"] == "create"
    assert trail[0]["entity_type"] == "medicine"
    assert trail[0]["entity_id"] == "med-1"
    assert trail[0]["prev_hash"] == GENESIS_HASH


@pytest.mark.asyncio
async def test_log_audit_chains_entries(db):
    h1 = await log_audit(db, tenant_id="t1", action="create", entity_type="medicine", entity_id="m1")
    h2 = await log_audit(db, tenant_id="t1", action="update", entity_type="medicine", entity_id="m1")
    h3 = await log_audit(db, tenant_id="t1", action="delete", entity_type="medicine", entity_id="m1")

    assert h1 != h2 != h3

    trail = await get_audit_trail(db, tenant_id="t1")
    assert len(trail) == 3
    assert trail[0]["hash"] == h3
    assert trail[2]["hash"] == h1


@pytest.mark.asyncio
async def test_verify_chain_intact(db):
    for i in range(5):
        await log_audit(
            db,
            tenant_id="t2",
            action="update",
            entity_type="reminder",
            entity_id=f"r-{i}",
            changes={"index": i},
        )

    assert await verify_chain(db, "t2") is True


@pytest.mark.asyncio
async def test_verify_chain_detects_tamper(db):
    await log_audit(db, tenant_id="t3", action="create", entity_type="herb", entity_id="h1", changes={"v": 1})
    await log_audit(db, tenant_id="t3", action="update", entity_type="herb", entity_id="h1", changes={"v": 2})

    await db.execute(
        "UPDATE audit_log SET changes = ? WHERE tenant_id = ? AND entity_id = ?",
        ('{"v": 999}', "t3", "h1"),
    )

    assert await verify_chain(db, "t3") is False


@pytest.mark.asyncio
async def test_tenant_isolation(db):
    await log_audit(db, tenant_id="tenant-a", action="create", entity_type="medicine", entity_id="m-a")
    await log_audit(db, tenant_id="tenant-b", action="create", entity_type="medicine", entity_id="m-b")

    trail_a = await get_audit_trail(db, tenant_id="tenant-a")
    trail_b = await get_audit_trail(db, tenant_id="tenant-b")

    assert len(trail_a) == 1
    assert len(trail_b) == 1
    assert trail_a[0]["entity_id"] == "m-a"
    assert trail_b[0]["entity_id"] == "m-b"


@pytest.mark.asyncio
async def test_get_audit_trail_filter_by_entity(db):
    await log_audit(db, tenant_id="t4", action="create", entity_type="medicine", entity_id="m1")
    await log_audit(db, tenant_id="t4", action="create", entity_type="reminder", entity_id="r1")
    await log_audit(db, tenant_id="t4", action="update", entity_type="medicine", entity_id="m1")

    all_entries = await get_audit_trail(db, tenant_id="t4")
    assert len(all_entries) == 3

    med_entries = await get_audit_trail(db, tenant_id="t4", entity_type="medicine")
    assert len(med_entries) == 2

    m1_entries = await get_audit_trail(db, tenant_id="t4", entity_type="medicine", entity_id="m1")
    assert len(m1_entries) == 2


@pytest.mark.asyncio
async def test_empty_chain_verifies(db):
    assert await verify_chain(db, "nonexistent-tenant") is True
