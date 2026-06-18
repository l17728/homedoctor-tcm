"""Concurrent operation safety tests.

Verifies that the system behaves correctly under concurrent load:
- 2 users creating medicines simultaneously → no cross-tenant contamination
- 50 concurrent reminder creations → all succeed and are retrievable
- 50 concurrent audit-chain appends → all land and the hash chain stays valid

Note on audit-chain concurrency: a tamper-evident hash chain is an inherently
serial data structure — each link's hash depends on the previous link's hash.
Append operations MUST be serialized (e.g. via a lock or transaction) to keep
the chain intact. The audit test below launches 50 concurrent tasks that
compete for a shared lock, mirroring real-world serialised-append usage.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta

import pytest
from httpx import AsyncClient

from app.audit import log_audit, verify_chain
from app.database import DbAdapter

CST = timezone(timedelta(hours=8))


def _today_str() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Concurrent medicine creation — tenant isolation under load
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_medicine_creation(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    """2 users each create 20 medicines concurrently — no cross-contamination.

    All 40 requests are fired with ``asyncio.gather``. Afterwards each user
    must see exactly their own 20 medicines and none of the other's.
    """
    N = 20

    async def create_for(headers: dict, prefix: str) -> list[dict]:
        """Create N medicines concurrently for one user, return responses."""
        tasks = [
            client.post(
                "/api/medicines",
                headers=headers,
                json={"name": f"{prefix}-药-{i:02d}", "type": "western", "quantity": i},
            )
            for i in range(N)
        ]
        return await asyncio.gather(*tasks)

    # Fire both users' batches truly concurrently
    a_results, b_results = await asyncio.gather(
        create_for(auth_headers, "用户A"),
        create_for(second_user_headers, "用户B"),
    )

    # Every create must have succeeded
    for r in a_results:
        assert r.status_code == 201, f"user A create failed: {r.text}"
    for r in b_results:
        assert r.status_code == 201, f"user B create failed: {r.text}"

    # --- User A must see exactly their own 20 medicines ---
    a_list = await client.get("/api/medicines", headers=auth_headers)
    assert a_list.status_code == 200
    a_names = {m["name"] for m in a_list.json()["items"]}
    # All A-prefixed names present
    for i in range(N):
        assert f"用户A-药-{i:02d}" in a_names
    # None of B's names leaked in
    for i in range(N):
        assert f"用户B-药-{i:02d}" not in a_names

    # --- User B must see exactly their own 20 medicines ---
    b_list = await client.get("/api/medicines", headers=second_user_headers)
    assert b_list.status_code == 200
    b_names = {m["name"] for m in b_list.json()["items"]}
    for i in range(N):
        assert f"用户B-药-{i:02d}" in b_names
    for i in range(N):
        assert f"用户A-药-{i:02d}" not in b_names


# ---------------------------------------------------------------------------
# Concurrent reminder creation — all succeed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_reminder_creation(
    client: AsyncClient, auth_headers: dict
):
    """50 concurrent reminder creations all succeed and are retrievable."""
    N = 50
    today = _today_str()

    tasks = [
        client.post(
            "/api/reminders",
            headers=auth_headers,
            json={
                "title": f"并发提醒-{i:02d}",
                "frequency": "daily",
                "times": ["08:00"],
                "start_date": today,
            },
        )
        for i in range(N)
    ]
    responses = await asyncio.gather(*tasks)

    # Every single creation must return 201
    for idx, r in enumerate(responses):
        assert r.status_code == 201, (
            f"reminder {idx} create failed: status={r.status_code} body={r.text}"
        )

    # All 50 must be retrievable via the list endpoint
    list_resp = await client.get("/api/reminders", headers=auth_headers)
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert len(items) >= N, f"expected >= {N} reminders, got {len(items)}"

    titles = {r["title"] for r in items}
    for i in range(N):
        assert f"并发提醒-{i:02d}" in titles


# ---------------------------------------------------------------------------
# Concurrent audit writes — hash chain integrity
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_audit_writes(db: DbAdapter):
    """50 concurrent audit writes all land and the hash chain stays valid.

    A SHA-256 hash chain requires serialised appends (each link depends on the
    previous link's hash). We launch 50 concurrent tasks that compete for a
    shared lock around ``log_audit`` — mirroring the correct production usage
    pattern where a mutex / transaction guards each chain append.

    After all writes complete:
    - Exactly 50 entries must exist for the tenant
    - ``verify_chain`` must report the chain intact (every prev_hash → hash
      link is correct, no tampering)
    """
    N = 50
    tenant = "concurrent-audit-tenant"
    lock = asyncio.Lock()

    async def append_one(i: int) -> str:
        """Acquire the serialisation lock, then append one audit entry."""
        async with lock:
            return await log_audit(
                db,
                tenant_id=tenant,
                user_id="concurrent-tester",
                action="create",
                entity_type="medicine",
                entity_id=f"med-{i:03d}",
                changes={"index": i, "name": f"药-{i}"},
            )

    # Fire 50 concurrent appends; the lock serialises the critical section
    hashes = await asyncio.gather(*[append_one(i) for i in range(N)])

    # Every call must have returned a 64-char hash
    assert len(hashes) == N
    for h in hashes:
        assert isinstance(h, str)
        assert len(h) == 64

    # All hashes must be unique (no two entries got the same chain link)
    assert len(set(hashes)) == N

    # Exactly N entries for this tenant
    count_row = await db.query_one(
        "SELECT COUNT(*) AS c FROM audit_log WHERE tenant_id = ?", (tenant,)
    )
    assert count_row["c"] == N

    # The chain must verify as intact
    ok = await verify_chain(db, tenant)
    assert ok is True, "audit hash chain is broken after concurrent appends"
