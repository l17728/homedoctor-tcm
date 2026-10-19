"""Atomicity tests for the knowledge_agent Step-6 transaction.

Covers (task: knowledge_agent 原子性):
  * provenance (Step 6b) failure → the entity insert (Step 6) is rolled back
  * failure right after entity creation → no half-written entity survives
  * success path → entity AND provenance row both persist
"""

from __future__ import annotations

import asyncio

import pytest


async def _entity_count(db) -> int:
    row = await db.query_one("SELECT COUNT(*) AS n FROM knowledge_entities")
    return int(row["n"])


@pytest.mark.asyncio
async def test_provenance_failure_rolls_back_entity(db, monkeypatch):
    """溯源插入失败 → 实体必须整体回滚，不留半成品。"""
    import app.agent_tools as agent_tools
    from app.knowledge_agent import process_input

    async def failing_provenance(*args, **kwargs):
        raise RuntimeError("provenance insert failed")

    # process_input imports tool_record_provenance from app.agent_tools at
    # call time, so patching it there intercepts Step 6b.
    monkeypatch.setattr(agent_tools, "tool_record_provenance", failing_provenance)

    before = await _entity_count(db)
    result = await process_input(
        db,
        content="灵芝补气安神，止咳平喘，用于心神不宁、失眠心悸、虚劳短气。" * 8,
        title="灵芝功效详解",
        source_type="text",
    )

    assert result["decision"] == "failed"
    assert await _entity_count(db) == before, (
        "entity insert must be rolled back together with the failed provenance insert"
    )
    # The pipeline must recover: the bus is free for further writes.
    await db.execute(
        "INSERT INTO agent_logs (id, action_type) VALUES ('probe-1', 'probe')"
    )
    row = await db.query_one(
        "SELECT action_type FROM agent_logs WHERE id = 'probe-1'"
    )
    assert row["action_type"] == "probe"


@pytest.mark.asyncio
async def test_failure_after_entity_create_rolls_back_partial_writes(db, monkeypatch):
    """实体创建后立即失败 → 已写入的实体必须回滚。"""
    import app.knowledge_agent as ka
    from app.knowledge_agent import process_input

    real_create = ka.tool_create_or_update_entity

    async def create_then_fail(*args, **kwargs):
        result = await real_create(*args, **kwargs)
        raise RuntimeError("post-create failure")

    # knowledge_agent binds tool_create_or_update_entity into its own module
    # namespace at import time — patch it there.
    monkeypatch.setattr(ka, "tool_create_or_update_entity", create_then_fail)

    before = await _entity_count(db)
    result = await process_input(
        db,
        content="三七化瘀止血，活血消肿，用于咯血、吐血、外伤出血。" * 8,
        title="三七功效详解",
        source_type="text",
    )

    assert result["decision"] == "failed"
    assert await _entity_count(db) == before


@pytest.mark.asyncio
async def test_cancelled_step_six_rolls_back_and_releases_database_bus(db, monkeypatch):
    """Cancellation in the entity/provenance transaction rolls back and unlocks DB."""
    import app.knowledge_agent as ka
    from app.knowledge_agent import process_input

    real_create = ka.tool_create_or_update_entity

    async def create_then_cancel(*args, **kwargs):
        await real_create(*args, **kwargs)
        raise asyncio.CancelledError()

    monkeypatch.setattr(ka, "tool_create_or_update_entity", create_then_cancel)
    before = await _entity_count(db)

    with pytest.raises(asyncio.CancelledError):
        await process_input(
            db,
            content="灸甘草调和诸药，补脾益气，缓急止痛。" * 8,
            title="甘草功效补充",
            source_type="text",
        )

    assert await _entity_count(db) == before
    await asyncio.wait_for(
        db.execute("INSERT INTO agent_logs (id, action_type) VALUES ('cancel-probe', 'probe')"),
        timeout=2,
    )
    assert not db.in_transaction


@pytest.mark.asyncio
async def test_success_path_persists_entity_and_provenance(db):
    """成功路径：实体与溯源同事务提交，二者都存在。"""
    from app.knowledge_agent import process_input

    result = await process_input(
        db,
        content="山楂消食健胃，行气散瘀，化浊降脂，用于肉食积滞、脘腹胀满。" * 10,
        title="山楂功效详解",
        source_type="text",
    )

    assert result["decision"] in ("created", "merged", "auto_adopted", "pending_review")
    entity_id = result["entity_id"]
    assert entity_id

    entity = await db.query_one(
        "SELECT id FROM knowledge_entities WHERE id = ?", (entity_id,)
    )
    assert entity is not None

    prov = await db.query_one(
        "SELECT id FROM knowledge_provenance WHERE entity_id = ?", (entity_id,)
    )
    assert prov is not None, "provenance must commit together with the entity"
